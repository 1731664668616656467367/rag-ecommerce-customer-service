/** 与后端 Pydantic 模型一一对应的类型定义。
 *  手写而不是代码生成，好处是新同学能直接读懂接口契约。 */

export type Intent = "查订单" | "退款" | "物流" | "售后" | "其他";

/** 回答模式。与后端 runtime_mode.VALID_MODES 一一对应。 */
export type AnswerMode = "knowledge_only" | "llm";

export interface ModeOption {
  value: AnswerMode;
  label: string;
  description: string;
}

/** 模型状态只有四种，且都能被证据支撑：
 *  not_configured 没密钥 / unverified 配了没调用过 / ok 调用成功过 / error 上次失败。 */
export type ModelStatus = "not_configured" | "unverified" | "ok" | "error";

export interface ModelServiceStatus {
  provider: string;
  model: string;
  configured: boolean;
  status: ModelStatus;
  status_text: string;
  will_be_called: boolean;
  last_failure: { code: string; text: string; at: string } | null;
  last_success_at: string | null;
}

/** GET /api/settings/answer-mode 的响应。 */
export interface AnswerModeState {
  mode: AnswerMode;
  label: string;
  scope: "global";
  scope_note: string;
  default_mode: AnswerMode;
  overridden: boolean;
  updated_at: string | null;
  options: ModeOption[];
  valid_values: string[];
  model: ModelServiceStatus;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  app: string;
  env: string;
  version: string;
  answer_mode: AnswerMode;
  database: string;
  embedding: {
    provider: string;
    dim?: number;
    model?: string | null;
    available?: boolean;
    detail?: string;
    /** local-hashing 不是语义模型：页面必须写清楚，不能和 bge-m3 混为一谈 */
    is_semantic?: boolean;
    /** .env 里要求用哪个实现（auto / ollama / local） */
    configured_provider?: string;
    /** 本进程实际使用的实现 */
    active_provider?: string;
    /** 降级原因（连不上 / 没 pull 模型 / 模型列表为空），有值即说明不是理想状态 */
    fallback_reason?: string | null;
    is_fallback?: boolean;
    service_reachable?: boolean;
    model_installed?: boolean;
    installed_models?: string[];
    base_url?: string;
    /** 进程用降级实现建过索引，即使 Ollama 现在可用也要重启才会切换 */
    restart_required?: boolean;
    /** 实时探测结果：与进程启动时的探测结果可能不同 */
    ollama_now_reachable?: boolean;
    ollama_model_now_ready?: boolean;
    index_dim_note?: string | null;
  };
  retrieval: {
    mode: string;
    channels: string[];
    vector_backend: string;
    embedding_signature: string;
    index_signature: string;
    needs_reindex: boolean;
    /** 以下来自后端真实配置，设置页直接展示，不在前端写死默认值 */
    top_k?: number;
    min_score?: number;
    min_coverage?: number;
    chunk_size?: number;
    chunk_overlap?: number;
    embedding_provider?: string;
    embedding_model?: string | null;
  };
  llm: {
    provider: string;
    model: string;
    mode: AnswerMode;
    source: "env" | "runtime";
    enabled: boolean;
    configured: boolean;
    will_be_called: boolean;
    note: string;
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

/** 回复类别，与后端 ReplyType 一一对应。
 *
 *  为什么要这么细？
 *  因为“来源标签”必须说实话：只有 knowledge 才真的引用了知识库原文，
 *  问候语和闲聊不是。共用一个标签会让用户误以为问候语也是从文档里摘的。 */
export type ReplyType =
  | "greeting"
  | "identity"
  | "thanks"
  | "farewell"
  | "human_service"
  | "knowledge"
  | "no_answer"
  | "fallback"
  | "unclear";

/** 快捷问题。query 才是点击后真正发给 /api/chat 的内容，label 只是按钮上的短标题。 */
export interface SuggestionItem {
  label: string;
  query: string;
  description?: string | null;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  intent: string | null;
  sources: SourceItem[] | null;
  degraded: string | null;
  answer_mode: string | null;
  reply_type: ReplyType | null;
  suggestions: SuggestionItem[] | null;
  created_at: string;
}

/** GET /api/chat/welcome 的响应：首屏欢迎语，不建会话、不写库。 */
export interface WelcomeResponse {
  reply: string;
  reply_type: ReplyType;
  suggestions: SuggestionItem[];
}

export interface ChatResponse {
  session_id: string;
  session_title: string;
  message_id: string;
  /** reply 是主字段，answer 与它内容相同，保留是为了兼容旧调用方 */
  reply: string;
  answer: string;
  reply_type: ReplyType;
  suggestions: SuggestionItem[];
  answer_mode: "knowledge_only" | "llm";
  answer_kind: string;
  intent: Intent;
  intent_method: string;
  sources: SourceItem[];
  degraded: string | null;
  retrieval: {
    has_context: boolean;
    top_score: number;
    reason: string;
    embedding: string;
    methods: string[];
    threshold: number;
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

/** 上传限制，来自后端配置，不在前端写死。 */
export interface UploadPolicy {
  max_mb: number;
  extensions: string[];
  accepts: string;
}

export interface KnowledgeList {
  documents: DocumentItem[];
  index: {
    chunks: number;
    documents: number;
    dim: number;
    backend: string;
  };
  upload: UploadPolicy;
}

export interface ApiError {
  detail: string;
  code?: string;
}

/** GET /api/stats 的响应：全部来自数据库聚合与索引统计，没有编造指标。 */
export interface StatsResponse {
  sessions_total: number;
  sessions_today: number;
  messages_total: number;
  messages_today: number;
  assistant_total: number;
  docs_total: number;
  docs_indexed: number;
  chunks: number;
  dim: number;
  index_backend: string;
  answer_mix: Record<string, number>;
  /** 有分母才给值；没有任何回答时为 null（前端显示"—"） */
  knowledge_ratio: number | null;
  degraded_total: number;
  feedback_helpful: number;
  feedback_unhelpful: number;
  answer_mode: AnswerMode;
  mode_label: string;
  generated_at: string;
}
