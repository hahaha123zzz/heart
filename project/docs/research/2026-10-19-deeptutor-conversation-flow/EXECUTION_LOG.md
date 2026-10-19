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
