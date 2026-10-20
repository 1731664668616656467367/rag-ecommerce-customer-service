"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertIcon, RefreshIcon, TrashIcon, UploadIcon } from "@/components/icons";
import { api } from "@/lib/api";
import { formatBytes, formatTime } from "@/lib/format";
import type { DocumentItem, KnowledgeList } from "@/lib/types";

const STATUS_TEXT: Record<DocumentItem["status"], string> = {
  indexed: "已索引",
  pending: "处理中",
  failed: "处理失败",
};

const STATUS_STYLE: Record<DocumentItem["status"], string> = {
  indexed: "bg-[#eaf3ea] text-[#2c5f33]",
  pending: "bg-mist text-muted",
  failed: "bg-[#fdf3f2] text-[#8c2f28]",
};

const ACCEPT = ".txt,.md,.pdf,.docx";

export default function KnowledgePage() {
  const [data, setData] = useState<KnowledgeList | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.listKnowledge());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载知识库失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function uploadFiles(files: FileList | File[]) {
    const list = Array.from(files);
    if (list.length === 0) return;
    setUploading(true);
    setError(null);
    setNotice(null);

    const results: string[] = [];
    for (const file of list) {
      try {
        const doc = await api.uploadKnowledge(file);
        results.push(`${doc.file_name}：已索引 ${doc.chunk_count} 个片段`);
      } catch (e) {
        results.push(`${file.name}：失败 — ${e instanceof Error ? e.message : "未知错误"}`);
      }
    }
    setNotice(results.join("；"));
    setUploading(false);
    await load();
    if (inputRef.current) inputRef.current.value = "";
  }

  async function remove(doc: DocumentItem) {
    if (!window.confirm(`删除「${doc.file_name}」？其向量片段会一并移除，检索将不再命中。`)) return;
    try {
      await api.deleteKnowledge(doc.id);
      setNotice(`已删除 ${doc.file_name}`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    }
  }

  return (
    <div className="px-5 py-8 sm:px-0 sm:py-10">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-semibold tracking-tight">知识库</h1>
          <p className="mt-1.5 max-w-xl text-[14px] leading-relaxed text-muted">
            客服回答的依据来自这里的文档。上传后会立即切块、向量化并写入索引，后续问答立刻生效。
          </p>
        </div>
        <button type="button" onClick={load} className="btn-ghost">
          <RefreshIcon className="h-4 w-4" />
          刷新
        </button>
      </header>

      {data && (
        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: "文档数", value: data.index.documents },
            { label: "索引片段", value: data.index.chunks },
            { label: "向量维度", value: data.index.dim || "—" },
            { label: "检索引擎", value: data.index.backend },
          ].map((item) => (
            <div key={item.label} className="surface px-4 py-3">
              <p className="text-[12px] text-muted">{item.label}</p>
              <p className="mt-1 text-[20px] font-medium tracking-tight">{item.value}</p>
            </div>
          ))}
        </div>
      )}

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (e.dataTransfer.files?.length) uploadFiles(e.dataTransfer.files);
        }}
        className={`mt-6 rounded-card border border-dashed px-6 py-8 text-center transition-colors ${
          dragging ? "border-accent bg-[#f5f9ff]" : "border-hairline bg-mist/40"
        }`}
      >
        <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full border border-hairline bg-white text-muted">
          <UploadIcon className="h-5 w-5" />
        </div>
        <p className="mt-3 text-[15px] font-medium">拖拽文件到这里，或选择文件上传</p>
        <p className="mt-1 text-[12.5px] text-muted">
          支持 .txt / .md / .pdf / .docx，单个文件不超过 10MB。同名文件会自动覆盖旧版本。
        </p>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          className="btn-primary mt-4"
        >
          {uploading ? "正在处理…" : "选择文件"}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) uploadFiles(e.target.files);
          }}
        />
      </div>

      {notice && (
        <p className="mt-4 rounded-xl border border-hairline bg-mist/60 px-4 py-2.5 text-[12.5px] text-muted">
          {notice}
        </p>
      )}

      {error && (
        <div className="mt-4 flex items-start gap-2 rounded-xl border border-[#f3c6c2] bg-[#fdf3f2] px-4 py-2.5 text-[12.5px] text-[#8c2f28]">
          <AlertIcon className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <section className="mt-8">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-[17px] font-medium">文档列表</h2>
          <span className="text-[12px] text-muted">{data?.documents.length ?? 0} 份</span>
        </div>

        {loading && <p className="text-[13px] text-muted">加载中…</p>}

        {!loading && data && data.documents.length === 0 && (
          <div className="surface px-6 py-10 text-center">
            <p className="text-[14px] text-ink">知识库还是空的</p>
            <p className="mt-1 text-[12.5px] text-muted">
              上传一份商品政策文档，聊天时就能检索到依据。
            </p>
          </div>
        )}

        {!loading && data && data.documents.length > 0 && (
          <ul className="surface divide-y divide-hairline overflow-hidden">
            {data.documents.map((doc) => (
              <li key={doc.id} className="flex flex-wrap items-start gap-3 px-4 py-3.5 sm:px-5">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-[14px] font-medium text-ink">{doc.file_name}</span>
                    <span className={`rounded-full px-2 py-0.5 text-[11px] ${STATUS_STYLE[doc.status]}`}>
                      {STATUS_TEXT[doc.status]}
                    </span>
                  </div>
                  <p className="mt-1 text-[12px] text-muted">
                    {doc.file_type.toUpperCase()} · {formatBytes(doc.size_bytes)} ·{" "}
                    {doc.chunk_count} 个片段 · {formatTime(doc.created_at)}
                  </p>
                  {doc.status === "failed" && doc.error && (
                    <p className="mt-1.5 text-[12px] text-[#8c2f28]">原因：{doc.error}</p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => remove(doc)}
                  aria-label={`删除 ${doc.file_name}`}
                  className="btn-quiet px-2 py-1 text-muted"
                >
                  <TrashIcon className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="mt-8 text-[11.5px] leading-relaxed text-muted">
        说明：当前知识库管理接口没有登录保护，仅适合本地开发。部署到公网前必须加认证与权限控制。
      </p>
    </div>
  );
}
