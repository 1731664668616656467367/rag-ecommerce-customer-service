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
│  │ RAG 层       │   │ 模型客户端层     │  │ customer_service │  │
│  │ chunker      │   │ llm/factory.py  │  │ 意图识别（加权    │  │
│  │ embeddings   │   │  ← 唯一总闸门    │  │ 关键词 + 白名单） │  │
│  │ retriever    │   │ DeepSeekClient  │  │ 对话引导规则      │  │
│  │ lexical(BM25)│   │ 超时/重试/错误   │  │ (问候/致谢/告别/  │  │
│  │ answer       │   │ 分类            │  │  人工客服/快捷问题)│  │
│  │ vector_store │   └────────┬────────┘  │ 全本地，零外联    │  │
│  │ prompt       │            │           └──────────────────┘  │
│  └──────┬───────┘            │                                 │
│  ┌──────▼────────────────────▼──────────────────────────────┐  │
│  │ 数据层：SQLAlchemy + SQLite（backend/data/app.db）        │  │
│  │ sessions / messages / knowledge_documents / feedback      │  │
│  └──────────────────────────────────────────────────────────┘  │
│  向量索引：numpy 矩阵 + meta.json（backend/data/index/）        │
└──────────────────────────────────────────────────────────────┘
                │
        ┌───────┴────────┐
        │ DeepSeek API   │   仅 ANSWER_MODE=llm 时可能被调用
        │ Ollama(bge-m3) │   仅 embedding 使用，不生成文本
        └────────────────┘
```

**关键边界**：业务数据库（SQLite）与向量索引（`data/index/`）是**两套独立存储**，
只通过 `document_id` 关联。删文档时先清向量、再删文件、最后删库记录。

**模式总闸门**：能不能调用大模型，只在 `app/llm/factory.py::get_llm_client` 一处判断。
`answer_mode != "llm"` 时直接返回 `None`，连客户端对象都不会构造。
这样“有没有 Key”和“允不允许调用”是两件独立的事——环境里躺着一个有效 Key，
纯知识库模式也不会有任何请求发出（`tests/test_knowledge_only.py` 用拦截网络证明）。

## 2. 一次问答的完整链路

回答来源由 `ANSWER_MODE` 决定，**默认 `knowledge_only`（纯知识库，零外联）**：

```
POST /api/chat {message, session_id?}
  → 1. Pydantic 校验（长度、非空）          失败 → 422
  → 2. 取会话 / 新建会话                    不存在 → 404
  → 3. 先保存用户消息（失败也不丢输入）
  → 4. 对话引导判定（纯本地规则，不检索、不调模型）
       命中“纯问候/身份/致谢/告别/人工客服”→ 直接返回固定话术 + 快捷问题，结束
       判不出来（如“你好，我想退款”）→ 继续往下走
  → 5. 去句首客套前缀：“你好，我想退款” → “退款”
  → 6. 意图识别
       knowledge_only：只走本地加权关键词规则，绝不调用模型
       llm：规则置信足够就直接用，否则问模型并要求 JSON，再白名单校验
  → 7. 检索（RETRIEVAL_MODE=hybrid，双通道 + RRF 融合）
       向量通道：query → embedding → top-K → 阈值过滤
       词法通道：BM25 → 加权覆盖度门槛
       两路按排名做 RRF 融合，再合并去重（同文档相邻片段只留一个）
  → 8. 分支
       knowledge_only：有依据 → 直接拼接原文摘录 + 来源
                       无依据 → 三分支：业务问题给“没找到”/ 无关问题说明服务范围 /
                                看不懂请重述
       llm：组装提示词 → 调用 DeepSeek
            402/超时/不可用 → 降级：只陈列检索原文，标记 degraded
  → 9. 保存助手消息（含 intent、sources、degraded、answer_mode、reply_type）
  → 10. 返回 {reply, reply_type, suggestions, answer_mode, answer_kind, intent,
             sources, degraded, retrieval}
```

### 为什么对话引导要先于检索

`你好` 这句话如果丢进知识库检索，BM25 和向量都会返回“最像的片段”——
也就是某段无关政策原文。这不是检索写错了，而是**这类发言本来就不该走检索**。

所以引导类发言由 `app/customer_service/conversation_rules.py` 的本地规则先判定并短路，
`retrieval.reason` 记为 `skipped_smalltalk`。

判定原则是 **宁可漏判，不误判**：

```
把“问候词 + 客套词 + 语气词”全部剥掉，看还剩什么
  剩空壳            → 是纯问候
  剩业务词（退款/物流/订单…）→ 不是问候，交给业务链路
  剩其他实义内容     → 不拦，保守放行到检索
```

所以 `你好` → 问候；`你好，我想退款` → 剥完只剩“退款” → 正常检索退款政策。
另外第 5 步的“去客套前缀”不只是为了判意图：不剥掉“你好”“我想”这些二元组，
它们几乎不可能出现在政策文档里，会把词面覆盖度从 1.0 稀释到 0.05（门槛 0.12），
明明是退款问题却返回“没找到”。

### reply_type 与 answer_kind 的分工

`reply_type` 面向用户（决定显示哪种标签），`answer_kind` 面向内部（决定这条回答是怎么造出来的）。
只有 `reply_type == "knowledge"` 时才允许贴“知识库原文”——问候语不是从文档里摘的，
给它贴“知识库原文”就是在骗用户。

| answer_kind | 含义 | 前端标签 |
| --- | --- | --- |
| `knowledge_extract` | 知识库原文摘录 | 知识库原文 |
| `no_answer` | 没有可靠依据，返回固定提示 | 知识库未覆盖 |
| `conversation` | 对话引导（问候/致谢/超范围/没听懂） | 问候 / 致谢 / 服务范围 / 需要澄清 |
| `llm` | 模型生成 | AI 生成 |
| `llm_degraded` | 模型失败，退回原文陈列 | 降级提示条 |

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
| app_settings | key(PK), value, updated_at | 运行期配置覆盖（当前只有 `answer_mode`），作用域全局 |

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
| 检索（向量） | 余弦 top-K + 阈值过滤 | `rag/retriever.py` |
| 检索（词法） | BM25 + 加权覆盖度门槛 | `rag/lexical.py` |
| 融合 | RRF（倒数排名融合）+ 相邻片段去重 | `rag/retriever.py` |
| 回答构造 | 纯知识库模式：原文摘录拼接，不调模型 | `rag/answer.py` |
| 组提示词 | 仅 llm 模式使用，强制“只依据资料” | `rag/prompt.py` |

### 为什么阈值要按模型区分

余弦相似度的绝对值取决于模型本身：

| 模型 | 相关片段得分 | 无关片段得分 | 采用阈值 |
| --- | --- | --- | --- |
| bge-m3（Ollama） | 0.5 ~ 0.8 | < 0.3 | 0.35 |
| 本地哈希（降级） | 0.26 ~ 0.47（组合分） | ≤ 0.11 | 0.15 |

同一个阈值用两套模型，必然一套全过滤、一套全放行。所以 `AUTO_MIN_SCORE`
按 provider 分别校准，`.env` 里的 `RETRIEVAL_MIN_SCORE` 可以强制覆盖。

### 本地降级模式的额外门槛：加权覆盖度

纯词面向量对“语义相近但用词不同”的问题无能为力（问“东西是坏的”，文档写“质量问题”）。
所以本地哈希通道和 BM25 通道都还要过一道**加权覆盖度**门槛（`rag/lexical.py::CorpusStats`）。

**为什么不能只用“命中比例”**：等权覆盖度会分不清这两句话——

| 问句 | 该不该回答 | 等权覆盖度 |
| --- | --- | --- |
| 你们支持火星配送吗？ | 不该（知识库没有“火星”） | 0.250 |
| 换货要多久？ | 该 | 0.250 |

两者命中的二元组比例一模一样。真正的差别是：前者的关键词“火星”语料里一个字都没有，
后者命中的“换货”是实打实的话题词。所以权重取 `w = 1 / (1 + 文档频率)`：
越常见的词越不重要，语料里没出现过的词权重最高（1.0）。

**为什么不用标准 IDF**：IDF 绝对值依赖语料规模。只有 1 个片段时，未登录词只是已登录词的
4.8 倍；语料涨到 200 段时这个比例掉到 1.26 倍。同一个阈值在小知识库上严、在大知识库上松，
这种漂移会让门槛变成一个说不清的东西。`1/(1+df)` 的比例是恒定的，阈值在 1 段和 200 段上
是同一把尺子。

**当前校准结果**（`scripts/eval_retrieval.py`，5 篇文档 / 9 个片段）：

| 样本 | 分数区间 | 门槛 0.12 的表现 |
| --- | --- | --- |
| 8 条无关问题 | ≤ 0.091（最高是“今天天气怎么样”） | 全部拒绝 ✅ |
| 13 条真实问题 | 0.143 ~ 1.000（最低是“保修多久”“发票怎么开”） | 10 条命中，3 条漏答 |

**已知代价（如实记录）**：纯词法检索区分不了“关键词被修饰”的情况。“怎么退货”“换货要多久”
这类短问句里大部分二元组是切词碎片（“么退”“货要”），覆盖度天然偏低，会被判成“没找到”。
这与“今天天气怎么样”在特征上完全同构（都是单个话题词命中），任何阈值都无法两全。
取舍是**宁可漏答，也不猜答**——漏答时用户看到固定提示并转人工，误答则是给出错误的政策条款。
提高召回的可行路径是接上 Ollama + bge-m3 走语义通道（未在当前环境实测）。

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

## 7. 回答模式的运行期切换

模式有两个来源，**不是一个**：

```
backend/.env  ANSWER_MODE ──┐
                            ├─→ effective_answer_mode() ─→ factory / chat_service / health
app_settings 表（页面设置）──┘        （唯一读口）
```

| 层 | 位置 | 作用 |
| --- | --- | --- |
| 默认值 | `.env` 的 `ANSWER_MODE` | 首次启动、或页面上点「恢复默认」时使用 |
| 覆盖值 | SQLite `app_settings` 表（`key='answer_mode'`） | 页面切换后落库，进程重启从库重载 |
| 内存缓存 | `runtime_mode._override` | 每请求都要读，避免反复查库 |
| 读取口 | `effective_answer_mode()` / `effective_llm_enabled()` / `effective_llm_ready()` | 全链路**只**调用这三个函数 |

为什么必须让后端真正执行：如果只改前端的标签或 `localStorage`，
界面显示「大语言模型模式」而 `/api/chat` 依旧走知识库分支，
那就是纯粹的谎报。所以：

1. `PUT /api/settings/answer-mode` 先落库、再改内存缓存；
2. 前端只认这个接口的返回值，不做乐观更新；
3. 切换失败时前端**回读**真实状态，界面不会停在「假已切换」；
4. 知识库模式下，`factory` 直接返回 `None`，意图识别与回答生成都没有模型句柄可用
   —— 即使 `.env` 里配了 Key 也发不出请求（`test_llm_mode_without_key_degrades_without_network`
   用 `no_network` fixture 验证零外联）。

### 模型可用性怎么回答

不用「启动时探测」判断可用性（费钱，且证明不了下一次）。改为记录**最近一次真实调用**：

| status | 触发条件 | 页面文案 |
| --- | --- | --- |
| `not_configured` | 没有密钥 | 未配置密钥 |
| `unverified` | 有密钥但本进程没调用过 | 已配置 · 尚未调用验证 |
| `ok` | 最近一次调用成功 | 最近一次调用成功 |
| `error` | 最近一次调用失败 | 上次调用失败 + 原因（402 → 余额不足/额度受限） |

对应实现：`app/llm/status.py`；`chat_service` 在每个成功/失败分支写入。

### 作用域

当前覆盖值是**全局**的（`app_settings` 单行），所有会话、所有访问者共享。
页面与接口响应里的 `scope` / `scope_note` 都直说这一点，不让人误以为是个人设置。
按会话/按用户隔离需要先有鉴权，见「6. 可扩展点」。
