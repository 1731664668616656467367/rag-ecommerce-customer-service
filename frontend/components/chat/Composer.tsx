"use client";

import { useEffect, useRef, useState } from "react";
import { SendIcon } from "@/components/icons";

interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
  maxLength?: number;
}

export default function Composer({
  onSend,
  disabled = false,
  placeholder = "描述你的问题，例如：退款一般几天到账？",
  maxLength = 2000,
}: Props) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  // 输入框随内容长高，但有上限，避免挤占消息区
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
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
    <div className="border-t border-hairline bg-white px-4 py-3 sm:px-6">
      <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-3xl border border-hairline bg-white px-3 py-2 transition-colors focus-within:border-accent/60">
        <textarea
          ref={ref}
          rows={1}
          value={value}
          maxLength={maxLength}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={placeholder}
          aria-label="输入消息"
          className="max-h-40 flex-1 resize-none bg-transparent px-2 py-2 text-[15px] leading-relaxed text-ink outline-none placeholder:text-muted/70"
        />
        <button
          type="button"
          onClick={submit}
          disabled={!canSend}
          aria-label="发送"
          className="mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-white transition-opacity hover:bg-[#0077ed] disabled:bg-hairline"
        >
          <SendIcon />
        </button>
      </div>
      <p className="mx-auto mt-2 max-w-3xl text-center text-[11.5px] text-muted">
        Enter 发送，Shift + Enter 换行 · 回答依据知识库资料，仅供参考
      </p>
    </div>
  );
}
