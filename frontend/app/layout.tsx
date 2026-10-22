import type { Metadata } from "next";
import NavBar from "@/components/NavBar";
import "./globals.css";

export const metadata: Metadata = {
  title: "智能客服工作台 · 电商 RAG",
  description: "管理对话、知识库与 AI 回答服务的电商智能客服工作台",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="h-dvh overflow-hidden bg-shell">
        {/* 外层灰底 + 内层暖白大圆角容器：整站只有一个滚动区，
            这样切换页面时外框不会跟着跳，视觉上更像一个"应用"而不是网页 */}
        <div className="mx-auto flex h-full max-w-[1680px] flex-col p-2 sm:p-3.5 lg:p-5">
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-frame bg-paper shadow-frame ring-1 ring-[#E4E0D6]">
            <NavBar />
            <main className="scroll-thin flex min-h-0 flex-1 flex-col overflow-y-auto">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
