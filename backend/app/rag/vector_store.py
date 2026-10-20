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
        self._load()

    # ---------------- 持久化 ----------------
    def _load(self) -> None:
        with self._lock:
            if self.meta_path.exists() and self.vectors_path.exists():
                try:
                    raw = json.loads(self.meta_path.read_text(encoding="utf-8"))
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
        np.save(self.vectors_path, self._vectors)
        payload = {
            "dim": int(self._vectors.shape[1]) if self._vectors.size else 0,
            "records": [asdict(r) for r in self._records],
        }
        self.meta_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

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
    ) -> int:
        """整篇替换某文档的片段：先删旧片段，再写入新片段。

        用“整篇替换”而不是“追加”，可以天然处理同一文档被重新上传/更新索引的情况，
        同时不会影响其它文档。
        """
        if vectors.shape[0] != len(texts):
            raise ValueError("文本数量与向量数量不匹配")
        with self._lock:
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
                if vectors.shape[1] != self._vectors.shape[1]:
                    raise ValueError(
                        f"向量维度不一致：索引 {self._vectors.shape[1]}，新数据 {vectors.shape[1]}。"
                        "请清空 data/index 后重建知识库。"
                    )
                self._vectors = np.vstack([self._vectors, vectors.astype(np.float32)])
            self._records.extend(new_records)
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
                self._persist()
                self._rebuild_faiss()
            return removed

    def clear(self) -> None:
        with self._lock:
            self._records = []
            self._vectors = np.zeros((0, 0), dtype=np.float32)
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

    def stats(self) -> dict:
        docs = {r.document_id for r in self._records}
        return {
            "chunks": len(self._records),
            "documents": len(docs),
            "dim": int(self._vectors.shape[1]) if self._vectors.size else 0,
            "backend": "faiss" if self._faiss_index is not None else "numpy",
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
