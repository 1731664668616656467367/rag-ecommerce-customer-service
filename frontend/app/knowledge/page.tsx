"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Badge from "@/components/ui/Badge";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import {
  AlertIcon,
  CheckIcon,
  DatabaseIcon,
  FileIcon,
  RefreshIcon,
  SearchIcon,
  TrashIcon,
  UploadIcon,
} from "@/components/icons";
import { api } from "@/lib/api";
import { formatBytes, formatTime } from "@/lib/format";
import type { DocumentItem, KnowledgeList } from "@/lib/types";

const STATUS_META: Record<
  DocumentItem["status"],
  { text: string; tone: "green" | "neutral" | "red" }
> = {
  indexed: { text: "已索引", tone: "green" },
  pending: { text: "处理中", tone: "neutral" },
  failed: { text: "处理失败", tone: "red" },
};

type StatusFilter = "all" | DocumentItem["status"];

const FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "indexed", label: "已索引" },
  { value: "pending", label: "处理中" },
  { value: "failed", label: "处理失败" },
];

/** 单次上传的结果。成功也好、失败也好，都要把原因原样告诉用户，
 *  而不是统一弹一句"上传失败"。 */
type UploadResult = { name: string; ok: boolean; message: string };

export default function KnowledgePage() {
  const [data, setData] = useState<KnowledgeList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ---- 上传 ----
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number; current: string } | null>(
    null
  );
  const [results, setResults] = useState<UploadResult[]>([]);
  const [dragging, setDragging] = useState(false);
  const dragDepth = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // ---- 删除 / 重建索引 ----
  const [deleteTarget, setDeleteTarget] = useState<DocumentItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [reindexing, setReindexing] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  // ---- 列表筛选（纯前端过滤已取回的真实列表，不伪造数据） ----
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");

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
    if (list.length === 0 || uploading) return;

    setUploading(true);
    setError(null);
    setNotice(null);
    setResults([]);

    const collected: UploadResult[] = [];
    for (let i = 0; i < list.length; i += 1) {
      const file = list[i];
      setProgress({ done: i, total: list.length, current: file.name });
      try {
        const doc = await api.uploadKnowledge(file);
        collected.push({
          name: doc.file_name,
          ok: true,
          message: `已索引 ${doc.chunk_count} 个片段`,
        });
      } catch (e) {
        collected.push({
          name: file.name,
          ok: false,
          message: e instanceof Error ? e.message : "未知错误",
        });
      }
      setResults([...collected]);
    }

    setProgress(null);
    setUploading(false);
    if (inputRef.current) inputRef.current.value = "";
    // 只把后端真实列表刷出来，不在前端"猜测"新状态
    await load();
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.deleteKnowledge(deleteTarget.id);
      setNotice(`已删除「${deleteTarget.file_name}」，其索引片段一并移除。`);
      setDeleteTarget(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  }

  async function reindex() {
    setReindexing(true);
    setNotice(null);
    setError(null);
    try {
      const r = await api.reindexKnowledge();
      setNotice(
        `重建完成：成功 ${r.indexed} 份、失败 ${r.failed} 份，当前索引 ${r.chunks} 个片段。`
      );
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "重建索引失败");
    } finally {
      setReindexing(false);
    }
  }

  const policy = data?.upload;
  const docs = data?.documents ?? [];

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return docs.filter((d) => {
      if (status !== "all" && d.status !== status) return false;
      if (!kw) return true;
      return (
        d.file_name.toLowerCase().includes(kw) || d.file_type.toLowerCase().includes(kw)
      );
    });
  }, [docs, keyword, status]);

  // 索引状态只用真实数据推导：没有文档 = 空库；有文档但没片段 = 异常；
  // 其余交给"已索引 / 处理中 / 失败"逐条展示，不在这里编造一个"健康分"。
  const indexState =
    docs.length === 0
      ? { label: "空索引", tone: "neutral" as const }
      : (data?.index.chunks ?? 0) === 0
        ? { label: "无可用片段", tone: "red" as const }
        : { label: "可检索", tone: "green" as const };

  return (
    <div className="mx-auto w-full max-w-content px-4 pb-16 pt-7 sm:px-6 sm:pt-9">
      {/* ---------- 标题 ---------- */}
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[11.5px] font-medium uppercase tracking-[0.08em] text-muted">
            知识库
          </p>
          <h1 className="mt-1.5 text-[26px] font-semibold tracking-[-0.02em] text-ink sm:text-[32px]">
            知识库管理
          </h1>
          <p className="mt-2 max-w-2xl text-[13.5px] leading-relaxed text-muted">
            客服回答的依据全部来自这里的文档。上传后系统会切块、向量化并写入索引，
            下一次提问就能检索到；删除文档会同时移除它的所有片段，检索将不再命中。
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={reindex}
            disabled={reindexing || docs.length === 0}
            className="btn-ghost"
            title={docs.length === 0 ? "知识库为空，暂无可重建的内容" : "按当前配置重新切块并向量化全部文档"}
          >
            <DatabaseIcon className="h-4 w-4" />
            {reindexing ? "重建中…" : "重建索引"}
          </button>
          <button type="button" onClick={load} disabled={loading} className="btn-ghost">
            <RefreshIcon className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            刷新
          </button>
        </div>
      </header>

      {/* ---------- 真实统计：数字全部来自 /api/knowledge ---------- */}
      <div className="mt-6 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <div className="rounded-card border border-[#EADFAF] bg-cream-soft px-4 py-3.5">
          <p className="text-[12px] text-[#8A6A1F]">文档数</p>
          <p className="mt-1 truncate text-[22px] font-semibold tracking-tight text-ink">
            {loading && !data ? "—" : (data?.index.documents ?? 0)}
          </p>
        </div>
        {[
          { label: "索引片段", value: loading && !data ? "—" : (data?.index.chunks ?? 0) },
          { label: "向量维度", value: data?.index.dim || "—" },
        ].map((s) => (
          <div key={s.label} className="rounded-card border border-hairline bg-surface px-4 py-3.5">
            <p className="text-[12px] text-muted">{s.label}</p>
            <p className="mt-1 truncate text-[22px] font-semibold tracking-tight text-ink">
              {s.value}
            </p>
          </div>
        ))}
        <div className="rounded-card border border-[#333331] bg-dark px-4 py-3.5 text-white shadow-dark">
          <p className="text-[12px] text-white/60">检索方式</p>
          <p className="mt-1 truncate text-[15px] font-semibold tracking-tight">
            {data?.index.backend ?? "—"}
          </p>
          <p className="mt-0.5 flex items-center gap-1.5 text-[11.5px] text-white/55">
            <span className="h-1.5 w-1.5 rounded-full bg-cream" aria-hidden="true" />
            索引状态：{loading && !data ? "读取中" : indexState.label}
          </p>
        </div>
      </div>

      {/* ---------- 上传区 ---------- */}
      <section className="mt-5">
        <div
          onDragEnter={(e) => {
            e.preventDefault();
            dragDepth.current += 1;
            setDragging(true);
          }}
          onDragOver={(e) => e.preventDefault()}
          onDragLeave={(e) => {
            e.preventDefault();
            // 拖过子元素也会触发 leave，用计数避免高亮闪烁
            dragDepth.current -= 1;
            if (dragDepth.current <= 0) {
              dragDepth.current = 0;
              setDragging(false);
            }
          }}
          onDrop={(e) => {
            e.preventDefault();
            dragDepth.current = 0;
            setDragging(false);
            if (e.dataTransfer.files?.length) uploadFiles(e.dataTransfer.files);
          }}
          className={`rounded-card border border-dashed px-5 py-7 text-center transition-colors sm:px-8 sm:py-8 ${
            dragging
              ? "border-[#DFCF94] bg-cream-soft"
              : "border-hairline-strong bg-surface hover:border-[#D6D0C2]"
          }`}
          data-testid="upload-zone"
        >
          <div
            className={`mx-auto flex h-12 w-12 items-center justify-center rounded-full border transition-colors ${
              dragging ? "border-[#EADFAF] bg-cream text-ink" : "border-hairline bg-mist text-ink"
            }`}
          >
            <UploadIcon className="h-5 w-5" />
          </div>

          <p className="mt-3.5 text-[15px] font-medium text-ink">
            {dragging ? "松手即可开始上传" : "把文件拖到这里，或点击选择文件"}
          </p>
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted">
            支持{" "}
            <span className="font-medium text-ink">
              {policy ? policy.extensions.join(" / ") : ".txt / .md / .pdf / .docx"}
            </span>
            ，单个文件不超过{" "}
            <span className="font-medium text-ink">
              {policy ? `${policy.max_mb} MB` : "10 MB"}
            </span>
            。同名文件会覆盖旧版本并替换其索引片段。
          </p>

          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
            className="btn-primary mt-4"
          >
            {uploading ? (
              <>
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                {progress ? `处理中 ${progress.done + 1}/${progress.total}` : "处理中…"}
              </>
            ) : (
              "选择文件"
            )}
          </button>

          <input
            ref={inputRef}
            type="file"
            accept={policy?.accepts ?? ".txt,.md,.pdf,.docx"}
            multiple
            className="hidden"
            onChange={(e) => {
              if (e.target.files?.length) uploadFiles(e.target.files);
            }}
          />

          {/* 进度：只显示"第几个 / 共几个"，不编造百分比 */}
          {uploading && progress && (
            <div className="mx-auto mt-4 max-w-sm text-left">
              <div className="flex items-center justify-between text-[11.5px] text-muted">
                <span className="truncate">正在处理：{progress.current}</span>
                <span className="ml-2 shrink-0">
                  {progress.done}/{progress.total}
                </span>
              </div>
              <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-mist">
                <div
                  className="h-full rounded-full bg-ink transition-[width] duration-300"
                  style={{ width: `${Math.round((progress.done / progress.total) * 100)}%` }}
                />
              </div>
            </div>
          )}
        </div>

        {/* 逐文件结果 */}
        {results.length > 0 && (
          <ul className="mt-3 space-y-1.5" data-testid="upload-results">
            {results.map((r, i) => (
              <li
                key={`${r.name}-${i}`}
                className={`flex items-start gap-2 rounded-control border px-3 py-2 text-[12.5px] leading-relaxed ${
                  r.ok
                    ? "border-[#DCE8D6] bg-success-soft text-success"
                    : "border-[#EFD6D2] bg-danger-soft text-danger"
                }`}
              >
                {r.ok ? (
                  <CheckIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                ) : (
                  <AlertIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                )}
                <span className="min-w-0 break-words">
                  <span className="font-medium">{r.name}</span>
                  {" — "}
                  {r.message}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {notice && (
        <p className="mt-4 rounded-control border border-[#EADFAF] bg-cream-soft px-3.5 py-2.5 text-[12.5px] leading-relaxed text-[#8A6A1F]">
          {notice}
        </p>
      )}

      {error && (
        <div
          role="alert"
          className="mt-4 flex items-start gap-2 rounded-control border border-[#EFD6D2] bg-danger-soft px-3.5 py-2.5 text-[12.5px] leading-relaxed text-danger"
        >
          <AlertIcon className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="min-w-0 break-words">{error}</span>
        </div>
      )}

      {/* ---------- 文档列表 ---------- */}
      <section className="mt-8">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-baseline gap-2">
            <h2 className="text-[16px] font-semibold tracking-tight text-ink">文档列表</h2>
            <span className="text-[12px] text-muted">
              {keyword || status !== "all"
                ? `${filtered.length} / ${docs.length} 份`
                : `共 ${docs.length} 份`}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* 搜索：只过滤已经取回的真实列表，不发新请求、不显示假数据 */}
            <label className="relative flex items-center">
              <SearchIcon className="pointer-events-none absolute left-3 h-3.5 w-3.5 text-muted" />
              <input
                type="search"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder="搜索文件名"
                aria-label="搜索文档"
                className="h-9 w-full min-w-[180px] rounded-pill border border-hairline bg-surface pl-8 pr-3 text-[12.5px] text-ink outline-none transition-shadow placeholder:text-muted/70 focus:border-hairline-strong focus:ring-4 focus:ring-cream/50 sm:w-[220px]"
              />
            </label>

            <div className="flex items-center gap-1 rounded-pill border border-hairline bg-surface p-1">
              {FILTERS.map((f) => (
                <button
                  key={f.value}
                  type="button"
                  onClick={() => setStatus(f.value)}
                  aria-pressed={status === f.value}
                  className={`h-7 rounded-pill px-2.5 text-[12px] font-medium transition-colors ${
                    status === f.value
                      ? "bg-ink text-white"
                      : "text-muted hover:bg-mist hover:text-ink"
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {loading && !data && (
          <div className="rounded-card border border-hairline bg-surface px-5 py-10 text-center text-[13px] text-muted">
            加载中…
          </div>
        )}

        {!loading && docs.length === 0 && (
          <div className="rounded-card border border-hairline bg-surface px-5 py-12 text-center">
            <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-mist text-muted">
              <FileIcon className="h-5 w-5" />
            </div>
            <p className="mt-3 text-[14px] font-medium text-ink">知识库还是空的</p>
            <p className="mx-auto mt-1.5 max-w-sm text-[12.5px] leading-relaxed text-muted">
              上传一份退换货政策或物流说明，聊天时就能检索到依据。没有文档时，
              知识库模式会如实回答&ldquo;没有找到依据&rdquo;，不会编造。
            </p>
          </div>
        )}

        {docs.length > 0 && filtered.length === 0 && (
          <div className="rounded-card border border-hairline bg-surface px-5 py-10 text-center">
            <p className="text-[13.5px] font-medium text-ink">没有匹配的文档</p>
            <p className="mt-1 text-[12.5px] text-muted">
              换个关键字，或把筛选切回&ldquo;全部&rdquo;。
            </p>
            <button
              type="button"
              onClick={() => {
                setKeyword("");
                setStatus("all");
              }}
              className="btn-ghost btn-sm mt-3"
            >
              清除筛选
            </button>
          </div>
        )}

        {filtered.length > 0 && (
          <ul className="divide-y divide-hairline overflow-hidden rounded-card border border-hairline bg-surface">
            {filtered.map((doc) => {
              const meta = STATUS_META[doc.status];
              return (
                <li
                  key={doc.id}
                  className="flex items-start gap-3 px-4 py-3.5 transition-colors hover:bg-mist/50 sm:px-5"
                >
                  <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-hairline bg-mist text-ink">
                    <FileIcon className="h-4 w-4" />
                  </span>

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="min-w-0 truncate text-[13.5px] font-medium text-ink">
                        {doc.file_name}
                      </span>
                      <Badge tone={meta.tone}>{meta.text}</Badge>
                    </div>
                    <p className="mt-1 flex flex-wrap items-center gap-x-1.5 text-[12px] text-muted">
                      <span className="font-medium text-ink/70">
                        {doc.file_type.toUpperCase()}
                      </span>
                      <span aria-hidden="true">·</span>
                      <span>{formatBytes(doc.size_bytes)}</span>
                      <span aria-hidden="true">·</span>
                      <span>{doc.chunk_count} 个片段</span>
                      <span aria-hidden="true">·</span>
                      <span>{formatTime(doc.created_at)}</span>
                    </p>
                    {doc.status === "failed" && doc.error && (
                      <p className="mt-1.5 rounded-md bg-danger-soft px-2 py-1 text-[11.5px] leading-relaxed text-danger">
                        失败原因：{doc.error}
                      </p>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={() => setDeleteTarget(doc)}
                    aria-label={`删除 ${doc.file_name}`}
                    className="btn-quiet btn-icon -mr-1 text-muted hover:text-danger"
                  >
                    <TrashIcon className="h-4 w-4" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <p className="mt-8 rounded-control border border-hairline bg-mist/50 px-3.5 py-2.5 text-[11.5px] leading-relaxed text-muted">
        安全提示：知识库管理接口当前没有登录与权限校验，仅适合本地开发环境。
        部署到公网前必须先加认证，否则任何访问者都能上传或删除文档。
      </p>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="删除这份文档？"
        description={
          deleteTarget && (
            <span>
              将删除 <span className="font-medium text-ink">{deleteTarget.file_name}</span>
              （{deleteTarget.chunk_count} 个索引片段）。删除后该文档不再参与检索，
              此操作不可撤销。
            </span>
          )
        }
        confirmText="删除"
        busy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => !deleting && setDeleteTarget(null)}
      />
    </div>
  );
}
