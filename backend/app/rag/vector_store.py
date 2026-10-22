"""向量索引存储。

存储结构（刻意做得“可读可查”，而不是一个黑盒二进制）：
    data/index/vectors.npy   —— N x dim 的归一化向量矩阵
    data/index/meta.json     —— 与矩阵行一一对应的元数据（文档、片段号、原文）

为什么这样设计：
1. 向量索引不是业务数据库。文档的“文件名/状态/上传时间”在 SQLite 里，
   这里只存检索必需的向量和原文片段。两者用 document_id 关联。
2. 删除某文档时，按 document_id 过滤重建矩阵，不会误删其他文档的片段
   （这是“共享索引内容被误删”的常见坑）。
3. 归一化向量 + 点积 = 余弦相似度，所以搜索就是一次矩阵乘法，速度快且确定性好。
4. 若安装了 faiss，会额外构建 IndexFlatIP 加速搜索；没装则用 numpy 精确计算，
   结果一致。faiss 只是“更快的同一种算法”，不是另一套数据。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ChunkRecord:
    document_id: str
    file_name: str
    chunk_index: int
    text: str
    index_version: str = "v1"


@dataclass
class SearchHit:
    document_id: str
    file_name: str
    chunk_index: int
    text: str
    score: float


class VectorIndex:
    """线程安全的极简向量索引。写入少、读取多，写入时整体重建。"""

    def __init__(self, index_dir: Path | None = None) -> None:
        self.dir = Path(index_dir or settings.index_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.vectors_path = self.dir / "vectors.npy"
        self.meta_path = self.dir / "meta.json"
        self._lock = threading.RLock()
        self._records: list[ChunkRecord] = []
        self._vectors: np.ndarray = np.zeros((0, 0), dtype=np.float32)
        self._faiss_index = None
        # 每次写入/删除都 +1，供上层缓存 BM25 语料用（避免每问一句就重新分词全库）
        self._version = 0
        # 记录索引是用哪个 embedding 模型建出来的，换模型后可检测出来要求重建
        self._signature = ""
        self._load()

    # ---------------- 持久化 ----------------
    def _load(self) -> None:
        with self._lock:
            if self.meta_path.exists() and self.vectors_path.exists():
                try:
                    raw = json.loads(self.meta_path.read_text(encoding="utf-8"))
                    self._signature = raw.get("signature", "") or ""
                    self._records = [ChunkRecord(**r) for r in raw.get("records", [])]
                    self._vectors = np.load(self.vectors_path).astype(np.float32)
                    if self._vectors.shape[0] != len(self._records):
                        raise ValueError("向量与元数据数量不一致")
                    logger.info("已加载向量索引：%d 个片段", len(self._records))
                except Exception as exc:  # noqa: BLE001
                    logger.error("索引损坏，已重置：%s", exc)
                    self._records, self._vectors = [], np.zeros((0, 0), dtype=np.float32)
            self._rebuild_faiss()

    def _persist(self) -> None:
        """先写临时文件、再原子替换。

        直接覆盖写的话，写到一半进程被杀/磁盘满，留下的是半截 vectors.npy 配完整 meta.json，
        下次启动 _load 会判定“索引损坏”并把整个索引重置为空 —— 一次写失败把知识库清空。
        改成临时文件 + os.replace 后，失败最多丢掉这一次写入，旧文件仍然完整。
        """
        vectors_tmp = self.vectors_path.with_name("vectors.npy.tmp")
        meta_tmp = self.meta_path.with_name("meta.json.tmp")
        with open(vectors_tmp, "wb") as fh:  # 用文件句柄，避免 np.save 自动追加 .npy
            np.save(fh, self._vectors)
        payload = {
            "dim": int(self._vectors.shape[1]) if self._vectors.size else 0,
            "signature": self._signature,
            "records": [asdict(r) for r in self._records],
        }
        meta_tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(vectors_tmp, self.vectors_path)
        os.replace(meta_tmp, self.meta_path)

    def replace_all(
        self,
        records: list[ChunkRecord],
        vectors: np.ndarray,
        signature: str,
    ) -> None:
        """用一份**已经建好**的索引整体替换当前索引。

        这是“重建索引”的落点：暂存区全部成功后，一次替换到位。
        替换前先校验数量和维度，避免把半成品写进线上索引。
        """
        mat = np.asarray(vectors, dtype=np.float32)
        if mat.size == 0:
            mat = np.zeros((0, 0), dtype=np.float32)
        if mat.ndim != 2:
            raise ValueError("向量矩阵必须是二维")
        if mat.shape[0] != len(records):
            raise ValueError(
                f"向量行数（{mat.shape[0]}）与元数据条数（{len(records)}）不一致，拒绝替换"
            )
        with self._lock:
            self._records = list(records)
            self._vectors = mat
            self._signature = signature
            self._version += 1
            self._persist()
            self._rebuild_faiss()

    def _rebuild_faiss(self) -> None:
        self._faiss_index = None
        if self._vectors.shape[0] == 0:
            return
        try:
            import faiss  # type: ignore

            idx = faiss.IndexFlatIP(self._vectors.shape[1])
            idx.add(self._vectors)
            self._faiss_index = idx
        except Exception:
            # 没装 faiss 属于正常情况，numpy 路径同样精确
            self._faiss_index = None

    # ---------------- 写入 ----------------
    def upsert_document(
        self,
        document_id: str,
        file_name: str,
        texts: list[str],
        vectors: np.ndarray,
        index_version: str = "v1",
        signature: str = "",
    ) -> int:
        """整篇替换某文档的片段：先删旧片段，再写入新片段。

        用“整篇替换”而不是“追加”，可以天然处理同一文档被重新上传/更新索引的情况，
        同时不会影响其它文档。
        """
        if vectors.shape[0] != len(texts):
            raise ValueError("文本数量与向量数量不匹配")
        with self._lock:
            # 混用不同 embedding 模型的向量没有意义，直接拒绝并提示重建
            if (
                self._records
                and signature
                and self._signature
                and signature != self._signature
            ):
                raise ValueError(
                    f"索引由 {self._signature} 建立，当前为 {signature}。"
                    "请调用 /api/knowledge/reindex 重建索引后再使用。"
                )
            # 维度检查必须在改动任何状态之前：否则抛异常时内存里已经把这篇文章的
            # 片段删掉了，而磁盘上还在 —— 内存与磁盘不一致，之后的表现会非常难查。
            if self._vectors.size and texts:
                if vectors.shape[1] != self._vectors.shape[1]:
                    raise ValueError(
                        f"向量维度不一致：索引 {self._vectors.shape[1]}，新数据 {vectors.shape[1]}。"
                        "请调用 /api/knowledge/reindex 重建索引。"
                    )
            self._drop_locked(document_id)
            if not texts:
                self._persist()
                self._rebuild_faiss()
                return 0
            new_records = [
                ChunkRecord(document_id, file_name, i, t, index_version)
                for i, t in enumerate(texts)
            ]
            if self._vectors.size == 0:
                self._vectors = vectors.astype(np.float32)
            else:
                self._vectors = np.vstack([self._vectors, vectors.astype(np.float32)])
            self._records.extend(new_records)
            if signature:
                self._signature = signature
            self._version += 1
            self._persist()
            self._rebuild_faiss()
            return len(new_records)

    def _drop_locked(self, document_id: str) -> int:
        keep = [i for i, r in enumerate(self._records) if r.document_id != document_id]
        removed = len(self._records) - len(keep)
        if removed:
            self._records = [self._records[i] for i in keep]
            self._vectors = self._vectors[keep] if keep else np.zeros((0, 0), dtype=np.float32)
        return removed

    def remove_document(self, document_id: str) -> int:
        with self._lock:
            removed = self._drop_locked(document_id)
            if removed:
                self._version += 1
                self._persist()
                self._rebuild_faiss()
            return removed

    def clear(self) -> None:
        with self._lock:
            self._records = []
            self._vectors = np.zeros((0, 0), dtype=np.float32)
            self._signature = ""
            self._version += 1
            self._persist()
            self._rebuild_faiss()

    # ---------------- 检索 ----------------
    def search(self, query_vector: np.ndarray, top_k: int = 4) -> list[SearchHit]:
        with self._lock:
            if not self._records or self._vectors.size == 0:
                return []
            q = np.asarray(query_vector, dtype=np.float32).reshape(1, -1)
            n = np.linalg.norm(q)
            if n == 0:
                return []
            q = q / n
            if q.shape[1] != self._vectors.shape[1]:
                raise ValueError("查询向量维度与索引不一致，请检查 embedding 配置")

            k = min(top_k, len(self._records))
            if self._faiss_index is not None:
                scores, idxs = self._faiss_index.search(q, k)
                pairs = list(zip(idxs[0].tolist(), scores[0].tolist()))
            else:
                sims = (self._vectors @ q.T).reshape(-1)
                order = np.argsort(-sims)[:k]
                pairs = [(int(i), float(sims[i])) for i in order]

            hits: list[SearchHit] = []
            for i, score in pairs:
                if i < 0:
                    continue
                r = self._records[int(i)]
                hits.append(
                    SearchHit(r.document_id, r.file_name, r.chunk_index, r.text, float(score))
                )
            return hits

    # ---------------- 状态 ----------------
    @property
    def size(self) -> int:
        return len(self._records)

    @property
    def version(self) -> int:
        return self._version

    @property
    def signature(self) -> str:
        return self._signature

    def documents(self) -> list[ChunkRecord]:
        """返回片段快照（副本），供 BM25 等词法检索使用。"""
        with self._lock:
            return list(self._records)

    def snapshot(self) -> tuple[list[ChunkRecord], np.ndarray]:
        """一次性取走 (片段, 向量副本)，用于把暂存区索引整体搬到线上。"""
        with self._lock:
            return list(self._records), self._vectors.copy()

    def stats(self) -> dict:
        docs = {r.document_id for r in self._records}
        return {
            "chunks": len(self._records),
            "documents": len(docs),
            "dim": int(self._vectors.shape[1]) if self._vectors.size else 0,
            "backend": "faiss" if self._faiss_index is not None else "numpy",
            "signature": self._signature,
            "version": self._version,
        }


_index: VectorIndex | None = None


def get_index() -> VectorIndex:
    global _index
    if _index is None:
        _index = VectorIndex()
    return _index


def reset_index() -> None:
    """测试用：重建内存实例。"""
    global _index
    _index = None
