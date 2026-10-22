"use client";

import type { SuggestionItem } from "@/lib/types";

/** 快捷问题按钮组。
 *
 *  为什么做成独立组件？
 *  首屏欢迎、问候回复、超范围回复、没听懂回复都要出现同一组按钮。
 *  如果每处各写一遍，样式会慢慢走散，行为也会不一致（有的禁用有的不禁用）。
 *
 *  关键行为：`onPick` 传出去的是 `query`，不是 `label`。
 *  label 是给人看的短标题（“退款政策”），query 才是真正发给后端的完整问句
 *  （“退款政策是什么？”）。混用会让检索拿到一个信息量不足的短词。
 *
 *  禁用逻辑由父组件控制：`disabled` 为真时所有按钮不可点，
 *  这是“不会重复发送”的第一道闸——请求还没回来就点不动。
 */
interface Props {
  suggestions: SuggestionItem[];
  onPick: (query: string) => void;
  disabled?: boolean;
  title?: string | null;
  /** 紧凑模式：用在消息气泡下方，间距更小、不显示说明文字 */
  compact?: boolean;
}

export default function SuggestionChips({
  suggestions,
  onPick,
  disabled = false,
  title = "你可以这样问",
  compact = false,
}: Props) {
  if (suggestions.length === 0) return null;

  return (
    <div className={compact ? "mt-3" : "mt-7"}>
      {title && <p className="label mb-2">{title}</p>}
      <div className="flex flex-wrap gap-2">
        {suggestions.map((s) => (
          <button
            key={s.query}
            type="button"
            disabled={disabled}
            onClick={() => onPick(s.query)}
            // 供端到端测试断言“点的是哪一个、发的是什么”
            data-testid="suggestion-chip"
            data-query={s.query}
            title={s.description ?? undefined}
            aria-label={s.description ? `${s.label}：${s.description}` : s.label}
            className={`group flex max-w-full flex-col items-start rounded-full border border-hairline px-3.5 py-2 text-left transition-colors ${
              disabled
                ? "cursor-not-allowed opacity-45"
                : "hover:border-ink/30 hover:bg-mist"
            }`}
          >
            <span className="text-[13px] font-medium text-ink">{s.label}</span>
            {!compact && s.description && (
              <span className="text-[11.5px] leading-tight text-muted">{s.description}</span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
