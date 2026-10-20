"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Composer from "@/components/chat/Composer";
import MessageItem from "@/components/chat/MessageItem";
import SessionSidebar from "@/components/chat/SessionSidebar";
import { AlertIcon, MenuIcon, RefreshIcon } from "@/components/icons";
import { api, ApiRequestError } from "@/lib/api";
import type { ChatMessage, HealthResponse, SessionItem } from "@/lib/types";

const SUGGESTIONS = [
  "商品有质量问题，签收后多久内可以退货？",
  "退款一般多久能到账？",
  "同城配送一般几天能到？",
  "怎么修改收货地址？",
];

type FeedbackState = { state: "idle" | "sending" | "done" | "error"; rating: "helpful" | "unhelpful" | null };

export default function ChatPage() {
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastFailed, setLastFailed] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [feedback, setFeedback] = useState<Record<string, FeedbackState>>({});

  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const loadSessions = useCallback(async () => {
    try {
      const list = await api.listSessions();
      setSessions(list);
      return list;
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载会话失败");
      return [];
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  // 首屏：加载会话列表与健康状态
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const list = await loadSessions();
      if (cancelled) return;
      const saved = typeof window !== "undefined" ? localStorage.getItem("activeSessionId") : null;
      const target = list.find((s) => s.id === saved) ?? list[0];
      if (target) {
        setActiveId(target.id);
      }
      try {
        const h = await api.health();
        if (!cancelled) setHealth(h);
      } catch {
        /* 健康检查失败不阻塞聊天 */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadSessions]);

  // 切换会话时加载历史消息
  useEffect(() => {
    if (!activeId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    setMessagesLoading(true);
    api
      .listMessages(activeId)
      .then((msgs) => {
        if (!cancelled) setMessages(msgs);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "加载消息失败");
      })
      .finally(() => {
        if (!cancelled) setMessagesLoading(false);
      });
    if (typeof window !== "undefined") localStorage.setItem("activeSessionId", activeId);
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  // 新消息后滚动到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, sending]);

  async function send(text: string) {
    if (sending) return;
    setSending(true);
    setError(null);
    setLastFailed(null);

    // 先本地插入用户消息：让界面立即响应，这叫“乐观更新”
    const temp: ChatMessage = {
      id: `temp-${Date.now()}`,
      session_id: activeId ?? "",
      role: "user",
      content: text,
      intent: null,
      sources: null,
      degraded: null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, temp]);

    try {
      const res = await api.chat(text, activeId);

      const assistant: ChatMessage = {
        id: res.message_id,
        session_id: res.session_id,
        role: "assistant",
        content: res.answer,
        intent: res.intent,
        sources: res.sources,
        degraded: res.degraded,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev.filter((m) => m.id !== temp.id), { ...temp, session_id: res.session_id }, assistant]);

      if (!activeId) setActiveId(res.session_id);

      // 会话标题/排序会变，刷新列表
      const list = await loadSessions();
      const current = list.find((s) => s.id === res.session_id);
      if (current) setActiveId((prev) => prev ?? current.id);
    } catch (e) {
      // 失败时把本地插入的消息收回，并保留输入内容供重试
      setMessages((prev) => prev.filter((m) => m.id !== temp.id));
      setLastFailed(text);
      setError(e instanceof ApiRequestError ? e.message : "发送失败，请重试");
    } finally {
      setSending(false);
    }
  }

  async function createSession() {
    try {
      const s = await api.createSession();
      setSessions((prev) => [s, ...prev]);
      setActiveId(s.id);
      setMessages([]);
      setSidebarOpen(false);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "新建会话失败");
    }
  }

  async function removeSession(id: string) {
    if (!window.confirm("删除这个会话及其全部消息？该操作不可恢复。")) return;
    try {
      await api.deleteSession(id);
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (activeId === id) setActiveId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    }
  }

  async function sendFeedback(messageId: string, rating: "helpful" | "unhelpful") {
    setFeedback((prev) => ({ ...prev, [messageId]: { state: "sending", rating } }));
    try {
      await api.feedback(messageId, rating);
      setFeedback((prev) => ({ ...prev, [messageId]: { state: "done", rating } }));
    } catch {
      setFeedback((prev) => ({ ...prev, [messageId]: { state: "error", rating } }));
    }
  }

  const llmMissing = health ? !health.llm.configured : false;
  const activeTitle = sessions.find((s) => s.id === activeId)?.title ?? "新对话";
  const empty = messages.length === 0 && !messagesLoading;

  return (
    <div className="flex h-[calc(100vh-3.5rem)] overflow-hidden sm:rounded-t-[24px]">
      <SessionSidebar
        sessions={sessions}
        activeId={activeId}
        loading={sessionsLoading}
        mobileOpen={sidebarOpen}
        onSelect={(id) => {
          setActiveId(id);
          setSidebarOpen(false);
          setError(null);
        }}
        onCreate={createSession}
        onDelete={removeSession}
        onCloseMobile={() => setSidebarOpen(false)}
      />

      <section className="flex min-w-0 flex-1 flex-col bg-white">
        {/* 移动端顶栏 */}
        <div className="flex items-center gap-3 border-b border-hairline px-4 py-3 lg:hidden">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            aria-label="打开会话列表"
            className="btn-quiet px-2"
          >
            <MenuIcon />
          </button>
          <span className="truncate text-[14px] font-medium">{activeTitle}</span>
        </div>

        {/* 后端状态提示：只在真的有问题时出现 */}
        {llmMissing && (
          <div className="flex items-start gap-2 border-b border-[#f0d9a8] bg-[#fffaf0] px-5 py-2.5 text-[12.5px] text-[#7a5b14]">
            <AlertIcon className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              后端未配置 DeepSeek 密钥，当前回答仅展示知识库原文。配置方法见「系统状态」页面。
            </span>
          </div>
        )}

        {error && (
          <div className="flex items-start justify-between gap-3 border-b border-[#f3c6c2] bg-[#fdf3f2] px-5 py-2.5 text-[12.5px] text-[#8c2f28]">
            <span className="flex items-start gap-2">
              <AlertIcon className="mt-0.5 h-4 w-4 shrink-0" />
              {error}
            </span>
            <div className="flex shrink-0 items-center gap-2">
              {lastFailed && (
                <button
                  type="button"
                  onClick={() => send(lastFailed)}
                  className="inline-flex items-center gap-1 rounded-full px-2 py-1 hover:bg-white"
                >
                  <RefreshIcon className="h-3.5 w-3.5" />
                  重试
                </button>
              )}
              <button type="button" onClick={() => setError(null)} className="px-1 hover:underline">
                关闭
              </button>
            </div>
          </div>
        )}

        <div ref={scrollRef} className="scroll-thin flex-1 overflow-y-auto px-4 py-6 sm:px-6">
          <div className="mx-auto max-w-3xl space-y-6">
            {messagesLoading && <p className="text-[13px] text-muted">正在加载历史消息…</p>}

            {empty && (
              <div className="pt-6 sm:pt-16">
                <h1 className="text-[26px] font-semibold tracking-tight sm:text-[32px]">
                  你好，需要什么帮助？
                </h1>
                <p className="mt-2 max-w-xl text-[14.5px] leading-relaxed text-muted">
                  我会先识别你的问题类型（查订单 / 退款 / 物流 / 售后），再从知识库检索相关规则后回答。
                  涉及具体订单状态时，我会明确告诉你当前能否查询，不会编造信息。
                </p>

                <div className="mt-7">
                  <p className="label mb-2">你可以这样问</p>
                  <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
                    {SUGGESTIONS.map((q) => (
                      <button
                        key={q}
                        type="button"
                        onClick={() => send(q)}
                        className="rounded-full border border-hairline px-3.5 py-2 text-left text-[13px] text-ink transition-colors hover:border-ink/30 hover:bg-mist"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {messages.map((m) => (
              <MessageItem
                key={m.id}
                message={m}
                onFeedback={sendFeedback}
                feedbackState={feedback[m.id]?.state ?? "idle"}
                feedbackRating={feedback[m.id]?.rating ?? null}
              />
            ))}

            {sending && (
              <div className="flex items-center gap-3 text-[13px] text-muted">
                <span className="flex h-6 w-6 items-center justify-center rounded-full border border-hairline">
                  <span className="flex gap-0.5">
                    <span className="dot h-1 w-1 rounded-full bg-muted" />
                    <span className="dot h-1 w-1 rounded-full bg-muted" />
                    <span className="dot h-1 w-1 rounded-full bg-muted" />
                  </span>
                </span>
                正在检索知识库并生成回答…
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        </div>

        <Composer onSend={send} disabled={sending} />
      </section>
    </div>
  );
}
