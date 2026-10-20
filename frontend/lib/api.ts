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
  ChatResponse,
  DocumentItem,
  HealthResponse,
  KnowledgeList,
  SessionItem,
  ChatMessage,
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

  feedback: (messageId: string, rating: "helpful" | "unhelpful") =>
    request<{ id: string }>("/feedback", {
      method: "POST",
      body: JSON.stringify({ message_id: messageId, rating }),
    }),
};
