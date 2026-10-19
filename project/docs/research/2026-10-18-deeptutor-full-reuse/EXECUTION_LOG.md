# DeepTutor 整体复用执行记录

开始日期：2026-10-18；更新：2026-10-19。

| 批次 | 状态 | 完成条件/当前工作 |
| --- | --- | --- |
| A 源码与运行基础 | 已完成 | 3,764 个文件校验；独立环境/后端；11 项能力发现；只读桥接通过 |
| B 对话与证据 | 进行中 | B1、B2 回合协议与恢复已接通；正式知识库、上游模型执行与完整富文本仍待完成 |
| C 阅读与图文交互 | 待执行 | 阅读、批注、图解、原图练习和相关组件 |
| D 教学与复习 | 待执行 | Mastery、统一作答事实、出题、题库、复习与记忆 |
| E 内容与管理 | 待执行 | Book、报告、统计、任务及音视频 |
| F 扩展与总体验收 | 待执行 | 扩展工具、部署、恢复及完整回归 |

## 本轮范围

遵照已确认的整体复用设计分批执行。保留现有业务修改，不覆盖教材和学生数据库。A、B1 与 B2 回合协议已完成；B 的生成/知识库/富文本及 C—F 仍待接通，源码迁入不等于全部业务完成。

## A 批次已完成的改动

- `project/vendor/DeepTutor`：完整固定源码副本，包括后端、CLI、前端源码、提示词/模板、测试、部署与依赖文件。`UPSTREAM_SNAPSHOT.json` 记录 3,764 个文件哈希。
- `LOCAL_PATCHES/llm-config-adapter.patch`：单独保留已核查的 7 行 LLMConfig 类型兼容修复，并记录上游/本地哈希。
- `project/scripts/vendor_deeptutor.py`：从固定 Git 提交迁入、校验归档路径、拒绝覆盖已有副本、校验文件完整性。
- 宿主 `scripts/setup_deeptutor.py`、`scripts/start_deeptutor.py` 和 `integrations/deeptutor/worker.py`：安装项目专属环境，在独立进程启动仓库内源码；默认监听 127.0.0.1:18001，数据位于 `.runtime/deeptutor`。
- 宿主新增 `/api/deeptutor/status` 和 `/api/deeptutor/capabilities`，只暴露健康状态与公开能力说明，未开放写入代理。
- 本机地址检查、禁用系统代理和 HTTP 跳转、限制响应大小；不把上游异常正文或内部配置返回浏览器。
- 安装完整默认后端依赖到宿主 `.venv-deeptutor`，没有更改既有 `.venv` / `.venv-gpu`。
- `requirements-deeptutor-win32-py313.lock.txt` 保存本次实际验证环境，源码 editable 路径使用仓库内相对引用。
- 根 README、宿主 README、环境示例与忽略规则已同步。

## 真实验证结果

| 检查 | 环境与范围 | 结果 |
| --- | --- | --- |
| 固定源码完整性 | 3,764 个文件 SHA256，包含独立记录的本地修复 | 通过 |
| 新增接入测试 | URL/重定向、响应校验、错误降级、能力字段、宿主隔离、归档路径、哈希、覆盖保护、环境/锁文件安装 | 13 项通过 |
| 原有聊天 API/SSE | 既有 `.venv-gpu`，`tests/test_task_api.py`，临时数据库与 mock | 8 项通过 |
| 上游相关测试 | 新 `.venv-deeptutor`，可视化 registry/tool、课程服务、reading grounding、RAG metrics | 27 项通过 |
| 依赖一致性 | 新环境 `pip check` | No broken requirements found |
| 锁文件复现检查 | 匹配平台/Python 清单，pip dry-run 与仓库内 editable 引用 | 通过 |
| 真实后端与桥接 | 新环境 Python 3.13.2，127.0.0.1:18187，独立烟测运行目录 | ready；11 个能力；宿主未 import 上游 |

发现的能力：ask_questions、audio_overview、chat、course_study、deep_question、deep_research、deep_solve、immersive_reading、mastery_path、math_animator、visualize。

烟测记录：宿主 `artifacts/deeptutor/phase-a-smoke.json`（运行产物，不纳入源码提交）。最初用现有依赖环境检查后端；最终又用新安装的项目环境独立启动并验证，运行不再需要 D 盘解释器。

两个临时烟测后端进程均已停止，没有替换或重启原服务。依赖清单记录 169 项实际版本。Windows 中文 Git 路径导致 pip freeze 的 VCS 探测失败，改用 pip list 的已安装元数据生成等价版本清单，并验证可解析安装；未修改 pip 或上游源码。

上游测试最初因环境缺少 pytest 未能启动；确认缺少工具后，在新环境安装 pytest/pytest-asyncio 再运行，27 项全部通过。没有据此修改上游业务逻辑。

## 复现命令

宿主目录：`project/integration/discrete-math-tutor`。

```powershell
python scripts/setup_deeptutor.py
python scripts/start_deeptutor.py
.venv-deeptutor/Scripts/python.exe -B -m unittest discover -s tests -p test_deeptutor_integration.py -v
.venv-gpu/Scripts/python.exe -B -m unittest discover -s tests -p test_task_api.py -v
.venv-deeptutor/Scripts/python.exe -m pip check
```

仓库根目录：

```powershell
python project/scripts/vendor_deeptutor.py --verify
```

上游测试在 `project/vendor/DeepTutor` 执行，设置 `DEEPTUTOR_HOME` 为宿主 `.runtime/deeptutor-tests`，并将 `PYTHONPATH` 指向当前上游副本：

```powershell
../../integration/discrete-math-tutor/.venv-deeptutor/Scripts/python.exe -B -m pytest tests/visualizers/test_registry_and_tool.py tests/services/test_courses.py tests/reading/test_grounding.py tests/services/rag/eval/test_eval_metrics.py -q -p no:cacheprovider
```

## 尚未接通的范围

- 未向上游复制真实模型密钥；当前 `model_execution_verified` 保持 false，没有把能力注册等同于模型执行成功。
- 现有聊天、教材证据、学生状态与练习仍走原链路。B1 已接身份/课程/空会话映射，受约束回合执行和前端消息组件见后续批次。
- 上游前端源码已迁入，尚未安装/构建或挂载进当前页面；Manim、额外解析引擎、外部服务不因基础环境安装而全部具备运行条件。
- 未执行完整上游测试和浏览器端到端回归，也未迁移业务数据库。

## B1 用户、课程与会话映射（2026-10-19）

完成范围：直接调用已迁入上游 `CurrentUser` / `UserScope` / `user_context`、`CourseService`、`SQLiteSessionStore`，在独立 worker 中实际建立学生作用域、课程及空会话。未改动固定上游源码。

- 以 student/course/session 为映射键，注册表保存在 worker 运行目录 `heart-bridge/bindings.sqlite3`；上游用户以 student 角色运行，数据根目录独立。不同课程在同一学生作用域中有各自课程与会话。
- 重复绑定、并发重复请求和重新创建服务实例均保持映射。上游创建后、注册表提交前失败，可通过固定作用域和会话键认领，不重复建立课程/会话。
- 宿主 `POST /api/deeptutor/session` 只接受已有学生与宿主会话 ID；课程来自当前服务端教材配置。禁止浏览器提交上游用户、课程或角色。不存在的学生返回 404。
- worker 数据接口和 WebSocket 要求 `DEEPTUTOR_BRIDGE_TOKEN`，健康/能力只读入口保留。宿主与 worker 从同一本机 `.env` 读取配置，环境变量优先；凭据不得下发前端。未配置至少32字符凭据时不能访问数据接口。
- 原 `/api/chat`、`/api/chat/stream` 保存已核验回答后，可通过 `DEEPTUTOR_SESSION_SYNC=1` 自动绑定。绑定失败明确返回 `deeptutor_session.status=unavailable`，不撤销已保存回答。原 request_id 重发可重试绑定，不再次生成或写入原对话。
- 同步默认关闭，README 和 `.env.example` 已记录启用方式。当前不复制正文、教材、成绩或掌握状态，避免在删除/撤销协议接通前产生另一份学习事实。

本批检查：

| 检查 | 结果 |
| --- | --- |
| 新增宿主边界与真实上游存储测试 | 独立环境 8 项通过：身份契约、凭据、HTTP/WS、故障保护、真实存储、学生/会话/课程隔离、重复请求、重建实例和部分写入恢复 |
| A 批次接入回归 | 原宿主环境 13 项通过 |
| 原聊天 API/SSE 与新增绑定接线 | 原宿主环境 10 项通过；含失败后通过同 request_id 重放恢复绑定，生成器仅执行一次，对话仅一对 user/assistant |
| 真实独立后端烟测 | 启动成功；实际调用课程/会话服务；重复映射一致；学生/标签页隔离；匿名数据访问 401；验证进程已停止 |
| 固定源码完整性 | 3,764 个文件通过，保持原有唯一兼容补丁 |

测试初次暴露 Python sqlite3 连接上下文只负责事务、不负责关闭连接，Windows 临时目录因此被占用；适配层已增加显式 finally 关闭连接，存储与清理重跑通过。没有通过忽略清理失败掩盖问题。

复现（宿主目录）：

```powershell
$env:DEEPTUTOR_HOME = Join-Path (Get-Location) '.runtime/deeptutor-session-tests'
.venv-deeptutor/Scripts/python.exe -B -m unittest discover -s tests -p test_deeptutor_sessions.py -v
.venv-gpu/Scripts/python.exe -B -m unittest discover -s tests -p test_deeptutor_integration.py -v
.venv-gpu/Scripts/python.exe -B -m unittest discover -s tests -p test_task_api.py -v
.venv-deeptutor/Scripts/python.exe -B scripts/check_deeptutor_sessions.py
```

烟测脚本用随机临时凭据、本机临时端口和独立烟测目录，不访问宿主学习数据库。结果写入 `artifacts/deeptutor/phase-b1-smoke.json`。当前没有更改实际 `.env`、切换生产入口或重启已有服务。

B1 结束时安排下一部分 B2：发布教材与版本、PDFSelection/reader_location/task revision、上游回合与持久化事件游标、取消及删除/撤销；本批实现和检查见下文。宿主原有 student_id 接口尚未升级为登录/班级授权，不能把存储隔离等同于完整账户认证。

## B2 回合协议、教材版本与原页面恢复（2026-10-19）

完成范围：直接使用上游 SQLiteSessionStore 的回合创建、批量事件追加、状态转换、事件游标查询与作用域隔离。宿主 TaskService/收据仍负责唯一的教学正文与学习事实，不再复制一套可绕过删除的回答。

### 接入行为

- 每个宿主 task_id/revision 映射固定上游 turn_id；保存 sources(seq=1) 和 done(seq=2)。同版本同内容重发不增加事件；不同内容的同版本拒绝写入。结果哈希保留数学符号差异，不使用上游的去标点证据比较。
- sources 记录发布教材 ID/版本、选区归一化坐标、章节与证据 ID；学生问题、回答、教材引文与分数均不进入上游事件。正文仍通过原精细证据、语义和坐标核验后保存。
- TaskService 在生成开始前保存发布教材版本快照，支持 PDFSelection、reader_location 和澄清后有效任务。换版或实际 PDF 文件哈希变化时拒绝恢复；没有历史版本快照的旧章节任务不能被包装成当前版回答。
- 新增请求编号查询和版本化事件恢复 API。恢复前后均检查宿主归属、任务版本、账户/任务期限、记忆 epoch 与原对话存在性。取消/删除/过期/旧版本不能通过上游事件还原正文。
- 原 SSE done 添加 `task_id:revision:2` 事件 id；恢复支持 after_seq 和 Last-Event-ID，原 progress/answer/done 数据继续兼容。实时进度和模型 token 尚未写入上游事件，当前恢复的是已保存的任务终态。
- 原页面移出已有 SSE 解析器到 chat-transport.js，保留页面结构。连接提前关闭时，按原 request_id 查收据；已完成则恢复，启用上游事件时再读取事件流；不重新提交生成。仍在执行时提示稍后恢复，不无限轮询。
- 同步中断后可按原版本重试，并可在下个任务完成后补传旧投影。仅收尾中断的 heart_snapshot 回合，不取消真实 chat/模型执行。
- `DEEPTUTOR_TURN_SYNC` 默认 0；1 时自动包含会话绑定，沿用宿主凭据。worker 接口没有开放任意写入代理，也未改动上游固定源码。

### 本批验证

| 检查 | 结果 |
| --- | --- |
| 原聊天与新增恢复 API/SSE | 18 项通过；含归属、游标、删除、等待期间删除、取消、过期、换版、幂等补传 |
| 教材来源投影 | 5 项通过；跨页坐标、版本/文件改变、缺少历史快照、符号摘要差异和无正文投影 |
| 真实上游回合存储 | 6 项通过；幂等、冲突、用户/会话/课程/版本隔离、中断、真实执行保护及各终态 |
| B1 会话边界与存储回归 | 8 项通过 |
| A 接入边界回归 | 13 项通过 |
| 原澄清任务事务/取消/删除回归 | 29 项通过 |
| 前端传输 | Node 8 项通过；CRLF、中文分片、带 id 事件、断线恢复、仍执行、删除和输入拒绝 |
| 真实浏览器页面/API 替身 | 通过；保留焦点/组件/引用/滚动，断线后恢复带游标事件且只发一次生成请求，删除后拒绝恢复，无 pageerror |
| 独立后端 HTTP 与重启烟测 | 通过；实际写入回合/读取事件；发布清单版本指针往返一致；停止并重启后从 seq=1 继续读 seq=2；结束后进程已停止 |
| 源码完整性 | 3,764 个固定文件继续通过 |

核心 Python 检查合计 79 项，Node 8 项；真实浏览器及后端烟测单列。没有将下面的旧题库失败计入通过项。

额外运行旧 `test_task_resource_execution.py`：11 项中 3 项通过、8 项失败。失败依赖离散数学题 `ex-01-01-003` 或证明题，当前心理学题库按教材实际情况为空。进一步以离散数学模式运行时，导入阶段因 `knowledge/textbook_text` 等旧正式资源已归档而失败。确认是原测试对旧教材资源的依赖，本批未恢复/覆盖正式教材，也未为得到绿色结果伪造题库；这组专项回归仍待按现有教材重建隔离夹具。

浏览器使用 playwright 技能及原 chat-lifecycle 隔离服务器。技能 runner 初次因尝试在只读技能目录写临时文件而被沙箱拒绝；改为复制 runner 到专用系统临时目录运行，未修改技能安装或申请扩大权限，最终检查通过。

### 复现与边界

在宿主目录执行：

```powershell
$env:DEEPTUTOR_HOME = Join-Path (Get-Location) '.runtime/deeptutor-turn-tests'
.venv-deeptutor/Scripts/python.exe -B -m unittest discover -s tests -p test_deeptutor_turns.py -v
.venv-deeptutor/Scripts/python.exe -B -m unittest discover -s tests -p test_deeptutor_sessions.py -v
.venv-gpu/Scripts/python.exe -B -m unittest discover -s tests -p test_deeptutor_projection.py -v
.venv-gpu/Scripts/python.exe -B -m unittest discover -s tests -p test_deeptutor_integration.py -v
.venv-gpu/Scripts/python.exe -B -m unittest discover -s tests -p test_task_api.py -v
.venv-gpu/Scripts/python.exe -B -m unittest discover -s tests -p test_clarification_tasks.py -q
node --test tests/chat-transport.cjs
.venv-deeptutor/Scripts/python.exe -B scripts/check_deeptutor_sessions.py --turns
```

真实烟测结果：`artifacts/deeptutor/phase-b2-smoke.json`。原页面浏览器检查：`tests/browser/chat-lifecycle.cjs`（需 Playwright 与本机 Edge；自建隔离 HTTP 服务）。

未修改实际 `.env` 或开启生产同步，未重启已有应用；临时烟测服务和浏览器均已关闭。本批没有调用真实模型，没有导入上游正式知识库，没有接完整 Markdown/上游消息组件，也没有完成心理学真实模型黄金集。后续 B 工作优先接这些生成与知识库功能，再完成富文本和全链路验收；整个 B 尚未标记完成。上游仅保留协议版本/来源指针，不含可复原的教学正文；旧协议指针的物理清理仍需后续维护策略，当前通过宿主删除/版本门禁拒绝恢复。

## B 教材知识库与模型生成小阶段（2026-10-19）

本阶段直接复用上游 Obsidian create_note/search_notes/read_note、KnowledgeBaseManager.register_obsidian_vault、CourseService.attach_resource、LLMConfig 和隔离 Provider。保留原页面、教学策略、精细引用和质量检查。

- 正式教材 1,465 个规范 chunk 发布为不可变 Markdown vault；校验原文件、11章 PDF、索引及每个发布文件哈希。换版新建目录，重复发布幂等。原生课程挂载按学生隔离，冷启动挂载在线程执行。
- 检索只返回规范 chunk ID；宿主校验索引版本并回原 SQLite 读取正文，原结果优先，最多补充两条。当前是文本检索，vector_indexed=false，不宣称向量检索。
- 原 LLMClient 可通过共享凭据调用本机生成网关；上游隔离 Provider 读取服务端模型配置。限制消息、模型、大小、PNG 图片及超时，不接远程图片/任意工具/浏览器密钥。失败不绕过网关，图片失败不做无图降级，截断仍由原逻辑识别。
- 用户明确授权将教材片段、图片和教学上下文发送至当前 DeepSeek 配置；没有修改实际 .env、学习数据库或默认开关。

实际检查：DeepTutor 相关 Python 测试 45 项、原任务 API 18 项、Node 传输 8 项全部通过；固定源码 3,764 个文件完整性通过。45 项包含新增生成 7 项、知识库 6 项及原 A/B 会话、回合、投影回归。

独立真实模型案例使用“随机分配如何帮助控制无关变量？请只给我一个提示”。真实教材检索、上游模型生成、精细引用定位和原 QualityChecker 全部通过，一次生成即通过质量检查。结果位于本机忽略目录 artifacts/deeptutor/phase-b-generation-smoke.json；临时后端结束后关闭，不写学生学习记录。

为本次验证，使用原 build_index 在 .runtime/deeptutor-generation-smoke/citation-index.sqlite3 构建完整隔离索引：11章、4,273 个块，4,187 exact、7 ambiguous、79 unmatched。未把歧义或未匹配块标为精确，也未将隔离索引设为生产默认。

复现：先用独立解释器执行 scripts/publish_deeptutor_course.py --home .runtime/deeptutor-generation-smoke；用原 knowledge.citation_index.build_index 构建该目录的新 citation-index.sqlite3（已存在则不能覆盖）；再执行 scripts/check_deeptutor_sessions.py --generation。需本机有效模型密钥及教材，详细开关见宿主 README。新增两个开关默认关闭。

未完成：完整 Markdown 组件、上游完整 AgenticChatLoop、向量索引、真实图片问答和完整心理学黄金集。因此没有把 B 标为整批完成或切换默认入口。旧离散数学资源专项失败仍见上一阶段记录。

按用户新要求，此后每个验证通过的小阶段自动提交并推送。本次一并保存此前尚未提交的 A/B 接入源码和运行所依赖的当前心理学课程代码；教材、数据库、运行数据及已有旧文件删除不纳入提交。

## B3 聊天富文本小阶段（2026-10-19）

直接导入固定上游 SimpleMarkdownRenderer、markdown-renderer-core、markdown-display、latex、latex-normalize 等完整组件/工具源码，不改写 vendor。现有 reader 环境新增独立 Vite 聊天入口，使用上游版本 react-markdown 10.1.0、remark-gfm 4.0.1、remark-math 6.0.0、rehype-katex 7.0.1；共享宿主 React 18 和 KaTeX 0.19。Markdown 与公式在浏览器内同步生成 HTML，再由原 ChatMessageRenderer 更新正文，不引入第二套消息存储或 React 组件根。

支持标题、列表、表格、删除线、只读勾选列表、块级/行内代码、中英文强调、原有 ==高亮==、行内/块级公式。宿主补齐上游基础组件的单行围栏代码显示。原始 HTML 不执行，图片不产生网络请求，工作区/不安全 URL 转为文字；普通 HTTP(S) 外链采用 noopener noreferrer。正文引用只触发同一消息已有来源按钮；未保存的标号不会借用其他消息或工作区来源。原 PDF 版本和证据检查继续负责跳转。

保留现有页面和互动组件生命周期；进度变化使用 WeakMap 缓存避免反复解析正文，消息不再被引用后缓存可随其释放。阅读器跳过已排版富文本，练习反馈仍可排版其他旧公式。资源加载失败时保留原基础正文显示。生成 CSS 约 1.79 kB，脚本约 555 kB（gzip 约 171 kB），公式字体直接复用原 reader.css，不再重复打包。依赖许可自动汇总至前端 THIRD_PARTY_NOTICES.txt。

本阶段检查：
- 两个构建均通过；预期的 Next.js use client 指令被 Vite 忽略，不依赖 Next.js 运行时。
- 真实 Edge + Playwright 扩展 chat-lifecycle 全部通过：20 次进度只在正文改变时重新解析；保留焦点、组件、折叠、滚动和历史；真实页面断线恢复只发一次生成请求，删除后拒绝恢复。
- 标题、列表、表格、勾选、代码、中文强调、高亮、公式、公式/代码内引用保护、HTML/URL/媒体限制、同消息来源跳转全部通过；390px 长表格和长代码不撑破页面，已检查本机截图。
- 实际加载阅读器构建产物验证不重复排版富文本；旧公式仍渲染，练习提示引用保持原入口，危险 TeX 不产生可执行链接或媒体。
- Node 传输 8 项通过；原基础显示降级自检通过；固定上游 3,764 个文件完整性通过。

浏览器测试使用 API 替身及临时独立服务，未写学生数据库、未调用真实模型、未修改实际 .env；结束后测试浏览器与服务关闭。现有 8000 服务未重启。前端刷新即可使用，新模型入口仍默认关闭。

详细方案与复现见 MARKDOWN_STAGE.md 和宿主 README。本批没有接 RichMarkdownRenderer 的代码主题、Mermaid、原生工作区附件或完整 AgenticChatLoop，也没有完成完整心理学真实模型黄金集；这些继续属于后续阶段，B 整批未标记完成。按用户要求，本小阶段验证后自动提交并推送。

## B 心理学真实模型代表性黄金集（2026-10-19）

新增 scripts/check_deeptutor_golden.py、9类合成案例及8项判定自检。复用原API、TaskService、教学/质量/证据规则与DeepTutor网关、知识库、会话和回合，不构造另一套教学流程。每次新建隔离数据库/课程发布/裁图目录，CPU检索，关闭后台记忆worker和附加图解；实际.env和既有8000服务保持原状。

初轮8类检查暴露提示属性误读与数据缺失被误路由为任务澄清。修复后相关2类真实重跑通过。随后逐条对照原文发现选区解释无依据地排除了选择性自变量；在共用心理学课程规则中限制局部定义的过度泛化，并新增分类边界回归。没有把失败产物覆盖成成功。

最终完整运行20261019T011227Z-4a5cb9的9类均通过：概念、三类变量、操作性/选择性分类、被试间/被试内设计、提示、文字选区、真实公式图片、同会话追问、缺少数据拒答。共43次生成网关、10次知识库调用，6次成功图像模型输入；20条引用均exact，核验原文、坐标和教材版本。重复请求不新增生成，原API事件重放及其他学生访问拒绝通过，临时worker已停止。当前验收函数又对最终原始记录重新核对通过；Codex对照了回答、原文与公式图片。

专项回归96项通过：黄金判定8、澄清29、路由10、充分性22、心理学问答9、任务API18。本次并未宣称全量旧教材专项全部通过。正式模型默认入口未切换，未做全教材穷尽、生产并发或CUDA性能验收。完整AgenticChatLoop、向量索引及后续批次仍保留。

详细复现、各例结果、初轮问题和最终产物/索引SHA-256见GOLDEN_VALIDATION.md；原始回答、教材引句、图片及学习库只留本机.runtime，提交仅含代码、合成问题及汇总文档。按用户要求，本阶段验证后自动提交并推送。

## B 原生 AgentLoop 受限试点（2026-10-19）

教材回答和 PDF 选区讲解已接入固定上游的 AgenticChatPipeline/AgentLoop。工具 schema、调度、多轮协议、上下文保护、截断续写与输出过滤继续复用原生代码；宿主保留教学计划、提示、充分性、质量、教材版本、引用及保存规则。每请求只注册读取本轮证据的工具，首轮指定准确工具名；草稿与工具正文仅留请求内存，不发前端，不写原生会话。最多6次模型请求，期限最多180秒。

复用原生 finish_instruction 钩子在结束前检查宿主原字数预算，超长重写，不截断；禁止移除图片/工具降级。临时传输错误复用原生有限重试，耗尽后拒绝发布兜底文本。普通 Provider 网关也开启一次0.5秒临时重试，期限与图片要求保持原样。回合投影等待与既有会话绑定对齐到至少25秒。

真实案例暴露并修复了工具名被误设为auto、公式超长、对参照点差异的无依据数值推断，以及“不要编造数据”被误判为no_full_answer。生成/质检共同约束公式比较范围，任务执行层有限校正准确性否定句；明确仅提示、只说思路及服务端hint范围保持有效。黄金判定新增真实原生轮次与完整公式回答范围检查。失败原始记录均保留，未改成成功。

针对性回归共94项通过：原生执行14、普通生成7、黄金判定10、个性化8、心理学问答9、任务API18、质量发布保护6、任务执行22。最终分批接受9类真实案例及19条exact引用：20261019T062531Z-fe5efc中7类，20261019T063310Z-2aa2dc的追问，20261019T065303Z-6af00b的公式。各次接受报告的幂等、事件恢复、跨学生拒绝及进程停止检查均通过。完整运行中的超时和人工拒绝项没有被覆盖；修复后仅复跑受影响案例，未声称最后有一份完整9/9报告。

最终公式报告SHA-256：e40144963a24ebd8a4acea248bfc079fb410c42bf77d84aac434622d55f054f5；原精细索引SHA-256仍为8b3b6bad671f626d1f96017e4fe6c3cf5854ac647b16780dbefb18696ce4a666。详细复现、边界及全部失败记录见AGENTIC_STAGE.md。原始答案、引文、图片和数据库只保存在.runtime。

本阶段不修改实际.env、不更换现有页面，不启用默认模型入口；DEEPTUTOR_AGENTIC_ENABLED默认为0。未开放全库自主补查、通用工作区和外部工具；宿主取消尚不即时中断worker中已发出的模型请求，但仍阻止保存且受总期限限制。模型路由与质检并非可靠性证明，未做全教材、教师审核、生产并发或新旧性能对照。与本阶段无关的工作区修改继续保留，按用户要求仅提交并推送本阶段文件。
