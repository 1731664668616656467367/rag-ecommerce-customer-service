"use client";

import type { ReactNode } from "react";
import { ArrowUpRightIcon } from "@/components/icons";

/** 通用卡片容器。
 *
 *  三个变体对应参考图里的三种卡：
 *  - `plain`：白底细边（大多数信息卡）
 *  - `cream`：奶油黄（强调但不需要对比）
 *  - `dark`  ：深色（需要视觉重心的"状态/提醒"卡）
 *
 *  `href` 存在时整张卡变成可点击入口，并显示右上角箭头——
 *  这是"每张卡都必须通往真实功能"的视觉承诺，不是装饰。
 */
interface Props {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  tone?: "plain" | "cream" | "dark";
  className?: string;
  bodyClassName?: string;
  children?: ReactNode;
  /** 有值时卡片右上角出现箭头，并作为"进入"的语义提示 */
  href?: string;
  testId?: string;
}

const TONE: Record<NonNullable<Props["tone"]>, string> = {
  plain: "surface",
  cream: "surface-cream",
  dark: "surface-dark",
};

export default function Card({
  title,
  subtitle,
  action,
  tone = "plain",
  className = "",
  bodyClassName = "",
  children,
  href,
  testId,
}: Props) {
  return (
    <section className={`${TONE[tone]} ${className}`} data-testid={testId}>
      {(title || action) && (
        <div className="flex items-start justify-between gap-3 px-5 pt-4">
          <div className="min-w-0">
            {title && (
              <h2
                className={`truncate text-[14px] font-semibold tracking-tight ${
                  tone === "dark" ? "text-white" : "text-ink"
                }`}
              >
                {title}
              </h2>
            )}
            {subtitle && (
              <p
                className={`mt-1 text-[11.5px] leading-snug ${
                  tone === "dark" ? "text-white/55" : "text-muted"
                }`}
              >
                {subtitle}
              </p>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {action}
            {href && (
              <span
                aria-hidden="true"
                className={`flex h-7 w-7 items-center justify-center rounded-full border transition-colors ${
                  tone === "dark"
                    ? "border-white/15 text-white/70"
                    : "border-hairline bg-surface text-muted"
                }`}
              >
                <ArrowUpRightIcon className="h-3.5 w-3.5" />
              </span>
            )}
          </div>
        </div>
      )}
      <div className={`px-5 pb-5 pt-3 ${bodyClassName}`}>{children}</div>
    </section>
  );
}
