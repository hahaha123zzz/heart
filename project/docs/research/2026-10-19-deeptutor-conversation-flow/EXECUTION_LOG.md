# 完整原生对话实施记录

> 2026-10-19 路线修订：当前目标为整套代码集成，见 IMPLEMENTATION_PLAN.md（Q0—Q6）和 LOCAL_REUSE_CONTRACT.md。以下 P0/P1 是此前应用委托路线的历史记录，不计入新路线的功能完成。

## P0：基线、接入契约与质量口径（2026-10-19）

起点为 c639a4f。保留用户的完整调研、计划和 11/14/100 台账；没有覆盖无关工作区修改、旧课程删除、心理学教材及数据库。完整工作区状态只保存于本机隔离运行目录，不将文件内容或学生数据带入提交。

新增 scripts/check_deeptutor_native_baseline.py，以仓库固定副本运行原调研的6个上游测试模块，校验全部3,764个文件，登记 Python/依赖元数据及8000/18001监听状态，不读取密钥或源项目配置。此次8000监听、18001未监听，仅代表端口状态；SentenceTransformers未安装，不能宣称原生重排环境齐备。

复现命令（宿主目录）：`.venv-deeptutor/Scripts/python.exe -B scripts/check_deeptutor_native_baseline.py`。输出 `.runtime/deeptutor-native-baseline/20261019T071211Z-8d9a8f/`，包含 report.json、原始工作区状态、upstream.xml 和 upstream.log。实际225项：224通过、1失败、无collection错误或跳过；耗时308.91秒，CLI保留退出码1。

失败仍为 test_cold_start_stalled_provider_settles_with_bounded_retries[partial_stream] 的消费者事件断言，与原 VALIDATION.md 一致。未修改上游测试或将失败静默排除；此前已验证emit与异步消费时序的诊断继续保留。新增基线汇总自检1项通过，确保失败、错误、跳过不被算作成功。

本次report.json的SHA-256：ec8eef8a7ded9e21937ca21a9893d7cb151832dd601d58ec3b861aa564477893。

接入契约见 NATIVE_CONTRACT.md，明确原生与旧投影分离、工作区及课程作用域、submission去重、取消/答复命令、DONE尾部事件、正文持久化和独立发布状态。P1—P5后续负责逐项实现这些行为，契约通过不等于门禁已经实现。

质量优先落实为 QUALITY_BASELINE.md 与6组连续对话样本，复用原9类心理学问题；从P0建档，P3起做同模型同教材的新旧对照，不等P8才评估。此次没有运行在线模型、质量A/B、浏览器或原生RAG，不声称对话质量已经提高。

P0完成后按用户约定自动提交/推送；下一检查点接入P1内部原生持久化回合，仍不切学生默认入口。

P0已提交并推送：6c156cc。

## P1 检查点一：真实应用层的私有运行时（2026-10-19）

新增 native_contract.py / native_bridge.py，worker 注册原生 start/status/events/reply/cancel。通过真实 DeepTutorApp、应用容器、TurnApplicationService、TurnRequestPreparer/TurnExecutor、ContextBuilder、TurnEngine/ChatOrchestrator、协调器和 SQLite；没有调用旧教学执行链或受限 AgentLoop 来代替应用层。

实现宿主全键→原生账户/课程工作区/会话/submission/turn 的持久化映射及请求摘要。登记和 admission 串行，模型任务、事件订阅与用户等待不持有登记锁。同一请求完成/失败/取消后重发不重新执行；turn 映射尚未落库时查询原生 submission 认领。每次状态、事件、命令按完整宿主身份找映射，修改 task revision 或请求快照拒绝。

集成中确认原 SessionBridge 的合成身份没有原生模型 grant，单传 LLMConfig 无法通过学生模型门禁。改为直接复用原生 identity、grants 与 model catalog 创建保留前缀的普通账户和宿主模型授权，不提升管理员、不绕过模型门禁。旧投影身份和数据保持原样；新正文写入原生 data/users 私有账户与独立课程工作区。grant 默认禁止 built-in/MCP/CLI/exec，后续按阶段挂载。模型凭据只保存在服务端管理员 catalog。

固定上游协调器 admission 冲突抛出 RuntimeError 而非 ActiveTurnConflict，仅对该明确错误映射409；其他错误不吞掉。上游在已越过 DONE 的游标重放中会合成 terminal envelope，测试保留这一语义，不把它当新生成或断言必须空响应。未修改 vendor。

验证命令（宿主目录，PYTHONPATH 指向固定 vendor 和宿主）：`.venv-deeptutor/Scripts/python.exe -B -m unittest discover -s tests -p test_deeptutor_native_runtime.py -v`。11项全部通过，54.589秒，日志 `.runtime/native-runtime-tests.log`。模型回答用受控能力替换，标题模型替换为空操作，仍使用真实应用层和临时数据库，禁止意外联网模型调用。

覆盖：共享凭据/开关/禁止客户端模型和工具字段、真实正文持久化、事件游标重放、重复请求、映射缺口认领、失败/取消不重跑、多轮真实上下文接续、两个学生与两个课程并发隔离、同会话活跃冲突、澄清答复继续原回合和命令去重、取消到达执行协程，以及无租约活动行被原生服务回收为 worker_lost 后允许新执行。运行时还断言普通账户非 admin、实际解析为宿主选择模型。

宿主环境回归：`.venv-gpu/Scripts/python.exe -B -m unittest discover -s tests -p 'test_deeptutor_*.py' -v`，45项、6跳过，无失败；跳过项需要独立原生环境，新原生运行时另按上述命令验证。日志 `.runtime/native-host-regressions.log`。再次执行固定源码校验，3,764文件通过，仍只有已登记的原 factory.py 兼容补丁。P0记录的上游224通过/1失败仍保留，没有混算为本阶段全绿。

边界：DEEPTUTOR_NATIVE_ENABLED默认0，实际.env未改、已有服务未重启。内部接口登记memory_epoch/material_versions，但尚未与宿主权威版本、删除及发布流程联动；所有状态/事件标记pending_verification。当前只有文字答复，未接多问题卡、正式发布、学生页面、真实模型/RAG或质量A/B。本检查点完成P1.1/P1.3/P1.6，P1整阶段未完成；继续P1宿主任务生命周期、P2原生教材服务和P3页面闭环。

## 路线修订：整套代码集成，保持原目标（2026-10-19）

用户指出：希望直接复用项目代码，不希望将项目功能路由到 DeepTutor 应用；随后明确“可以整套地接入”，要求不能擅自改变执行目标。因此，本次修订保留整套能力范围、11/14/100完整台账、现有页面以及对话质量优先级，改变实现方式，不缩减为少数工具或仅提示词优化。

有效计划改为 Q0—Q6：Q0整理边界及调用点；Q1成组迁入上下文/提示词/回答模块，优先对话质量；Q2迁入教材解析/检索/来源；Q3迁入完整本地循环与澄清/恢复；Q4完成工具/扩展底座；Q5接学习、记忆、阅读、评分、解题和研究；Q6完成多媒体和整套验收。本项目 API、任务、课程和数据仍为权威，内部实现可以整块替换，不能重复跑两套回答流程。

旧 IMPLEMENTATION_PLAN.md 归档至 archive/NATIVE_RUNTIME_PLAN.md，NATIVE_CONTRACT.md 明确标为历史契约，新建 LOCAL_REUSE_CONTRACT.md；完整矩阵与质量口径已同步。旧 P0/P1 测试保留历史归属，不计作新路线能力通过。已提交实验代码尚未删除，其调用点清理列入 Q0.4，没有把文档改动冒充运行代码清理完成。

此前中断时尚未提交的开发涉及 .env.example、client.py、native_bridge.py、main.py，以及新建的 database/native_tasks.py 和 integrations/deeptutor/native_tasks.py。逐一核对 diff 后，全部备份到项目 .runtime/abandoned-native-host-20261019/，4个已跟踪文件恢复为本轮开始前的 HEAD，2个未跟踪文件移入本机隔离目录，未提交/推送这些开发内容。无关工作区修改、正式教材、配置、数据库、历史提交均未清理或覆盖。

本次交付为修订后的计划及一致的配套文档。验证范围为完整矩阵项数/名称保留、阶段和文档链接一致、待核验/停用路线说明、旧路由代码已撤出及暂存范围核对；没有运行模型或浏览器，不宣称对话质量已经提高。下一步按 Q0.4/Q0.5 和 Q1执行，不继续 P1应用委托路线。

## Q1-A/Q1-B：预算化上下文、提示词块与连续追问（2026-10-19）

本轮只接入对话质量所需的第一批模块，不改变 Q2—Q6 的能力范围。来源固定为 `project/vendor/DeepTutor`，实际迁入与适配如下：

| 来源（SHA-256 前 12 位） | 本项目落点 | 处理 |
| --- | --- | --- |
| `services/llm/context_window.py`（c1652a7760cd） | `agents/context_window.py` | 原样迁入，保留模型窗口表与预算解析 |
| `services/prompt/language.py`（8ade4d5f031c） | `agents/prompt_language.py` | 原样迁入语言指令 |
| `services/session/context_builder.py`（520b17920ea8） | `agents/conversation_context.py` | 改为同步显示行输入；保留整轮分组、预算裁剪、超过预算保留最新一轮和滚动摘要；摘要由本项目确定性生成，未启动上游应用 |
| `agents/loop/prompt_blocks.py`（70c0cabeb6a2） | `agents/prompt_blocks.py` | 保留具名块、空块省略、语言收尾；未迁入本轮尚未挂载的工具清单 |
| `core/context.py`、`services/session/model_history.py` | 仅作接口参考 | 其 `UnifiedContext`/完整模型回合概念用于本地设计；完整 `model_turn` 工具协议留到 Q3 |
| `services/session/ask_user_trace.py`、`provider_response_state.py` | 未迁入 | 依赖 ask_user 与 provider 回放，按 Q3 接入，未冒充完成 |

本地新增 `agents/followup_context.py`，把连续追问拆成可测试契约：简化上一轮解释、缩小比较范围、显式完整解释覆盖上一轮仅提示、准确性要求不等于仅提示。`ConversationRouter`、`TaskExecution`、`ResponseGenerator` 和 `TaskContextBuilder` 已接这些输入；`TaskContext` 历史从固定 4 条改为预算化最多 40 条，并新增 `history_summary`。常规会话从最近 2 个完成任务提高到最多 12 个，再按预算裁剪。

验证：

- 离线回归 `199` 项：除既有 4 项因心理学教材替换而失效的离散数学测试（`chapter-07` 文档不存在、练习目录为空）外全部通过；这 4 项在 Q1 前已同样失败，未算作本轮回归。
- 连续对话样本自检：`scripts/check_conversation_quality.py` 的 6 个样本结构、追问契约和预算摘要全部通过；`clarify_and_continue` 明确留到 Q3，`correct_and_forget` 留到 Q5。
- 真实模型本地链路（不是独立 DeepTutor 应用）：
  - `20261019T084522Z-3e1dc3` `explicit_hint_then_explain` 通过：首轮 `hint_only=true`、无新题；次轮 `explain`、尊重完整解释。
  - `20261019T085050Z-99b070` `simplify_without_switching` 通过：简化上一轮自变量解释，未改答检查题，引用保留。
  - `20261019T085625Z-14a93f` `comparison_followup` 通过：只回答被试内设计，不再引入被试间设计。
  - `20261019T085849Z-a0ad95` `accuracy_is_not_hint` 通过：`hint_only=false`，完整解释公式符号和参照点，未用自然流畅冒充数据。
  - `20261019T090554Z-ac15d2` 黄金集 `hint` 通过：只给核对提示，质量核验通过。
  - `20261019T090717Z-8877c1` 黄金集 `concept`、`variables`、`design`、`refusal` 通过；同轮 `classification` 因 260 字预算过短、`followup` 因历史未传入检查而失败，作为基线保留。
  - `20261019T091139Z-2f1ac7` 修复多子问题预算后 `classification` 通过。
  - `20261019T091329Z-46a33d` `concept` + `followup` 通过：追问沿用上一轮自变量解释并简化。
- 失败记录：`20261019T084304Z-31cd97` 首次 hint 运行暴露出“只给提示”未进入 hint 作用域，已修复并复跑；`20261019T084609Z-092614` 首次简化运行因路由把追问标为 statement 而质量拒绝，已修复并复跑。两次失败均保留在原运行目录，没有改写成成功。

仍未完成：`ask_user` 问题卡与答复恢复、完整 provider 模型回合、选区/视觉入口的摘要接入、Q2 教材检索重排、Q3 AgentLoop。Q1 的 M1 只证明普通对话和连续追问在本项目页面链路中使用了迁入模块；不把它写成整套能力完成。

### Q1 页面级连续追问复验

使用现有页面、独立端口 `8010` 和隔离数据库 `.runtime/q1-page2`（`DATABASE_URL`/`COURSE_DATABASE_URL` 均指向临时文件），未触碰现有 8000 服务或正式学习库；测试后已停止该进程。

- 首次页面运行：第一问“请解释教材里的自变量，不要出题。”以 39 秒完成并带教材引用；第二问“没听懂，请换一种更简单的说法。”在 80 秒后 `quality_rejected`。原因是阅读器仍把当前章节作为 `knowledge_point`，质检按章节目标要求回答，未把追问目标认定为上一轮自变量解释。
- 修复：`orchestrator` 在简化追问时把本轮计划目标改为“用更简单的说法重述上一轮助教解释”，并在质检上下文写入 `followup_simplify`、`followup_target`；`QualityChecker` 明确不得因未覆盖当前阅读章节而拒绝。新增 `test_quality_guard` 回归用例。
- 复验：同一页面流程第一问 47 秒完成；第二问 75 秒完成，回复变为“自变量就是研究者主动改变的那个条件……”，保留教材引用 [2]，未引入新章节或新题。页面状态为“已完成”，无“处理未完成”。

页面级复验证明 M1 的普通对话与连续追问已在本项目页面链路使用迁入模块；仍未覆盖浏览器中的选区/视觉入口和 Q2—Q6 能力。

### Q1 页面修复收尾核对

按最新执行进度核对，本地已存在主体提交 dc278fe；此次仅收尾7个文件：quality_checker.py、orchestrator.py、两份相关测试及本目录3份Q1文档。没有混入main.py、教材删除或其他未提交修改。

提交前复跑test_conversation_context.py（25项）和test_quality_guard.py（7项），32项全部通过；未重跑真实模型、浏览器或199项大范围回归。已有页面运行和数据漂移记录保持原有证据归属。Q1.1保留未完成，7个文本案例与剩余2个选区/视觉案例分开；M1达标不等于Q1整阶段或Q2—Q6完成。

## Q2-A：本地混合检索与来源范围（2026-10-19）

成组迁入DeepTutor的LlamaIndex配置、混合检索/RRF和重排模块，改用本项目配置、只读教材SQLite、现有BGE模型、TextbookChunk和来源体系。原心理学检索可通过RAG_RETRIEVAL_ENGINE=local_llamaindex选择本地实现，不启动或委托完整DeepTutor应用；默认和实际.env仍保留当前检索。全部来源/目标哈希、增量依赖锁及许可证说明已登记。

新增14项专项通过，最终相关回归81项全通过。真实CPU embedding与重排的4组案例在同一次完整运行通过：自变量、被试内/被试间、内部/外部效度、教材外拒绝；实际hybrid且重排applied，索引1,465片段/512维且前后SHA未变，无聊天模型调用或学习库写入。首次运行发现表格缺少原文范围，保留失败报告，修复后另起完整复验。详情、命令、耗时及报告哈希见[Q2检索模块检查点](Q2_RETRIEVAL_STAGE.md)。

Q2仍在实施。原件解析、摄取/全量发布、完整签名绑定、视觉输入和页面生成验收尚未完成；本检查点不标记Q2.1—Q2.6整项或后续能力完成。本轮不混入已有章节学习文档、main.py或教材删除等其他修改。

## Q2-B：章节与下一目标基础导航（2026-10-19）

依现行 Q2.7/Q2.8 优先项，提取 DeepTutor 的 SyllabusUnit 数据结构，并把本项目真实章/节/叶子标题、正文来源和既有任务收据接入模型识别之前。普通对话可按中文章号、数字章号、章节名称启动；下一知识点先选择目标再读正文；下一节、下一章分层处理。没有路径不猜下一概念，路径结束不报教材缺失，讲解与掌握分别记录。现有页面、API 和学习记录所有权不变。

最终相关回归 **125 项全部通过**（`.runtime/q2-navigation-final-regressions.log`），含导航专项20项、心理学教材/检索、Q1追问、任务执行和质检。真实模型完整三轮在 `.runtime/course-navigation/20261019T125852Z-1d2943/report.json` 全部通过：第一章启动、下一教学点、简化追问；阅读器停在第二章未带偏，三轮均有PDF引用，掌握分未增加，正式索引SHA未变。发现并修复的来源标题失配、简化追问丢失目标、260字预算不足均保留原始失败运行，不合并挑选成功结果。

详细迁入、命令、耗时、报告哈希及限制见 [Q2导航检查点](Q2_NAVIGATION_STAGE.md)。基础接续仍沿用默认30分钟任务TTL，长期课程位置与Mastery路径未完成；本轮未启动常驻服务或做浏览器验收。Q2.7/Q2.8完整验收、Q2其余项和Q3—Q6仍保留，不据此宣布完成。提交仅含本检查点代码、测试、来源记录和两份阶段文档；不混入main.py、用户未提交计划或教材删除。

## Q2-C：统一新回答证据协议与恢复（2026-10-19）

按新增 Q2.9 实施：默认没有已发布坐标索引时直接核验当前 PDF/原文，不再自动退回旧引用；已有活动索引保留校验，显式 off 保留可见的旧协议回退。复用现有定位、选择和证据包，发布时按真实原文范围去重并同步重映射正文、来源和结论绑定，普通聊天/选区入口统一保存；同节不同引句不删除，无引用检查题不硬加卡片。失效仅投影展示、禁用跳转，旧历史不伪升级、不覆盖原记录。

最终相关回归 **154 项通过**，新增发布/存储专项12项；真实现有页面在隔离8010/隔离数据库中完成普通回答、引用点击、刷新恢复和真实选区解释，最终17项页面检查通过。另核对实际PDF、页码、矩形和可见高亮；新协议下章节启动/下一目标/简化追问三轮也全部通过。保留旧协议baseline、首轮测试替身失败和选区首稿质检失败。补齐证据不足的拒答分支后，另一次回归出现原30秒超时；剖析确认整份PDF被反复规范化，复用版本化文本/映射后原上限不变，完整154项与17项页面检查通过。所有运行分开保存，没有将不同运行拼为一轮成功。

原始用户截图的输入/响应未取得，baseline仅复现相同配置下的旧协议分支。原始报告、耗时、SHA、命令和发布/性能边界见 [Q2引用检查点](Q2_CITATION_STAGE.md)。未修改正式教材、RAG索引、学习库、实际.env或用户未提交main.py；8000服务未重启，测试服务验收后停止。Q2其余任务及Q3—Q6不标记完成。
