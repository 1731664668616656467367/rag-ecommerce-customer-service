# 系统架构说明

## 1. 全景图

```
┌──────────────────────────────────────────────────────────────┐
│  浏览器（Next.js / React / TypeScript / Tailwind）            │
│  /chat        /knowledge        /settings                    │
│  只做展示与交互，不含任何密钥                                  │
└───────────────┬──────────────────────────────────────────────┘
                │ HTTP + JSON（CORS 白名单）
┌───────────────▼──────────────────────────────────────────────┐
│  FastAPI（backend/app）                                       │
│  ┌─────────────── API 层 ───────────────┐                     │
│  │ routes/  health chat sessions         │                    │
│  │          knowledge feedback           │                    │
│  │ 职责：参数校验、状态码、统一错误响应    │                    │
│  └───────────────┬──────────────────────┘                     │
│  ┌───────────────▼──── 业务服务层 ──────┐                     │
│  │ chat_service       编排一次问答        │                    │
│  │ session_service    会话/消息/反馈      │                    │
│  │ knowledge_service  上传/索引/删除      │                    │
│  └──────┬─────────────────┬─────────────┘                     │
│  ┌──────▼──────┐   ┌──────▼──────────┐  ┌──────────────────┐  │
│  │ RAG 层       │   │ 模型客户端层     │  │ 意图识别          │  │
│  │ chunker      │   │ DeepSeekClient  │  │ 规则 + LLM +     │  │
│  │ embeddings   │   │ 超时/重试/错误   │  │ 白名单校验        │  │
│  │ retriever    │   │ 分类             │  │                  │  │
│  │ vector_store │   └────────┬────────┘  └──────────────────┘  │
│  │ prompt       │            │                                 │
│  └──────┬───────┘            │                                 │
│  ┌──────▼────────────────────▼──────────────────────────────┐  │
│  │ 数据层：SQLAlchemy + SQLite（backend/data/app.db）        │  │
│  │ sessions / messages / knowledge_documents / feedback      │  │
│  └──────────────────────────────────────────────────────────┘  │
│  向量索引：numpy 矩阵 + meta.json（backend/data/index/）        │
└──────────────────────────────────────────────────────────────┘
                │
        ┌───────┴────────┐
        │ DeepSeek API   │   可选：Ollama（bge-m3 embedding）
        └────────────────┘
```

**关键边界**：业务数据库（SQLite）与向量索引（`data/index/`）是**两套独立存储**，
只通过 `document_id` 关联。删文档时先清向量、再删文件、最后删库记录。

## 2. 一次问答的完整链路

```
POST /api/chat {message, session_id?}
  → 1. Pydantic 校验（长度、非空）          失败 → 422
  → 2. 取会话 / 新建会话                    不存在 → 404
  → 3. 先保存用户消息（失败也不丢输入）
  → 4. 意图识别
       规则关键词命中 ≥2 → 直接用
       否则问 LLM（要求 JSON）→ 解析 → 白名单校验
       非法值 → 丢弃，退回规则 / 其他
  → 5. 检索
       query → embedding → 向量索引 top-K
       → 阈值过滤 + 词面覆盖度门槛 + 相邻片段去重
  → 6. 组装提示词：system 规则 + 最近 N 轮历史 + 资料片段 + 问题
  → 7. 调用 DeepSeek
       成功 → 回答
       402/超时/不可用 → 降级：只陈列检索原文，标记 degraded
  → 8. 保存助手消息（含 intent、sources、degraded）
  → 9. 返回 {answer, intent, sources, degraded, retrieval}
```

## 3. 数据模型

```
sessions 1 ──── n messages 1 ──── n feedback
                    │
                    └── sources (JSON 列，存片段来源快照)

knowledge_documents ──(document_id)──> 向量索引中的片段
```

| 表 | 关键字段 | 说明 |
| --- | --- | --- |
| sessions | id, title, created_at, updated_at, user_id(预留) | 会话，标题取首条问题前 24 字 |
| messages | id, session_id(FK), role, content, intent, sources, degraded, created_at | 消息，删会话级联删除 |
| knowledge_documents | id, file_name, stored_name, file_type, size_bytes, status, chunk_count, index_version, error | 文档元数据 + 处理状态 |
| feedback | id, message_id(FK), rating, comment | 有帮助 / 没帮助 |

为什么 `sources` 存在消息里：刷新历史时不需要重新检索就能还原“当时依据了什么”，
也方便事后排查“为什么答错了”。

## 4. RAG 管线

| 阶段 | 实现 | 文件 |
| --- | --- | --- |
| 读取 | txt/md/pdf/docx 统一转纯文本 | `rag/loaders.py` |
| 清洗 | 去控制字符、压缩空白、保留段落 | `rag/chunker.py::clean_text` |
| 分块 | 按句边界聚合，块间 60 字重叠 | `rag/chunker.py::chunk_text` |
| 向量化 | Ollama bge-m3 优先，失败降级本地哈希 | `rag/embeddings.py` |
| 索引 | `.npy` 矩阵 + `meta.json`，可选 faiss 加速 | `rag/vector_store.py` |
| 检索 | 余弦 top-K + 阈值 + 覆盖度门槛 | `rag/retriever.py` |
| 组提示词 | 强制“只依据资料”“不足就承认” | `rag/prompt.py` |

### 为什么阈值要按模型区分

余弦相似度的绝对值取决于模型本身：

| 模型 | 相关片段得分 | 无关片段得分 | 采用阈值 |
| --- | --- | --- | --- |
| bge-m3（Ollama） | 0.5 ~ 0.8 | < 0.3 | 0.35 |
| 本地哈希（降级） | 0.26 ~ 0.47（组合分） | ≤ 0.11 | 0.15 |

同一个阈值用两套模型，必然一套全过滤、一套全放行。所以 `AUTO_MIN_SCORE`
按 provider 分别校准，`.env` 里的 `RETRIEVAL_MIN_SCORE` 可以强制覆盖。

### 本地降级模式的额外门槛

纯词面向量对“语义相近但用词不同”的问题无能为力（问“东西是坏的”，文档写“质量问题”）。
为了减少误命中，加了**词面覆盖度**：问题切成字符二元组，计算有多少比例真的出现在片段里，
低于 12% 直接丢弃。实测“火星探测器什么时候发射”覆盖度为 0，政策类问题在 0.2~0.7。

这不是语义检索，README 与 `/api/health` 都会如实标注降级状态。

## 5. 技术选择与理由

| 选择 | 理由 | 替代方案为何暂不采用 |
| --- | --- | --- |
| FastAPI | 类型校验 + 自动 OpenAPI 文档 + 异步 | Flask 需自己拼校验与文档 |
| SQLAlchemy 2.0 | 参数化查询防注入、模型可迁移到 PG | 裸 SQL 易注入、难迁移 |
| SQLite | 零运维、单文件、便于本地复现 | PostgreSQL 增加本地启动成本 |
| numpy 向量检索 | 千级片段下精确且零依赖 | FAISS 已预留接口（装了自动启用） |
| Next.js App Router | 前端路由/构建一体化，类型友好 | 纯 React 需自建路由与构建 |
| 无状态 JWT 未实现 | 当前无多用户需求，不做假权限 | 假登录比没有登录更危险 |

## 6. 可扩展点（已预留位置）

- **鉴权**：`sessions.user_id` 已留字段；在 `api/routes/*` 加依赖注入即可做数据隔离。
- **真实业务系统**：在 `customer_service/` 新增 `order_provider` 接口，替换
  `BUSINESS_DATA_NOTICE` 的静态提示；当前绝不伪造订单/物流数据。
- **换向量库**：`VectorIndex` 是唯一入口，替换为 pgvector/Milvus 不影响上层。
- **流式回答**：`chat_service.handle_chat` 改为异步生成器 + SSE 即可。
