"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import Badge from "@/components/ui/Badge";
import {
  AlertIcon,
  CheckIcon,
  DatabaseIcon,
  InfoIcon,
  RefreshIcon,
  ShieldIcon,
  SparklesIcon,
} from "@/components/icons";
import { api, API_BASE } from "@/lib/api";
import { formatTime } from "@/lib/format";
import type { AnswerMode, AnswerModeState, HealthResponse, ModelStatus } from "@/lib/types";

/** 模型四态 → 展示。只有 ok 才允许说"可用"，
 *  其余一律如实说"未配置 / 未验证 / 上次失败"。 */
const MODEL_BADGE: Record<ModelStatus, { tone: "green" | "amber" | "red" | "neutral"; text: string }> =
  {
    ok: { tone: "green", text: "最近一次调用成功" },
    unverified: { tone: "neutral", text: "已配置 · 尚未调用验证" },
    not_configured: { tone: "amber", text: "未配置密钥" },
    error: { tone: "red", text: "上次调用失败" },
  };

function Card({
  title,
  desc,
  icon,
  action,
  children,
}: {
  title: string;
  desc?: string;
  icon: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-card border border-hairline bg-surface shadow-card">
      <div className="flex items-start gap-3 border-b border-hairline bg-mist/40 px-5 py-4">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[#EADFAF] bg-cream-soft text-ink">
          {icon}
        </span>
        {/* 标题与说明同处一列，说明才不会跑到图标下面去 */}
        <div className="min-w-0 flex-1">
          <h2 className="text-[14.5px] font-semibold tracking-tight text-ink">{title}</h2>
          {desc && <p className="mt-1 text-[12.5px] leading-relaxed text-muted">{desc}</p>}
        </div>
        {action && <div className="shrink-0 pt-0.5">{action}</div>}
      </div>
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

function Row({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="flex flex-col gap-1 border-b border-hairline/70 py-2.5 last:border-0 sm:flex-row sm:items-baseline sm:gap-4">
      <span className="shrink-0 text-[12.5px] text-muted sm:w-[118px]">{label}</span>
      <span className="min-w-0 flex-1 break-words text-[13px] font-medium leading-relaxed text-ink">
        {value}
        {hint && (
          <span className="mt-0.5 block text-[11.5px] font-normal leading-relaxed text-muted">
            {hint}
          </span>
        )}
      </span>
    </div>
  );
}

export default function SettingsPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [mode, setMode] = useState<AnswerModeState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modeBusy, setModeBusy] = useState<AnswerMode | "reset" | null>(null);
  const [modeError, setModeError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [h, m] = await Promise.all([api.health(), api.getAnswerMode()]);
      setHealth(h);
      setMode(m);
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

  /** 只在后端确认后才更新界面；失败则回读真实状态，绝不留在"假已切换"。 */
  async function changeMode(next: AnswerMode) {
    if (modeBusy || mode?.mode === next) return;
    setModeBusy(next);
    setModeError(null);
    setNotice(null);
    try {
      const updated = await api.setAnswerMode(next);
      setMode(updated);
      setNotice(`已切换到「${updated.label}」，该设置对所有会话、所有访问者立即生效。`);
      setHealth(await api.health());
    } catch (e) {
      setModeError(e instanceof Error ? e.message : "切换失败");
      try {
        setMode(await api.getAnswerMode());
      } catch {
        /* 回读也失败时保持原状态，界面不会显示成功 */
      }
    } finally {
      setModeBusy(null);
    }
  }

  async function resetMode() {
    if (modeBusy) return;
    setModeBusy("reset");
    setModeError(null);
    try {
      const updated = await api.resetAnswerMode();
      setMode(updated);
      setNotice(`已恢复为后端默认模式「${updated.label}」。`);
      setHealth(await api.health());
    } catch (e) {
      setModeError(e instanceof Error ? e.message : "恢复默认失败");
      try {
        setMode(await api.getAnswerMode());
      } catch {
        /* 同上 */
      }
    } finally {
      setModeBusy(null);
    }
  }

  const modelBadge = mode ? MODEL_BADGE[mode.model.status] : null;
  const llmOn = mode?.mode === "llm";

  /** Embedding 展示用的派生字段。
   *  放在这里而不是 JSX 里，是为了让“配置要求 / 实际生效 / 降级原因”这三件事
   *  有唯一一处判断逻辑——页面任何地方都用同一份口径。 */
  const emb = (() => {
    const e = health?.embedding;
    const configured = (e?.configured_provider ?? "auto").toLowerCase();
    const active = e?.active_provider ?? e?.provider ?? "unknown";
    const isOllama = active === "ollama";
    const model = e?.model ?? null;
    const isFallback = Boolean(e?.is_fallback);

    let connectionLabel: string;
    if (isOllama) {
      connectionLabel = e?.available
        ? `已连接 ${e?.base_url ?? ""}，模型已安装`
        : `已连接 ${e?.base_url ?? ""}，但模型不可用`;
    } else if (configured === "local") {
      connectionLabel = "不适用（已按配置固定为本地哈希）";
    } else if (e?.ollama_now_reachable === true) {
      connectionLabel = "Ollama 现在可达，但本进程仍用降级实现（需重启后端）";
    } else {
      connectionLabel = "未连接 Ollama（未安装或未启动）";
    }

    return {
      configured,
      active,
      isOllama,
      isFallback,
      semantic: Boolean(e?.is_semantic),
      activeLabel: isOllama ? `Ollama · ${model ?? "bge-m3"}` : "本地哈希（local-hashing）",
      modelLabel: isOllama ? (model ?? "bge-m3") : "无模型（字符 n-gram 哈希，非神经网络）",
      embedderDim: e?.dim ?? 0,
      connectionLabel,
      fallbackReason: e?.fallback_reason ?? null,
    };
  })();

  return (
    <div className="mx-auto w-full max-w-content px-4 pb-16 pt-7 sm:px-6 sm:pt-9">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[11.5px] font-medium uppercase tracking-[0.08em] text-muted">设置</p>
          <h1 className="mt-1.5 text-[26px] font-semibold tracking-[-0.02em] text-ink sm:text-[32px]">
            系统设置
          </h1>
          <p className="mt-2 max-w-2xl text-[13.5px] leading-relaxed text-muted">
            这里显示后端真实返回的配置与运行状态。页面读不到任何密钥内容，
            也不会用&ldquo;连接成功&rdquo;之类的字样去猜测模型是否可用——只有真正调用成功过才算数。
          </p>
        </div>
        <button type="button" onClick={load} disabled={loading} className="btn-ghost shrink-0">
          <RefreshIcon className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          {loading ? "检测中…" : "重新检测"}
        </button>
      </header>

      {error && (
        <div
          role="alert"
          className="mt-5 flex items-start gap-2 rounded-control border border-[#EFD6D2] bg-danger-soft px-3.5 py-2.5 text-[12.5px] leading-relaxed text-danger"
        >
          <AlertIcon className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="min-w-0 break-words">{error}</span>
        </div>
      )}

      {notice && (
        <div className="mt-5 flex items-start gap-2 rounded-control border border-[#DCE8D6] bg-success-soft px-3.5 py-2.5 text-[12.5px] leading-relaxed text-success">
          <CheckIcon className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="min-w-0 break-words">{notice}</span>
        </div>
      )}

      <div className="mt-6 space-y-4">
        {/* ---------- 1. 回答模式 ---------- */}
        <Card
          title="回答模式"
          desc="决定客服的回答由谁生成。切换后立即生效，无需重启服务。"
          icon={<SparklesIcon className="h-4 w-4" />}
          action={
            mode && (
              <span data-testid="settings-current-mode">
                <Badge tone="blue">当前：{mode.label}</Badge>
              </span>
            )
          }
        >
          {!mode && <p className="text-[13px] text-muted">读取中…</p>}

          {mode && (
            <>
              <div className="grid gap-2.5 sm:grid-cols-2" role="radiogroup" aria-label="回答模式">
                {mode.options.map((opt) => {
                  const active = mode.mode === opt.value;
                  const busy = modeBusy === opt.value;
                  // 大模型模式的选中态用深色卡（高对比），知识库模式用奶油黄。
                  // 两者都保留"图标 + 文字 + 已启用"，不单靠颜色区分。
                  const darkActive = active && opt.value === "llm";
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      role="radio"
                      aria-checked={active}
                      disabled={modeBusy !== null || active}
                      onClick={() => changeMode(opt.value)}
                      data-testid={`settings-mode-${opt.value}`}
                      className={`flex items-start gap-3 rounded-card border p-3.5 text-left transition-all disabled:cursor-default ${
                        darkActive
                          ? "border-dark bg-dark text-white shadow-dark"
                          : active
                            ? "border-[#EADFAF] bg-cream-soft"
                            : "border-hairline bg-surface hover:border-hairline-strong hover:bg-mist/50"
                      }`}
                    >
                      <span
                        className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                          darkActive
                            ? "border-white/70 bg-white"
                            : active
                              ? "border-ink bg-ink"
                              : "border-hairline-strong bg-surface"
                        }`}
                      >
                        {busy ? (
                          <span className="h-2.5 w-2.5 animate-spin rounded-full border-[1.5px] border-white/50 border-t-white" />
                        ) : (
                          active && (
                            <CheckIcon className={`h-2.5 w-2.5 ${darkActive ? "text-ink" : "text-white"}`} />
                          )
                        )}
                      </span>
                      <span className="min-w-0">
                        <span className="flex items-center gap-1.5">
                          <span
                            className={`text-[13px] font-medium ${darkActive ? "text-white" : "text-ink"}`}
                          >
                            {opt.label}
                          </span>
                          {active && (
                            <span
                              className={`inline-flex items-center rounded-full px-1.5 py-[1px] text-[10.5px] font-medium ${
                                darkActive
                                  ? "bg-white/15 text-white ring-1 ring-white/25"
                                  : "bg-surface text-[#8A6A1F] ring-1 ring-[#EADFAF]"
                              }`}
                            >
                              已启用
                            </span>
                          )}
                        </span>
                        <span
                          className={`mt-1 block text-[12px] leading-relaxed ${
                            darkActive ? "text-white/65" : "text-muted"
                          }`}
                        >
                          {opt.description}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>

              <div className="mt-3.5 border-t border-hairline pt-2">
                <Row
                  label="作用范围"
                  value="全局（所有会话、所有访问者共用）"
                  hint={mode.scope_note}
                />
                <Row
                  label="取值来源"
                  value={mode.overridden ? "页面设置（已覆盖 .env）" : ".env 默认值"}
                  hint={mode.updated_at ? `更新于 ${formatTime(mode.updated_at)}` : undefined}
                />
                <Row label="默认模式" value={mode.default_mode === "llm" ? "大模型模式" : "知识库模式"} />
              </div>

              {mode.overridden && (
                <button
                  type="button"
                  onClick={resetMode}
                  disabled={modeBusy !== null}
                  className="btn-quiet mt-2 px-0 text-[12.5px] text-accent hover:bg-transparent hover:underline"
                >
                  {modeBusy === "reset" ? "恢复中…" : "恢复为后端默认模式"}
                </button>
              )}

              {modeError && (
                <p className="mt-3 flex items-start gap-2 rounded-control border border-[#EFD6D2] bg-danger-soft px-3 py-2 text-[12px] leading-relaxed text-danger">
                  <AlertIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span className="min-w-0 break-words">{modeError}</span>
                </p>
              )}

              <p className="mt-3 rounded-control bg-mist/60 px-3 py-2 text-[11.5px] leading-relaxed text-muted">
                说明：本版本的覆盖值保存在后端数据库，作用域为全局。没有按会话或按用户区分，
                因此切换后其他人看到的也是同一模式。
              </p>
            </>
          )}
        </Card>

        {/* ---------- 2. 模型服务 ---------- */}
        <Card
          title="模型服务"
          desc="大语言模型接口的配置状态。密钥只保存在后端进程，前端无法读取。"
          icon={<SparklesIcon className="h-4 w-4" />}
          action={modelBadge && <Badge tone={modelBadge.tone}>{modelBadge.text}</Badge>}
        >
          {!mode && <p className="text-[13px] text-muted">读取中…</p>}

          {mode && (
            <>
              <Row label="服务提供方" value={mode.model.provider} />
              <Row label="模型名称" value={mode.model.model} />
              <Row
                label="密钥配置"
                value={mode.model.configured ? "已配置（内容不展示）" : "未配置"}
                hint="仅后端可读"
              />
              <Row
                label="是否会调用模型"
                value={
                  mode.model.will_be_called ? (
                    <span className="text-accent">会（模式为 llm 且密钥已配置）</span>
                  ) : (
                    <span className="text-muted">不会</span>
                  )
                }
              />
              <Row label="状态说明" value={mode.model.status_text} />
              {mode.model.last_success_at && (
                <Row label="最近一次成功调用" value={formatTime(mode.model.last_success_at)} />
              )}
              {mode.model.last_failure && (
                <div className="mt-2 rounded-control border border-[#EFD6D2] bg-danger-soft px-3 py-2 text-[12px] leading-relaxed text-danger">
                  <p className="font-medium">最近一次失败：{mode.model.last_failure.code}</p>
                  <p className="mt-0.5">{mode.model.last_failure.text}</p>
                  <p className="mt-0.5 text-[11.5px] opacity-80">{formatTime(mode.model.last_failure.at)}</p>
                </div>
              )}

              {llmOn && !mode.model.configured && (
                <p className="mt-3 rounded-control border border-[#EADFAF] bg-warning-soft px-3 py-2 text-[12px] leading-relaxed text-warning">
                  当前尚未配置可用的大语言模型服务，请先在后端配置模型接口。
                  在配置完成前，回答会自动退回知识库原文，不会假装已经生成。
                </p>
              )}

              <p className="mt-3 text-[11.5px] leading-relaxed text-muted">
                "最近一次调用成功"来自真实请求记录，不是启动时的试探性探测——探测既费钱，
                也证明不了下一次可用。
              </p>
            </>
          )}
        </Card>

        {/* ---------- 3. 检索设置 ---------- */}
        <Card
          title="检索设置"
          desc="知识库检索的真实参数，来自后端配置。此处只读，修改请编辑 backend/.env。"
          icon={<DatabaseIcon className="h-4 w-4" />}
          action={
            health && (
              <Badge tone={health.retrieval.needs_reindex ? "red" : "neutral"}>
                {health.retrieval.needs_reindex ? "需要重建索引" : "索引与模型匹配"}
              </Badge>
            )
          }
        >
          {!health && <p className="text-[13px] text-muted">读取中…</p>}
          {health && (
            <>
              <Row
                label="检索方式"
                value={
                  health.retrieval.mode === "hybrid"
                    ? "混合检索（向量 + BM25）"
                    : health.retrieval.mode === "vector"
                      ? "仅向量检索"
                      : "仅词法检索"
                }
              />
              <Row label="实际生效通道" value={health.retrieval.channels.join(" + ") || "—"} />
              <Row label="返回片段数 top_k" value={health.retrieval.top_k ?? "—"} />
              <Row
                label="相关性阈值"
                value={
                  health.retrieval.min_score === 0
                    ? "自动校准（配置为 0）"
                    : (health.retrieval.min_score ?? "—")
                }
              />
              <Row label="最小覆盖度" value={health.retrieval.min_coverage ?? "—"} />
              <Row
                label="切块大小 / 重叠"
                value={`${health.retrieval.chunk_size ?? "—"} / ${health.retrieval.chunk_overlap ?? "—"} 字符`}
              />
              <Row label="向量后端" value={health.retrieval.vector_backend} />

              {/* Embedding 状态块：把“配置要求什么 / 实际用了什么 / 为什么不是它”摊开写。
                  只显示一句“Ollama 未连接”，用户没法判断下一步该启动服务还是该 pull 模型。 */}
              <div className="mt-4 rounded-card border border-hairline bg-mist/40 p-3.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[12.5px] font-medium text-ink">Embedding（向量化）</p>
                  <Badge tone={emb.semantic ? "green" : "amber"}>
                    {emb.semantic ? "语义向量" : "本地哈希降级"}
                  </Badge>
                </div>

                <dl className="mt-2.5 space-y-1.5 text-[12.5px]">
                  <div className="flex gap-3">
                    <dt className="w-[92px] shrink-0 text-muted">配置要求</dt>
                    <dd className="min-w-0 flex-1 break-words font-medium text-ink">
                      <code className="rounded bg-surface px-1 py-0.5 text-[12px]">
                        EMBEDDING_PROVIDER={emb.configured}
                      </code>
                    </dd>
                  </div>
                  <div className="flex gap-3">
                    <dt className="w-[92px] shrink-0 text-muted">实际生效</dt>
                    <dd className="min-w-0 flex-1 break-words font-medium text-ink">
                      {emb.activeLabel}
                      {emb.isFallback && (
                        <span className="ml-1.5 rounded-full bg-warning-soft px-1.5 py-[1px] text-[10.5px] text-warning">
                          已降级
                        </span>
                      )}
                    </dd>
                  </div>
                  <div className="flex gap-3">
                    <dt className="w-[92px] shrink-0 text-muted">模型名称</dt>
                    <dd className="min-w-0 flex-1 break-words text-ink">{emb.modelLabel}</dd>
                  </div>
                  <div className="flex gap-3">
                    <dt className="w-[92px] shrink-0 text-muted">真实维度</dt>
                    <dd className="min-w-0 flex-1 break-words text-ink">
                      {emb.embedderDim > 0
                        ? `${emb.embedderDim} 维（模型实际输出）`
                        : "尚未调用模型，维度未知"}
                      <span className="ml-1.5 text-muted">
                        · 索引 {health.index.dim || "—"} 维
                      </span>
                    </dd>
                  </div>
                  <div className="flex gap-3">
                    <dt className="w-[92px] shrink-0 text-muted">服务连接</dt>
                    <dd className="min-w-0 flex-1 break-words text-ink">
                      {emb.connectionLabel}
                    </dd>
                  </div>
                  <div className="flex gap-3">
                    <dt className="w-[92px] shrink-0 text-muted">知识库</dt>
                    <dd className="min-w-0 flex-1 break-words text-ink">
                      {health.index.documents} 份文档 · {health.index.chunks} 个片段
                    </dd>
                  </div>
                </dl>

                {emb.fallbackReason && (
                  <p className="mt-2.5 flex items-start gap-2 rounded-control border border-[#EADFAF] bg-cream-soft px-2.5 py-2 text-[11.5px] leading-relaxed text-[#8A6A1F]">
                    <AlertIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    <span className="min-w-0 break-words">
                      降级原因：{emb.fallbackReason}
                      {health.embedding.restart_required && (
                        <span className="mt-0.5 block">
                          检测到 Ollama 现在已经可用，重启后端即可切换（当前进程仍在用降级实现）。
                        </span>
                      )}
                    </span>
                  </p>
                )}

                {health.embedding.index_dim_note && (
                  <p className="mt-2 text-[11.5px] leading-relaxed text-muted">
                    {health.embedding.index_dim_note}
                  </p>
                )}
              </div>
              {health.retrieval.needs_reindex && (
                <p className="mt-3 flex items-start gap-2 rounded-control border border-[#EFD6D2] bg-danger-soft px-3 py-2 text-[12px] leading-relaxed text-danger">
                  <AlertIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span>
                    索引由 {health.retrieval.index_signature} 建立，当前 embedding 为{" "}
                    {health.retrieval.embedding_signature}，两者不一致会导致检索质量下降。
                    请到 <Link href="/knowledge" className="underline">知识库管理</Link> 点击"重建索引"。
                  </span>
                </p>
              )}
            </>
          )}
        </Card>

        {/* ---------- 4. 系统状态 ---------- */}
        <Card
          title="系统状态"
          desc="服务、数据库与索引的实时状态。"
          icon={<ShieldIcon className="h-4 w-4" />}
          action={
            health && (
              <Badge tone={health.status === "ok" ? "green" : "amber"}>
                {health.status === "ok" ? "运行正常" : "降级运行"}
              </Badge>
            )
          }
        >
          {!health && <p className="text-[13px] text-muted">读取中…</p>}
          {health && (
            <>
              <Row label="后端服务" value={`${health.app} v${health.version}`} />
              <Row label="运行环境" value={health.env} />
              <Row label="接口地址" value={<code className="break-all text-[12px]">{API_BASE}</code>} />
              <Row
                label="数据库"
                value={health.database === "ok" ? "连接正常（SQLite）" : health.database}
              />
              <Row
                label="知识索引"
                value={`${health.index.documents} 份文档 · ${health.index.chunks} 个片段`}
              />
              <Row label="索引维度" value={health.index.dim || "—"} />

              {health.warnings.length > 0 ? (
                <ul className="mt-3 space-y-1.5">
                  {health.warnings.map((w) => (
                    <li
                      key={w}
                      className="flex items-start gap-2 rounded-control border border-[#EADFAF] bg-warning-soft px-3 py-2 text-[12px] leading-relaxed text-warning"
                    >
                      <AlertIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      <span className="min-w-0 break-words">{w}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-3 flex items-center gap-2 rounded-control bg-success-soft px-3 py-2 text-[12px] text-success">
                  <CheckIcon className="h-3.5 w-3.5" />
                  没有需要处理的警告。
                </p>
              )}
            </>
          )}
        </Card>

        {/* ---------- 5. 关于项目 ---------- */}
        <Card
          title="关于项目"
          desc="技术构成与使用边界。"
          icon={<InfoIcon className="h-4 w-4" />}
        >
          <Row label="前端" value="Next.js 15（App Router）· TypeScript · Tailwind CSS" />
          <Row label="后端" value="FastAPI · SQLAlchemy · SQLite" />
          <Row label="检索链路" value="切块 → 向量化 → BM25 + 向量 RRF 融合 → 阈值判定" />
          <Row label="意图识别" value="本地规则（知识库模式下零外联）" />
          <Row
            label="接口文档"
            value={
              <a
                href={API_BASE.replace(/\/api$/, "") + "/docs"}
                target="_blank"
                rel="noreferrer"
                className="text-accent hover:underline"
              >
                打开 Swagger UI
              </a>
            }
          />
          <p className="mt-3 rounded-control bg-mist/60 px-3 py-2 text-[11.5px] leading-relaxed text-muted">
            安全边界：系统没有登录与权限体系，知识库管理与设置接口对任何访问者开放，
            仅适用于本地开发。生产部署前必须补上认证、权限与速率限制。
          </p>
        </Card>
      </div>
    </div>
  );
}
