"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AnswerModeState } from "@/lib/types";
import { BookIcon, ChatIcon, GearIcon, GridIcon, ShieldIcon, SparklesIcon } from "./icons";

/** 顶部导航。
 *
 *  参考图的设计语言：品牌胶囊 + 中间一组胶囊导航（选中项是深色实心）+ 右侧状态入口。
 *  "工作台 / 聊天 / 知识库 / 设置" 对应四个真实路由，全部可点。
 *
 *  右侧的"模式 + 服务状态"读的是后端真实状态（/api/settings/answer-mode），
 *  没有拿到数据时显示"状态未知"，不默认写成"正常"。
 */
const NAV = [
  { href: "/", label: "工作台", Icon: GridIcon },
  { href: "/chat", label: "聊天", Icon: ChatIcon },
  { href: "/knowledge", label: "知识库", Icon: BookIcon },
  { href: "/settings", label: "设置", Icon: GearIcon },
];

export default function NavBar() {
  const pathname = usePathname();
  const [mode, setMode] = useState<AnswerModeState | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .getAnswerMode()
      .then((m) => !cancelled && setMode(m))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  const active = (href: string) =>
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);

  const llmOn = mode?.mode === "llm";
  const statusTone = failed
    ? "text-danger"
    : !mode
      ? "text-muted"
      : mode.model.status === "ok"
        ? "text-success"
        : mode.model.status === "not_configured"
          ? "text-warning"
          : mode.model.status === "error"
            ? "text-danger"
            : "text-muted";

  const statusText = failed
    ? "状态未知"
    : !mode
      ? "读取中"
      : mode.model.status === "ok"
        ? "模型可用"
        : mode.model.status === "not_configured"
          ? "未配置模型"
          : mode.model.status === "error"
            ? "模型异常"
            : "模型未验证";

  return (
    <header className="relative z-30 flex h-[60px] shrink-0 items-center gap-2 border-b border-hairline/80 px-3 sm:px-5">
      {/* 品牌 */}
      <Link href="/" className="flex min-w-0 shrink-0 items-center gap-2.5" aria-label="回到工作台">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink text-cream">
          <SparklesIcon className="h-4 w-4" />
        </span>
        <span className="hidden min-w-0 sm:block">
          <span className="block truncate text-[13.5px] font-semibold leading-tight tracking-tight text-ink">
            智能客服
          </span>
          <span className="block truncate text-[10.5px] leading-tight text-muted">电商 RAG 工作台</span>
        </span>
      </Link>

      {/* 胶囊导航 */}
      <nav
        aria-label="主导航"
        className="ml-1 flex items-center gap-0.5 rounded-pill border border-hairline bg-surface/80 p-1 sm:ml-3"
      >
        {NAV.map(({ href, label, Icon }) => {
          const on = active(href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={on ? "page" : undefined}
              className={`flex h-8 items-center gap-1.5 rounded-pill px-2.5 text-[12.5px] font-medium transition-all duration-150 ${
                on
                  ? "bg-ink text-white shadow-lift"
                  : "text-muted hover:bg-mist hover:text-ink"
              }`}
            >
              <Icon className="h-[15px] w-[15px]" />
              <span className="hidden md:inline">{label}</span>
              <span className="sr-only md:hidden">{label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="flex-1" />

      {/* 模式与服务状态入口：点击进入设置页 */}
      <Link
        href="/settings"
        aria-label={`当前回答模式：${mode?.label ?? "读取中"}，服务状态：${statusText}，点击查看设置`}
        className={`flex h-8 max-w-[240px] items-center gap-2 rounded-pill border px-3 text-[12px] font-medium transition-colors ${
          llmOn
            ? "border-dark bg-dark text-white hover:bg-black"
            : "border-[#E7D79B] bg-cream-soft text-ink hover:bg-cream"
        }`}
      >
        {llmOn ? <SparklesIcon className="h-3.5 w-3.5" /> : <ShieldIcon className="h-3.5 w-3.5" />}
        <span className="truncate">{mode?.label ?? "读取中…"}</span>
        <span className={`hidden items-center gap-1 sm:flex ${llmOn ? "text-white/70" : "text-muted"}`}>
          <span aria-hidden="true">·</span>
          <span className={llmOn ? "text-white/70" : statusTone}>{statusText}</span>
        </span>
      </Link>

      <Link
        href="/settings"
        aria-label="设置"
        className="hidden h-8 w-8 items-center justify-center rounded-full border border-hairline bg-surface text-muted transition-colors hover:bg-mist hover:text-ink sm:flex"
      >
        <GearIcon className="h-4 w-4" />
      </Link>
    </header>
  );
}
