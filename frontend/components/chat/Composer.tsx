"use client";

import { useEffect, useRef, useState } from "react";
import { SendIcon } from "@/components/icons";

/** 底部输入区。
 *
 *  细节说明：
 *  - Enter 发送 / Shift+Enter 换行；中文输入法组字过程中按 Enter 不发送
 *    （`isComposing`）——少了这个判断，打拼音时选词会把半截句子发出去。
 *  - 输入为空或正在发送时按钮禁用，这是"不会重复提交"的第一道闸（第二道在页面里）。
 *  - 高度随内容增长但有上限，超过 168px 后内部滚动，不会把输入区顶到屏幕外。
 */
interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
  maxLength?: number;
  modeHint?: string;
}

export default function Composer({
  onSend,
  disabled = false,
  placeholder = "描述你的问题，例如：退款一般几天到账？",
  maxLength = 2000,
  modeHint = "基于知识库回答",
}: Props) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 168)}px`;
  }, [value]);

  const canSend = value.trim().length > 0 && !disabled;

  function submit() {
    if (!canSend) return;
    onSend(value.trim());
    setValue("");
    requestAnimationFrame(() => {
      if (ref.current) ref.current.style.height = "auto";
    });
  }

  return (
    <div className="shrink-0 border-t border-hairline bg-paper/95 px-3 py-2.5 sm:px-6 sm:py-3.5">
      <div className="mx-auto max-w-3xl">
        <div className="rounded-card border border-hairline bg-surface px-2 py-1.5 shadow-card transition-all focus-within:border-hairline-strong focus-within:ring-4 focus-within:ring-cream/50">
          <textarea
            ref={ref}
            rows={1}
            value={value}
            maxLength={maxLength}
            disabled={disabled}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder={placeholder}
            aria-label="输入消息"
            className="max-h-[168px] w-full resize-none bg-transparent px-2.5 py-2 text-[14.5px] leading-relaxed text-ink outline-none placeholder:text-muted/70 disabled:opacity-60"
          />

          <div className="flex items-center justify-between gap-2 px-1 pb-0.5 pt-1">
            <span className="flex min-w-0 items-center gap-1.5 text-[11.5px] text-muted">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-cream-deep" aria-hidden="true" />
              <span className="truncate">{modeHint}</span>
            </span>

            <div className="flex shrink-0 items-center gap-2">
              <span className="hidden text-[11px] tabular-nums text-muted sm:inline">
                {value.length}/{maxLength}
              </span>
              <button
                type="button"
                onClick={submit}
                disabled={!canSend}
                aria-label="发送"
                className="flex h-8 w-8 items-center justify-center rounded-full bg-ink text-white transition-all hover:bg-black hover:shadow-lift active:scale-95 disabled:bg-hairline disabled:text-white/80 disabled:shadow-none disabled:active:scale-100"
              >
                {disabled ? (
                  <span className="h-3.5 w-3.5 rounded-full border-2 border-white/40 border-t-white spinner" />
                ) : (
                  <SendIcon className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>
        </div>

        <p className="mt-1.5 hidden text-[11px] text-muted sm:block">
          Enter 发送，Shift + Enter 换行 · 回答依据知识库资料，仅供参考
        </p>
      </div>
    </div>
  );
}
