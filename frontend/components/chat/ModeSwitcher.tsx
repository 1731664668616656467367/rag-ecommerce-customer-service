"use client";

import { useEffect, useId, useRef, useState } from "react";
import { AlertIcon, CheckIcon, ChevronDownIcon, ShieldIcon, SparklesIcon } from "@/components/icons";
import type { AnswerMode, AnswerModeState } from "@/lib/types";

/** 回答模式切换控件。
 *
 *  设计取舍：
 *  1. 不用原生 <select>：两个选项各带一句说明，原生下拉无法展示第二行文字；
 *  2. 必须同时有**图标 + 文字**，不能只靠颜色区分（色盲/灰度屏就失效了）；
 *  3. 键盘可用：Enter/Space 展开、↑↓ 移动、Enter 选中、Esc 关闭并回到触发器；
 *  4. 切换中禁用重复点击，避免一次点击发出多个 PUT。
 *
 *  重要：这个组件**不做乐观更新**。点完之后界面显示的是后端返回的模式，
 *  失败就回退——因为"前端显示切了、后端其实没切"比切不过去更糟。
 */
interface Props {
  state: AnswerModeState | null;
  loading?: boolean;
  switching?: boolean;
  error?: string | null;
  onChange: (mode: AnswerMode) => void;
}

const ICON: Record<AnswerMode, typeof ShieldIcon> = {
  knowledge_only: ShieldIcon,
  llm: SparklesIcon,
};

export default function ModeSwitcher({
  state,
  loading = false,
  switching = false,
  error = null,
  onChange,
}: Props) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const wrapRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  const options = state?.options ?? [];
  const current = state?.mode ?? "knowledge_only";
  const CurrentIcon = ICON[current];

  // 点击外部关闭：菜单浮在内容上，不关会挡住消息
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  // Esc 关闭：挂在 document 上而不是只挂列表，
  // 这样焦点不管落在触发器、列表还是别处，Esc 都能关掉（用户不关心焦点在哪）
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      setOpen(false);
      triggerRef.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  // 打开后把焦点移到当前选中项，键盘用户不用再摸索
  useEffect(() => {
    if (!open) return;
    const idx = Math.max(0, options.findIndex((o) => o.value === current));
    setActiveIndex(idx);
    const timer = window.setTimeout(() => optionRefs.current[idx]?.focus(), 0);
    return () => window.clearTimeout(timer);
  }, [open, options, current]);

  function close(focusTrigger = true) {
    setOpen(false);
    if (focusTrigger) triggerRef.current?.focus();
  }

  function choose(mode: AnswerMode) {
    if (switching) return;
    close();
    if (mode !== current) onChange(mode);
  }

  function onListKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      const next = (activeIndex + 1) % options.length;
      setActiveIndex(next);
      optionRefs.current[next]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const prev = (activeIndex - 1 + options.length) % options.length;
      setActiveIndex(prev);
      optionRefs.current[prev]?.focus();
    } else if (e.key === "Tab") {
      close(false);
    }
  }

  const modelWarning =
    state && state.model.status === "not_configured"
      ? "当前尚未配置可用的大语言模型服务，请先在后端配置模型接口。"
      : state && state.model.status === "error"
        ? `模型服务当前不可用：${state.model.status_text}。`
        : null;

  // 配了密钥但没调用过，同样不能暗示"可用"——只说事实
  const modelHint =
    state && state.model.status === "unverified"
      ? "密钥已配置，但还没有成功调用记录，暂时无法确认模型是否可用。"
      : null;

  return (
    <div className="relative" ref={wrapRef}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setOpen(true);
          }
        }}
        disabled={loading || switching}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={`回答模式：${state?.label ?? "知识库模式"}，点击切换`}
        data-testid="mode-trigger"
        className={`flex h-9 items-center gap-1.5 rounded-pill border px-3 text-[12.5px] font-medium transition-all ${
          switching
            ? "border-hairline bg-mist text-muted"
            : current === "llm"
              ? "border-dark bg-dark text-white hover:bg-black"
              : "border-[#EADFAF] bg-cream-soft text-ink hover:bg-cream"
        }`}
      >
        <CurrentIcon
          className={`h-4 w-4 ${switching ? "text-muted" : current === "llm" ? "text-cream" : "text-[#8A6A1F]"}`}
        />
        <span className="hidden sm:inline">{loading ? "读取模式…" : (state?.label ?? "知识库模式")}</span>
        <span className="sm:hidden">{current === "llm" ? "大模型" : "知识库"}</span>
        {switching ? (
          <span className="ml-0.5 h-3 w-3 rounded-full border-2 border-hairline border-t-accent spinner" />
        ) : (
          <ChevronDownIcon
            className={`h-3.5 w-3.5 transition-transform ${
              current === "llm" && !switching ? "text-white/70" : "text-muted"
            } ${open ? "rotate-180" : ""}`}
          />
        )}
      </button>

      {open && (
        <div
          id={listId}
          role="listbox"
          aria-label="选择回答模式"
          tabIndex={-1}
          onKeyDown={onListKeyDown}
          data-testid="mode-menu"
          className="absolute right-0 top-[calc(100%+8px)] z-50 w-[320px] overflow-hidden rounded-card border border-hairline bg-surface p-1.5 shadow-pop animate-pop"
        >
          <p className="px-2.5 pb-1 pt-1.5 text-[11px] font-medium uppercase tracking-[0.06em] text-muted">
            回答模式
          </p>

          {options.map((option, index) => {
            const Icon = ICON[option.value];
            const selected = option.value === current;
            // 两种模式各有一套选中外观：知识库=奶油黄，大模型=深色高对比。
            // 深色卡里所有文字都要换成浅色，否则白底黑字直接糊在一起。
            const darkSelected = selected && option.value === "llm";
            return (
              <button
                key={option.value}
                ref={(el) => {
                  optionRefs.current[index] = el;
                }}
                type="button"
                role="option"
                aria-selected={selected}
                data-testid={`mode-option-${option.value}`}
                onClick={() => choose(option.value)}
                onFocus={() => setActiveIndex(index)}
                className={`flex w-full items-start gap-2.5 rounded-control px-2.5 py-2 text-left transition-colors ${
                  darkSelected
                    ? "bg-dark text-white"
                    : selected
                      ? "bg-cream-soft ring-1 ring-[#EADFAF]"
                      : "hover:bg-mist focus:bg-mist"
                }`}
              >
                <Icon
                  className={`mt-0.5 h-4 w-4 shrink-0 ${
                    darkSelected ? "text-cream" : selected ? "text-[#8A6A1F]" : "text-muted"
                  }`}
                />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5">
                    <span
                      className={`text-[13px] font-medium ${darkSelected ? "text-white" : "text-ink"}`}
                    >
                      {option.label}
                    </span>
                    {/* 选中态必须同时有图标与文字：只靠底色区分，色觉障碍用户看不出来 */}
                    {selected && (
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-1.5 py-[1px] text-[10.5px] font-medium ${
                          darkSelected
                            ? "bg-white/15 text-white ring-1 ring-white/25"
                            : "bg-surface text-[#8A6A1F] ring-1 ring-[#EADFAF]"
                        }`}
                      >
                        <CheckIcon className="h-2.5 w-2.5" />
                        当前使用
                      </span>
                    )}
                  </span>
                  <span
                    className={`mt-0.5 block text-[11.5px] leading-snug ${
                      darkSelected ? "text-white/65" : "text-muted"
                    }`}
                  >
                    {option.description}
                  </span>
                </span>
              </button>
            );
          })}

          <div className="mt-1 border-t border-hairline px-2.5 pb-1 pt-2">
            {modelWarning ? (
              <p className="flex items-start gap-1.5 text-[11.5px] leading-snug text-warning">
                <AlertIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{modelWarning}</span>
              </p>
            ) : modelHint ? (
              <p className="flex items-start gap-1.5 text-[11.5px] leading-snug text-muted">
                <ShieldIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>
                  {modelHint}
                  <span className="mt-0.5 block">模式为全局设置，对所有会话生效。</span>
                </span>
              </p>
            ) : (
              <p className="text-[11.5px] leading-snug text-muted">
                模式为全局设置，对所有会话生效。
              </p>
            )}
          </div>
        </div>
      )}

      {error && (
        <p className="absolute right-0 top-[calc(100%+6px)] z-40 w-[300px] rounded-control border border-[#EFD6D2] bg-danger-soft px-2.5 py-1.5 text-[11.5px] leading-snug text-danger shadow-card">
          {error}
        </p>
      )}
    </div>
  );
}
