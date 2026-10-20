"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertIcon, RefreshIcon } from "@/components/icons";
import { api, API_BASE } from "@/lib/api";
import type { HealthResponse } from "@/lib/types";

export default function SettingsPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setHealth(await api.health());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "无法获取系统状态");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const rows = health
    ? [
        {
          title: "后端服务",
          value: `${health.app} v${health.version}`,
          detail: `环境：${health.env} · API：${API_BASE}`,
          ok: true,
        },
        {
          title: "数据库",
          value: health.database === "ok" ? "连接正常（SQLite）" : health.database,
          detail: "会话、消息、文档元数据、反馈均持久化在本地文件",
          ok: health.database === "ok",
        },
        {
          title: "向量检索",
          value:
            health.embedding.provider === "ollama"
              ? `Ollama · ${health.embedding.model ?? "bge-m3"}`
              : "本地哈希向量（降级模式）",
          detail:
            health.embedding.provider === "ollama"
              ? "语义检索，效果最佳"
              : "仅做词面匹配，语义能力弱于 bge-m3；启动 Ollama 后自动切换",
          ok: health.embedding.provider === "ollama",
        },
        {
          title: "生成模型",
          value: health.llm.configured ? `已配置 · ${health.llm.model}` : "未配置密钥",
          detail: health.llm.configured
            ? "密钥仅存在于后端进程，前端无法读取"
            : "未配置时聊天只能展示知识库原文",
          ok: health.llm.configured,
        },
        {
          title: "知识索引",
          value: `${health.index.documents} 份文档 · ${health.index.chunks} 个片段`,
          detail: `维度 ${health.index.dim || "—"} · 引擎 ${health.index.backend}`,
          ok: health.index.chunks > 0,
        },
      ]
    : [];

  return (
    <div className="px-5 py-8 sm:px-0 sm:py-10">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-semibold tracking-tight">系统状态</h1>
          <p className="mt-1.5 max-w-xl text-[14px] leading-relaxed text-muted">
            这里显示后端真实返回的运行状态与配置要求，不读取前端环境变量，也不展示任何密钥内容。
          </p>
        </div>
        <button type="button" onClick={load} className="btn-ghost" disabled={loading}>
          <RefreshIcon className="h-4 w-4" />
          {loading ? "检测中…" : "重新检测"}
        </button>
      </header>

      {error && (
        <div className="mt-6 flex items-start gap-2 rounded-xl border border-[#f3c6c2] bg-[#fdf3f2] px-4 py-3 text-[13px] text-[#8c2f28]">
          <AlertIcon className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {health && (() => {
        const hasWarn = health.warnings.length > 0;
        const healthy = health.status === "ok" && !hasWarn;
        return (
        <>
          <div className="mt-6 flex flex-wrap items-center gap-3 rounded-card border border-hairline bg-white px-5 py-4">
            <span
              className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-[12px] ${
                healthy ? "bg-[#eaf3ea] text-[#2c5f33]" : "bg-[#fffaf0] text-[#7a5b14]"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${healthy ? "bg-[#2c5f33]" : "bg-[#b8860b]"}`}
              />
              {healthy ? "运行正常" : hasWarn ? "可用 · 有提示" : "降级运行"}
            </span>
            <p className="text-[13px] text-muted">
              {healthy
                ? "所有必要组件均已就绪。"
                : hasWarn
                  ? "核心对话功能可用，但部分能力处于降级状态，详见下方提示。"
                  : "系统可用，但部分组件未就绪，详见下方提示。"}
            </p>
          </div>

          <div className="mt-4 space-y-3">
            {rows.map((r) => (
              <div key={r.title} className="surface flex flex-wrap items-start gap-4 px-5 py-4">
                <div className="min-w-0 flex-1">
                  <p className="text-[12px] text-muted">{r.title}</p>
                  <p className="mt-1 text-[15px] font-medium text-ink">{r.value}</p>
                  <p className="mt-1 text-[12.5px] leading-relaxed text-muted">{r.detail}</p>
                </div>
                <span
                  className={`mt-1 h-2 w-2 shrink-0 rounded-full ${
                    r.ok ? "bg-[#2c5f33]" : "bg-[#d4a017]"
                  }`}
                  aria-label={r.ok ? "正常" : "需要关注"}
                />
              </div>
            ))}
          </div>

          {health.warnings.length > 0 && (
            <section className="mt-8">
              <h2 className="text-[17px] font-medium">需要处理</h2>
              <ul className="mt-3 space-y-2">
                {health.warnings.map((w) => (
                  <li
                    key={w}
                    className="flex items-start gap-2 rounded-xl border border-[#f0d9a8] bg-[#fffaf0] px-4 py-2.5 text-[12.5px] leading-relaxed text-[#7a5b14]"
                  >
                    <AlertIcon className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{w}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
        );
      })()}

      <section className="mt-8 rounded-card border border-hairline bg-mist/40 px-5 py-5">
        <h2 className="text-[15px] font-medium">配置说明（不含密钥内容）</h2>
        <p className="mt-2 text-[13px] leading-relaxed text-muted">
          后端配置位于 <code className="rounded bg-white px-1.5 py-0.5 text-[12px]">backend/.env</code>，
          参考 <code className="rounded bg-white px-1.5 py-0.5 text-[12px]">backend/.env.example</code>。
          修改后需要重启 FastAPI 才能生效。
        </p>
        <dl className="mt-4 grid gap-3 sm:grid-cols-2">
          {[
            ["DEEPSEEK_API_KEY", "DeepSeek 密钥，仅后端读取"],
            ["EMBEDDING_PROVIDER", "auto / ollama / local"],
            ["OLLAMA_EMBEDDING_MODEL", "默认 bge-m3"],
            ["RETRIEVAL_TOP_K", "每次检索返回的片段数"],
            ["RETRIEVAL_MIN_SCORE", "相关性阈值，0 表示自动校准"],
            ["MAX_UPLOAD_MB", "上传大小上限"],
          ].map(([k, v]) => (
            <div key={k} className="rounded-xl border border-hairline bg-white px-3.5 py-2.5">
              <dt className="text-[12px] font-medium text-ink">{k}</dt>
              <dd className="mt-0.5 text-[12px] text-muted">{v}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-4 text-[12px] leading-relaxed text-muted">
          接口文档：
          <a
            href={API_BASE.replace(/\/api$/, "") + "/docs"}
            target="_blank"
            rel="noreferrer"
            className="ml-1 text-accent hover:underline"
          >
            打开 FastAPI Swagger
          </a>
        </p>
      </section>

      <p className="mt-8 text-[11.5px] leading-relaxed text-muted">
        安全提醒：当前系统没有登录与权限体系，知识库管理接口对任何访问者开放，仅适用于本地开发环境。
      </p>
    </div>
  );
}
