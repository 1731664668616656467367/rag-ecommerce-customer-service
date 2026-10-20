# API 接口说明

- Base URL：`http://127.0.0.1:8000/api`
- 交互式文档：`http://127.0.0.1:8000/docs`
- 所有请求/响应均为 `application/json`，上传接口除外。
- 错误统一格式：

```json
{ "detail": "会话不存在", "code": "http_404" }
```

参数校验错误（422）会额外带 `errors` 数组：

```json
{
  "detail": "message: String should have at least 1 character",
  "code": "validation_error",
  "errors": [{ "loc": ["body", "message"], "msg": "...", "type": "..." }]
}
```

## 状态码约定

| 码 | 何时使用 |
| --- | --- |
| 200 | 成功（聊天在“模型降级”时也返回 200，见下方说明） |
| 201 | 创建成功（会话、文档、反馈） |
| 204 | 删除成功，无响应体 |
| 400 | 业务参数不合法（如不支持的文件类型） |
| 404 | 会话/文档/消息不存在 |
| 409 | 同名文档且 `replace=false` |
| 413 | 文件超过大小限制 |
| 422 | 请求结构或字段校验失败 |
| 500 | 未预期异常（不暴露内部细节） |
| 503 | 外部服务不可用（仅在 LLM 不可用时由健康检查体现） |

> 聊天接口的设计取舍：模型不可用（超时/402/未配密钥）时仍返回 **200**，
> 但响应体 `degraded` 字段标明原因，`answer` 只陈列知识库原文。
> 理由：客服场景下断开会话比展示降级内容体验更差；同时降级状态是显式的，不会伪装成模型回答。

---

## GET /api/health

系统状态。前端 `/settings` 页面直接消费此接口。

```json
{
  "status": "degraded",
  "app": "电商智能客服 RAG",
  "env": "development",
  "version": "1.0.0",
  "database": "ok",
  "embedding": { "provider": "local-hashing", "dim": 4096, "available": true },
  "llm": { "provider": "deepseek", "model": "deepseek-chat", "configured": true },
  "index": { "chunks": 9, "documents": 5, "dim": 4096, "backend": "numpy" },
  "warnings": ["未连接 Ollama，当前使用本地哈希向量（检索效果弱于 bge-m3...）"]
}
```

`status` 只有在数据库可用且密钥已配置时为 `ok`；`warnings` 每条都是待处理事项。

## POST /api/chat

```json
// 请求
{ "message": "退款一般多久能到账？", "session_id": "可选，省略则新建会话" }
```

```json
// 响应
{
  "session_id": "611c133a...",
  "session_title": "退款一般多久能到账？",
  "message_id": "9f1c...",
  "answer": "退货商品经仓库验收合格后，退款将在 1 至 3 个工作日内发起……",
  "intent": "退款",
  "intent_method": "rule",
  "sources": [
    {
      "document_id": "c1a2...",
      "file_name": "01-退换货政策.md",
      "chunk_index": 0,
      "score": 0.2573,
      "snippet": "退换货政策 七天无理由退货 自签收之日起 7 个自然日内……"
    }
  ],
  "degraded": null,
  "retrieval": { "has_context": true, "top_score": 0.2573, "reason": "ok", "embedding": "local-hashing" }
}
```

`degraded` 取值：`null` / `llm_not_configured` / `llm_timeout` / `llm_unavailable` /
`llm_quota_exceeded` / `llm_auth_error`。

`intent_method` 取值：`rule`（关键词）/ `llm`（模型）/ `llm_invalid`（模型输出非法被拒）/
`fallback`（无法判断，归为“其他”）。

## 会话

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/sessions` | 会话列表，按最近活跃排序，最多 50 条 |
| POST | `/api/sessions` | 新建会话，body 可为 `{}` 或 `{"title":"..."}` |
| GET | `/api/sessions/{id}/messages` | 该会话全部消息，按时间升序 |
| DELETE | `/api/sessions/{id}` | 删除会话及其全部消息（级联） |

消息对象：

```json
{
  "id": "9f1c...",
  "session_id": "611c...",
  "role": "assistant",
  "content": "……",
  "intent": "退款",
  "sources": [ ... ],
  "degraded": null,
  "created_at": "2026-10-20T03:42:11.123456"
}
```

## 知识库

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/knowledge` | 文档列表 + 索引统计 |
| POST | `/api/knowledge/upload` | `multipart/form-data`，字段 `file`；查询参数 `replace`（默认 true） |
| DELETE | `/api/knowledge/{document_id}` | 删除文档、磁盘文件与向量片段 |
| POST | `/api/knowledge/reindex` | 全量重建索引（换 embedding 模型后必做） |

上传成功返回文档对象，`status` 为 `indexed` 时表示已进入索引：

```json
{
  "id": "8a7b...",
  "file_name": "退换货政策.md",
  "file_type": "md",
  "size_bytes": 866,
  "status": "indexed",
  "chunk_count": 2,
  "index_version": "v1",
  "error": null,
  "created_at": "...",
  "updated_at": "..."
}
```

解析失败时接口返回 4xx/5xx，但数据库中会保留 `status=failed` 与 `error` 原因，
便于在页面上定位问题（索引中不会保留残片）。

## POST /api/feedback

```json
{ "message_id": "9f1c...", "rating": "helpful", "comment": "可选" }
```

`rating` 只接受 `helpful` / `unhelpful`；`message_id` 不存在返回 404。

## curl 速查

```bash
curl http://127.0.0.1:8000/api/health

curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"同城配送几天能到"}'

curl -X POST http://127.0.0.1:8000/api/knowledge/upload \
  -F "file=@./knowledge_base/01-退换货政策.md"

curl http://127.0.0.1:8000/api/sessions
```
