"use client";

import { useState } from "react";
import type { ChatMessage } from "@/lib/types";
import { DEGRADED_TEXT, formatTime } from "@/lib/format";
import {
  AlertIcon,
  CheckIcon,
  CopyIcon,
  ThumbDownIcon,
  ThumbUpIcon,
} from "@/components/icons";

interface Props {
  message: ChatMessage;
  onFeedback?: (messageId: string, rating: "helpful" | "unhelpful") => void;
  feedbackState?: "idle" | "sending" | "done" | "error";
  feedbackRating?: "helpful" | "unhelpful" | null;
}

export default function MessageItem({
  message,
  onFeedback,
  feedbackState = "idle",
  feedbackRating = null,
}: Props) {
  const [copied, setCopied] = useState(false);
  const [showSources, setShowSources] = useState(false);
  const isUser = message.role === "user";
  const sources = message.sources ?? [];
  const degradedText = message.degraded ? DEGRADED_TEXT[message.degraded] : null;

  async function copy() {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  if (isUser) {
    return (
      <div className="flex justify-end animate-rise">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-mist px-4 py-2.5 text-[15px] leading-relaxed text-ink sm:max-w-[75%]">
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-rise">
      <div className="flex gap-3">
        <div
          aria-hidden="true"
          className="mt-1 h-6 w-6 shrink-0 rounded-full border border-hairline bg-white text-[11px] font-semibold leading-[22px] text-center text-muted"
        >
          客
        </div>
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center gap-2 text-[12px] text-muted">
            <span>智能客服</span>
            {message.intent && message.intent !== "其他" && (
              <span className="rounded-full bg-mist px-2 py-0.5 text-[11px] text-muted">
                {message.intent}
              </span>
            )}
            <span className="text-hairline">·</span>
            <span>{formatTime(message.created_at)}</span>
          </div>

          <div className="whitespace-pre-wrap break-words text-[15px] leading-[1.75] text-ink">
            {message.content}
          </div>

          {degradedText && (
            <div className="mt-3 flex items-start gap-2 rounded-xl border border-[#f0d9a8] bg-[#fffaf0] px-3 py-2 text-[12.5px] text-[#7a5b14]">
              <AlertIcon className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{degradedText}</span>
            </div>
          )}

          {sources.length > 0 && (
            <div className="mt-3">
              <button
                type="button"
                onClick={() => setShowSources((v) => !v)}
                className="text-[12.5px] text-accent hover:underline"
                aria-expanded={showSources}
              >
                {showSources ? "收起来源" : `查看 ${sources.length} 条来源`}
              </button>

              {showSources && (
                <ul className="mt-2 space-y-2">
                  {sources.map((s) => (
                    <li
                      key={`${s.document_id}-${s.chunk_index}`}
                      className="rounded-xl border border-hairline bg-mist/60 px-3 py-2"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2 text-[12px] text-muted">
                        <span className="font-medium text-ink">{s.file_name}</span>
                        <span>
                          第 {s.chunk_index + 1} 段 · 相关度 {s.score.toFixed(2)}
                        </span>
                      </div>
                      <p className="mt-1 line-clamp-3 text-[12.5px] leading-relaxed text-muted">
                        {s.snippet}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className="mt-2.5 flex items-center gap-1">
            <button type="button" onClick={copy} className="btn-quiet gap-1.5 px-2 py-1 text-[12.5px]">
              {copied ? <CheckIcon className="h-3.5 w-3.5" /> : <CopyIcon className="h-3.5 w-3.5" />}
              {copied ? "已复制" : "复制"}
            </button>

            <span className="mx-1 h-3.5 w-px bg-hairline" aria-hidden="true" />

            <button
              type="button"
              disabled={feedbackState === "sending" || feedbackRating !== null}
              onClick={() => onFeedback?.(message.id, "helpful")}
              aria-label="这条回答有帮助"
              className={`btn-quiet gap-1.5 px-2 py-1 text-[12.5px] ${
                feedbackRating === "helpful" ? "text-accent" : ""
              }`}
            >
              <ThumbUpIcon className="h-3.5 w-3.5" />
              有帮助
            </button>
            <button
              type="button"
              disabled={feedbackState === "sending" || feedbackRating !== null}
              onClick={() => onFeedback?.(message.id, "unhelpful")}
              aria-label="这条回答没有帮助"
              className={`btn-quiet gap-1.5 px-2 py-1 text-[12.5px] ${
                feedbackRating === "unhelpful" ? "text-ink" : ""
              }`}
            >
              <ThumbDownIcon className="h-3.5 w-3.5" />
              没帮助
            </button>

            {feedbackState === "done" && <span className="ml-1 text-[12px] text-muted">已记录</span>}
            {feedbackState === "error" && (
              <span className="ml-1 text-[12px] text-[#b3261e]">提交失败</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
