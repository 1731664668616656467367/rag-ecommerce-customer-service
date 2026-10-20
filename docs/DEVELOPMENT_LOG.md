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
