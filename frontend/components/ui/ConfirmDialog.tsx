"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { CloseIcon } from "@/components/icons";

/** 确认弹窗。
 *
 *  为什么不用 window.confirm？
 *  原生 confirm 无法说明"删除后会发生什么"，也不能显示文档名/片段数这类上下文，
 *  更不能做 loading 与失败重试。删除是不可逆操作，值得一个真正的对话框。
 *
 *  可访问性：role="dialog" + aria-modal，Esc 关闭，打开时焦点落到取消按钮
 *  （危险操作的默认焦点不放在"确认"上，避免随手回车就删了）。
 */
interface Props {
  open: boolean;
  title: string;
  description?: ReactNode;
  confirmText?: string;
  cancelText?: string;
  tone?: "danger" | "primary";
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmText = "确认",
  cancelText = "取消",
  tone = "danger",
  busy = false,
  onConfirm,
  onCancel,
}: Props) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onCancel();
    };
    document.addEventListener("keydown", onKey);
    // 弹窗打开时锁滚动，避免背景跟着动
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, busy, onCancel]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-6">
      <div
        className="absolute inset-0 bg-ink/25 animate-fade"
        onClick={() => !busy && onCancel()}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        className="relative w-full max-w-[420px] rounded-t-[20px] border border-hairline bg-surface p-5 shadow-pop animate-pop sm:rounded-card"
      >
        <div className="flex items-start justify-between gap-3">
          <h2 id="confirm-title" className="text-[15.5px] font-semibold text-ink">
            {title}
          </h2>
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            aria-label="关闭"
            className="btn-quiet btn-icon -mr-1 -mt-1"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        </div>

        {description && <div className="mt-2 text-[13px] leading-relaxed text-muted">{description}</div>}

        <div className="mt-5 flex justify-end gap-2">
          <button ref={cancelRef} type="button" onClick={onCancel} disabled={busy} className="btn-ghost">
            {cancelText}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={tone === "danger" ? "btn-danger" : "btn-primary"}
          >
            {busy ? "处理中…" : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
