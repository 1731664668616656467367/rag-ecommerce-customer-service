/** 与后端 Pydantic 模型一一对应的类型定义。
 *  手写而不是代码生成，好处是新同学能直接读懂接口契约。 */

export type Intent = "查订单" | "退款" | "物流" | "售后" | "其他";

export interface HealthResponse {
  status: "ok" | "degraded";
  app: string;
  env: string;
  version: string;
  database: string;
  embedding: {
    provider: string;
    dim?: number;
    model?: string;
    available?: boolean;
    detail?: string;
  };
  llm: {
    provider: string;
    model: string;
    configured: boolean;
  };
  index: {
    chunks: number;
    documents: number;
    dim: number;
    backend: string;
  };
  warnings: string[];
}

export interface SessionItem {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface SourceItem {
  document_id: string;
  file_name: string;
  chunk_index: number;
  score: number;
  snippet: string;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  intent: string | null;
  sources: SourceItem[] | null;
  degraded: string | null;
  created_at: string;
}

export interface ChatResponse {
  session_id: string;
  session_title: string;
  message_id: string;
  answer: string;
  intent: Intent;
  intent_method: string;
  sources: SourceItem[];
  degraded: string | null;
  retrieval: {
    has_context: boolean;
    top_score: number;
    reason: string;
    embedding: string;
  };
}

export interface DocumentItem {
  id: string;
  file_name: string;
  file_type: string;
  size_bytes: number;
  status: "pending" | "indexed" | "failed";
  chunk_count: number;
  index_version: string;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeList {
  documents: DocumentItem[];
  index: {
    chunks: number;
    documents: number;
    dim: number;
    backend: string;
  };
}

export interface ApiError {
  detail: string;
  code?: string;
}
