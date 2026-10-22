"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Composer from "@/components/chat/Composer";
import MessageItem from "@/components/chat/MessageItem";
import ModeSwitcher from "@/components/chat/ModeSwitcher";
import SuggestionCards from "@/components/chat/SuggestionCards";
import WorkspaceSidebar from "@/components/chat/WorkspaceSidebar";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import Badge from "@/components/ui/Badge";
import {
  AlertIcon,
  CheckIcon,
  MenuIcon,
  RefreshIcon,
  ShieldIcon,
  SparklesIcon,
} from "@/components/icons";
import { api, ApiRequestError } from "@/lib/api";
import type {
  AnswerMode,
  AnswerModeState,
  ChatMessage,
  SessionItem,
  WelcomeResponse,
} from "@/lib/types";

type FeedbackState = {
  state: "idle" | "sending" | "done" | "error";
  rating: "helpful" | "unhelpful" | null;
};

export default function ChatPage() {
  // ---- 会话与消息 ----
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [messagesLoading, setMessagesLoading] = useState(false);

  // ---- 发送 ----
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastFailed, setLastFailed] = useState<string | null>(null);

  // ---- 回答模式（全局，来自后端） ----
  const [mode, setMode] = useState<AnswerModeState | null>(null);
  const [modeLoading, setModeLoading] = useState(true);
  const [modeSwitching, setModeSwitching] = useState(false);
  const [modeError, setModeError] = useState<string | null>(null);

  // ---- 其它 UI ----
  const [welcome, setWelcome] = useState<WelcomeResponse | null>(null);
  const [welcomeLoading, setWelcomeLoading] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<SessionItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [feedback, setFeedback] = useState<Record<string, FeedbackState>>({});
  const [toast, setToast] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  // setSending 是异步的，连点两下时第二下读到的还是旧值 → 会真的发两条。ref 立刻生效。
  const sendingRef = useRef(false);
  // 首屏的 ?q= 只允许自动提交一次
  const autoSentRef = useRef(false);

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

  const loadMode = useCallback(async () => {
    try {
      setMode(await api.getAnswerMode());
    } catch {
      /* 模式读不到时不阻塞聊天，界面按默认值展示并禁用切换 */
    } finally {
      setModeLoading(false);
    }
  }, []);

  // 首屏：会话 + 模式 + 欢迎语
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const list = await loadSessions();
      if (cancelled) return;
      // 只有"上次就是你正在看的这个会话"才恢复。
      // 不自动打开最近的会话：那会让欢迎区与快捷问题永远看不到，
      // 回访用户也没法一眼知道这个工作台能做什么。历史会话在左侧一点即开。
      // 用 window.location 而不是 useSearchParams：后者要求整棵子树包 Suspense，
      // 对一个纯客户端页面来说代价大于收益。
      const params = new URLSearchParams(window.location.search);
      const wantSession = params.get("session");
      const wantQuery = params.get("q");

      const saved = localStorage.getItem("activeSessionId");
      const byParam = wantSession ? list.find((s) => s.id === wantSession) : undefined;
      const target = byParam ?? (saved ? list.find((s) => s.id === saved) : undefined);
      if (target) setActiveId(target.id);

      // 从工作台的"常见问题"进来：用一次真实请求把它发出去，
      // 然后清掉地址栏参数，避免刷新时重复提问。
      if (wantQuery && !autoSentRef.current) {
        autoSentRef.current = true;
        window.history.replaceState(null, "", "/chat");
        void send(wantQuery, byParam?.id ?? null);
      }
    })();

    loadMode();

    api
      .welcome()
      .then((w) => !cancelled && setWelcome(w))
      .catch(() => undefined)
      .finally(() => !cancelled && setWelcomeLoading(false));

    const savedCollapsed = localStorage.getItem("sidebarCollapsed");
    if (savedCollapsed === "1") setCollapsed(true);

    return () => {
      cancelled = true;
    };
  }, [loadSessions, loadMode]);

  // 切换会话时加载历史
  useEffect(() => {
    if (!activeId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    setMessagesLoading(true);
    api
      .listMessages(activeId)
      .then((msgs) => !cancelled && setMessages(msgs))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : "加载消息失败"))
      .finally(() => !cancelled && setMessagesLoading(false));
    localStorage.setItem("activeSessionId", activeId);
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, sending]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 2600);
    return () => window.clearTimeout(timer);
  }, [toast]);

  function toggleCollapse() {
    setCollapsed((prev) => {
      localStorage.setItem("sidebarCollapsed", prev ? "0" : "1");
      return !prev;
    });
  }

  /** 发送一条消息。
   *  sessionIdOverride 用于"从工作台带参数跳进来"的场景：
   *  此时 activeId 还没在 state 里生效，直接读会拿到 null 而多建一个会话。 */
  async function send(text: string, sessionIdOverride?: string | null) {
    const trimmed = text.trim();
    if (!trimmed || sendingRef.current) return;
    const sid = sessionIdOverride !== undefined ? sessionIdOverride : activeId;
    sendingRef.current = true;
    setSending(true);
    setError(null);
    setLastFailed(null);

    const temp: ChatMessage = {
      id: `temp-${Date.now()}`,
      session_id: sid ?? "",
      role: "user",
      content: trimmed,
      intent: null,
      sources: null,
      degraded: null,
      answer_mode: null,
      reply_type: null,
      suggestions: null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, temp]);

    try {
      const res = await api.chat(trimmed, sid);

      const assistant: ChatMessage = {
        id: res.message_id,
        session_id: res.session_id,
        role: "assistant",
        content: res.reply,
        intent: res.intent,
        sources: res.sources,
        degraded: res.degraded,
        answer_mode: res.answer_mode,
        reply_type: res.reply_type,
        suggestions: res.suggestions,
        created_at: new Date().toISOString(),
      };

      setMessages((prev) => [
        ...prev.filter((m) => m.id !== temp.id),
        { ...temp, session_id: res.session_id },
        assistant,
      ]);

      if (!sid) setActiveId(res.session_id);
      else localStorage.setItem("activeSessionId", res.session_id);

      // 模型失败时把真实原因顶到界面上（402 / 未配置都在这条横幅里）
      if (res.degraded) {
        setToast("模型未能生成回答，已退回知识库原文");
      }

      await loadSessions();
      // 模式状态可能因这次调用而改变（成功/失败的记录），刷新一次
      void loadMode();
    } catch (e) {
      setMessages((prev) => prev.filter((m) => m.id !== temp.id));
      setLastFailed(trimmed);
      setError(
        e instanceof ApiRequestError
          ? e.status === 0
            ? "无法连接后端服务，请确认 FastAPI 已启动。"
            : e.message
          : "发送失败，请重试"
      );
    } finally {
      sendingRef.current = false;
      setSending(false);
    }
  }

  /** 切换模式：只认后端返回的结果。失败就回读真实状态，绝不停在"假已切换"。 */
  async function changeMode(next: AnswerMode) {
    if (modeSwitching || !mode || mode.mode === next) return;
    setModeSwitching(true);
    setModeError(null);
    try {
      const updated = await api.setAnswerMode(next);
      setMode(updated);
      setToast(
        updated.mode === "llm"
          ? updated.model.will_be_called
            ? "已切换到 大语言模型模式"
            : "已切换到 大语言模型模式（模型尚不可用，回答将降级）"
          : "已切换到 知识库模式"
      );
    } catch (e) {
      setModeError(e instanceof Error ? e.message : "切换失败");
      try {
        setMode(await api.getAnswerMode());
      } catch {
        /* 读不到就保持旧状态，错误提示已经给出 */
      }
    } finally {
      setModeSwitching(false);
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

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.deleteSession(deleteTarget.id);
      setSessions((prev) => prev.filter((s) => s.id !== deleteTarget.id));
      if (activeId === deleteTarget.id) setActiveId(null);
      setToast("会话已删除");
      setDeleteTarget(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    } finally {
      setDeleting(false);
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

  function pickSuggestion(query: string) {
    void send(query);
  }

  const modeIsLlm = mode?.mode === "llm";
  const modelUsable = Boolean(mode?.model.will_be_called);
  const modeHint = modeIsLlm ? "知识库检索 + 大语言模型" : "基于知识库回答";
  const activeTitle = sessions.find((s) => s.id === activeId)?.title ?? "新对话";
  const empty = messages.length === 0 && !messagesLoading;
  const lastAssistantId = [...messages].reverse().find((m) => m.role === "assistant")?.id;
  const lastUserText = [...messages].reverse().find((m) => m.role === "user")?.content;

  return (
    <div className="flex h-full min-h-0 overflow-hidden">
      <WorkspaceSidebar
        sessions={sessions}
        activeId={activeId}
        loading={sessionsLoading}
        mobileOpen={sidebarOpen}
        collapsed={collapsed}
        modeLabel={mode?.label ?? "知识库模式"}
        modeUsable={modeIsLlm ? modelUsable : true}
        modelHint={
          modeIsLlm
            ? modelUsable
              ? "大模型已就绪，全局生效"
              : "模型不可用，将降级"
            : "不调用外部大模型"
        }
        onSelect={(id) => {
          setActiveId(id);
          setSidebarOpen(false);
          setError(null);
        }}
        onCreate={createSession}
        onDelete={(id) => {
          const target = sessions.find((s) => s.id === id) ?? null;
          setDeleteTarget(target);
        }}
        onToggleCollapse={toggleCollapse}
        onCloseMobile={() => setSidebarOpen(false)}
      />

      <section className="flex min-w-0 flex-1 flex-col">
        {/* 顶栏：会话名 + 模式切换 */}
        {/* z-30 不能省：backdrop-blur 会让顶栏自成一个层叠上下文，
            不加层级的话模式下拉菜单会被后面的消息区盖住。 */}
        <header className="relative z-30 flex h-[60px] shrink-0 items-center gap-2 border-b border-hairline bg-paper/90 px-3 backdrop-blur sm:px-5">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            aria-label="打开导航"
            className="btn-quiet btn-icon lg:hidden"
          >
            <MenuIcon className="h-4 w-4" />
          </button>

          <div className="min-w-0 flex-1">
            <h1 className="truncate text-[14px] font-semibold tracking-tight text-ink">
              {activeTitle}
            </h1>
            <p className="hidden truncate text-[11.5px] text-muted sm:block">
              {modeIsLlm ? "知识库检索 + 大语言模型组织回答" : "仅使用本地规则与知识库检索"}
            </p>
          </div>

          <ModeSwitcher
            state={mode}
            loading={modeLoading}
            switching={modeSwitching}
            error={modeError}
            onChange={changeMode}
          />
        </header>

        {/* 模式不可用提示：不谎称"一切正常" */}
        {modeIsLlm && mode?.model.status === "not_configured" && (
          <div className="flex items-start gap-2 border-b border-[#EADFAF] bg-warning-soft px-4 py-2 text-[12.5px] leading-relaxed text-warning sm:px-5">
            <AlertIcon className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              当前尚未配置可用的大语言模型服务，请先在后端配置模型接口。在此之前，回答会自动退回知识库原文。
            </span>
          </div>
        )}
        {modeIsLlm && mode?.model.status === "error" && (
          <div className="flex items-start gap-2 border-b border-[#EFD6D2] bg-danger-soft px-4 py-2 text-[12.5px] leading-relaxed text-danger sm:px-5">
            <AlertIcon className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              模型服务当前不可用，可能是账户余额不足或服务限制，请检查模型账户状态。
              <span className="ml-1 opacity-80">（{mode.model.status_text}）</span>
            </span>
          </div>
        )}
        {modeIsLlm && mode?.model.status === "unverified" && (
          <div className="flex items-start gap-2 border-b border-hairline bg-mist/60 px-4 py-2 text-[12.5px] leading-relaxed text-muted sm:px-5">
            <SparklesIcon className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
            <span>
              已切换到大语言模型模式。密钥已配置，但还没有成功调用记录，
              本次回答是否由模型生成取决于真实调用结果；若调用失败会自动退回知识库原文。
            </span>
          </div>
        )}

        {error && (
          <div className="flex items-start justify-between gap-3 border-b border-[#EFD6D2] bg-danger-soft px-4 py-2 text-[12.5px] text-danger sm:px-5">
            <span className="flex items-start gap-2">
              <AlertIcon className="mt-0.5 h-4 w-4 shrink-0" />
              {error}
            </span>
            <div className="flex shrink-0 items-center gap-1">
              {lastFailed && (
                <button type="button" onClick={() => send(lastFailed)} className="btn-quiet btn-sm gap-1">
                  <RefreshIcon className="h-3.5 w-3.5" />
                  重试
                </button>
              )}
              <button type="button" onClick={() => setError(null)} className="btn-quiet btn-sm">
                关闭
              </button>
            </div>
          </div>
        )}

        {/* 消息区：独立滚动，输入框永远可见 */}
        <div className="scroll-thin flex-1 overflow-y-auto px-3 py-5 sm:px-5">
          <div className="mx-auto max-w-3xl space-y-5">
            {messagesLoading && <p className="text-[12.5px] text-muted">正在加载历史消息…</p>}

            {empty && (
              <div className="pt-2 sm:pt-8">
                <Badge
                  tone="blue"
                  icon={
                    modeIsLlm ? (
                      <SparklesIcon className="h-3 w-3" />
                    ) : (
                      <ShieldIcon className="h-3 w-3" />
                    )
                  }
                >
                  {mode?.label ?? "知识库模式"}
                </Badge>

                <h2 className="mt-3 max-w-2xl text-[26px] font-semibold leading-[1.15] tracking-[-0.02em] text-ink sm:text-[34px]">
                  您好，今天有什么可以帮您？
                </h2>

                {welcome ? (
                  <p className="mt-2.5 max-w-xl text-[13.5px] leading-relaxed text-muted">
                    我可以根据知识库中的信息，帮助您了解物流配送、退款政策、退换货和售后服务。
                  </p>
                ) : welcomeLoading ? (
                  <div className="mt-3 max-w-xl space-y-2" aria-hidden="true">
                    <div className="skeleton h-3 w-full rounded" />
                    <div className="skeleton h-3 w-4/5 rounded" />
                  </div>
                ) : (
                  <p className="mt-2.5 max-w-xl text-[13.5px] leading-relaxed text-danger">
                    暂时无法获取欢迎语，请检查后端服务是否正常。
                  </p>
                )}

                {welcome && welcome.suggestions.length > 0 && (
                  <div className="mt-7">
                    <p className="mb-2.5 text-[11.5px] font-medium uppercase tracking-[0.06em] text-muted">
                      常见问题
                    </p>
                    <SuggestionCards
                      suggestions={welcome.suggestions}
                      onPick={pickSuggestion}
                      disabled={sending}
                    />
                  </div>
                )}

                <p className="mt-5 flex items-start gap-1.5 text-[11.5px] leading-relaxed text-muted">
                  <CheckIcon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" />
                  订单查询与人工客服尚未接入真实系统，相关回答只会说明能力边界，不会编造状态。
                </p>
              </div>
            )}

            {messages.map((m) => (
              <MessageItem
                key={m.id}
                message={m}
                isLast={m.id === lastAssistantId}
                onFeedback={sendFeedback}
                feedbackState={feedback[m.id]?.state ?? "idle"}
                feedbackRating={feedback[m.id]?.rating ?? null}
                onPickSuggestion={pickSuggestion}
                suggestionsDisabled={sending}
                onRetry={
                  m.id === lastAssistantId && lastUserText
                    ? () => void send(lastUserText)
                    : undefined
                }
              />
            ))}

            {sending && (
              <div className="flex items-center gap-2.5 text-[12.5px] text-muted">
                <span className="flex h-7 w-7 items-center justify-center rounded-full border border-hairline bg-surface">
                  <span className="flex gap-0.5">
                    <span className="dot h-1 w-1 rounded-full bg-muted" />
                    <span className="dot h-1 w-1 rounded-full bg-muted" />
                    <span className="dot h-1 w-1 rounded-full bg-muted" />
                  </span>
                </span>
                正在处理你的问题…
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        </div>

        <Composer onSend={(t) => void send(t)} disabled={sending} modeHint={modeHint} />
      </section>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="删除这个会话？"
        description={
          <>
            将删除<strong className="font-medium text-ink">「{deleteTarget?.title}」</strong>
            及其全部消息与反馈记录，该操作不可恢复。
          </>
        }
        confirmText="删除会话"
        busy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />

      {toast && (
        <div className="pointer-events-none fixed bottom-24 left-1/2 z-50 -translate-x-1/2 animate-fade">
          <div className="flex items-center gap-2 rounded-full border border-hairline bg-ink px-3.5 py-2 text-[12.5px] text-white shadow-pop">
            <CheckIcon className="h-3.5 w-3.5" />
            {toast}
          </div>
        </div>
      )}
    </div>
  );
}
