# 单条用户消息的完整处理：DeepTutor 与本项目深度对照

日期：2026-10-20。上游：`D:/deeptutor`，HEAD `6cf793bd868ba5ecbe64722936d4be8fab5a01df`。本项目对照主目录与集成 worktree；核查期间远端跟踪主线/集成 HEAD 已推进到 `2b5d5d6`（含 Q5 接线 `32213b6`），主目录本地 main 仍为 `95b956a`。本报告不将磁盘代码等同于8000进程正在运行的版本。

## 1. 结论

DeepTutor 先由宿主代码校验并准备本轮资源、状态与可用工具，再在对应能力的提示词和规则下执行模型/工具循环。它没有一个每轮强制经过的全能意图识别模型，也不是每句都自动创建计划、检索、测评或写画像。

本项目已经具备任务收据、教材导航、Q3循环、Q4授权注册和Q5初步状态接线。主要差距是：循环输入不完整、学习策略/工具不足、全书规划入口仍简化、资源入口分裂、结果和状态没有像上游一样充分形成下一轮的有效上下文。换检索后端不能独自补齐这些差距。

## 2. 上游实际调用顺序

### A. 模型调用之前：宿主代码执行

1. WebSocket/CLI/SDK 适配为 `TurnRequest`，进入 `app/service.py::TurnApplicationService.start_turn`。校验结构、当前作用域，按client_submission_id处理重复提交；建立/恢复会话和任务，防止同一请求重复执行。
2. `services/session/turns/request_preparer.py::TurnRequestPreparer.start_turn` 检查工作区状态、语言、会话偏好和资源绑定。当前工作区/学习路径属于持久约定，不能由过期页面悄悄改写。学习路径有关请求还涉及绑定、题卡作答提交及路径写入租约。
3. 能力按请求/会话/工作区约定确定。`runtime/capability_routing.py::route_explicit_quiz_request` 仅是可选、默认关闭的窄规则自动分流：明确生成题组可从chat到deep_question；有工作区绑定时不自动分流。“考考我”不等于创建静态题组。
4. `services/session/turns/executor.py::TurnExecutor` 准备历史、附件、选定教材、笔记/历史引用、来源清单、课程约定、工具/技能、模型配置等。`ContextBuilder` 按预算选择历史并必要时压缩，保留可回放模型协议。
5. 记忆/画像按条件加载：选定记忆可读L3；学习日志在适用场景注入；账号learner画像在适用账户条件下注入；Mastery路径画像由mastery状态提供。不能称所有用户每轮都自动拥有完整画像。选区辅导会隔离无关全局记忆和自动工具。
6. 构造 `UnifiedContext`，由 `TurnEngine.execute → ChatOrchestrator.handle` 运行指定能力，缺省为chat。普通chat和Mastery共用循环基础设施，但Mastery使用自己的基础教学提示词和工具扩展。

### B. 进入回答循环前：挂工具和场景预处理

7. `agents/loop/pipeline.py::AgenticLoopPipeline.run` 准备知识库清单、延迟工具、工作区与执行权限，按每轮可信状态构造工具视图。注册了100个工具不等于这轮开放100个。
8. 普通chat若有可读文字来源，`capabilities/explore_context/capability.py` 激活受限预读，用read_source按本轮问题读取必要材料，返回客观简报；正式回答循环一般不直接挂read_source。纯图片不按文字来源预读处理。Mastery资料不直接触发这个预读，而由Mastery拥有read_source按需读，避免每轮固定调查所有教材。
9. Mastery的 `loop.py::pre_loop` 在首个回答模型调用前读取本轮mastery_status，并核对读取前后路径/模式未切换，注入当前状态快照。题卡作答/跳过若已由运行时处理，会作为已完成结果告知导师，不能重复评分或重新出同题。
10. 根据场景可提供有界KB seed。模型消息由课程/模式规则、工具schema、历史协议、来源/记忆/日志/画像/工作区快照和当前用户消息组成。动态快照仅更新变化块，旧块不应覆盖新状态。

### C. 回答循环：模型决定动作，工具执行并返回

11. `agents/loop/agent_loop.py::AgentLoop` 请求模型返回文字或tool_calls。模型可能先检索、澄清、读学习状态、改计划，也可能无需工具直接答复；不是每条消息必检索。
12. `runtime/agentic/tool_dispatch.py` 校验/增补参数、同批去重，单assistant最多15次调用。先串行执行会改变路径/模式的工具，再普通并行工具，最后暂停交互工具，避免同批改模式后出题仍使用旧状态。限制是每批，不是整轮总共15次。
13. 服务端注入路径、资源和账户上下文，不让模型任意决定资源权限。失败结果仍回到对应role=tool消息，模型看结果后可以补查、纠正或说明限制。
14. ask_user使当前任务等待用户，答复替换原工具结果后继续同一任务；无等待接口的调用方可能降为可见问题后结束，不能宣称所有入口都支持同样的跨重启恢复。
15. 无tool_calls的有效回答通常结束；部分工具（例如Mastery出题）是本轮最后动作。循环有探索、收尾、强制无工具结束及上下文预算。存在协议/提供商兼容降级，不能把每次上游返回都称为严格证据核验通过。

### D. 回答后的持久化与下一轮

16. 保存实际模型/工具协议、来源、领域状态和会话事件；将有效答案与模型内部消息分别管理。正常完成会先提交主要事件/终态/消息，再向客户端发DONE，标题等后续元数据另处理。
17. 学习状态通过相应工具/运行时事务改变：讲解记录、偏好、评分、计划不是每轮自动全部更新。讲过不等于掌握，日志也不是成绩。下一条消息重新准备当前状态，而非只凭上一段文字猜测。

## 3. 模型可能执行的“指令”是什么

| 层次 | 由谁决定 | 具体例子与边界 |
| --- | --- | --- |
| 宿主硬规则 | 代码 | 请求校验、绑定和权限、ID/版本、重复提交、预算、题目状态和评分门槛；不是依靠提示词承诺 |
| 模式教学规则 | 提示词＋工具限制 | outline用于规划，study用于学习，review用于复习；只讲解不强制出题；出题后本轮结束；部分由工具模式检查强制，部分仍需模型遵守 |
| 动态事实 | 读取的状态/来源 | 学生基础、当前目标、待答题、资料可用性、原文内容；不能升级为覆盖系统规则的指令 |
| 工具动作 | 模型发起，代码授权执行 | 调用rag、mastery_build、learning_update等；不是直接在回复写一句“已保存”就真的保存 |
| 技能和外部工具 | 按需加载 | read_skill读技能说明，load_tools加载已授权schema后再调用；没有配置/授权不能凭工具名执行 |

## 4. 可能调用的工具：按场景核查

| 场景 | 上游工具 | 条件/用途 | 本项目当前对应 |
| --- | --- | --- | --- |
| 查教材 | rag / kb_files / knowledge_frontier | 有相应知识库，检索/清点文件/了解覆盖 | retrieve_course已接；KB清单与覆盖发现工具未同等接入 |
| 读附件原文 | read_source | chat预读或Mastery自有工具；权限绑定来源ID | 无同等通用来源预读链；Q2精确目标读取已存在 |
| 读教材页面/图片 | material_outline / search_material / read_material / view_figure / reader_goto | 阅读场景工具，读原文、看像素、导航高亮 | 选区/PDF/原图有专门接口，尚非统一阅读工具闭环 |
| 澄清 | ask_user | 必要信息缺失，暂停原任务再继续 | 已接并有部分页面验证；不能当正式评分题卡 |
| 偏好和记忆 | read_memory / write_memory | 有记忆时读，显式偏好按规则写 | 旧链路有记忆服务，但Q3实际工具注册未挂同等读写工具 |
| 学习接续 | learning_status / learning_update | 学习日志/目标/会话接续，不等同掌握 | Q2游标、Q5状态部分可替代，跨模式日志尚不等价 |
| 建/改计划 | mastery_build / mastery_revise / mastery_profile / mastery_mode | 资料、画像、outline及目标边界 | Q5已接9个基础工具，页面规划仍是单章草稿；缺mastery_profile等完整行为 |
| 切换学习目标 | mastery_status / mastery_paths / mastery_switch / mastery_leave | 当前路径、列表、切换/离开与恢复 | Q5有服务及部分工具；页面、画像与完整状态快照有缺口 |
| 考核与纠错 | mastery_quiz / mastery_grade / mastery_assess / mastery_skip_question / mastery_repair_question / mastery_defer_objective | 持久题卡、评分、跳题、申诉、延后分别处理 | 正式闭环未迁入；mastery_understood是本项目自述理解推进，不能冒充grade/assess |
| 笔记/题库 | list_notebook / write_note / question_bank | 有权限及资源，保存用户需要的学习产物 | 工具台账不等于实际挂入Q3 |
| 工作区和技能 | workspace_list/read/search/present/export、read_skill | 场景/授权限制 | 已接部分只读工作区和read_skill，呈现/导出未同等完成 |
| 外部增强 | web_search / paper_search / reason / exec / load_tools等 | 用户开关、provider配置、授权和沙箱 | Q4基础设施存在，多数provider/业务未接；不应全部开放才算学习可用 |

## 5. 我们现在每条消息实际如何走

`main.py::_execute_task` → `TaskService.run`：确认学生/账户、幂等收据、恢复待处理任务、构建历史/偏好/对象/目录游标，核查文档版本，建立任务及guard。

随后有多个入口：

- Q5开关开启且识别计划/确认/调整/理解请求时，先在TaskService中处理Q5动作；当前 `Q5Runtime.propose_chapter_plan` 默认第一章、每节取首目标，构造PlanDraft，不是调用LLMPlanGenerator完成全书个性化课程设计。首次有计划之后的其它新计划请求还需核查识别与路径生命周期，不能推断任意请求均完整支持。
- 普通聊天且 `LOCAL_AGENT_LOOP_ENABLED=1`：进入 `run_agent_loop_turn`，选Q5或Q2权威目标，挂工具，调用LocalAgentLoop；实际调用探索上限为4（类默认8），工具超时120秒；循环后经事实/引用发布门禁、保存对话和来源，更新已讲状态。
- 圈选、练习、可视化仍分别走专门入口；Q3关闭时普通聊天回到原Orchestrator。
- 原Orchestrator按 Router→目标→检索→证据充分性/补检索→教学策略/局部计划→生成→质量引用核验→保存处理。某些直接回答分支跳过LessonPlanner，证据拒绝也会在教学规划之前结束。

新Q3当前提示词主要为课程规则、循环协议、单个目标、工具清单；`seed_messages=context.history`。没有看到它完整注入旧链路的相关学习记忆、长期偏好、完整模块目标/学习画像、关系与复习状态。TaskContext中有preferences不等于模型消息中已使用preferences。

完成回合的模型协议存在loop_state/任务结果内，暂停恢复可使用；普通下一轮仍主要从可见对话历史构建上下文，未见与上游branch-aware model_history统一等价的回放实现。

Q3当前“只回答明确对象、不主动扩展、尽量400字”适合短问答，但未按教学规划场景切换；即便挂更多工具也不保证自动生成长篇全书课程。不能简单全局解除限制，应按学习任务调整提示和预算，保留普通问答约束。

## 6. 差距与实施优先级

| 优先级 | 差距 | 学生感受 | 应交付 |
| --- | --- | --- | --- |
| P1 | 每轮上下文缺少画像/有效学习快照 | 换个学生仍像同一个助教，重复讲、忘记目标 | 统一有来源、有预算、有版本的画像/记忆/模块/当前动作输入，检查实际模型请求 |
| P1 | 规划真实入口未调用完整生成链 | 只能单章目录推进，没有个性化主线/重点/时间安排 | Q5.16—19接通资料清点、画像、生成、验证、确认与实际执行 |
| P1 | 模式教学规则不完整 | 会回答但不主动衔接、补讲或引导 | 区分短问答、规划、讲解、练习、复习规则；Q3.10/Q5.13—15知识关联落地 |
| P1 | 工具能力缺口 | 模型只能查教材和追问，无法可靠记录/调整整个学习过程 | 优先接画像/日志/原文阅读/计划工具，再接题卡与评分，不必先开100个工具 |
| P1 | 圈选/普通聊天/练习状态分裂 | 同样“继续”在不同入口表现不同 | 保留正确专门处理，统一活动学习任务和来源绑定，验证跨入口接续 |
| P2 | 正常回合协议与动态快照恢复不足 | 多轮后遗失工具事实或沿用过期信息 | 有界模型协议/摘要回放、删除及换版失效；不把旧工具结果当当前状态 |
| P2 | 正式评估与复习未接 | 自述理解推进，不能形成完整掌握式循环 | 接题卡状态机、证据/评分/纠错、到期复习和只讲解边界 |
| P2 | 调用证据和部署身份不可见 | 无法知道新功能是否真的在8000生效 | 记录入口、能力、有效开关、工具、模型上下文摘要/来源身份及发布结果；敏感内容不公开 |

本项目的教材原文、版本和正式引用门禁有自身约束，不应为追求与上游相似而删除。上游普通chat没有一个统一的、每轮强制的独立事实质检器，不能称上游全流程均更严格。

## 7. 验证与证据范围

本轮重新运行上游6组测试：capability_routing、tool_dispatch_pause_ordering、tool_dispatch_events、ask_user、explore_context、context_builder。固定本项目 `.venv-deeptutor`、`PYTHONPATH=D:/deeptutor`、禁字节码/cache、显式pytest_asyncio插件，HOME及临时文件写本项目隔离 `.runtime`。

结果：**136 passed，2 warnings，10.32s**。这些是路由/协议/上下文与受控模型测试，不是真实LLM任意任务的保证。另两项前序专项：关系/策略40通过，路线/覆盖31通过，独立记录，不能拼成单次运行。

本轮没有修改业务代码、上游源码、服务开关、正式库或正在运行的LightRAG任务。未取得用户那次DeepTutor详细规划的工具轨迹，未验证8000加载的具体代码版本。源码快照和文件哈希见 `TURN_PROCESSING_SOURCE_AUDIT.json`。
