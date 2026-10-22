/** 统一的 API 客户端。
 *
 *  为什么不让组件里直接 fetch？
 *  1. 错误处理只写一次，前端每个页面都能得到一致的提示；
 *  2. 后端地址只在这里配置，换环境不用满项目改；
 *  3. 以后要加 token、重试、埋点，只改这个文件。
 *
 *  注意：这里只放“公开”配置。DeepSeek 密钥永远只在后端，前端拿不到。
 */

import type {
  AnswerMode,
  AnswerModeState,
  ChatResponse,
  DocumentItem,
  HealthResponse,
  KnowledgeList,
  SessionItem,
  ChatMessage,
  WelcomeResponse,
  StatsResponse,
} from "./types";

const RAW_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000/api";
export const API_BASE = RAW_BASE.replace(/\/$/, "");

export class ApiRequestError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(init?.headers || {}),
      },
      cache: "no-store",
    });
  } catch {
    // 网络层失败：后端没启动、端口不对、被浏览器拦截
    throw new ApiRequestError(
      `无法连接后端服务（${API_BASE}）。请确认 FastAPI 已启动，并且 CORS 允许当前地址。`,
      0,
      "network_error"
    );
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }

  if (!res.ok) {
    const detail =
      (data as { detail?: string } | null)?.detail || `请求失败（HTTP ${res.status}）`;
    throw new ApiRequestError(detail, res.status, (data as { code?: string } | null)?.code);
  }

  return data as T;
}

export const api = {
  health: () => request<HealthResponse>("/health"),

  /** 工作台概览：会话/消息/文档/索引/回答类型分布，全部为真实聚合。 */
  stats: () => request<StatsResponse>("/stats"),

  /** 首屏欢迎语。这是个纯读取接口：不创建会话、不写数据库，刷新多少次都安全。 */
  welcome: () => request<WelcomeResponse>("/chat/welcome"),

  /** 当前回答模式 + 模型服务状态（不含任何密钥）。 */
  getAnswerMode: () => request<AnswerModeState>("/settings/answer-mode"),

  /** 切换回答模式。由后端校验并持久化，前端只认后端返回的结果。 */
  setAnswerMode: (mode: AnswerMode) =>
    request<AnswerModeState>("/settings/answer-mode", {
      method: "PUT",
      body: JSON.stringify({ mode }),
    }),

  /** 清除页面上的覆盖值，回到 .env 的默认模式。 */
  resetAnswerMode: () =>
    request<AnswerModeState>("/settings/answer-mode/reset", { method: "POST" }),

  listSessions: () => request<SessionItem[]>("/sessions"),
  createSession: (title?: string) =>
    request<SessionItem>("/sessions", {
      method: "POST",
      body: JSON.stringify(title ? { title } : {}),
    }),
  deleteSession: (id: string) => request<void>(`/sessions/${id}`, { method: "DELETE" }),
  listMessages: (id: string) => request<ChatMessage[]>(`/sessions/${id}/messages`),

  chat: (message: string, sessionId?: string | null) =>
    request<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId || null }),
    }),

  listKnowledge: () => request<KnowledgeList>("/knowledge"),
  uploadKnowledge: (file: File, replace = true) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentItem>(`/knowledge/upload?replace=${replace}`, {
      method: "POST",
      body: form,
    });
  },
  deleteKnowledge: (id: string) =>
    request<void>(`/knowledge/${id}`, { method: "DELETE" }),
  /** 全量重建索引。换 embedding 模型后必须调它，否则向量维度/语义对不上。 */
  reindexKnowledge: () =>
    request<{ indexed: number; failed: number; chunks: number }>("/knowledge/reindex", {
      method: "POST",
    }),

  feedback: (messageId: string, rating: "helpful" | "unhelpful") =>
    request<{ id: string }>("/feedback", {
      method: "POST",
      body: JSON.stringify({ message_id: messageId, rating }),
    }),
};
