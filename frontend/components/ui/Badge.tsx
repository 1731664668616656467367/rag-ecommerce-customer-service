import type { ReactNode } from "react";

/** 状态徽标。
 *
 *  颜色只是辅助——每个徽标都必须有文字，不允许"只有一个小圆点"，
 *  因为色盲用户和打印出来的页面都看不出颜色差异。
 */
type Tone = "neutral" | "blue" | "green" | "amber" | "red" | "outline" | "dark" | "cream";

const TONE: Record<Tone, string> = {
  neutral: "bg-mist text-muted border-transparent",
  // blue 是历史命名（原来指主色蓝），现在指向"主色=黑/奶油黄"体系
  blue: "bg-cream-soft text-[#6B5A1E] border-[#EADFAF]",
  cream: "bg-cream text-[#5F5019] border-[#E3D28F]",
  green: "bg-success-soft text-success border-[#D8E4D4]",
  amber: "bg-cream-soft text-warning border-[#EADFAF]",
  red: "bg-danger-soft text-danger border-[#EBC9C3]",
  outline: "bg-surface text-muted border-hairline",
  dark: "bg-ink text-white border-ink",
};

interface Props {
  tone?: Tone;
  children: ReactNode;
  icon?: ReactNode;
  className?: string;
}

export default function Badge({ tone = "neutral", children, icon, className = "" }: Props) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-[3px] text-[11.5px] font-medium leading-none ${TONE[tone]} ${className}`}
    >
      {icon}
      {children}
    </span>
  );
}
