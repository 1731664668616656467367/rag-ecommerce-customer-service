import type { Config } from "tailwindcss";

/** 设计变量集中在这一处。
 *
 *  为什么不全用任意值（如 bg-[#EDEDE9]）？
 *  同一个颜色如果在 50 个地方各写一遍字面量，改主题时必然漏掉几处，
 *  最后页面会出现三种"看起来差不多"的灰。
 *
 *  本版配色参考现代 SaaS 工作台：灰色外底 + 暖白主容器 + 奶油黄强调 + 黑色文字。
 *  语义名保持稳定（canvas/surface/ink/muted…），只换值，
 *  这样已有组件不用跟着改名就能整体换肤。
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ---- 基本面 ----
        shell: "#EDEDE9", // 最外层灰底
        paper: "#FCFBF7", // 主容器（暖白）
        canvas: "#EDEDE9", // 兼容旧名：页面底色
        surface: "#FFFFFF", // 卡片
        mist: "#F5F3ED", // 浅填充（hover / 次要区块）
        ink: "#222222", // 主文字
        muted: "#77746D", // 次文字
        hairline: "#E9E6DE", // 细边框
        "hairline-strong": "#DCD8CE",

        // ---- 强调色：奶油黄 + 黑 ----
        cream: "#F6E6A6",
        "cream-soft": "#FBF3D3",
        "cream-deep": "#EBD688",
        dark: "#292929", // 深色卡片 / 选中态
        "dark-soft": "#3A3A38",
        accent: "#222222", // 主按钮与链接统一为黑，避免第二主色打架
        "accent-strong": "#000000",
        "accent-soft": "#FBF3D3", // 选中底 = 奶油黄

        // ---- 状态色（暖调、低饱和）----
        success: "#3F6B4A",
        "success-soft": "#EAF1E6",
        warning: "#8A6A1F",
        "warning-soft": "#FBF3D3",
        danger: "#A23A31",
        "danger-soft": "#F8E7E4",
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "SF Pro Text",
          "Segoe UI",
          "PingFang SC",
          "Hiragino Sans GB",
          "Microsoft YaHei",
          "Noto Sans SC",
          "sans-serif",
        ],
        mono: ["SFMono-Regular", "Consolas", "Menlo", "monospace"],
      },
      borderRadius: {
        frame: "32px", // 主容器
        card: "22px", // 卡片
        control: "12px", // 控件
        pill: "999px",
      },
      boxShadow: {
        frame: "0 1px 2px rgba(34,34,34,0.04), 0 24px 60px -32px rgba(34,34,34,0.18)",
        card: "0 1px 2px rgba(34,34,34,0.03)",
        pop: "0 16px 40px -12px rgba(34,34,34,0.18), 0 2px 6px rgba(34,34,34,0.05)",
        lift: "0 6px 18px -10px rgba(34,34,34,0.22)",
        dark: "0 18px 40px -24px rgba(0,0,0,0.55)",
      },
      maxWidth: {
        content: "1240px",
      },
      fontSize: {
        "2xs": ["11px", "16px"],
        display: ["clamp(28px, 3.4vw, 44px)", { lineHeight: "1.08", letterSpacing: "-0.02em" }],
      },
      transitionTimingFunction: {
        "out-soft": "cubic-bezier(0.22, 0.61, 0.36, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
