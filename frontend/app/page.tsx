"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import Card from "@/components/ui/Card";
import {
  AlertIcon,
  ArrowUpRightIcon,
  BookIcon,
  ChatIcon,
  ClockIcon,
  DatabaseIcon,
  LayersIcon,
  MessageIcon,
  RefreshIcon,
  ShieldIcon,
  SparklesIcon,
} from "@/components/icons";
import { api } from "@/lib/api";
import { relativeDay } from "@/lib/format";
import type { AnswerModeState, SessionItem, StatsResponse, WelcomeResponse } from "@/lib/types";

/** 工作台首页。
 *
 *  这里刻意不做"欢迎页"，而是做一个**能看状态、能进功能**的仪表盘：
 *  每个数字都来自 /api/stats（数据库聚合 + 索引统计），
 *  接口挂了就显示"—"并说明原因，不拿 0 或假数据顶上。
 */
export default function DashboardPage() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [statsError, setStatsError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [welcome, setWelcome] = useState<WelcomeResponse | null>(null);
  const [mode, setMode] = useState<AnswerModeState | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const [s, ss, w, m] = await Promise.allSettled([
      api.stats(),
      api.listSessions(),
      api.welcome(),
      api.getAnswerMode(),
    ]);
    if (s.status === "fulfilled") {
      setStats(s.value);
      setStatsError(null);
    } else {
      setStatsError(s.reason instanceof Error ? s.reason.message : "统计接口不可用");
    }
    if (ss.status === "fulfilled") setSessions(ss.value);
    if (w.status === "fulfilled") setWelcome(w.value);
    if (m.status === "fulfilled") setMode(m.value);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const recent = [...sessions]
    .sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1))
    .slice(0, 4);

  const modeIsLlm = (stats?.answer_mode ?? mode?.mode) === "llm";
  const modelStatus = mode?.model.status;
  const modelText =
    modelStatus === "ok"
      ? "最近一次调用成功"
      : modelStatus === "not_configured"
        ? "未配置密钥"
        : modelStatus === "error"
          ? "最近一次调用失败"
          : modelStatus === "unverified"
            ? "已配置 · 尚未验证"
            : "状态未知";
  const modelTone =
    modelStatus === "ok"
      ? "text-success"
      : modelStatus === "not_configured" || modelStatus === "unverified"
        ? "text-warning"
        : modelStatus === "error"
          ? "text-danger"
          : "text-muted";

  const n = (v: number | undefined | null) =>
    loading || v === undefined || v === null ? "—" : String(v);

  const quickQueries = (welcome?.suggestions ?? []).slice(0, 6);

  return (
    <div className="px-4 pb-8 pt-5 sm:px-7 sm:pt-7">
      {/* ---------- 标题区 ---------- */}
      <div className="flex flex-wrap items-end justify-between gap-5">
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
            AI 电商客服 · 工作台
          </p>
          <h1 className="mt-2 text-display font-semibold text-ink">智能客服工作台</h1>
          <p className="mt-2 text-[13.5px] leading-relaxed text-muted">
            管理对话、知识库与 AI 回答服务。
          </p>
        </div>

        {/* 右侧：三个真实计数（来自 /api/stats） */}
        <div className="flex items-center gap-4 sm:gap-7">
          {[
            { Icon: MessageIcon, label: "会话", value: n(stats?.sessions_total) },
            { Icon: LayersIcon, label: "消息", value: n(stats?.messages_total) },
            { Icon: DatabaseIcon, label: "索引片段", value: n(stats?.chunks) },
          ].map(({ Icon, label, value }, i) => (
            <div
              key={label}
              className={`flex items-center gap-2.5 ${i > 0 ? "border-l border-hairline pl-4 sm:pl-7" : ""}`}
            >
              <Icon className="h-4 w-4 text-muted" />
              <div>
                <p className="text-[17px] font-semibold leading-none tracking-tight text-ink">{value}</p>
                <p className="mt-1 text-[11px] leading-none text-muted">{label}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ---------- 三块状态胶囊 ---------- */}
      <div className="mt-5 grid gap-2.5 sm:grid-cols-3">
        <div className="flex items-center justify-between gap-3 rounded-card border border-hairline bg-surface px-4 py-3">
          <div className="min-w-0">
            <p className="text-[11px] text-muted">知识库文档数</p>
            <p className="mt-1 text-[22px] font-semibold leading-none tracking-tight text-ink">
              {n(stats?.docs_total)}
            </p>
          </div>
          <span className="shrink-0 rounded-pill bg-mist px-2.5 py-1 text-[11px] text-muted">
            已索引 {n(stats?.docs_indexed)}
          </span>
        </div>

        <div className="flex items-center justify-between gap-3 rounded-card border border-[#E7D79B] bg-cream-soft px-4 py-3">
          <div className="min-w-0">
            <p className="text-[11px] text-[#8A7A3F]">当前回答模式</p>
            <p className="mt-1 truncate text-[17px] font-semibold leading-tight tracking-tight text-ink">
              {stats?.mode_label ?? mode?.label ?? "读取中…"}
            </p>
          </div>
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-cream text-ink">
            {modeIsLlm ? <SparklesIcon className="h-4 w-4" /> : <ShieldIcon className="h-4 w-4" />}
          </span>
        </div>

        <div className="flex items-center justify-between gap-3 rounded-card border border-hairline bg-surface px-4 py-3">
          <div className="min-w-0">
            <p className="text-[11px] text-muted">模型服务状态</p>
            <p className={`mt-1 truncate text-[15px] font-semibold leading-tight tracking-tight ${modelTone}`}>
              {modelText}
            </p>
          </div>
          <span
            className={`h-2 w-2 shrink-0 rounded-full ${
              modelStatus === "ok" ? "bg-success" : modelStatus === "error" ? "bg-danger" : "bg-[#D9C46B]"
            }`}
          />
        </div>
      </div>

      {statsError && (
        <p className="mt-3 flex items-start gap-2 rounded-control border border-[#EBC9C3] bg-danger-soft px-3 py-2 text-[12px] leading-relaxed text-danger">
          <AlertIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>统计接口不可用（{statsError}），下方数字显示为“—”。这不是 0，是没有拿到数据。</span>
        </p>
      )}

      {/* ---------- 卡片区 ---------- */}
      <div className="mt-3.5 grid gap-3.5 xl:grid-cols-12">
        {/* 快速开始 */}
        <Card
          tone="cream"
          title="快速开始对话"
          subtitle="从一句真实提问开始，答案只来自知识库"
          className="xl:col-span-4"
          action={
            <Link
              href="/chat"
              className="flex h-7 items-center gap-1 rounded-pill bg-ink px-2.5 text-[11.5px] font-medium text-white hover:bg-black"
            >
              打开聊天
              <ArrowUpRightIcon className="h-3 w-3" />
            </Link>
          }
        >
          <div className="flex items-start gap-3 rounded-control border border-[#EADFAF] bg-white/70 p-3.5">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink text-cream">
              <ChatIcon className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <p className="text-[13px] font-medium text-ink">您好，今天有什么可以帮您？</p>
              <p className="mt-1 text-[11.5px] leading-relaxed text-muted">
                物流配送、退款政策、退换货与售后，回答都会附上知识库来源。
              </p>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {quickQueries.slice(0, 4).map((s) => (
              <Link
                key={s.label}
                href={`/chat?q=${encodeURIComponent(s.query)}`}
                className="rounded-pill border border-[#E3D5A0] bg-white px-2.5 py-1 text-[11.5px] text-ink transition-colors hover:bg-cream"
              >
                {s.label}
              </Link>
            ))}
            {quickQueries.length === 0 && (
              <span className="text-[11.5px] text-muted">快捷问题加载中…</span>
            )}
          </div>
        </Card>

        {/* 最近会话 */}
        <Card
          title="最近会话"
          subtitle={`共 ${stats?.sessions_total ?? sessions.length} 个会话 · 今日新增 ${stats?.sessions_today ?? 0}`}
          className="xl:col-span-5"
          action={
            <Link href="/chat" className="text-[11.5px] font-medium text-muted hover:text-ink">
              全部
            </Link>
          }
        >
          {recent.length === 0 ? (
            <div className="flex h-[132px] flex-col items-center justify-center rounded-control border border-dashed border-hairline text-center">
              <p className="text-[12.5px] text-muted">还没有对话记录</p>
              <Link href="/chat" className="mt-2 text-[12px] font-medium text-ink underline underline-offset-4">
                去问第一个问题
              </Link>
            </div>
          ) : (
            <ul className="space-y-1">
              {recent.map((s) => (
                <li key={s.id}>
                  <Link
                    href={`/chat?session=${s.id}`}
                    className="group flex items-center gap-2.5 rounded-control px-2.5 py-2 transition-colors hover:bg-mist"
                  >
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-hairline bg-surface text-muted">
                      <MessageIcon className="h-3.5 w-3.5" />
                    </span>
                    <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink">{s.title}</span>
                    <span className="shrink-0 text-[11px] text-muted">{relativeDay(s.updated_at)}</span>
                    <ArrowUpRightIcon className="h-3.5 w-3.5 shrink-0 text-muted opacity-0 transition-opacity group-hover:opacity-100" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* 服务状态（深色卡，参考图里的 Attention Report） */}
        <section className="surface-dark relative overflow-hidden xl:col-span-3">
          <div className="dotgrid pointer-events-none absolute inset-x-0 bottom-0 h-24 opacity-70" aria-hidden="true" />
          <div className="relative px-5 pb-5 pt-4">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-[14px] font-semibold tracking-tight text-white">服务状态</h2>
                <p className="mt-1 text-[11.5px] text-white/55">来自健康检查与模式接口</p>
              </div>
              <Link
                href="/settings"
                aria-label="查看详细设置"
                className="flex h-7 w-7 items-center justify-center rounded-full border border-white/15 text-white/70 transition-colors hover:bg-white/10 hover:text-white"
              >
                <ArrowUpRightIcon className="h-3.5 w-3.5" />
              </Link>
            </div>

            <p className="mt-5 text-[26px] font-semibold leading-none tracking-tight text-cream">
              {stats?.chunks ?? "—"}
              <span className="ml-1.5 text-[12px] font-normal text-white/50">个索引片段</span>
            </p>

            <div className="mt-4 space-y-2">
              {[
                { k: "回答模式", v: stats?.mode_label ?? "—", tone: "text-white" },
                { k: "模型服务", v: modelText, tone: modelStatus === "ok" ? "text-[#9ECFA8]" : "text-cream" },
                { k: "降级回答", v: `${stats?.degraded_total ?? 0} 条`, tone: "text-white" },
              ].map((row) => (
                <div key={row.k} className="flex items-center justify-between gap-2 text-[11.5px]">
                  <span className="text-white/50">{row.k}</span>
                  <span className={`truncate font-medium ${row.tone}`}>{row.v}</span>
                </div>
              ))}
            </div>

            <div className="mt-4 flex items-center gap-1.5 border-t border-white/10 pt-3 text-[11px] text-white/45">
              <RefreshIcon className="h-3 w-3" />
              {loading ? "正在读取…" : "刚刚更新"}
            </div>
          </div>
        </section>

        {/* 知识库 */}
        <Card
          title="知识库"
          subtitle="回答的唯一依据"
          className="xl:col-span-4"
          action={
            <Link href="/knowledge" className="text-[11.5px] font-medium text-muted hover:text-ink">
              管理
            </Link>
          }
        >
          <div className="grid grid-cols-3 gap-2">
            {[
              { k: "文档", v: n(stats?.docs_total) },
              { k: "片段", v: n(stats?.chunks) },
              { k: "维度", v: stats?.dim ? String(stats.dim) : "—" },
            ].map((x) => (
              <div key={x.k} className="rounded-control bg-mist px-3 py-2.5">
                <p className="text-[10.5px] text-muted">{x.k}</p>
                <p className="mt-1 truncate text-[15px] font-semibold tracking-tight text-ink">{x.v}</p>
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-center justify-between gap-2 text-[11.5px]">
            <span className="flex items-center gap-1.5 text-muted">
              <BookIcon className="h-3.5 w-3.5" />
              索引引擎 {stats?.index_backend ?? "—"}
            </span>
            <Link
              href="/knowledge"
              className="flex items-center gap-1 rounded-pill border border-hairline px-2.5 py-1 font-medium text-ink hover:bg-mist"
            >
              上传文档
              <ArrowUpRightIcon className="h-3 w-3" />
            </Link>
          </div>
        </Card>

        {/* 常见问题 */}
        <Card title="常见问题" subtitle="点击直接带着问题进入聊天" className="xl:col-span-5">
          <ul className="grid gap-1 sm:grid-cols-2">
            {quickQueries.map((s) => (
              <li key={s.label}>
                <Link
                  href={`/chat?q=${encodeURIComponent(s.query)}`}
                  className="group flex items-center gap-2 rounded-control px-2.5 py-2 transition-colors hover:bg-mist"
                >
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[#D9C46B]" />
                  <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink">{s.label}</span>
                  <ArrowUpRightIcon className="h-3.5 w-3.5 shrink-0 text-muted opacity-0 transition-opacity group-hover:opacity-100" />
                </Link>
              </li>
            ))}
            {quickQueries.length === 0 && (
              <li className="px-2.5 py-2 text-[12px] text-muted">快捷问题加载中…</li>
            )}
          </ul>
        </Card>

        {/* 今日概览 */}
        <Card
          title="今日概览"
          subtitle="按服务器本地时区统计"
          className="xl:col-span-3"
          action={<ClockIcon className="h-4 w-4 text-muted" />}
        >
          <div className="space-y-2.5">
            {[
              { k: "今日会话", v: n(stats?.sessions_today), hint: "" },
              { k: "今日消息", v: n(stats?.messages_today), hint: "" },
              {
                k: "知识引用率",
                v: stats?.knowledge_ratio == null ? "—" : `${Math.round(stats.knowledge_ratio * 100)}%`,
                hint:
                  stats?.knowledge_ratio == null
                    ? "还没有回答记录"
                    : `${stats.answer_mix.knowledge ?? 0} / ${stats.assistant_total} 条回答`,
              },
            ].map((row) => (
              <div key={row.k} className="flex items-baseline justify-between gap-2">
                <span className="text-[11.5px] text-muted">{row.k}</span>
                <span className="text-right">
                  <span className="text-[15px] font-semibold tracking-tight text-ink">{row.v}</span>
                  {row.hint && <span className="ml-1.5 text-[10.5px] text-muted">{row.hint}</span>}
                </span>
              </div>
            ))}
            <p className="border-t border-hairline pt-2.5 text-[10.5px] leading-relaxed text-muted">
              没有埋点的指标（如在线人数、真实成功率）不做展示。
            </p>
          </div>
        </Card>
      </div>
    </div>
  );
}
