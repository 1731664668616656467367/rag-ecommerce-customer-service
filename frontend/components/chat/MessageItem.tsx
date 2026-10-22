"use client";

import { useState } from "react";
import type { ChatMessage, ReplyType } from "@/lib/types";
import { DEGRADED_TEXT, formatTime } from "@/lib/format";
import { Markdown } from "@/lib/markdown";
import Badge from "@/components/ui/Badge";
import SuggestionCards from "@/components/chat/SuggestionCards";
import {
  AlertIcon,
  CheckIcon,
  ChevronDownIcon,
  CopyIcon,
  FileIcon,
  RefreshIcon,
  ShieldIcon,
  SparklesIcon,
  ThumbDownIcon,
  ThumbUpIcon,
} from "@/components/icons";

/** 回答类型的展示规则。
 *
 *  这张表是整个前端最容易"说谎"的地方：
 *  只有真正引用了知识库片段时，才允许出现"知识库回答"。
 *  引导语、超范围说明、降级提示各有各的标签，不能混用，
 *  更不能把知识库原文标成"大模型生成"，反之亦然。
 */
const REPLY_META: Record<
  ReplyType,
  { label: string; tone: "blue" | "neutral" | "amber" | "red" | "green"; kind: string }
> = {
  greeting: { label: "问候", tone: "neutral", kind: "conversation" },
  identity: { label: "服务介绍", tone: "neutral", kind: "conversation" },
  thanks: { label: "致谢", tone: "neutral", kind: "conversation" },
  farewell: { label: "结束语", tone: "neutral", kind: "conversation" },
  human_service: { label: "能力说明", tone: "neutral", kind: "conversation" },
  knowledge: { label: "知识库回答", tone: "blue", kind: "knowledge" },
  no_answer: { label: "未找到可靠信息", tone: "amber", kind: "knowledge" },
  fallback: { label: "服务范围说明", tone: "neutral", kind: "conversation" },
  unclear: { label: "需要澄清", tone: "amber", kind: "conversation" },
};

interface Props {
  message: ChatMessage;
  isLast?: boolean;
  onFeedback?: (messageId: string, rating: "helpful" | "unhelpful") => void;
  feedbackState?: "idle" | "sending" | "done" | "error";
  feedbackRating?: "helpful" | "unhelpful" | null;
  onPickSuggestion?: (query: string) => void;
  suggestionsDisabled?: boolean;
  onRetry?: () => void;
}

export default function MessageItem({
  message,
  isLast = false,
  onFeedback,
  feedbackState = "idle",
  feedbackRating = null,
  onPickSuggestion,
  suggestionsDisabled = false,
  onRetry,
}: Props) {
  const [copied, setCopied] = useState(false);
  const [showSources, setShowSources] = useState(false);

  const isUser = message.role === "user";
  const sources = message.sources ?? [];
  const suggestions = message.suggestions ?? [];
  const replyType = message.reply_type;
  const meta = replyType ? REPLY_META[replyType] : null;
  const conversational = meta?.kind === "conversation";
  const degradedText = message.degraded ? DEGRADED_TEXT[message.degraded] : null;

  // 标签优先级：引导/无答案 > 降级 > 大模型生成 > 知识库原文
  let badge: { label: string; tone: "blue" | "neutral" | "amber" | "red" | "green"; icon?: React.ReactNode } | null =
    meta ? { label: meta.label, tone: meta.tone } : null;

  if (degradedText) {
    badge = { label: "已降级 · 仅展示知识库原文", tone: "amber", icon: <AlertIcon className="h-3 w-3" /> };
  } else if (message.answer_mode === "llm" && replyType === "knowledge") {
    // 只有 llm 模式下真正由模型组织出来的答案才敢标"大语言模型回答"
    badge = { label: "大语言模型回答", tone: "blue", icon: <SparklesIcon className="h-3 w-3" /> };
  } else if (replyType === "knowledge") {
    badge = { label: "知识库回答", tone: "blue", icon: <ShieldIcon className="h-3 w-3" /> };
  } else if (!replyType && message.answer_mode === "knowledge_only") {
    // 历史消息（改版前入库，没有 reply_type）：有来源才算原文，没有就是没找到
    badge = sources.length
      ? { label: "知识库回答", tone: "blue", icon: <ShieldIcon className="h-3 w-3" /> }
      : { label: "未找到可靠信息", tone: "amber" };
  }

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
      <div className="flex justify-end animate-rise" data-testid="message-user">
        <div className="max-w-[85%] rounded-[18px] rounded-br-[6px] bg-ink px-4 py-2.5 text-[14.5px] leading-relaxed text-white shadow-lift sm:max-w-[72%]">
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-rise" data-testid="message-assistant">
      <div className="flex gap-3">
        <span
          aria-hidden="true"
          className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ink text-cream shadow-lift"
        >
          <SparklesIcon className="h-4 w-4" />
        </span>

        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className="text-[12.5px] font-medium text-ink">智能客服</span>
            {badge && (
              <Badge tone={badge.tone} icon={badge.icon}>
                {badge.label}
              </Badge>
            )}
            {message.intent && message.intent !== "其他" && (
              <Badge tone="outline">{message.intent}</Badge>
            )}
            <span className="text-[11.5px] text-muted">{formatTime(message.created_at)}</span>
          </div>

          <div className="rounded-[18px] rounded-tl-[6px] border border-hairline bg-surface px-4 py-3 shadow-card">
            <Markdown text={message.content} />
          </div>

          {degradedText && (
            <div className="mt-2 flex items-start gap-2 rounded-control border border-[#EADFAF] bg-cream-soft px-3 py-2 text-[12.5px] leading-relaxed text-warning">
              <AlertIcon className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{degradedText}</span>
            </div>
          )}

          {/* 来源：只有真的检索到片段才渲染。没有来源却摆一个"来源"入口，就是在骗人。 */}
          {!conversational && sources.length > 0 && (
            <div className="mt-2">
              <button
                type="button"
                onClick={() => setShowSources((v) => !v)}
                aria-expanded={showSources}
                className="inline-flex items-center gap-1 text-[12.5px] text-accent transition-colors hover:text-accent-strong"
              >
                <FileIcon className="h-3.5 w-3.5" />
                {showSources ? "收起来源" : `查看 ${sources.length} 条来源`}
                <ChevronDownIcon
                  className={`h-3 w-3 transition-transform ${showSources ? "rotate-180" : ""}`}
                />
              </button>

              {showSources && (
                <ul className="mt-2 space-y-1.5">
                  {sources.map((s) => (
                    <li
                      key={`${s.document_id}-${s.chunk_index}`}
                      className="rounded-[10px] border border-hairline bg-[#F8FAFC] px-3 py-2"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="flex min-w-0 items-center gap-1.5 text-[12.5px] font-medium text-ink">
                          <FileIcon className="h-3.5 w-3.5 shrink-0 text-muted" />
                          <span className="truncate">{s.file_name}</span>
                        </span>
                        <span className="shrink-0 text-[11.5px] text-muted">
                          第 {s.chunk_index + 1} 段 · 相关度 {s.score.toFixed(2)}
                        </span>
                      </div>
                      <p className="mt-1 line-clamp-2 text-[12px] leading-relaxed text-muted">
                        {s.snippet}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {suggestions.length > 0 && onPickSuggestion && (
            <SuggestionCards
              suggestions={suggestions}
              onPick={onPickSuggestion}
              disabled={suggestionsDisabled}
              variant="chip"
            />
          )}

          <div className="mt-2 flex items-center gap-0.5">
            <button type="button" onClick={copy} className="btn-quiet btn-sm gap-1">
              {copied ? <CheckIcon className="h-3.5 w-3.5" /> : <CopyIcon className="h-3.5 w-3.5" />}
              {copied ? "已复制" : "复制"}
            </button>

            {isLast && onRetry && !conversational && (
              <button type="button" onClick={onRetry} className="btn-quiet btn-sm gap-1">
                <RefreshIcon className="h-3.5 w-3.5" />
                重新回答
              </button>
            )}

            {/* 对"你好"点"没帮助"没有意义，所以引导类回复不显示评价 */}
            {!conversational && (
              <>
                <span className="mx-1 h-3.5 w-px bg-hairline" aria-hidden="true" />
                <button
                  type="button"
                  disabled={feedbackState === "sending" || feedbackRating !== null}
                  onClick={() => onFeedback?.(message.id, "helpful")}
                  aria-label="这条回答有帮助"
                  className={`btn-quiet btn-sm gap-1 ${feedbackRating === "helpful" ? "text-accent" : ""}`}
                >
                  <ThumbUpIcon className="h-3.5 w-3.5" />
                  有帮助
                </button>
                <button
                  type="button"
                  disabled={feedbackState === "sending" || feedbackRating !== null}
                  onClick={() => onFeedback?.(message.id, "unhelpful")}
                  aria-label="这条回答没有帮助"
                  className={`btn-quiet btn-sm gap-1 ${feedbackRating === "unhelpful" ? "text-ink" : ""}`}
                >
                  <ThumbDownIcon className="h-3.5 w-3.5" />
                  没帮助
                </button>
                {feedbackState === "done" && (
                  <span className="ml-1 text-[11.5px] text-success">已记录</span>
                )}
                {feedbackState === "error" && (
                  <span className="ml-1 text-[11.5px] text-danger">提交失败</span>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
