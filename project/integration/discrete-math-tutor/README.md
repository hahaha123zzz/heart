# 实验心理学教材 AI 助教

当前教材为甲方提供的《实验心理学（第3版）》，沿用原项目页面、PDF阅读器、RAG、Agent、学习记忆和对话图解框架。

## 启动与使用

Windows 双击 `3-start-api.bat`，或在本目录运行：

```powershell
.venv-gpu/Scripts/python.exe -X utf8 -m scripts.start_server --port 8000
```

打开 http://127.0.0.1:8000/ 。配置保存在本机 `.env`，不要分享密钥。真实模型要求 `LLM_MOCK=0`；当前重排模型运行在GPU，embedding运行在CPU。

教材共11章、37节，阅读版PDF共376页。页码标注为生成阅读版页码，不能作为印刷版页码引用。支持教材圈选提问、回答引用定位与高亮；教学需要时自动调用实验流程、变量关系和设计矩阵图解，学生只需点击上一步或下一步。

当前提供的教材未发现独立习题栏。实验目的与实验程序保留在阅读器中；练习页不展示其他教材题目，也不虚构官方题目或答案。

## 数据与验收

正式教材和索引：`knowledge/courses/experimental-psychology-3/`。

心理学学习库自动采用独立SQLite文件 `ai_tutor.experimental-psychology-3.db`。原学习数据库不覆盖、不清空，启动时不会因代码变化删除心理学测试账户；测试账户原有有效期规则仍生效。

教材替换计划及验收详情见 `docs/原项目教材替换实施计划.md` 和 `docs/正式教材迁移实施记录.md`。旧教材资源和旧说明归档于 `artifacts/archive/discrete-math-20261015/`，不会经静态教材目录提供或进入当前检索；原库切换前备份位于 `artifacts/service-backups/before-psychology-cutover-20261015.sqlite`。

已验证代表性概念、随机区组设计、表格图解、文本选区及跨章引用；尚未逐页人工复核全部版面，也未覆盖全部统计公式和纯图片问答。图解核验失败时保留文字回答，不展示未通过的图解。

连续对话质量样本（Q1）：

```powershell
.venv-gpu/Scripts/python.exe -B scripts/check_conversation_quality.py
.venv-gpu/Scripts/python.exe -B scripts/check_conversation_quality.py --live --case simplify_without_switching
```

默认只做结构与追问契约自检，不调用模型；`--live` 使用本机模型和隔离数据库运行本地链路，报告写入 `.runtime/conversation-quality/`。`--include-golden` 可加入 9 类心理学黄金集中的文本案例。

## DeepTutor 整体接入

实施计划与进度：[实施计划](../../docs/research/2026-10-18-deeptutor-full-reuse/IMPLEMENTATION_PLAN.md)、[执行记录](../../docs/research/2026-10-18-deeptutor-full-reuse/EXECUTION_LOG.md)。完整上游源码位于 `../../vendor/DeepTutor`，包含前后端源码、提示词、测试与部署文件。

在本目录执行以下命令，创建独立环境并启动后端：

```powershell
python scripts/setup_deeptutor.py
python scripts/start_deeptutor.py
```

默认仅监听 `127.0.0.1:18001`，运行文件位于 `.runtime/deeptutor`。也可通过 `--python` 指定已装好上游依赖的解释器，或通过 `--port`、`--home` 指定本机端口和独立运行目录。代码从本仓库加载，不依赖原 `D:` 盘源码。

安装脚本优先使用匹配操作系统及 Python 小版本的 `requirements-deeptutor-*.lock.txt` 验证清单；没有匹配清单时按上游依赖声明安装，需要重新验证该环境。

现有应用提供 `/api/deeptutor/status` 和 `/api/deeptutor/capabilities`。状态探测不会调用模型，其中 `model_execution_verified: false` 只表示本次只读探测未执行模型；真实调用结果见独立验收产物。

身份接入已复用上游 `user_context`、`CourseService`、`SQLiteSessionStore`。`POST /api/deeptutor/session` 只接收现有 `student_id` 和 `session_id`，课程及上游身份由服务端确定；不存在的学生返回 404。同一映射重复调用或重启后保持一致，不同学生采用独立上游存储。这里沿用宿主现有学生 ID 入口，尚未增加登录认证或班级权限。

在本机 `.env` 配置 `DEEPTUTOR_BRIDGE_TOKEN`（至少32字符随机值），重启宿主和 worker 后可调用会话绑定。worker 自动读取宿主 `.env`，环境变量优先；除健康检查和能力目录外，HTTP/WebSocket 均要求此凭据，不要把它写入前端。可以运行 `python -c "import secrets; print(secrets.token_hex(32))"` 生成随机值，再仅保存到本机 `.env`。

`DEEPTUTOR_SESSION_SYNC=1` 时，原聊天完成核验和保存后自动建立上游课程及空会话，响应附带 `deeptutor_session.status`：`ready` 或 `unavailable`。后端故障不会撤销已经保存的回答，重发原请求或调用绑定接口可重试。默认仍为 `0`，等待后续教材与回合验收再切换。

注册表位于 worker 运行目录 `heart-bridge/bindings.sqlite3`，学生数据位于 `heart-bridge/users/`；需一并备份。原 API/SSE 的回答、引用、取消与幂等继续由宿主处理。

独立环境可运行 `.venv-deeptutor/Scripts/python.exe -B scripts/check_deeptutor_sessions.py`，自动启动临时后端、检查真实映射/隔离/匿名访问并停止进程。它只使用烟测学生和 `.runtime/deeptutor-session-smoke`，不会写入宿主学习数据库。

### 原生多轮教学执行链（受限试点）

同时设置 `DEEPTUTOR_LLM_ENABLED=1`、`DEEPTUTOR_AGENTIC_ENABLED=1`，启动 worker 并重启宿主后，教材回答及 PDF 选区讲解复用上游原生 AgentLoop。每次先通过只读工具读取本轮已核验教材，再生成回答，原教学、提示和引用检查继续生效。模型不兼容图片/工具或执行中断时明确失败，不移除条件降级生成。

每请求最多 6 次模型调用，总期限最多 180 秒；中间草稿不显示或写入上游会话。工具仅限本轮证据，尚未开放自主全库补查和通用工作区。默认开关为 `0`；关闭并重启即可回到已有 Provider 入口。新增轮次尚无性能收益对照。

验证命令：`.venv-gpu/Scripts/python.exe -B scripts/check_deeptutor_golden.py --agentic`；使用合成学生和隔离数据库，实际调用本机配置的模型。方案、边界与验收见 [AGENTIC_STAGE.md](../../docs/research/2026-10-18-deeptutor-full-reuse/AGENTIC_STAGE.md)。

### 回合版本与断线恢复

`DEEPTUTOR_TURN_SYNC=1` 开启上游回合投影，使用同一个宿主凭据。原任务保存后，直接复用上游 `begin_turn` / `append_events` / `transition_turn` / `get_events`；每个 task_id/revision 对应一个固定回合。同版本重复同步不增加事件，内容冲突返回失败。此开关自动包含会话绑定，无需同时开启 `DEEPTUTOR_SESSION_SYNC`。

投影只保存教材 document_id/version、圈选坐标、证据 ID、任务版本及结果摘要哈希。它不保存学生问题、回答正文、教材引文或成绩，也不调用上游模型。事件固定为 `sources`（seq=1）和 `done`（seq=2）；实时 progress 仍属于原连接，尚未持久化。

现有页面加载 `chat-transport.js`：连接提前结束时，先查询原 request_id；任务已保存则恢复结果，启用上游事件时再读取事件流，不重新 POST 生成请求。任务仍在执行时提示稍后恢复；不会无限轮询。页面布局和来源点击保持原行为。

- `GET /api/chat/requests/{request_id}?student_id=...&session_id=...`：定位原任务，返回当前 task_id/revision/status 和已保存结果；未完成时 result 为 null。
- `GET /api/chat/tasks/{task_id}/events?student_id=...&session_id=...&task_revision=...&after_seq=0`：补传缺失投影后按游标重放。支持 `Last-Event-ID: task_id:revision:seq`；旧版本游标不接受，after_seq=2 返回空流。
- `/api/chat/stream` 的最终 done 事件带上述格式的 id；原有 progress/answer/done 事件数据保持兼容。

恢复始终检查宿主任务归属、版本、账户/任务有效期、记忆 epoch、原对话存在性及教材版本，网络等待后再检查一次。取消、删除和换版后的旧结果不会从上游恢复。上游留存的协议指针不包含正文，正文删除由原存储生效。新任务在生成前保存发布教材版本快照；缺少历史版本快照的旧章节任务会拒绝恢复，不会假定它属于当前教材。

真实后端及重启恢复烟测：`.venv-deeptutor/Scripts/python.exe -B scripts/check_deeptutor_sessions.py --turns`。前端传输测试：`node --test tests/chat-transport.cjs`。

### 教材知识库和真实模型

执行 `.venv-deeptutor/Scripts/python.exe -B scripts/publish_deeptutor_course.py`，把正式教材的规范 chunk 发布为不可变 Obsidian vault。发布前校验原教材、11章 PDF 和索引版本；重复发布复用同版本，换版新建目录。会话绑定直接复用上游 KnowledgeBaseManager 和 CourseService 挂载 vault，文本检索复用上游 Obsidian 搜索。宿主只接受 chunk ID，回原 SQLite 索引读取正文；这是 Markdown 文本检索，尚未构建向量索引。

`DEEPTUTOR_KNOWLEDGE_ENABLED=1` 补充原检索结果；`DEEPTUTOR_LLM_ENABLED=1` 将原 LLMClient 接到上游隔离 Provider。两者沿用本机后端地址及共享凭据，默认均为 0。模型密钥只在服务端读取，生成失败不绕过网关，图片失败不降级为无图回答。生成输入会发送到本机 `.env` 指定的模型服务，当前配置使用 DeepSeek。

真实模型验收：`.venv-deeptutor/Scripts/python.exe -B scripts/check_deeptutor_sessions.py --generation`。需先运行 `scripts/publish_deeptutor_course.py --home .runtime/deeptutor-generation-smoke`，并配置有效的 `CITATION_GROUNDING_INDEX`，或在该目录放置原 `knowledge.citation_index.build_index` 构建的 `citation-index.sqlite3`。脚本配置只影响临时进程，不写 `.env` 或学习数据库。已通过随机分配提示案例的检索、生成、几何引用和原质量校验；后续 9 类代表性黄金集已通过，包含真实图像问答；未穷尽全教材，尚未切换默认模型入口。

从仓库根目录执行 `python project/scripts/vendor_deeptutor.py --verify` 可检查固定源码和已记录兼容补丁；不要在副本上覆盖安装另一个源码版本。

### 聊天富文本

聊天正文直接复用固定上游的 SimpleMarkdownRenderer、中文强调/排版与 LaTeX 规范化工具。现有页面支持标题、列表、GFM 表格、删除线、任务列表、围栏代码、原有高亮和 KaTeX 公式；正文引用调用同条消息已有来源按钮，保留原证据与教材版本检查。练习反馈共用此入口。原始 HTML 不执行，模型给出的图片/工作区链接不加载，可信图解和教材图片仍从原资源区展示。

前端静态资源已随代码提供，刷新现有页面即可使用；无需开启模型或知识库开关。重建时在 reader 目录执行 `npm ci --ignore-scripts`，然后分别执行 `npm run build:chat`、`npm run build`。两个构建输出目录独立，聊天 CSS 复用原 reader.css 的 KaTeX 字体；依赖许可随聊天构建生成。构建时忽略上游 Next.js 的 use client 指令属于预期警告，不需要安装 Next.js。

真实浏览器检查见 `tests/browser/chat-lifecycle.cjs`（需 Playwright 与本机 Edge，可通过 NODE_PATH 指向已有 Playwright 安装）；脚本自建隔离 HTTP 服务和 API 替身。已覆盖富文本/公式、同消息引用、恶意内容、练习引用、真实阅读器公式兼容、390px 布局、焦点/组件/滚动及断线恢复。没有调用模型或写学生数据库。源码与进度见研究目录 MARKDOWN_STAGE.md；代码主题、Mermaid 和工作区附件仍待后续接入。

### 心理学真实模型代表性黄金集

执行 `.venv-gpu/Scripts/python.exe -B scripts/check_deeptutor_golden.py`，通过原 `/api/chat` 同时启用本机 DeepTutor 模型、知识库、会话及回合同步，检查9类固定合成案例。`--case hint --case refusal` 可筛选，`--citation-index` 可指定已构建的精细引用索引。每次新建 `.runtime/deeptutor-golden/<run>/`，独立数据库与裁图缓存不写正式课程目录，结束时停止临时 worker；真实模型调用限180次，检索使用CPU避免争用现有服务的GPU。

本轮9类真实案例、20条精确引用、幂等/重放/学生隔离通过，另有96项专项回归通过。修复了把数据缺失误当任务不明的路由，并限制从局部定义追加无依据的排除结论。详细结果、初轮问题、产物哈希及未覆盖范围见研究目录 GOLDEN_VALIDATION.md。实际 .env 与默认入口保持原配置，现有服务未重启。

### 完整原生对话运行时（历史内部实验）

2026-10-19路线已修订：整套能力通过代码集成到本项目，停止将完整对话委托 DeepTutor 应用的主链建设。范围继续覆盖11个能力、14个扩展、100个工具；下文仅记录此前实验，不能据此继续接学生入口。有效计划见 [整套代码集成计划](../../docs/research/2026-10-19-deeptutor-conversation-flow/IMPLEMENTATION_PLAN.md) 及同目录 LOCAL_REUSE_CONTRACT.md。

此前实验提供 `/internal/heart/native/start|status|events|reply|cancel`，直接委托 DeepTutorApp 与原生持久化回合。Q0已从 worker 撤下这组接口的注册，并移除示例启用项；设置旧环境变量也不会通过当前 worker 启动这些接口。实验实现及测试保留历史，不作为当前业务入口。

当前仅完成 P1 私有运行时检查点，替身能力验证真实应用层的持久化、多轮上下文、澄清接续、取消、去重、并发隔离和无租约回收。新增原生正文写入 worker 私有 data/users，均为待核验产物；宿主归属/版本/删除/正式发布及页面尚未接通。不要据此开启学生入口或标记真实模型/RAG及质量验收完成。完整计划、契约与检查命令见 `project/docs/research/2026-10-19-deeptutor-conversation-flow/`。
