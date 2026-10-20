import type { Metadata } from "next";
import NavBar from "@/components/NavBar";
import "./globals.css";

export const metadata: Metadata = {
  title: "智能客服 · 电商知识库问答",
  description: "基于 RAG 的电商智能客服工作台：意图识别、知识库检索与对话记录",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen bg-canvas">
        <NavBar />
        <main className="mx-auto max-w-content px-0 sm:px-8">{children}</main>
      </body>
    </html>
  );
}
