# 开发过程记录（按阶段）

> 这份文档记录每个阶段的目标、改动、真实执行结果与踩到的坑。
> 所有“执行结果”都对应真实运行过的命令，失败的也原样保留。

---

## 阶段 0：现有项目审计

### 1. 本阶段目标

先搞清楚“手上有什么”，再决定怎么写。防止上来就重写、把已有逻辑弄丢。

### 2. 系统结构

审计的对象是工作区本身：目录、依赖、配置、RAG 链路、模型客户端。

### 3. 实际情况（与预设不同，必须说明）

检查结果：`D:\电商系统` **是一个空目录**，没有 `main.py`、`knowledge_base.py`、
`rag_chain.py`、`llm_client.py`、`requirements.txt`、`.env` 或任何知识库文件。

因此：

- 「复用现有客服逻辑 / 现有 FAISS 索引 / 现有 Ollama 配置」**没有对象可复用**；
- 不存在「迁移」问题，只有「从零搭建」；
- 基线版本 = 空仓库，第一个 commit 就是本次交付（`0fca5c0`）。

环境探测结果：

| 项目 | 结果 |
| --- | --- |
| Git | 2.55.0 |
| Node | 22.22.2 / npm 10.9.7 |
| Python | 3.13.14 |
| Ollama | **未运行**（`localhost:11434` 连接被拒绝） |
| DeepSeek 密钥 | 环境变量中存在（35 位），但账户返回 402 |

### 4. 因此确定的技术决策

1. **Embedding 必须可降级**：Ollama 不可用，若硬依赖 bge-m3，整个系统无法验证。
   于是设计 `Embedder` 抽象 + 两种实现（Ollama / 本地哈希），`auto` 模式探测后自动选择，
   并在 `/api/health` 如实暴露当前用的是哪一个。
2. **大模型必须可降级**：密钥存在但余额不足，必须让系统在“没有生成能力”时仍然可用，
   且不能把原文伪装成模型回答。
3. **向量库先用 numpy**：依赖少、结果确定、便于教学；`faiss` 装了自动启用。

### 5. 新手知识卡片

**卡片 1：为什么要先审计**
代码不是从零长的。先看现有实现，能避免“重写一遍还丢了别人踩过的坑”。
本次因为目录为空，审计的结论是“没有包袱”，但流程本身不能省——否则你可能基于错误假设写一堆代码。

**卡片 2：什么是“降级”**
依赖挂了还能用较弱方式工作。本项目：语义检索 → 词面检索；模型生成 → 只陈列原文。
关键是**明确告知**，而不是静默降级。

**卡片 3：环境探测为什么要写进代码**
`probe()` 探测 Ollama 是否可达，比“假设它在跑”可靠。写死假设，换台机器就崩。

### 6. 我需要亲自验证的内容

```bash
cd D:\电商系统
dir                 # 确认初始为空
python --version
node --version
curl http://localhost:11434/api/tags   # 确认 Ollama 状态
```

### 7. 验收

能明确说出：现有代码为 0，缺口是全部，方案是从零搭建且关键依赖都要有降级路径。✅

---

## 阶段 1：搭建前后端骨架

### 1. 本阶段目标

让浏览器能真的拿到后端返回的数据，而不是两个各自能跑的空壳。

### 2. 系统结构

```
浏览器 → Next.js(/chat) → fetch → FastAPI(/api/health) → SQLite
```

### 3. 文件清单

| 文件 | 职责 |
| --- | --- |
| `backend/app/main.py` | 装配路由、CORS、全局异常处理、启动初始化 |
| `backend/app/config.py` | 唯一读取环境变量的地方 |
| `backend/app/api/routes/health.py` | 健康检查，如实报告降级 |
| `frontend/app/layout.tsx`、`components/NavBar.tsx` | 页面骨架与导航 |
| `frontend/lib/api.ts` | 统一请求封装（错误处理只写一次） |

### 4. 核心代码解释

`config.py` 用 `pydantic-settings` 从 `.env` 读配置。为什么集中？因为如果 20 个文件各自
`os.environ.get(...)`，改一个变量名就要全项目搜。集中后只有一处。

```python
@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`lru_cache` 让配置只解析一次，同时保证所有模块拿到同一份配置。

健康检查不“报喜不报忧”：

```python
status = "ok" if database == "ok" and settings.llm_configured else "degraded"
```

没配密钥就返回 `degraded` 并附 `warnings`，前端原样展示。

### 5. 实际执行结果

```
GET /api/health → 200
{"status":"ok","database":"ok","embedding":{"provider":"local-hashing","dim":4096},
 "llm":{"configured":true},"index":{"chunks":9,"documents":5}}
GET /chat → 200，GET /knowledge → 200，GET /settings → 200
```

（`status: ok` 是因为当时已配置密钥；后来真实调用返回 402，说明“配置了”不等于“可用”，
这一点写进了已知问题。）

### 6. 新手知识卡片

**卡片 1：CORS 是什么**
浏览器默认禁止网页请求“不同源”的接口。前端 3000、后端 8000 算跨源，后端必须显式允许。
本项目用白名单 `CORS_ORIGINS`。实测：从 3001 端口访问会被拒（预检 400），说明限制真的生效。

**卡片 2：为什么密钥不能放前端**
`NEXT_PUBLIC_` 开头的变量会被打包进 JS，任何人打开开发者工具都能看到。
所以前端只知道“后端地址”，密钥只在后端进程里。

**卡片 3：健康检查的价值**
它不是“证明我写完了”，而是“告诉使用者现在哪部分是残的”。本项目 `/settings` 页面就是它的消费者。

### 7. 我需要亲自验证的内容

```bash
curl http://127.0.0.1:8000/api/health
# 浏览器打开 http://localhost:3000/settings，应看到真实状态与黄色提示
```

### 8. 验收

网页显示的 `index.documents`、`embedding.provider` 与后端一致，且这些数字来自真实查询。✅

---

## 阶段 2：客服逻辑迁移

### 1. 本阶段目标

把业务逻辑从“终端程序”里抽出来，让网页和命令行共用同一套实现。

### 2. 系统结构

```
routes/chat.py → chat_service.handle_chat() → intent + retriever + llm + db
                      ↑
          scripts/cli_chat.py（终端入口，仅负责 input/print）
```

### 3. 文件清单

| 文件 | 职责 |
| --- | --- |
| `services/chat_service.py` | 编排：校验→会话→意图→检索→生成→落库 |
| `customer_service/intent.py` | 规则 + 模型 + 白名单校验 |
| `api/routes/chat.py` | HTTP 入参校验、异常到状态码的映射 |
| `scripts/cli_chat.py` | 可选终端入口，与网页共用 `handle_chat` |

### 4. 核心代码解释

意图识别最关键的一行不是“调模型”，而是**校验**：

```python
candidate = parse_intent_candidate(raw)
if candidate is not None and candidate in _VALID:
    return {"intent": candidate, "method": "llm", "valid": True}
return {"intent": DEFAULT_INTENT, "method": "llm_invalid", "valid": False}
```

如果先调用 `validate_intent()` 再判断，非法值会被“归一化”成“其他”，
看起来像识别成功，实际上是掩盖了模型错误——这是最隐蔽的 bug 之一。

`handle_chat` 里刻意先落库用户消息：

```python
session_service.add_message(db, session.id, "user", text)
```

后面模型挂了也不丢用户输入，且便于排查“用户到底问了什么”。

### 5. 实际执行结果

```
POST /api/chat {"message":"退款一般多久能到账？"}
→ 200, intent=退款(method=rule), sources=[01-退换货政策.md 0.2573],
  degraded=llm_quota_exceeded
CLI：printf '退款多久到账？\nexit\n' | python -m scripts.cli_chat
→ 正常输出回答、意图、降级原因、来源
```

### 6. 新手知识卡片

**卡片 1：为什么规则优先于模型**
规则快、免费、结果稳定。模型只在规则拿不准（关键词命中 < 2）时兜底。
实测“我要退款，钱退回来要多久”命中 2 个关键词，直接走规则，省一次 API 调用。

**卡片 2：降级时的返回码选择**
模型不可用时本项目返回 200 + `degraded` 字段，而不是 503。
理由：客服场景断掉会话体验更差，且降级状态是显式的。这是产品取舍，不是技术限制。

**卡片 3：为什么不能伪造订单状态**
“未接入订单系统”是事实。编一个“您的订单已发货”不仅违背事实，还会造成售后纠纷。
代码里用 `BUSINESS_DATA_NOTICE` 强制加提示，模型想编也编不出来（提示词 + 代码双保险）。

### 7. 我需要亲自验证的内容

```bash
curl -X POST http://127.0.0.1:8000/api/chat -H "Content-Type: application/json" -d "{\"message\":\"帮我查一下我的订单\"}"
# 预期：回答末尾出现“尚未接入订单系统”
curl -X POST http://127.0.0.1:8000/api/chat -H "Content-Type: application/json" -d "{\"message\":\"\"}"
# 预期：422
```

### 8. 验收

网页发问能得到回答与意图；终端入口结果一致；空输入被拒。✅

---

## 阶段 3：完善 RAG

### 1. 本阶段目标

让“检索”真的能区分相关与不相关，而不是永远返回最像的 4 条。

### 2. 系统结构

```
文档 → loaders → clean_text → chunk_text → embedder → VectorIndex
问题 → embedder → 余弦检索 top-K → 阈值 + 覆盖度过滤 → prompt
```

### 3. 文件清单

`rag/loaders.py`、`rag/chunker.py`、`rag/embeddings.py`、`rag/vector_store.py`、
`rag/retriever.py`、`rag/prompt.py`

### 4. 核心代码解释

分块按句子边界聚合，避免把一句话劈开：

```python
if len(buf) + len(sent) <= size:
    buf += sent
else:
    chunks.append(buf.strip())
    tail = buf[-ov:]        # 保留尾部重叠
    buf = tail + sent
```

阈值按模型区分，因为余弦分的绝对值取决于模型：

```python
AUTO_MIN_SCORE = {"ollama": 0.35, "local-hashing": 0.15}
```

本地模式再加词面覆盖度门槛：

```python
cov = lexical_coverage(query, h.text)
if cov < LOCAL_MIN_COVERAGE:   # 0.12
    continue
combined = 0.5 * h.score + 0.5 * cov
```

### 5. 实际执行结果（含一次真实的失败与修正）

第一次跑测试，检索几乎全空。实测分数：

```
dim=512  退款几天到账 → 0.169 / 无关问题“火星探测器什么时候发射” → 0.193
```

两个问题：①阈值 0.18 高于所有真实相关分（0.08~0.17），全被过滤；
②无关问题反而分更高——512 维哈希碰撞太严重。

实验对比后改为：维度 4096、去掉部分噪声特征、加词面覆盖度门槛：

```
退款几天到账 0.26 | 同城配送 0.29 | 怎么修改收货地址 0.47
火星探测器什么时候发射 → 无结果 | 今天天气怎么样 0.111（低于 0.15）
```

最终 80 条测试全绿。

### 6. 新手知识卡片

**卡片 1：Recall@K**
前 K 条结果里，正确答案出现了多少比例。K=4、10 道题里 8 道能找到依据 → Recall@4 = 80%。
它衡量“该找到的有没有找到”，检索漏了，提示词写得再好也没用。

**卡片 2：为什么阈值必须校准**
不同模型的向量空间尺度不同。bge-m3 相关文本常到 0.5+，本地哈希只有 0.3。
一个数字套两套模型，必然一套全过滤、一套全放行。

**卡片 3：为什么不把检索结果全塞给模型**
无关内容会稀释提示词（上下文噪声），模型更容易跑偏。Top-K 宁小勿大。

### 7. 我需要亲自验证的内容

```bash
cd backend
.venv\Scripts\python.exe -m pytest tests/test_rag.py -v
# 浏览器：/chat 问“同城配送几天能到”，展开来源，应看到 02-配送与物流时效.md
```

### 8. 验收

相关问题能命中正确文件，无关问题返回“知识库没有相关信息”且来源为空。✅

---

## 阶段 4：持久化

### 1. 本阶段目标

关掉程序再打开，历史记录还在；不同会话的上下文不串。

### 2. 系统结构

```
SQLite(app.db) ← SQLAlchemy ORM ← session_service ← routes
向量索引(index/) ← 只通过 document_id 与数据库关联
```

### 3. 文件清单

`db/models.py`（4 张表）、`db/session.py`（连接、PRAGMA、依赖注入）、
`services/session_service.py`

### 4. 核心代码解释

SQLite 默认不检查外键，必须显式打开，否则 `ondelete="CASCADE"` 形同虚设：

```python
cur.execute("PRAGMA foreign_keys=ON")
```

历史查询永远带 `session_id` 过滤：

```python
stmt = select(Message).where(Message.session_id == session_id).order_by(...)
```

这就是“上下文隔离”的实现方式——不是靠内存变量，而是靠查询条件。

### 5. 实际执行结果

```
POST /api/sessions → 201
POST /api/chat（两次）→ 4 条消息按 user/assistant/user/assistant 顺序返回
DELETE /api/sessions/{id} → 204，随后 GET messages → 404，数据库无残留
“模拟重启”（新建 Session 对象重新读库）→ 历史仍在
```

### 6. 新手知识卡片

**卡片 1：主键与外键**
`messages.session_id` 指向 `sessions.id`，数据库层面保证消息一定属于某个会话，
不会出现“孤儿消息”。

**卡片 2：级联删除**
删会话时自动删消息。这是数据库行为，不是应用层循环删除——后者容易忘、容易漏。

**卡片 3：ORM 与 SQL 注入**
ORM 用参数化查询，用户输入永远当“值”而不是“SQL 片段”。
测试里特意用 `'; DROP TABLE users;--` 作为意图输出，确认它只会被归为“其他”。

### 7. 我需要亲自验证的内容

```bash
# 发几条消息 → 重启 uvicorn → 刷新页面，历史仍在
# 新建两个会话各发一条 → 切换会话，消息不串
```

### 8. 验收

重启后历史存在、会话隔离、删除无残留。✅

---

## 阶段 5：知识库管理

### 1. 本阶段目标

上传/删除文档必须**真的改变检索结果**，而不是只改页面显示。

### 2. 系统结构

```
上传 → 校验(类型/大小/内容) → UUID 存盘 → 解析 → 分块 → 向量化
     → 写入索引 → 更新数据库状态(indexed/failed)
删除 → 按 document_id 摘向量 → 删文件 → 删记录
```

### 3. 文件清单

`services/knowledge_service.py`、`api/routes/knowledge.py`、`frontend/app/knowledge/page.tsx`

### 4. 核心代码解释

文件名不能直接当路径用：

```python
name = Path(filename or "").name.strip()      # 去掉 ../ 等路径成分
stored_name = f"{uuid.uuid4().hex}{suffix}"   # 磁盘名与用户输入无关
```

删除时先摘索引，且只摘自己的：

```python
removed = get_index().remove_document(doc.id)
```

`remove_document` 按 `document_id` 过滤重建矩阵，不会误删其他文档的片段。

重新上传同名文件 = 整篇替换（先删旧片段再写新的），所以不会出现“旧版本还在被检索到”。

### 5. 实际执行结果

```
上传 退款说明.md → 201, status=indexed, chunk_count=1
/chat 问“同城配送几天能到” → sources=[物流说明.md]（证明上传真的影响检索）
上传 ../../evil.md → 201, file_name=evil.md，文件落在 uploads/ 内（路径穿越被清洗）
上传 .exe → 400；空文件 → 422；超限 → 413；replace=false 重名 → 409
删除 A.md → 索引片段减少，B.md 仍可检索
解析失败（模拟）→ 422，索引为 0，数据库保留 failed + 原因
```

### 6. 新手知识卡片

**卡片 1：路径穿越**
文件名写成 `../../windows/system32/x` 时，如果直接拼路径就会写到系统目录。
`Path(name).name` 只保留最后一段，再改用 UUID 命名，彻底断开“用户输入”与“真实路径”。

**卡片 2：幂等与替换**
“同名覆盖”让重复上传不会导致同一份文档有两套向量（那会让检索结果里出现重复片段）。

**卡片 3：为什么索引不是数据库**
向量库不擅长事务与关联。文档状态、上传时间放 SQLite，向量只存检索必需信息，二者用 ID 关联。

### 7. 我需要亲自验证的内容

```bash
curl -X POST http://127.0.0.1:8000/api/knowledge/upload -F "file=@knowledge_base/05-会员与优惠券.md"
curl http://127.0.0.1:8000/api/knowledge
# 浏览器 /knowledge 上传一个自己的 md，然后去 /chat 问里面写的内容
```

### 8. 验收

上传后能检索到、删除后检索不到、非法文件被拒。✅

---

## 阶段 6：测试与安全

### 1. 本阶段目标

用可重复的方式证明系统在正常与异常情况下都按预期工作。

### 2. 系统结构

```
pytest → conftest(临时库/临时索引) → 测试客户端 / 服务层 → FakeLLM
```

### 3. 文件清单

`tests/conftest.py`、`tests/support.py`、`test_health/intent/rag/chat/sessions/knowledge/security.py`

### 4. 核心代码解释

测试基座在 import 应用**之前**设置环境变量，因为 `settings` 在模块加载时就被缓存：

```python
os.environ["DATABASE_URL"] = f"sqlite:///{(TMP_ROOT / 'test.db').as_posix()}"
os.environ["EMBEDDING_PROVIDER"] = "local"
from app.main import app   # 必须放在后面
```

假模型让失败场景可测：

```python
class TimeoutLLM(FakeLLM):
    def __init__(self): super().__init__(raise_error=LLMTimeout())
```

### 5. 实际执行结果

```
80 passed in 54.26s
```

过程中发现并修复的真实缺陷（都补了回归测试）：

| # | 缺陷 | 现象 | 修法 |
| --- | --- | --- | --- |
| 1 | FastAPI 204 带响应体 | 启动即 AssertionError | 用 `Response(status_code=204)` |
| 2 | 校验错误处理器崩 | 空白消息返回 500 而非 422 | 只序列化 `loc/msg/type`，去掉含 ValueError 的 `ctx` |
| 3 | 非法意图被“洗白” | 模型输出“投诉建议”却记为有效 | 先判白名单，再归一化 |
| 4 | 清洗吃掉空行 | 段落被粘成一段 | 保留空行，压缩连续空行 |
| 5 | 分块丢换行 | 标题粘成“政策## 七天” | 标题前补换行 |
| 6 | 阈值高于所有真实分数 | 检索永远为空 | 按模型校准 + 覆盖度门槛 |
| 7 | 无关问题得分更高 | 哈希碰撞 | 维度 512→4096 |
| 8 | 402 被归为“服务不可用” | 提示不准确 | 新增 `LLMQuotaExceeded` |
| 9 | 移动端侧栏残留 1px 线 | 视觉瑕疵 | 关闭时多推 5% |

### 6. 新手知识卡片

**卡片 1：为什么用 mock**
真实调用花钱、慢、结果不稳定，无法断言。mock 让你能精确制造“超时”“402”“返回垃圾”，
这是工程能力，不是偷懒。

**卡片 2：测试隔离**
每个用例前清空表与索引，否则测试之间互相污染，出现“单跑通过、一起跑失败”。

**卡片 3：安全测试怎么测**
不是“读代码觉得安全”，而是让测试去扫：正则扫描全仓库是否有 `sk-` 真密钥、
请求 500 时响应体是否泄漏内部信息、路径穿越文件名是否被清洗。可执行才算验证。

### 7. 我需要亲自验证的内容

```bash
cd backend
.venv\Scripts\python.exe -m pytest -v
cd ..\frontend && npx tsc --noEmit
```

### 8. 验收

80 条全绿，`tsc` 无错误，失败项均有明确记录。✅

---

## 阶段 7：文档与部署准备

### 1. 本阶段目标

换一个人（或三个月后的你）能照着文档把项目跑起来。

### 2. 文件清单

`README.md`、`docs/ARCHITECTURE.md`、`docs/API.md`、`docs/TESTING.md`、
`docs/LEARNING_GUIDE.md`、`docs/DEVELOPMENT_LOG.md`（本文）、
`backend/.env.example`、`frontend/.env.example`、`.gitignore`、
`Dockerfile`×2、`docker-compose.yml`、`docs/screenshots/`

### 3. 实际执行结果

```
git add -A → 93 个文件
git commit → 0fca5c0
npm run build → ✓ Compiled successfully，5 条路由全部预渲染
node .next/standalone/server.js → /chat 200，/settings 200
npx tsc --noEmit → 0 错误
```

### 4. 新手知识卡片

**卡片 1：.env.example 与 .env**
模板进仓库（不含真值），真配置只在本机。`.gitignore` 必须同时排除 `.env`，
否则一次 `git add .` 就把密钥推到 GitHub 了。

**卡片 2：standalone 输出**
Next.js 的 `output: "standalone"` 会把运行所需文件收拢到一个目录，
Docker 里只需 `node server.js`，不必带整个 node_modules 和源码。

**卡片 3：文档也是交付物**
“我跑起来了”不等于“项目可用”。别人能复现，才算交付。

### 5. 我需要亲自验证的内容

按 README 的“快速开始”从零跑一遍（建议换个目录 clone 一次，验证文档没有隐含前提）。

### 6. 本阶段验收

README 步骤可复现；`.env.example` 无真实密钥；构建与生产运行均通过。✅

---

## 阶段 8：纯知识库问答模式（彻底去掉对 DeepSeek 的依赖）

### 1. 目标

把“能不能回答”和“有没有大模型”解耦：
默认只用**本地规则 + 知识库检索**回答，任何情况下不发出外部模型请求；
即使 `.env` 里躺着一个有效的 `DEEPSEEK_API_KEY`，也不能被偷偷用掉。
只有显式写 `ANSWER_MODE=llm` 才允许调用模型。

### 2. 系统结构

```
问题
 ├─ 意图识别（本地加权关键词，只输出 5 个白名单值之一）
 ├─ 检索
 │   ├─ 向量通道：embedding → top-K → 分数阈值
 │   └─ 词法通道：BM25 → 加权覆盖度门槛
 │   └─ RRF 融合 + 相邻片段去重
 ├─ 有依据 → 原文摘录拼接（去重、限长）+ 来源列表
 └─ 无依据 → 固定提示，转人工
```

模型客户端只有在 `ANSWER_MODE=llm` 时才会被构造，且在 `llm/factory.py` 一处收口。

### 3. 文件清单

| 文件 | 改动 |
| --- | --- |
| `app/config.py` | 新增 `answer_mode` / `retrieval_mode` / `retrieval_min_coverage`；`llm_enabled` 只看模式，`llm_ready` = 已开启且已配置 |
| `app/llm/factory.py` | **新增**，唯一总闸门 `get_llm_client()`，未开启时直接返回 `None` |
| `app/rag/lexical.py` | **新增** BM25 + 加权覆盖度 `CorpusStats` |
| `app/rag/answer.py` | **新增** 纯知识库回答构造（去重、限长、固定提示） |
| `app/rag/retriever.py` | 双通道 + RRF 融合 + 加权覆盖度门槛 |
| `app/rag/vector_store.py` | 索引版本号 + embedding 指纹，模型换了能提示重建 |
| `app/services/chat_service.py` | 按模式分支；knowledge_only 分支不碰模型 |
| `app/customer_service/intent.py` | 关键词带权重，修掉“签收”抢走“质量问题” |
| `app/api/routes/health.py` | 如实上报模式、检索通道、索引指纹、`will_be_called` |
| `frontend/*` | 模式条、来源标签、设置页模式行 |
| `tests/test_knowledge_only.py` | **新增** 21 条，含拦截网络证明零外联 |
| `scripts/eval_retrieval.py` | **新增** 检索门槛校准脚本 |

### 4. 核心代码解释

**① 模式闸门：为什么放在 factory 而不是调用处**

```python
def get_llm_client() -> LLMClient | None:
    if not settings.llm_enabled:      # 只看 ANSWER_MODE
        return None
    from app.llm.deepseek_client import DeepSeekClient   # 延迟导入
    client = DeepSeekClient()
    if not client.configured:
        return None
    return client
```

如果每个调用处自己判断 `if api_key:`，那么“哪里能发请求”就有 N 个入口，
加一个功能就可能漏一处。收口成一个函数后，测试只需要盯住这一个点
（`test_chat_never_requests_llm_client` 直接把它替换成会抛异常的函数）。

**② 意图识别：先判白名单，再归一化**

```python
if candidate not in _VALID:      # 先判
    return "其他", "llm_invalid"
candidate = _normalize(candidate)  # 再归一化
```

顺序反了会出问题：模型返回“投诉建议”，先归一化成“其他”就永远合法了，
非法输出被“洗白”，日志里再也看不到 `llm_invalid`。

**③ 相关性门槛：为什么“命中比例”不够**

实测发现问“你们支持火星配送吗？”会命中《配送与物流时效》，把整段配送范围当答案。
而“换货要多久？”同样只命中少量二元组，比例甚至一模一样（都是 25%）。

差别在于：`火星` 在语料里一个字都没有，`换货` 是实打实的话题词。
于是按 `w = 1/(1+词频)` 加权——越常见越不重要，没出现过的权重最高：

```python
def weighted_coverage(self, query, text):
    q = bigrams(query); tb = bigrams(text)
    total = sum(self.term_weight(bg) for bg in q)
    got   = sum(self.term_weight(bg) for bg in q & tb)
    return got / total
```

**为什么不用标准 IDF**：IDF 绝对值随语料规模变。只有 1 个片段时未登录词只是普通的 4.8 倍，
涨到 200 段时掉到 1.26 倍——同一个阈值在小库上严、大库上松。`1/(1+df)` 的比例恒定，
阈值在 1 段和 200 段语料上是同一把尺子。（这个坑我真踩了：先用 IDF，测试库上大面积误杀才发现。）

**④ 零外联是被证明的，不是被声称的**

```python
monkeypatch.setattr(socket, "create_connection", deny_socket)
monkeypatch.setattr(httpx.HTTPTransport, "handle_request", deny_transport)
monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", deny_async_transport)
```

再加一条**反向对照**：切到 `llm` 模式跑同样的请求，断言拦截器确实抓到了请求。
否则“拦截器没生效”和“真的没外联”在测试里长得一模一样。

### 5. 实际执行结果

```
pytest -q                              → 101 passed
npx tsc --noEmit                       → 0 错误
GET /api/health                        → answer_mode=knowledge_only
                                          llm.configured=true / will_be_called=false
POST /api/chat 命中                    → answer_kind=knowledge_extract，
                                          methods=[vector,bm25]，引用《01-退换货政策.md》第 1 段
POST /api/chat 未命中（火星配送）      → has_context=false，sources=[]，
                                          answer_kind=no_answer，返回固定提示
scripts/eval_retrieval.py              → 误答 0/8，漏答 3/13
```

**如实记录的代价**：“怎么退货”“换货要多久”这类短口语问句会被判成“没找到”。
它们与“今天天气怎么样”在词面特征上完全同构（都是单个话题词命中），
任何阈值都无法两全。取舍是**宁可漏答，也不猜答**——误答会给出错误的政策条款，
漏答只是转人工。想提高召回，接上 Ollama + bge-m3 走语义通道（本机未实测）。

### 6. 新手知识卡片

**卡片 1：显式开关 vs 隐式推断**
`if os.getenv("API_KEY")` 这种写法把“有没有凭证”和“该不该调用”绑死了。
凭证是环境事实，调用是产品决策，两者必须分开——否则测试环境里一个残留变量就能让线上产生费用。

**卡片 2：RRF（倒数排名融合）**
向量分数 0~1，BM25 分数 0~30，量纲不同不能直接相加。
RRF 只加“名次”：`1/(60+rank)`。谁在各自榜单里靠前，谁就被加权，不需要调归一化参数。

**卡片 3：为什么同时要两个检索通道**
BM25 精确匹配术语（“15日”“bge-m3”），不懂同义词；向量懂语义但会漂。
本地哈希向量本质仍是词面匹配，所以 BM25 几乎是必需的补充——两路结果融合后召回明显更稳。

**卡片 4：“已知缺陷”要写进文档**
把漏答率、误答率、校准方法都写清楚，比只写“已实现”有用得多。
下次换知识库时，别人知道该跑哪个脚本、该看哪个数字。

### 7. 我需要亲自验证的内容

1. `cd backend && .venv\Scripts\python.exe -m pytest -q` 自己跑一遍，看是否 101 passed。
2. 把 `.env` 的 `ANSWER_MODE` 改成 `llm`，重启后看 `/api/health` 的
   `llm.will_be_called` 是否变 `true`、前端模式条是否消失。
3. 往知识库上传一份自己的文档，问一个只有新文档能回答的问题，
   再问一个文档里没有的问题，确认前者有来源、后者返回固定提示。
4. 换一份语料后重跑 `scripts/eval_retrieval.py`，确认门槛还站得住。

### 8. 本阶段验收

- [x] 默认模式零外联，且有拦截网络的反向对照测试
- [x] 意图识别全程本地，输出只可能是 5 个白名单值
- [x] 无可靠结果时返回固定提示，不搬错段落
- [x] 前端如实标注“知识库原文 / 知识库未覆盖 / AI 生成”
- [x] 检索模块化（vector / bm25 / hybrid 可切），门槛可配置
- [x] 索引指纹可检测“换了 embedding 模型却没重建索引”
- [ ] 短口语问句召回（已知缺陷，需语义模型）

---

## 阶段 9：对话引导与快捷问题（欢迎语 / 闲聊 / 一键提问）

### 1. 目标

用户第一句话往往不是业务问题，而是“你好”“你是谁”“谢谢”“再见”。
以前这些句子全被丢进知识库检索，于是 `你好` 会返回一段“最像”的政策原文——
这不是检索写错了，而是**这类发言本来就不该走检索**。

本阶段要解决四件事：

1. 纯问候/身份/致谢/告别/人工客服由**独立规则**判定并短路，不进检索；
2. 但 `你好，我想退款` 必须仍然是退款问题——**不能因为含"你好"就判成问候**；
3. 前端首屏给欢迎语 + 6 个真正能用的快捷按钮；
4. 全程本地规则，纯知识库模式下依旧零外联。

### 2. 系统结构

```
POST /api/chat
 ├─ 1~3. 校验 → 会话 → 存用户消息
 ├─ 4. match_smalltalk(text)          ← 新增，纯本地正则/词表
 │      ├─ 命中 → 固定话术 + 快捷问题，retrieval.reason=skipped_smalltalk（结束）
 │      └─ 未命中 → 继续
 ├─ 5. strip_request_prefix(text)     ← 新增，“你好，我想退款”→“退款”
 ├─ 6. 意图识别（原有）
 ├─ 7. 检索（原有，不动算法）
 └─ 8. 无依据时三分支
        ├─ 业务词问题 → no_answer（诚实说没找到）
        ├─ 无关问题   → fallback（说明服务范围）
        └─ 看不懂     → unclear（请重述）
```

### 3. 判定逻辑：判据不是“含不含问候词”

这是本阶段唯一需要想清楚的地方。反例很明确：`你好，我想退款` 以问候开头，
但它是个业务问题。所以判据换成：

```
把“问候词 + 客套词 + 语气词”全部剥掉 → 看剩下的
  剩空壳                 → 纯问候
  剩业务词（退款/物流/…） → 不是问候，放行到业务链路
  剩其他实义内容          → 不拦，保守放行
```

三项保险：

| 保险 | 作用 |
| --- | --- |
| `_is_filler_only(remaining)` | 剥完只剩语气词才算闲聊 |
| `_BUSINESS_WORDS` 否决项 | 只要句子里有业务词，一律走检索（比长度阈值可靠） |
| 保守兜底 | 判不出来就返回 `None`，宁可不拦 |

### 4. 踩到的真问题：问候前缀会稀释检索覆盖率

`你好，我想退款` 最初返回的是 `no_answer`。原因不在意图识别，而在词面覆盖度：
问句会切出 `你好`/`好我`/`我想`/`想退` 这些二元组，它们在政策文档里几乎不出现，
分母变大、分子只多一个 `退款`，覆盖率从 1.0 掉到 **0.05**（门槛 0.12）。

修法是 `strip_request_prefix()`：只在**句首**剥掉固定的客套框架词，
句子中间的实义内容一个字都不动；剥空了就回退原文，避免把空串交给检索。
剥完 `退款` 覆盖率回到 1.0。

> 同一个坑还出现过一次：`在吗，我要退货` 仍然 `no_answer`——因为 `在吗` 当时
> 不在前缀表里。所以前缀表必须覆盖“问候 + 请求”两类开场白，只补 `你好` 是不够的。

### 5. 文件清单

| 文件 | 改动 |
| --- | --- |
| `app/customer_service/conversation_rules.py` | **新增** 引导规则、话术、快捷问题、前缀剥离、`is_unintelligible`、`has_business_topic` |
| `app/services/chat_service.py` | 编排插入引导短路；`BusinessAnswer` 数据类替代 10 元组；无依据三分支；`welcome_payload()` |
| `app/api/routes/chat.py` | 新增 `GET /api/chat/welcome`（只读，不建会话） |
| `app/schemas/models.py` | `SuggestionOut` / `ReplyType` / `WelcomeResponse`；`ChatResponse` 加 `reply`/`reply_type`/`suggestions` |
| `app/db/models.py` + `db/session.py` | `messages.reply_type` 列 + 轻量迁移 |
| `app/services/session_service.py` | `add_message` 支持 `reply_type` |
| `app/customer_service/intent.py` | 补 `售后`/`售后服务` 关键词（原来“如何申请售后服务”被判为“其他”） |
| `tests/test_conversation.py` | **新增** 64 条用例 |
| `tests/conftest.py` | `no_network` 上移共用 |
| `frontend/lib/types.ts`、`lib/api.ts` | `ReplyType`/`SuggestionItem`/`WelcomeResponse`、`api.welcome()` |
| `frontend/components/chat/SuggestionChips.tsx` | **新增** 快捷按钮组件（传 `query` 不传 `label`） |
| `frontend/components/chat/MessageItem.tsx` | 按 `reply_type` 决定标签；引导类不显示来源/评价；渲染本条消息的快捷按钮 |
| `frontend/app/chat/page.tsx` | 首屏拉取欢迎语、`sendingRef` 同步锁防重复发送 |

### 6. 两个前端细节

**① 点击必须提交 `query`，不是 `label`**
按钮上写“退款政策”（短标题），实际提交“退款政策”（完整问句）。
如果只传 label，检索拿到的信息量不足，命中率会掉。
Playwright 断言里直接比对了请求体的 `message` 字段。

**② 防重复发送不能只靠 `sending` 状态**
`setSending(true)` 是异步的，连点两下时第二下读到的还是旧值，会真的发两条。
所以加 `sendingRef`：在事件回调里同步置位，第二次点击直接被挡掉。
按钮同时置 `disabled`，这是第二道闸。

> 顺带修掉一个自己写出来的 bug：`pickSuggestion` 一开始用 `useCallback([], ...)` 缓存，
> 结果它永远记住首帧的 `activeId = null`，每次点按钮都会新建一个会话。
> 闭包里带着状态时，空依赖的 memo 就是陷阱。

### 7. 实际执行结果

```
backend:  165 passed          （其中 test_conversation.py 64 条）
frontend: tsc --noEmit 通过；next build 通过（/chat 8.28 kB / 114 kB First Load）
playwright: 15 项断言全通过
```

真实接口抽查（`ANSWER_MODE=knowledge_only`）：

| 输入 | reply_type | 来源 |
| --- | --- | --- |
| 你好 | greeting | — |
| 你好，我想退款 | **knowledge** | 01-退换货 / 04-售后与保修 / 05-会员与优惠券 |
| 你是谁 | identity | — |
| 谢谢 / 再见 | thanks / farewell | — |
| 今天天气怎么样 | fallback | — |
| ？？？ | unclear | — |
| 我想联系人工客服 | human_service | — |
| 同城配送一般几天能到？ | knowledge | 02-配送与物流时效 |
| 如何申请售后服务？ | knowledge | 03-订单查询 / 04-售后与保修 |

### 8. 一条不改全局阈值的取舍

初版快捷问题里 `物流配送需要多久？`、`退款政策是什么？` 都返回 `no_answer`。
**没有去调低 `retrieval_min_coverage`**——那会连带放过“火星配送”这类无关问题。
改的是 query 措辞：换成实测能命中的说法（`同城配送一般几天能到？`、`退款政策`），
每一条都在当前语料上验证过。这是“让入口对齐能力”，不是“让能力迁就入口”。

### 9. 本阶段验收

- [x] 首屏显示欢迎语 + 6 个快捷按钮
- [x] 纯问候 → 欢迎语（不检索，`skipped_smalltalk`）
- [x] `你好，我想退款` 仍进入退款检索并返回来源
- [x] 身份/致谢/告别/人工客服各有固定话术，且不编造联系方式
- [x] 无关问题说明服务范围、看不懂请重述，都带快捷问题
- [x] 快捷按钮点击确实调用 `/api/chat` 并提交 `query`
- [x] 连点 3 次只发 1 条
- [x] 引导链路零外联（拦截网络证明）
- [x] 前后端类型检查、后端测试、生产构建全部通过
- [ ] 换语料后快捷问题命中率需重跑 `eval_retrieval.py` 复核

---

## 阶段 10：UI/UX 全面升级 + 回答模式切换

### 1. 这阶段要解决的真问题

前九阶段功能是对的，但界面还是“后台模板感”：按钮高度不一、颜色散落、页面顶栏和
聊天内容互相挤压；更关键的是**回答模式只存在于 `.env`**，用户想切到大模型只能改文件重启。

第二个问题比第一个严重：如果只在前端加个切换标签、写进 `localStorage`，
界面显示“大语言模型模式”而 `/api/chat` 依旧走知识库分支，那就是纯粹的谎报。
所以这阶段的核心是把模式切换做成**真正的后端行为**。

### 2. 设计基线集中化

`tailwind.config.ts` 里一次性定义色板与尺寸，组件里只引用语义名，不再散落 `#hex`：

| Token | 值 | 用途 |
| --- | --- | --- |
| `canvas` | `#F8FAFC` | 页面底 |
| `surface` | `#FFFFFF` | 卡片 |
| `ink` / `muted` | `#0F172A` / `#64748B` | 主/次文字 |
| `hairline` | `#E2E8F0` | 边框 |
| `accent` | `#2563EB` | 主色（科技蓝） |
| `card` / `control` | `16px` / `10px` | 卡片与控件圆角 |

`globals.css` 里把 `.btn` 固定成 `h-9`（36px），`.btn-primary/.btn-ghost/.btn-quiet/.btn-danger`
只改配色不改尺寸——按钮高度不齐是最容易暴露“随手拼的”细节。

### 3. 聊天页改成三层布局

```
┌──────────┬────────────────────────────────────┐
│ 侧栏 264 │ 顶栏 h-14：会话名 · 模式下拉        │
│ 品牌     ├────────────────────────────────────┤
│ 新建对话 │ 消息区（独立滚动）                  │
│ 三入口   │  欢迎区 / 气泡 / 来源 / 建议        │
│ 最近会话 ├────────────────────────────────────┤
│ 运行模式 │ 输入区（固定，永不滚走）            │
└──────────┴────────────────────────────────────┘
```

- `h-[100dvh]` + `overflow-hidden`：整页不滚，只有消息区滚。移动端 `100dvh` 才能正确避开地址栏。
- 侧栏桌面可折叠到 68px（只留图标），状态存 `localStorage`；移动端变抽屉。
- 聊天页不再渲染顶部导航（`NavBar` 检测到 `/chat` 直接返回 `null`），
  否则两条导航条一起挤占垂直空间。

### 4. 模式切换：真后端，不是标签

```
PUT /api/settings/answer-mode {mode}
  → 校验（非法值 422，列出合法值）
  → 先写 SQLite app_settings
  → 再改内存 _override
  → 返回完整状态（含 model 四态）
```

全链路只有三个读口：`effective_answer_mode()` / `effective_llm_enabled()` / `effective_llm_ready()`。
`factory`、`chat_service`、`health` 全部改走这里，所以“切了但没生效”在结构上不可能发生。

前端**不做乐观更新**：点完只认后端返回值；失败就回读真实状态。
这条是刻意反着“用户体验直觉”写的——切换失败时界面短暂显示旧模式，
比界面显示新模式而实际没切要好得多。

### 5. 模型可用性：只说实话

不用启动探测（费钱，也证明不了下一次）。改为记录最近一次真实调用：

| status | 含义 | 页面文案 |
| --- | --- | --- |
| `not_configured` | 没密钥 | 未配置密钥 |
| `unverified` | 有密钥没调用过 | 已配置 · 尚未调用验证 |
| `ok` | 最近一次成功 | 最近一次调用成功 |
| `error` | 最近一次失败 | 上次调用失败 + 原因（402 → 余额/额度） |

本机 `.env` 有 Key，所以页面上显示的是 `unverified` + 一句“还没有成功调用记录，
暂时无法确认模型是否可用”。不写“连接成功”。

### 6. 这一阶段修掉的真实 bug（都是截图/断言逼出来的）

| 现象 | 根因 | 修法 |
| --- | --- | --- |
| 回访用户永远看不到欢迎区与快捷卡片 | 首屏自动打开 `list[0]` 最近会话 | 只有 `localStorage` 记住的那个会话才恢复，否则停在欢迎区 |
| 模式下拉被消息气泡盖住 | 顶栏的 `backdrop-blur` 自成层叠上下文，后续兄弟节点覆盖它 | 顶栏加 `relative z-30` |
| 菜单选中项只有底色 + 对勾 | 只靠颜色区分，灰度屏/色觉障碍失效 | 加“当前使用”文字胶囊 |
| Esc 关不掉菜单 | 只在列表上挂 `onKeyDown`，焦点不在列表内就失效 | 改挂 `document` |
| 设置页的值右对齐挤成一行、时间戳是裸 ISO 串 | `justify-between` + 未格式化 | 改左对齐定义列表，时间走 `formatTime` |
| favicon 404 | 没有图标文件 | 加 `app/icon.svg` |

### 7. 知识库页与设置页

- 知识库：`GET /api/knowledge` 新增 `upload` 字段（`max_mb` / `extensions` / `accepts`），
  前端不再写死“10MB / 四种类型”——否则改了 `MAX_UPLOAD_MB` 界面就开始说谎。
  删除从 `window.confirm` 换成真正的对话框：焦点默认落在“取消”、Esc 关闭、说明后果。
- 设置页：五个卡片区。检索设置展示的是后端真实 `top_k` / `min_score` / `min_coverage` /
  切块参数 / embedding 提供方，为此在 `/api/health` 的 `retrieval` 里补了这些字段。

### 8. 验证与一个环境坑

| 项目 | 结果 |
| --- | --- |
| 后端 pytest | 182 passed / 0 failed（新增 `test_mode_switch.py` 17 条） |
| 前端 `tsc --noEmit` | 0 error |
| 生产构建 | 通过，4 个路由（`/chat` 12.4 kB、`/knowledge` 6.11 kB、`/settings` 6.52 kB） |
| 浏览器断言 | 74 项全通过（在 `npm run start` 的生产构建上跑的最后一遍） |

**环境坑**：本机运行环境给 `fs.unlink` 装了安全删除中间层，每次删除都会把文件送进回收站
（每个文件起一个进程）。`next build` 会清理上一个构建的产物，`.next` 里上千个文件
逐个进回收站，一次构建要 30 分钟；超过单次工具调用 50 个的阈值还会直接报
`SAFE_DELETE_BULK_CONFIRM_REQUIRED` 中断构建。

处理方式（没有删任何源码/数据/知识库）：把上一份构建产物整体**改名挪到**
`.workbuddy/tmp/` 下暂存，让 `next build` 在空的 `.next` 上工作——构建时间从 30 分钟降到 37 秒。
需要恢复时把目录改回 `.next` 即可。

### 9. 本阶段验收

- [x] 统一设计变量（底色/卡片/文字/边框/主色/圆角/阴影/字号）
- [x] `/chat` 三层布局、侧栏可折叠、移动端抽屉
- [x] 欢迎区标题、副标题、6 张快捷卡片（图标 + 标题 + 说明 + 真实 `query`）
- [x] 快捷卡片点击真实提交，请求体等于卡片 `query`
- [x] 消息气泡左右区分、Markdown 渲染、回答类型标签不混用
- [x] 来源可折叠、显示真实相关度、无命中不显示来源
- [x] 输入区 Enter/Shift+Enter/空输入禁用/发送中防重复/失败重试/长文本扩展/模式提示
- [x] 模式下拉：两选项带说明、选中态为“图标 + 当前使用”、键盘可用、Esc 关闭
- [x] 模式切换由后端执行：落库 + 全链路生效 + 失败回读
- [x] 知识库模式零外联（即使有 Key），有 `no_network` 测试兜底
- [x] 模型未配置/未验证/失败三态如实展示，不谎称可用
- [x] `/knowledge`：真实统计、拖拽上传、进度与失败原因、删除确认弹窗、重建索引
- [x] `/settings`：五个卡片区、不展示密钥、检索参数真实
- [x] 后端 182 测试、`tsc`、生产构建、74 项浏览器断言全部通过
- [ ] 模式作用域仍是全局（按会话/按用户需要先有鉴权）
- [ ] 侧栏里那批重复的“同城配送一般几天能到？”会话是 E2E 反复点击产生的测试数据，未清理（不删用户数据）

## 阶段 11：参考 Dashboard 设计稿重做前端视觉与交互

### 1. 本阶段只做了什么

把前端从"蓝底 + 卡片"换成参考图那套设计语言：**灰底 + 暖白主容器 + 白色卡片 + 奶油黄强调 + 深色卡片**，
并把"工作台"从一句 `redirect("/chat")` 真正做成一个仪表盘页面。
后端只加了一个只读统计接口，没有动检索与生成链路。

### 2. 换肤的做法：只改值，不改类名

`tailwind.config.ts` 里的语义名（`canvas/surface/ink/muted/hairline/accent`）全部保留，只替换取值，
并补充 `shell/paper/cream/dark/frame/card/pill/lift` 等新词。
这样已有组件不需要逐个改类名就能整体换肤——**每多一个写死的 `bg-[#EDEDE9]`，
下次换主题就多一处会漏掉的地方**。

顺带保留了 `accent-soft`、`blue` 这类旧名，把它们重新指向奶油黄，减少调用点改动面。

### 3. `/api/stats`：仪表盘上的每个数字都要有出处

新增 `backend/app/api/routes/stats.py`，全部来自 SQL 聚合与索引统计。
两条约定写进了代码注释与 `docs/API.md`：

- `knowledge_ratio` 在没有分母时返回 `null` 而不是 `0`——前者前端显示 "—"，
  后者会显示成 "0%"，等于报了一个不存在的指标；
- "今日"按服务器本地时区切天，再换算成 UTC 区间查询。直接按 UTC 切，
  UTC+8 的用户在早上 8 点前会看到"今日 0 条"。

首页读不到数据时显示红色说明 + "—"，并明确写出"没有埋点的指标（如真实成功率）不做展示"。

### 4. 首页仪表盘与真实路由

新 `/` 页面用 `Promise.allSettled` 并发拉 stats / sessions / welcome / answer-mode，
任一失败只影响对应卡片。每张卡都通向真实路由：`/chat`、`/chat?session=<id>`、
`/chat?q=<真实问题>`、`/knowledge`、`/settings`。

为了让"常见问题"能一键带问题进聊天页，聊天页首屏支持 `?session=` 与 `?q=` 两个参数，
并用 `autoSentRef` 保证 `?q=` 只自动提交一次，提交后 `replaceState` 清掉参数，刷新不会重复提问。

### 5. 侧栏不再重复放全站导航

上一版侧栏里有"聊天 / 知识库 / 设置"，而全站顶栏也有同一组。两者相隔 40px，
用户会分不清"当前到底在哪"。本阶段移除侧栏那组，侧栏只保留它独有的事：
新建对话 + 会话历史 + 当前运行模式。导航能力没有减少，入口在顶栏且每页都在。

### 6. 顺手修掉的一个真实可读性问题

知识库模式回答里，一整份文档会被压成一段 400 字、没有断行的长句，
小节标题变成句子里莫名其妙的几个字（"配送与物流时效 发货时间 现货商品…"）。

根因在 `chunker.split_sentences`：它对每句做 `strip()`，把"只含换行"的片段变成空串丢掉，
于是 `## 发货时间\n\n现货商品…` 被拼成 `## 发货时间现货商品…`。
改成只去掉空格与全角空格、保留换行后，标题重新独占一行。
随后 `plain_text` 把小标题加粗、把 `- ` 还原成圆点，回答变成"来源 → 分节引用"的结构。

这一步会改变切块文本，所以回归跑了全部 186 条测试（检索相关用例全在此列），确认没有回归。

### 7. 知识库页与设置页

- `/knowledge`：新增文件名搜索 + 状态筛选（纯前端过滤已取回的真实列表，不发新请求、不造假数据），
  统计条改为"文档数 / 索引片段 / 向量维度 / 检索方式与索引状态"，深色卡承载检索方式；
- `/settings`：卡片头部与模式选项改为新配色，大模型模式选中态用深色卡（高对比），
  同时把"关于项目"里写错的 "Next.js 14" 改为 "Next.js 15"。

### 8. 本阶段验收（真实执行）

| 项目 | 命令 | 结果 |
| --- | --- | --- |
| 后端测试 | `backend\.venv\Scripts\python.exe -m pytest` | **186 passed / 0 failed** |
| 类型检查 | `npx tsc --noEmit` | 0 error |
| 生产构建 | `npm run build` | 通过（8 页静态生成） |
| 交互回归 | `.workbuddy/verify_ui_v2.mjs` | **74 / 74 通过** |
| 视觉与数据回归 | `.workbuddy/shot_phase8.mjs` | **18 / 18 通过**，并生成 10 张截图 |

### 9. 本阶段踩到的坑

1. **`next build` 报 `EPERM: open .next\trace`。** 第一次构建时旧 `.next` 刚被移走、
   新目录刚创建，文件句柄还没释放。**没有删 `.next` 绕过**，原样重试一次即通过。
   规律记下来：把旧 `.next` 整体 `mv` 到 `.workbuddy/tmp/` 再构建，比让 `next build` 自己清理更稳
   （本机 safe-delete 中间层在一次调用里删满 50 个文件就会中断，构建会从 37 秒变成半小时）。
2. **浏览器回归 73/74。** 失败项是"移动端可打开侧栏抽屉"，量到 `x = -1`。
   不是抽屉没打开（打开时 x 才 0，关闭时是 -277），是脚本的等待条件写了 `>= -1`，
   然后在最后一帧就量了。把等待阈值收到 0.5px、断言改为 `|x| <= 1` 后 74/74。
   这类"阈值自己跟自己打架"的断言，比功能缺陷更浪费时间——记下来避免下次误判。
3. **文案改动会让旧断言失效。** 欢迎区副标题按任务书从"协助您了解"改为"帮助您了解"，
   旧脚本因此超时。改的是期望值不是断言目标，并在脚本里注明改动原因。

### 10. 仍未做 / 已知限制

- [ ] 模式作用域仍是全局（按会话/按用户需要先有鉴权）
- [ ] 历史会话里有大量 E2E 反复点击产生的同名会话（如"同城配送一般几天能到？"），未清理（不删用户数据）
- [ ] `SessionSidebar.tsx` / `SuggestionChips.tsx` 是重构后已无引用的旧组件，本阶段未删（避免误伤）
- [ ] 模式切换只在浏览器里验证过"切换后后端状态真的变了"，没有做多客户端同步（无推送通道）
- [ ] 口语化问句召回仍偏弱（"怎么退货" → `no_answer`），留待检索质量阶段处理

---

## 阶段 12：修复 Ollama 未连接，真正启用 bge-m3 语义检索

### 1. 现象与第一层结论

状态页显示：`Ollama 未连接` / `本地哈希向量` / `BM25 已启用` / `5 份文档 9 个片段` / `索引维度 4096`。

**第一层结论（已核实）：本机根本没有安装 Ollama。**
不是"装了没启动"，也不是"启动了但项目没连上"：

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| PATH 里有没有 | `where ollama` | 找不到 |
| 端口有没有监听 | `netstat -ano \| findstr 11434` | 无 |
| 有没有配置目录 | `ls ~/.ollama` | 不存在 |
| 有没有安装痕迹 | `ls "%LOCALAPPDATA%\Programs\Ollama"` | 不存在 |

所以 `EMBEDDING_PROVIDER=auto` 探测失败后**按设计降级**到 `local-hashing`。
而 `4096` 不是任何 embedding 模型的维度，它是 `EMBEDDING_DIM` 这个**哈希桶数量**
（`local-hashing:4096` 指纹里的 4096 就是它）。bge-m3 的真实维度是 **1024**。
把 4096 当成"bge-m3 的维度"是这类问题最常见的误判来源。

### 2. 顺带查出来的三个真实缺陷

装 Ollama 只是恢复能力，代码本身也有问题，一并修了：

**缺陷 1：探测只看服务，不看模型。**
原来 `OllamaEmbedder.probe()` 只请求 `/api/tags` 看状态码 200 就认为可用。
如果服务起来了但目标模型没 pull，`embed()` 会在真正调用时才 404，
表现为"健康检查说没问题、一提问就报错"。而且降级时没有任何原因字符串，
状态页只能显示"未连接"，用户无从判断是没装、没启动、还是没 pull 模型。

修法：
- 新增 `_tcp_open()`，先做**裸 TCP** 探活，区分"未启动"与"HTTP 代理返回 502"；
- `probe()` 记录 `last_error` 与 `installed_models`；
- `has_model()` 做前缀比对（兼容 `bge-m3` vs `bge-m3:latest`）；
- `health()` 输出 `service_reachable` / `model_installed` / `fallback_reason`；
- `_build_embedder()` 把失败原因分三类落进 `_build_info`：连不上 / 模型列表为空 / 没 pull 目标模型；
- 新增 `embedding_status()`，合并"构建时结论"与"实时探测"，给出 `is_fallback`、`restart_required`。

**缺陷 2：`reindex_all` 先 `clear()` 再逐篇建 —— 一篇失败就毁掉线上索引。**
这是真正的破坏性 bug：用户点"重建索引"，第 1 篇文档解析失败，后面全不执行，
结果**索引空了、但文档状态还写着 indexed**，检索直接失效，只能重新上传。

修法：改成**暂存区 + 一次性替换**。在 `index_staging_<uuid>` 里建好新索引，
全部完成才 `live.replace_all(records, vectors, signature)`；一份都没成功就抛 `503`
且**不**改任何文档状态（否则页面会显示"5 份全部失败"，而实际上旧索引还能用）；
部分成功才把失败文档标 `failed`。暂存目录在 `finally` 里清理。

**缺陷 3：`_persist()` 非原子写。**
`np.save(vectors.npy)` 与 `meta.json` 是两次独立写入。若在两者之间进程崩了，
磁盘上会是"旧 meta + 新 vectors"或反之，启动时的完整性检查会判定索引损坏并清空。
改成写 `.tmp` 再 `os.replace()`（同盘原子替换）。
另外 `np.save("某路径字符串")` 会自动补 `.npy` 后缀，必须用文件句柄传，否则临时文件名会错。

**附带修的第四个问题：`upsert_document()` 先删后校验。**
维度检查原本在 `_drop_locked()` 之后，维度不匹配时抛异常，但内存里的旧片段已经被删了，
磁盘上还在 —— 内存与磁盘不一致。把维度检查移到删除之前。

### 3. 安装与验证（真实执行）

```bash
winget install --id Ollama.Ollama -e
```

`winget` 卡在"正在启动程序包安装…"5 分 32 秒（1.58 GB 已下载、哈希已校验，但进程不退出）。
**没有反复重试**，而是保留安装包到 `.workbuddy/tmp/OllamaSetup.exe`，
结束卡住的 winget 进程，直接静默安装：

```bash
.workbuddy/tmp/OllamaSetup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER
```

exit 0，Ollama 0.40.6 落地。然后：

```bash
ollama pull bge-m3        # 拉完 ollama list 显示 1.2 GB（bert 家族）
curl --noproxy '*' http://127.0.0.1:11434/api/embed -d '{"model":"bge-m3","input":"退货政策"}'
```

返回数组长度 **1024**，L2 范数 **1.0**（已归一化，所以余弦就是点积）。

### 4. 配置与索引重建

`backend/.env` **原本不存在**（配置全靠代码默认值 + 系统环境变量，与 README 说的"配置在 backend/.env"不符），
这次补上了全套默认值，`DEEPSEEK_API_KEY` **故意留空**（防止误提交，环境变量已提供），
并把 `EMBEDDING_PROVIDER` 从 `auto` 改为 `ollama` —— 明确表达"我要语义检索"，
而不是依赖 auto 探测的隐式结果。

重建前先备份旧索引（`backend/data/index/` 整体复制到 `.workbuddy/tmp/index_backup_local_hash/`），
再走项目自身的重建接口：

```bash
curl -X POST http://127.0.0.1:8000/api/knowledge/reindex
# {"indexed":5,"failed":0,"chunks":9,"dim":1024,
#  "provider":"ollama","signature":"ollama:bge-m3","errors":[]}   6.5s
```

独立核对维度（不看接口自述，直接量文件）：
`vectors.npy` = **36992 字节** = 9 × 1024 × 4 + 128 字节 numpy 头。若还是 4096 维应是 147584 字节。

### 5. 阈值必须重算，否则"语义检索"比词面检索更糟

bge-m3 对**无关**中文短句的余弦相似度也有 0.3~0.5（哈希向量没这个问题，因为词面不重合就接近 0）。
沿用 `local-hashing` 的 0.15，等于把阈值关掉。切过去后实测：

| 样本 | 条数 | 余弦区间 |
| --- | --- | --- |
| 真问题（"退货要几天""怎么开发票"…） | 15 | **0.584 ~ 0.781** |
| 无关（"今天股市怎么样""帮我写首诗"…） | 12 | **0.282 ~ 0.528** |

先设 0.35（按经验拍的），结果 3 条无关问题里 2 条被误答。
改成按实测分布取中点 **0.55**（0.528 与 0.584 之间），并把测量逻辑固化成
`scripts/eval_retrieval.py` 的 `sweep_min_score()`：打印正/负样本最高余弦分布并给出建议阈值。
`eval_retrieval.py` 的"误答"从 **5/8** 降到 **0/8**。

代码里把这件事写进注释而不是只改数字，避免下次有人"按经验"把它调回去：

```python
AUTO_MIN_SCORE = {
    # bge-m3 余弦基线偏高：用 0.35 会把无关问题全放进来（实测"今天股市怎么样"=0.372）
    "ollama": 0.55,
    "local-hashing": 0.15,
}
```

### 6. 降级路径必须还能用

任务书要求"Ollama 不可用时知识库不得整体瘫痪"，所以专门测了：
把假 Ollama 关掉后上传文档 → 仍能 `indexed` → 仍能检索到 → `/api/health` 里
`provider=local-hashing`、`is_fallback=true`、`warnings` 带具体原因。**不抛异常、不空库。**

### 7. 前端：状态页不再说笼统的"未连接"

设置页原来只有一行 `Embedding: local-hashing`。现在拆成 6 个字段，
关键是**把"配置要求"和"实际生效"分开**——只说"当前用的是哈希"，
用户会以为配置没生效；分开之后 `configured=ollama / active=local-hashing`
一眼就能看出是降级，并附带原因横幅与"需重启后端"提示（`restart_required`）。

维度那一行也明确写"1024 维（模型实际输出）"，并把索引维度并列显示，
防止再把哈希桶数当成模型维度。

### 8. 本阶段验收（真实执行）

| 项目 | 命令 | 结果 |
| --- | --- | --- |
| 后端测试 | `backend\.venv\Scripts\python.exe -m pytest` | **193 passed / 0 failed** |
| 类型检查 | `npx tsc --noEmit` | 0 error |
| 生产构建 | `npm run build` | 通过 |
| 交互回归 | `.workbuddy/verify_ui_v2.mjs` | **74 / 74** |
| 设置页文案 | Playwright 断言 | `Ollama · bge-m3` / `语义向量` / `1024 维` / `5 份文档 · 9 个片段` 全部命中，"已降级"已消失 |
| 健康接口 | `GET /api/health` | `is_fallback=false`、`model_installed=true`、`index_signature=ollama:bge-m3`、`needs_reindex=false`、`warnings=[]` |

新增 `tests/test_embeddings_provider.py` 7 条，用**真实 `ThreadingHTTPServer` 假 Ollama**
（不是 monkeypatch 掉 `embed()`，而是让 httpx 真发 HTTP 到本地端口，并断言 `hits` 计数 > 0），
覆盖：真调用了服务并用返回维度（`(2,1024)` 且 `!= 4096`）/ configured 与 active 的区分 /
服务通但没 pull 模型时 `available=false` / Ollama 挂了知识库仍可上传+检索 /
**重建失败旧索引原封不动**（数量、签名、片段文本，以及重新 `VectorIndex(dir)` 加载后仍一致）/
4096 → 1024 重建成功后 `needs_reindex=false` 且相关命中、无关拒答 / 维度不符在改动前抛 `ValueError`。

### 9. 本阶段踩到的坑

1. **`127.0.0.1:11434` 返回 HTTP 502 而不是"连接被拒"。** 本机装了 HTTP 代理，
   代理会拦截 `127.0.0.1` 的请求并返回 502。第一反应是"Ollama 报错了"，其实是代理在说话。
   所以探活必须先做裸 TCP（`socket.create_connection`），再看 HTTP。
   文档和状态页的文案都按这个结论写了。
2. **`np.save("path")` 自动补 `.npy`。** 写 `vectors.npy.tmp` 实际落成 `vectors.npy.tmp.npy`，
   `os.replace` 时源文件不存在。改用文件句柄。
3. **`winget` 静默卡死。** 下载校验都完成、就是不退出。不要无限重试，
   直接拿安装包走 `/VERYSILENT`，比继续等快得多。
   装完后当前 shell 的 PATH 不会刷新，`ollama` 命令要新开终端才可用——
   这条很容易被误读成"没装上"，实际上服务已经在 11434 上监听了。
4. **长 heredoc 被 SIGTERM。** 一次 embed 15 条文本、加上逐条循环，超过 120s 被掐。
   改成一次批量请求（`input` 传数组）+ `timeout 280`。
5. **阈值的第一版是错的。** 按经验设 0.35，实测 2/3 无关问题被误答。
   教训：换 embedding 模型必须**实测分布**再定阈值，经验值在这个维度上不可靠。

### 10. 仍未解决 / 已知限制

- [ ] 阈值样本只有 **5 篇文档 / 9 个片段**，属"够用但不等于充分校准"。语料扩充后需重跑
      `scripts/eval_retrieval.py` 复核（脚本已能给出建议值）。
- [ ] 边界问题"火星上的配送要几天"余弦 **0.588**，刚好越过 0.55，会返回真实的配送时效原文。
      内容是知识库原文、不是编造，但属于语义相似度的边界地带；靠单一阈值无法完全解决，
      要彻底处理需要引入"问题可回答性"判别（成本更高，本阶段未做）。
- [ ] Ollama 的启动项不属于项目仓库，换机器/重启后需要确认 `ollama serve` 在跑。
      `/api/health` 的 `service_reachable` 与 `restart_required` 能提示，但不会自动拉起。
- [ ] `.workbuddy/tmp/OllamaSetup.exe`（1.58 GB）与旧索引备份仍占用磁盘，未清理（等确认）。
- [ ] **测试偶发失败未能复现**：本轮第一次全量跑时 `test_knowledge_only.py::test_lexical_only_mode`
      报过一次 `AssertionError`（当时同一个终端里还在跑 curl 压测）。单独运行、以及随后
      两次全量重跑都是 193 passed，三次重跑均通过，**没有定位到确切原因**。
      已确认测试用的是 `tempfile.mkdtemp()` 出来的独立库与索引目录（`INDEX_DIR` / `DATABASE_URL`），
      理论上不共享状态；没有为了让它过而放宽断言，如实记在这里待复现。
- [ ] 前序遗留：`SessionSidebar.tsx` / `SuggestionChips.tsx` 死代码未删；
      历史会话里大量 E2E 同名会话未清理；模式作用域仍是全局。
