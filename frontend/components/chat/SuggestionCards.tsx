"use client";

import type { SuggestionItem } from "@/lib/types";
import {
  ChatIcon,
  HeadsetIcon,
  ReceiptIcon,
  RefundIcon,
  SwapIcon,
  TruckIcon,
  WrenchIcon,
} from "@/components/icons";

/** 便捷问题：两种形态，一套数据。
 *
 *  card —— 首屏欢迎区的大卡片（图标 + 标题 + 说明），引导用户开口；
 *  chip —— 消息气泡下方的小按钮，不打断阅读，只在引导类回复后出现。
 *
 *  为什么要分两种：首屏没有上下文，需要更强的视觉引导；
 *  而聊到一半时再甩 6 张卡片，会把对话内容挤散。
 *
 *  点击传出去的是 `query`（完整问句），不是 `label`（短标题）。
 *  label 只有 4 个字，检索拿不到足够信息，命中率会掉。
 */
const ICONS: Record<string, typeof ChatIcon> = {
  物流配送: TruckIcon,
  退款政策: RefundIcon,
  退换货: SwapIcon,
  售后服务: WrenchIcon,
  订单查询: ReceiptIcon,
  联系人工客服: HeadsetIcon,
};

interface Props {
  suggestions: SuggestionItem[];
  onPick: (query: string) => void;
  disabled?: boolean;
  variant?: "card" | "chip";
  title?: string | null;
}

export default function SuggestionCards({
  suggestions,
  onPick,
  disabled = false,
  variant = "card",
  title = null,
}: Props) {
  if (suggestions.length === 0) return null;

  if (variant === "chip") {
    return (
      <div className="mt-3">
        {title && <p className="label mb-2">{title}</p>}
        <div className="flex flex-wrap gap-1.5">
          {suggestions.map((s) => (
            <button
              key={s.query}
              type="button"
              disabled={disabled}
              onClick={() => onPick(s.query)}
              data-testid="suggestion-chip"
              data-query={s.query}
              title={s.description ?? undefined}
              className="inline-flex h-8 items-center gap-1.5 rounded-pill border border-hairline bg-surface px-3
                         text-[12.5px] text-ink transition-colors
                         hover:border-[#E3D5A0] hover:bg-cream-soft
                         active:bg-cream disabled:cursor-not-allowed disabled:opacity-45"
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div>
      {title && <p className="label mb-2.5">{title}</p>}
      <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
        {suggestions.map((s, i) => {
          const Icon = ICONS[s.label] ?? ChatIcon;
          // 6 张卡片按 白/奶油/白… 轮换，其中第 2 张用深色做视觉锚点；
          // 只做配色变化，交互与语义完全一致。
          const dark = i === 1;
          const cream = !dark && (i === 3 || i === 5);
          return (
            <button
              key={s.query}
              type="button"
              disabled={disabled}
              onClick={() => onPick(s.query)}
              data-testid="suggestion-card"
              data-query={s.query}
              className={`group flex items-start gap-3 rounded-card border p-3.5 text-left transition-all duration-200 ease-out-soft
                         hover:-translate-y-0.5 hover:shadow-lift focus-visible:outline-none
                         active:translate-y-0 disabled:pointer-events-none disabled:opacity-50 ${
                           dark
                             ? "border-[#333331] bg-dark text-white shadow-dark hover:border-[#3d3d3a]"
                             : cream
                               ? "border-[#EADFAF] bg-cream-soft shadow-card hover:border-[#DFCF94]"
                               : "border-hairline bg-surface shadow-card hover:border-hairline-strong"
                         }`}
            >
              <span
                className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors ${
                  dark ? "bg-white/10 text-cream" : "bg-mist text-ink group-hover:bg-cream"
                }`}
              >
                <Icon className="h-4 w-4" />
              </span>
              <span className="min-w-0">
                <span className={`block text-[13.5px] font-medium ${dark ? "text-white" : "text-ink"}`}>
                  {s.label}
                </span>
                <span className={`mt-0.5 block text-[12px] leading-snug ${dark ? "text-white/55" : "text-muted"}`}>
                  {s.description ?? s.query}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
