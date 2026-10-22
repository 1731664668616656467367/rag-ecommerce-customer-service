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
>
> 纯知识库模式（`ANSWER_MODE=knowledge_only`，默认）下不存在降级概念：
> 回答要么来自知识库原文，要么是“没找到”的固定提示，`degraded` 恒为 `null`。

---

## GET /api/health

系统状态。前端 `/settings` 与 `/chat` 的模式条都直接消费此接口。

```json
{
  "status": "ok",
  "app": "电商智能客服 RAG",
  "env": "development",
  "version": "1.0.0",
  "answer_mode": "knowledge_only",
  "database": "ok",
  "embedding": {
    "provider": "ollama",
    "model": "bge-m3",
    "base_url": "http://localhost:11434",
    "dim": 1024,
    "available": true,
    "is_semantic": true,
    "service_reachable": true,
    "model_installed": true,
    "installed_models": ["bge-m3:latest"],
    "detail": "Ollama 可访问，模型 bge-m3 已安装",
    "configured_provider": "ollama",
    "active_provider": "ollama",
    "fallback_reason": null,
    "is_fallback": false,
    "index_dim_note": null
  },
  "retrieval": {
    "mode": "hybrid",
    "channels": ["vector", "bm25"],
    "vector_backend": "numpy",
    "embedding_signature": "ollama:bge-m3",
    "index_signature": "ollama:bge-m3",
    "needs_reindex": false,
    "top_k": 4,
    "min_score": 0.0,
    "min_coverage": 0.12,
    "chunk_size": 320,
    "chunk_overlap": 60,
    "embedding_provider": "ollama",
    "embedding_model": "bge-m3"
  },
  "llm": {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "mode": "knowledge_only",
    "source": "env",
    "enabled": false,
    "configured": true,
    "will_be_called": false,
    "note": "知识库模式：不调用任何外部模型"
  },
  "index": { "chunks": 9, "documents": 5, "dim": 1024, "backend": "numpy",
             "signature": "ollama:bge-m3", "version": 0 },
  "warnings": []
}
```

Ollama 不可用时的降级形态（`provider` 变成 `local-hashing`、`dim` 变成 4096、
`is_fallback=true`、`warnings` 会带上具体原因）：

```json
"embedding": {
  "provider": "local-hashing", "model": null, "base_url": null,
  "dim": 4096, "available": true, "is_semantic": false,
  "configured_provider": "ollama", "active_provider": "local-hashing",
  "fallback_reason": "端口 11434 未监听（Ollama 未启动）",
  "is_fallback": true, "service_reachable": false, "model_installed": false,
  "installed_models": [],
  "index_dim_note": "索引当前为 4096 维（本地哈希）。换成 bge-m3 后需重建索引（1024 维）"
}
```

| 字段 | 含义 |
| --- | --- |
| `answer_mode` | 当前**生效**的回答模式，`knowledge_only` 或 `llm`（含页面上的覆盖值） |
| `llm.source` | 模式值来自哪：`env` = `.env` 默认，`runtime` = 页面切换后的运行期覆盖 |
| `llm.enabled` | 是否**允许**调用模型（只看生效模式，不看有没有 Key） |
| `llm.configured` | 环境里是否**存在** Key（存在≠会被用） |
| `llm.will_be_called` | 下一次对话是否可能发出模型请求；知识库模式恒为 `false` |
| `retrieval.channels` | 实际启用的检索通道，`hybrid` → `["vector","bm25"]` |
| `retrieval.top_k` / `min_score` / `min_coverage` | 检索真实参数，设置页直接展示，避免前端写死默认值 |
| `retrieval.needs_reindex` | 索引指纹与当前 embedding 模型不一致时为 `true` |
| `embedding.configured_provider` | `.env` 里**要求**的 provider（`auto` / `ollama` / `local`） |
| `embedding.active_provider` | 本进程**实际生效**的实现。和上一条不同即为降级 |
| `embedding.is_semantic` | 是否真正的语义模型（哈希向量为 `false`） |
| `embedding.dim` | 模型**真实输出**维度：bge-m3 = 1024，本地哈希 = `EMBEDDING_DIM`(4096) |
| `embedding.is_fallback` | `configured_provider` 要求语义但实际用了哈希时为 `true` |
| `embedding.fallback_reason` | 降级的具体原因（连不上 / 模型列表为空 / 目标模型没 pull） |
| `embedding.service_reachable` | **实时**探测 11434 端口（裸 TCP，绕过 HTTP 代理），不代表本进程已切过去 |
| `embedding.model_installed` | `/api/tags` 里是否有目标模型 |
| `embedding.restart_required` | 服务现在可达但本进程仍用降级实现 → 需要重启后端重新探测 |
| `embedding.index_dim_note` | 索引维度与当前模型维度对不上时的提示文案 |
| `status` | 数据库可用即 `ok`；**知识库模式不算降级** |

## 回答模式：GET / PUT /api/settings/answer-mode

模式切换的**唯一真源在后端**。前端只负责发请求与展示后端返回的结果，
不做乐观更新；切换失败时会回读真实状态，界面不会停在“假已切换”。

### GET /api/settings/answer-mode

```json
{
  "mode": "knowledge_only",
  "label": "知识库模式",
  "scope": "global",
  "scope_note": "影响所有会话与所有访问者，重启后从数据库恢复",
  "default_mode": "knowledge_only",
  "overridden": false,
  "updated_at": null,
  "options": [
    { "value": "knowledge_only", "label": "知识库模式", "description": "只用知识库原文回答，不调用任何外部大模型" },
    { "value": "llm", "label": "大语言模型模式", "description": "先检索知识库，再由大模型组织语言；模型不可用时自动降级" }
  ],
  "valid_values": ["knowledge_only", "llm"],
  "model": {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "configured": false,
    "status": "not_configured",
    "status_text": "尚未配置模型密钥",
    "will_be_called": false,
    "last_failure": null,
    "last_success_at": null
  }
}
```

**响应中永远不含任何 API Key**，只有 `configured: true/false`。

`model.status` 只有四种，且每一种都有证据支撑：

| 状态 | 含义 |
| --- | --- |
| `not_configured` | 后端没有配置密钥 |
| `unverified` | 配了密钥，但本进程还没真正调用过 |
| `ok` | 最近一次真实调用成功 |
| `error` | 最近一次真实调用失败，`last_failure` 给出原因（如 402 余额不足） |

> 不用启动时的试探性请求判断可用性：既费钱，也证明不了下一次可用。

### PUT /api/settings/answer-mode

```json
{ "mode": "llm" }
```

成功返回与 GET 相同的结构。非法值返回 `422`，消息里列出 `valid_values`。
写入顺序是**先落库、再改内存**，所以进程重启后仍能恢复用户的选择。

### POST /api/settings/answer-mode/reset

清除页面覆盖值，回到 `.env` 的 `ANSWER_MODE`。

## GET /api/chat/welcome

首屏欢迎语与快捷问题。**只读接口**：不创建会话、不写数据库，刷新多少次都安全。

```json
{
  "reply": "您好！欢迎使用智能客服助手。我可以帮您了解物流配送、退款政策、退换货和售后服务等信息。您可以直接输入问题，也可以点击下方的快捷问题开始咨询。",
  "reply_type": "greeting",
  "suggestions": [
    { "label": "物流配送", "query": "同城配送一般几天能到？", "description": "发货时间与配送时效" },
    { "label": "退款政策", "query": "退款政策", "description": "退款条件与到账时间" },
    { "label": "退换货", "query": "退换货政策是怎样的？", "description": "七天无理由与质量问题" },
    { "label": "售后服务", "query": "如何申请售后服务？", "description": "保修与维修流程" },
    { "label": "订单查询", "query": "我想查询订单", "description": "订单状态与地址修改" },
    { "label": "联系人工客服", "query": "我想联系人工客服", "description": "本服务未接入在线人工客服" }
  ]
}
```

为什么把文案放在后端而不是写死在前端：
快捷问题的 `query` 必须和真实能力对齐（哪些能查到资料、哪些只能给能力说明）。
只有一份定义，才不会出现"按钮上写的"和"实际能查到的"不一致。
`query` 是点击后真正提交给 `POST /api/chat` 的内容，`label` 只是按钮上的短标题。

## POST /api/chat

```json
// 请求
{ "message": "退款一般多久能到账？", "session_id": "可选，省略则新建会话" }
```

```json
// 响应（knowledge_only 模式，命中知识库）
{
  "session_id": "611c133a...",
  "session_title": "退款一般多久能到账？",
  "message_id": "9f1c...",
  "reply": "根据知识库中的相关说明，整理如下（以下为原文摘录，未作改写）：\n\n1. ...",
  "answer": "同上（兼容旧字段，与 reply 内容一致）",
  "reply_type": "knowledge",
  "suggestions": [],
  "answer_mode": "knowledge_only",
  "answer_kind": "knowledge_extract",
  "intent": "退款",
  "intent_method": "rule",
  "sources": [
    {
      "document_id": "c1a2...",
      "file_name": "01-退换货政策.md",
      "chunk_index": 0,
      "score": 0.2265,
      "snippet": "退换货政策 七天无理由退货 自签收之日起 7 个自然日内……"
    }
  ],
  "degraded": null,
  "retrieval": {
    "has_context": true,
    "top_score": 0.2265,
    "reason": "ok",
    "embedding": "local-hashing",
    "methods": ["vector", "bm25"],
    "threshold": 0.15
  }
}
```

> 示例里的分数与 `threshold: 0.15` 是 `local-hashing` 下的取值。
> 换成 `ollama`/`bge-m3` 后阈值自动变为 **0.55**
> （bge-m3 对无关中文短句的余弦也有 0.3~0.5，沿用 0.15 会把无关问题全放进来；
> 0.55 由 2026-10-21 实测分布定：15 条真问题 0.584~0.781，12 条无关 0.282~0.528）。
> `retrieval.threshold` 字段始终回传**当时实际生效**的阈值，不需要前端推测。

### reply_type：这条回复到底是什么

前端据此决定显示哪种来源标签，**只有 `knowledge` 才允许贴"知识库原文"**。

| `reply_type` | 触发场景 | 是否检索 | `sources` | `suggestions` |
| --- | --- | --- | --- | --- |
| `greeting` | "你好""在吗""早上好"等纯问候 | ✗ 短路 | `[]` | 6 条 |
| `identity` | "你是谁""你能做什么" | ✗ | `[]` | 6 条 |
| `thanks` | "谢谢""感谢" | ✗ | `[]` | 6 条 |
| `farewell` | "再见""拜拜" | ✗ | `[]` | 6 条 |
| `human_service` | "转人工""联系人工客服" | ✗ | `[]` | 6 条 |
| `knowledge` | 业务问题命中知识库 | ✓ | 有 | `[]` |
| `no_answer` | 业务问题，但知识库没有依据 | ✓ | `[]` | 6 条 |
| `fallback` | 与电商无关（"今天天气怎么样"） | ✓ | `[]` | 6 条 |
| `unclear` | 明显看不懂（"？？？"） | ✓ | `[]` | 6 条 |

引导类回复（`greeting`/`identity`/`thanks`/`farewell`/`human_service`）走本地规则短路，
`retrieval.reason` 为 `skipped_smalltalk`，`intent` 固定为 `其他`、`intent_method` 为 `rule`。

**边界**：判据不是"含不含问候词"，而是"把问候词、客套词、语气词全部剥掉之后还剩什么"。
所以 `你好，我想退款` 剥完只剩"退款"，仍进入退款检索（`reply_type: knowledge`，带来源）。
详见 `app/customer_service/conversation_rules.py`。

未命中知识库时，按三种情况分别回应：

```json
// ① 业务问题但知识库没依据 → 诚实说没找到
{ "reply_type": "no_answer",
  "reply": "暂未在知识库中找到足够可靠的信息，建议联系人工客服进一步确认。",
  "answer_kind": "no_answer", "sources": [],
  "retrieval": { "has_context": false, "top_score": 0.0, "reason": "below_threshold" } }

// ② 与电商无关 → 说明服务范围
{ "reply_type": "fallback", "answer_kind": "conversation",
  "reply": "抱歉，我目前主要提供电商相关的客服咨询，暂时无法可靠回答这个问题。……" }

// ③ 没看懂 → 请用户换个说法
{ "reply_type": "unclear", "answer_kind": "conversation",
  "reply": "抱歉，我暂时没有理解您的意思。请换一种方式描述您的问题，也可以点击下方的常见问题。" }
```

`answer_mode` 取值：`knowledge_only`（本地规则 + 知识库，零外联）/ `llm`（模型生成）。

`answer_kind` 取值：`knowledge_extract`（原文摘录）/ `no_answer`（无可靠依据）/
`conversation`（对话引导，不来自知识库）/ `llm`（模型生成）/ `llm_degraded`（模型失败，退回原文陈列）。

`degraded` 取值：`null` / `llm_not_configured` / `llm_timeout` / `llm_unavailable` /
`llm_quota_exceeded` / `llm_auth_error`。纯知识库模式下恒为 `null`。

`intent_method` 取值：`rule`（关键词）/ `llm`（模型）/ `llm_invalid`（模型输出非法被拒）/
`fallback`（无法判断，归为“其他”）。纯知识库模式下只会出现 `rule` 或 `fallback`。

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
  "answer_mode": "knowledge_only",
  "reply_type": "knowledge",
  "suggestions": null,
  "created_at": "2026-10-20T03:42:11.123456"
}
```

`answer_mode` 会随消息落库，刷新页面后仍能还原“这条回答是怎么来的”；
`reply_type` 记录回答类别（`greeting` / `knowledge` / `no_answer` / `human_service` …），
刷新后仍能正确显示“知识库回答 / 能力说明”这类标签。

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

`GET /api/knowledge` 额外返回上传策略，让前端能显示**真实**的类型与大小限制，
而不是在界面里写死一个迟早会过期的默认值：

```json
{
  "documents": [ ... ],
  "index": { "chunks": 9, "documents": 5, "dim": 4096, "backend": "numpy" },
  "upload": { "max_mb": 10, "extensions": [".docx", ".md", ".pdf", ".txt"], "accepts": ".docx,.md,.pdf,.txt" }
}
```

## GET /api/stats

工作台首页的所有数字都来自这一个接口，**没有一个是写死的**。

```json
{
  "sessions_total": 21,
  "sessions_today": 8,
  "messages_total": 60,
  "messages_today": 26,
  "assistant_total": 30,
  "docs_total": 5,
  "docs_indexed": 5,
  "chunks": 9,
  "dim": 4096,
  "index_backend": "numpy",
  "answer_mix": { "knowledge": 13, "unknown": 17 },
  "knowledge_ratio": 0.4333,
  "degraded_total": 4,
  "feedback_helpful": 0,
  "feedback_unhelpful": 0,
  "answer_mode": "knowledge_only",
  "mode_label": "知识库模式",
  "generated_at": "2026-10-20T17:27:50.997433Z"
}
```

两条容易踩的约定：

1. **`knowledge_ratio` 在没有分母时返回 `null`，不是 `0`。**
   一条回答都没有的时候，“知识引用率”是没有意义的；返回 0 会被前端显示成 “0%”，
   等于在报一个不存在的指标。前端对 `null` 显示 “—”。
2. **“今日”按服务器本地时区切天。** 数据库存的是 UTC，
   直接用 UTC 切会让 UTC+8 的用户在早上 8 点前看到“今日 0 条”。
   实现是先算出本地 00:00 与次日 00:00，再换算成 UTC 区间去查。

`answer_mix` 的键来自 `messages.reply_type` 的真实分组，不是固定的枚举表；
出现新的回答类型时不需要改这个接口。

## POST /api/knowledge/reindex

全量重建索引。**换 embedding 模型后必做**——本地哈希是 4096 维、bge-m3 是 1024 维，
旧向量与新向量不能混在同一个索引里。

```bash
curl -X POST http://127.0.0.1:8000/api/knowledge/reindex
```

```json
{
  "indexed": 5,
  "failed": 0,
  "chunks": 9,
  "dim": 1024,
  "provider": "ollama",
  "signature": "ollama:bge-m3",
  "errors": []
}
```

| 字段 | 含义 |
| --- | --- |
| `indexed` / `failed` | 本次成功与失败的文档数 |
| `chunks` | 重建后的片段总数 |
| `dim` | 重建后向量的**真实**维度（来自模型输出，不是配置里的哈希桶数） |
| `provider` / `signature` | 写入索引的 provider 与指纹，与 `/api/health` 的 `retrieval.index_signature` 对应 |
| `errors` | 每份失败文档的 `{document_id, file_name, error}`，成功时为空数组 |

**失败语义（重要）**

- 重建在**暂存目录**里做（`backend/data/index_staging_<id>/`），
  全部完成才 `replace_all()` 一次性原子替换线上索引；
- **一份都没成功** → 返回 `503`，`detail` 里说明"线上旧索引与文档状态均已保留"，
  此时知识库仍然可用（跑的是重建前那套索引）；
- **部分成功** → 返回 `200`，`failed > 0`，失败文档在数据库里标记 `status=failed` 并写明 `error`，
  成功的文档已进入新索引；
- 暂存目录在 `finally` 里清理，不会残留。

> 因此"重建索引"不是破坏性操作：不会出现"点一下重建，知识库空了"。

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

# 换 embedding 模型后重建索引（暂存区构建，失败不动线上索引）
curl -X POST http://127.0.0.1:8000/api/knowledge/reindex
```

### 排查 embedding 用

```bash
# 1) Ollama 服务是否在跑（本机装了 HTTP 代理时，走代理会得到 502 而不是"连接被拒"）
curl --noproxy '*' http://127.0.0.1:11434/api/tags

# 2) 目标模型是否已安装
curl --noproxy '*' http://127.0.0.1:11434/api/tags | grep -o '"name":"[^"]*"'

# 3) 模型真实输出维度（bge-m3 = 1024）
curl --noproxy '*' http://127.0.0.1:11434/api/embed \
  -d '{"model":"bge-m3","input":"退货政策"}'

# 4) 本进程实际用了什么实现、索引是否对得上
curl --noproxy '*' http://127.0.0.1:8000/api/health
```

### 模式切换速查

```bash
# 看当前模式与模型状态（不会返回任何密钥）
curl http://127.0.0.1:8000/api/settings/answer-mode

# 切到大模型模式
curl -X PUT http://127.0.0.1:8000/api/settings/answer-mode \
  -H "Content-Type: application/json" -d '{"mode":"llm"}'

# 回到 .env 默认模式
curl -X POST http://127.0.0.1:8000/api/settings/answer-mode/reset
```
