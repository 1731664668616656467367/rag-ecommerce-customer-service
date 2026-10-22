# 测试说明

## 1. 自动化测试

```bash
cd backend
.venv\Scripts\python.exe -m pytest          # 全部
.venv\Scripts\python.exe -m pytest -v       # 显示每条用例名
.venv\Scripts\python.exe -m pytest tests/test_rag.py -q
```

最近一次实际执行结果：**182 passed / 0 failed**（Python 3.13 / Windows）。
其中 `test_conversation.py` 64 条（含参数化）、`test_mode_switch.py` 17 条、
`test_knowledge_only.py` 21 条。

测试使用独立的临时数据库与索引目录（`tests/conftest.py` 里创建），
**不会**污染 `backend/data/app.db` 和你上传的文档。默认环境就是
`ANSWER_MODE=knowledge_only`——测试跑的就是线上默认行为。

### 覆盖清单

| 类别 | 文件 | 用例要点 |
| --- | --- | --- |
| 健康检查 | `test_health.py` | 结构完整、模式与检索通道如实上报、索引统计 |
| 意图识别 | `test_intent.py` | 5 类规则命中、加权关键词、合法值放行、`退货`/`refund`/SQL 片段被拒、模型非法输出标记 `llm_invalid`、双关键词跳过模型 |
| RAG | `test_rag.py` | 清洗、分块不丢内容、向量归一化、相似文本得分更高、命中/无命中、删一份文档不影响另一份、同名覆盖、索引落盘重载、维度不一致报错 |
| 聊天 | `test_chat.py` | 正常问答、两种模式的降级路径、提示词含资料与来源、空输入 422、超长 422、会话不存在 404、超时/不可用/402 三种降级、订单意图追加“未接入”提示 |
| **纯知识库模式** | `test_knowledge_only.py` | 有 Key 也不外联（拦截网络证明）、完全不获取模型客户端、意图纯本地、命中返回原文与来源、无关问题返回固定提示、知识库为空、DeepSeek 故障无影响、删除即失效、`answer_mode` 落库、健康接口如实上报、单通道可插拔、索引指纹不一致报错 |
| 会话持久化 | `test_sessions.py` | 创建/列表、消息顺序、级联删除、上下文隔离、模拟重启后仍能读到、历史窗口、反馈流程与校验 |
| **对话引导与快捷问题** | `test_conversation.py` | 纯问候 → 欢迎语（不检索）、`你好，我想退款` 仍进退款检索、身份/致谢/告别/人工客服、无关问题给服务范围、看不懂请重述、业务问题仍带来源、欢迎接口只读且不建会话、6 个快捷问题逐个能通到真实链路、一次请求只产生 2 条消息、引导链路零外联、客套前缀剥离 |
| 知识库 | `test_knowledge.py` | 上传即生效、不支持类型 400、空文件 422、超大 413、二进制伪装 422、重复 409、删除同步索引、路径穿越被清洗、解析失败保留状态 |
| **模式切换** | `test_mode_switch.py` | 默认读 `.env`、响应不含密钥、切到 llm 后 fake 模型真被调用、切回后不再调用、非法值 422、模拟重启后仍保持（`reset_override()` + `load_answer_mode`）、reset 回默认、health 如实上报 `source`、未配密钥时降级且零外联、402 如实记录、成功后清除失败记录、切换不清空会话、模式值归一化 |
| 安全 | `test_security.py` | 全仓库扫描硬编码密钥、健康接口不泄露密钥、`.env.example` 只含占位符、未处理异常不泄露内部信息、消息长度上限 |

### “不调用 DeepSeek”是怎么被证明的

代码里搜不到 `requests.post` 不等于不会外联——依赖库、SDK、日志上报都可能偷偷发请求。
所以 `tests/conftest.py` 的 `no_network` fixture **主动拦截网络**（对话引导与纯知识库两组测试共用）：

```python
monkeypatch.setattr(socket, "create_connection", deny_socket)
monkeypatch.setattr(httpx.HTTPTransport, "handle_request", deny_transport)
monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", deny_async_transport)
```

任何出网尝试都会抛 `httpx.ConnectError` 并被记录。测试断言 `no_network == []`。

**反向对照**：`test_network_guard_would_catch_a_real_call` 切到 `llm` 模式再跑一次，
断言拦截器确实抓到了请求（`assert no_network`）且返回 `degraded=llm_unavailable`。
没有这条对照，"拦截器没生效"和"真的没外联"看起来会一模一样。

> 踩过的坑：不能 patch `socket.socket.connect`——Windows 上 TestClient 的事件循环
> 自建管道也走它，会把测试框架自己拦死。拦在 httpx 传输层才是正确位置。

### 为什么用假模型

`tests/support.py` 里的 `FakeLLM` / `TimeoutLLM` / `UnavailableLLM` / `QuotaLLM`
用来模拟外部服务的各种失败。真实调用每次都要花钱、有网络抖动、结果不可重复，
无法稳定断言。**这不是偷懒，是把不确定性挡在测试之外。**

### 检索门槛怎么校准

`backend/scripts/eval_retrieval.py` 用固定的 13 条真实问题 + 8 条无关问题跑当前索引，
打印每条问句的等权覆盖度、加权覆盖度、是否命中，最后给出漏答/误答清单。

```bash
cd backend
.venv\Scripts\python.exe scripts/eval_retrieval.py
```

改了知识库、分块参数或 embedding 模型后**都要重跑**——门槛是按当前语料实测校准的，
不是拍脑袋定的。最近一次结果：误答 0/8，漏答 3/13（3 条都是短口语问句，原因见
`ARCHITECTURE.md` 的“已知代价”）。

---

## 2. 手动端到端验收

启动（两个终端）：

```bash
# 终端 A
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# 终端 B
cd frontend
npm run dev
```

打开 <http://localhost:3000/chat>，依次验证：

| 步骤 | 操作 | 预期结果 |
| --- | --- | --- |
| 1 | 打开 `/chat` | 顶部模式条写明“纯知识库模式 / 回答直接摘自知识库原文，不调用任何大模型 / 检索方式：向量 + BM25”；左侧显示历史会话；中间显示**欢迎语 + 6 个快捷按钮**（物流配送 / 退款政策 / 退换货 / 售后服务 / 订单查询 / 联系人工客服） |
| 2 | 点“物流配送”按钮 | 自动提交“同城配送一般几天能到？”，用户气泡 → 处理中提示 → 回答下方有“查看 N 条来源”；消息头标签是**知识库原文** |
| 2b | 手动输入“你好” | 返回欢迎语，消息头标签是**问候**（不是“知识库原文/未覆盖”），下方带 6 个快捷按钮 |
| 2c | 输入“你好，我想退款” | **仍然进退款检索**：有来源、标签为“知识库原文”，不会被当成闲聊 |
| 2d | 输入“谢谢” / “再见” / “你是谁” | 分别是致谢 / 结束语 / 服务介绍，都附带快捷按钮 |
| 2e | 点“联系人工客服” | 说明“暂未接入在线人工客服”，**不出现**任何电话号码、链接或“已为您转接” |
| 2f | 快速连点同一个快捷按钮 3 次 | 只发出 1 条请求，会话里只出现 1 条用户消息 |
| 3 | 展开“查看来源” | 显示文件名、第几段、相关度分数、片段摘要 |
| 4 | 点“复制” | 按钮变成“已复制” |
| 5 | 点“有帮助” | 出现“已记录”；`feedback` 表新增一行 |
| 6 | 新建对话后问“你们支持火星配送吗？” | 回答“暂未在知识库中找到足够可靠的信息…”，来源为空，标签是**知识库未覆盖** |
| 6b | 问“今天天气怎么样” | 回答说明**服务范围**（标签“服务范围”）并给出快捷按钮，不应搬出配送范围段落 |
| 6c | 问“？？？” | 回答请用户换个说法（标签“需要澄清”） |
| 7 | 在左侧切换回上一个会话 | 历史消息完整还原（来自数据库，不是内存），`answer_mode` 与 `reply_type` 标签也在 |
| 8 | 刷新页面 | 当前会话仍在（localStorage 记住 + 数据库读取） |
| 9 | 打开 `/knowledge` 上传一个 `.md` 文件 | 列表出现该文档，状态“已索引”，片段数 > 0 |
| 10 | 回到 `/chat` 问一个只在新文档里出现的问题 | 能检索到，来源显示新文件名 |
| 11 | 在 `/knowledge` 删除该文档 | 列表消失；再问同样问题，来源不再出现该文件 |
| 12 | 打开 `/settings` | 显示真实状态：回答模式、检索方式、模型服务状态；未配 Ollama 时给出黄色提示 |
| 12b | 把 `.env` 的 `ANSWER_MODE` 改成 `llm` 并重启后端 | 模式条消失，`/settings` 显示“大模型模式”；回答标签变成 AI 生成（未配 Key 时显示降级提示条） |
| 13 | 缩窄窗口到手机宽度 | 侧栏折叠为菜单按钮，点击可展开；快捷按钮自动换行，无横向溢出 |
| 14 | 停掉后端（Ctrl+C）后发消息 | 显示“无法连接后端服务”，并提供“重试”按钮 |

### 浏览器交互已用 Playwright 断言

上表条目已由脚本 `.workbuddy/verify_ui_v2.mjs` 自动跑过（Chromium 无头，1440×900 + 390×844），
**74 项断言全通过**，且是在 `npm run build && npm run start` 的**生产构建**上跑的最后一遍。
覆盖内容：

| 分组 | 断言要点 |
| --- | --- |
| 首屏 | 三层布局、侧栏导航三项、欢迎标题与副标题（副标题只在 `/api/chat/welcome` 真返回后才出现）、6 张快捷卡片各有图标/标题/说明/真实 `query` |
| 快捷卡片 | 点击确实发出 1 次 `POST /api/chat`，请求体 `message` 等于卡片的 `query`；回答气泡渲染、无原始 Markdown 符号、标签为「知识库回答」而非「大语言模型回答」 |
| 来源 | 有命中时展开可见文档名与相关度分数，可收起；无命中时不存在来源按钮（不伪造来源） |
| 模式菜单 | 展开/两个选项/各带说明；选中项有「当前使用」文字标识（不只靠颜色）；Esc 关闭并回焦；↑ 键可展开 |
| 模式切换 | `PUT` 200 → 后端 `mode=llm` → `overridden=true` → 顶栏标签跟随；`will_be_called` 与 `configured` 一致；横幅文案与实际状态吻合；切回后 `will_be_called=false` |
| 输入区 | 空输入禁用、Enter 发送并清空、Shift+Enter 换行不发送、模式提示文案存在 |
| 知识库 | 标题/真实上传限制（来自后端 `upload` 字段）/真实统计；列表行数 = 后端行数；删除弹窗可取消且不删；**真实上传**一个 `.md` → 出现「已索引 N 个片段」→ 确认删除 → 后端回到 5 份；**重建索引**返回「成功 5 份」 |
| 设置页 | 五个卡片区齐全；不含密钥；模型状态为「未配置/未验证/失败」之一而非「连接成功」；展示真实 `top_k`/最小覆盖度；切换模式与「恢复默认」都真实落到后端 |
| 移动端 | `/chat`、`/knowledge`、`/settings` 均无横向溢出（390 宽）；侧栏默认收起、可打开抽屉、抽屉打开后仍无溢出 |
| 运行时 | 全流程 0 控制台错误 |

这一步不能只用"代码看起来对"代替：`onClick` 绑没绑对、是否误传了 `label`、
禁用状态是否生效、模式切换是不是只改了前端字符串，都只有真的点一下才知道。

### 缩略图

`docs/screenshots/` 下是实际运行截图（Chrome，1440×900 与 390×844）：

- `01-chat-home.png` 聊天主页面（三层布局 + 欢迎区 + 6 张快捷卡片）
- `02-chat-answer.png` 回答与来源折叠区
- `03-mode-menu.png` 回答模式下拉菜单（含「当前使用」标识与模型状态说明）
- `04-knowledge.png` 知识库管理页
- `05-delete-confirm.png` 删除确认弹窗
- `06-settings.png` 设置页五个卡片区（整页）
- `07-mobile-chat.png`、`08-mobile-drawer.png`、`09-mobile-knowledge.png` 移动端
- `chat.png`、`chat-welcome.png` 等为历史截图，保留以对比

---

## 3. 已知未验证项

| 项目 | 原因 | 影响 |
| --- | --- | --- |
| 真实 DeepSeek 生成质量 | 账户返回 402（余额不足），只验证到“正确识别 402 并降级” | `ANSWER_MODE=llm` 下模型输出的质量未经真实样本验证 |
| Ollama + bge-m3 检索效果 | 本机未启动 Ollama，改用本地哈希向量验证全链路 | 语义召回能力未实测；当前仅词面匹配 |
| 短口语问句的召回 | “怎么退货”“换货要多久”被判为“没找到” | 见 `ARCHITECTURE.md` 的“已知代价”，属有意取舍 |
| 快捷问题在换语料后的命中率 | 6 条 `query` 是按当前 5 篇文档实测挑的；“退款政策”“同城配送一般几天能到？”这类短问句在换了语料后可能落到 `no_answer` | 会诚实说“没找到”，不会编造；换语料后需重跑 `scripts/eval_retrieval.py` 复核 |
| 浏览器交互的 CI 化 | Playwright 脚本已跑通，但没有纳入 `npm test`（项目未引测试框架） | 需要手动执行脚本，不是 CI 门禁 |
| Docker 构建 | 已提供配置，但未在本机执行 `docker build`（见 README） | 容器化路径未验证 |
