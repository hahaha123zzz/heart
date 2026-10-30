# 输入理解层与后续多维分类器：源码调研与衔接建议

日期：2026-10-29。性质：调研与建议，不是已批准实施计划或功能交付。

后续深度调研已补充真实HTTP/浏览器、原生存储、模型解析及多项目对照，见 [INPUT_UNDERSTANDING_DEEP_AUDIT_20261029.md](INPUT_UNDERSTANDING_DEEP_AUDIT_20261029.md)。涉及实际运行行为时，以该报告分层证据为准；本文件的纯函数异常不能直接解释为整条链路误评分。

## 1. 结论与基线

建议一起设计、分步实现、联合验收。输入理解负责保留原话、确定对象、任务顺序与约束；分类器补充语义标签；现有业务服务负责执行与状态写入。不要新增一套 AgentLoop，也不要把全部输入固定串行送进“改写模型→理解模型→分类模型”。

用户确认：多维分类器的维度与标签目前尚未确定。下文维度仅为讨论候选，不能视为既定产品定义。

- 项目核查基线：本地 main `c701670`，已包含 TA1—TA4 的代码提交。用户所给方案以 `fe00703`/8137 为背景，不能直接用作当前缺口清单。
- 核查工作树存在其他窗口未提交的 `agents/adaptive_tutoring.py`、`agent_loop.py`、`agent_loop_service.py`、`teaching_policy.py` 修改。这些差异主要涉及禁考措辞、协议过滤与复习取证；本轮只读，不纳入已提交能力声明。
- DeepTutor 本地源码：`D:\deeptutor`，HEAD `6cf793bd868ba5ecbe64722936d4be8fab5a01df`。所核查 context/pending/routing/grounding 四文件没有本地 Git 修改。
- OpenMAIC：实际仓库为 `F:\openmaic\OpenMAIC`，HEAD `d128ef67c920571a86ce8a7c0430185689ab3d45`。阅读磁盘上的消息、澄清及恢复文件；未据此声明其最新线上版本或整个仓库无修改。
- 本轮未检查 8000 进程实际加载提交，不把 main 的新增能力等同于运行服务已启用。TA4 文档明确保留正式启用与 NT3/TA5 边界。

## 2. 现有输入链路并非空白

```text
ChatRequest → main._run_turn → TaskService
  ├─ 请求重放、待澄清任务恢复、revision/epoch
  ├─ _context / TaskContextBuilder：历史、偏好、教材对象、游标、教学快照
  ├─ Q5 计划生成/确认/本次安排等分支：部分直接返回
  └─ main._execute_task_turn
       ├─ 文本选区 → SelectionLoopInput → Q3
       ├─ 普通聊天且开关开启 → Q3：导航/用途规则/TeachingTurn → AgentLoop
       ├─ 练习入口 → 专用辅导
       └─ 旧 Orchestrator → ConversationRouter → TaskUnderstanding / TaskExecution

另有题卡/测评/复习动作 API → 原生适配与受控命令；不全经过聊天入口。
```

关键结论：只改 `ConversationRouter` 不会覆盖普通 Q3 聊天；只改 `run_agent_loop_turn` 又会漏掉 TaskService 提前处理的计划分支与专用动作 API。统一的理解结果必须在分流之前形成，并能被这些路径消费。

## 3. 已有能力、实际缺口及复用边界

| 能力 | 当前实现 | 缺口/建议 |
| --- | --- | --- |
| 输入与对象协议 | `models/chat_request.py` 已有选区、阅读位置、小题、可视化对象、task_id/revision、selected_option | 没有统一的输入事件来源、分支父关系及规范化结果协议；不要重复发明请求身份 |
| 可信教材/题目对象 | `TaskContextBuilder.build` 校验章节、选区、小题版本；构建 TaskObject | 对象种类未覆盖独立 figure/example/assistant_claim/teaching_step；对象上无 introduced_turn/active/绑定依据等统一属性 |
| 指代候选 | `TaskService._read_context` 从同会话已完成任务恢复已校验对象，最多4个 | 候选来自仍有效的任务；不是永久对象注册表，TTL 后历史指代可能丢失；缺统一消歧优先级 |
| 输入识别 | `ConversationRouter` + `TaskUnderstanding` 含 student_move、学习意图、target_refs、约束与缺失槽 | 主要属于旧链路；最多3个 learning_intents 是顺序标签，不能表达对象各异、依赖与暂停恢复 |
| 服务端验证 | `_validate_task` 拒绝未提供的对象 ID；`build_execution` 再检查引用 | 应保留并收敛到统一输出边界，不增加新的回答生成/撤回门禁 |
| 教法/连续追问 | `followup_context.py`、`resolve_teaching_mode`、`analyze_teaching_turn`、selection_loop | 同一句话可能由多个模块各自解析；尚未共同消费一份理解结果 |
| 答题 | `agents/deeptutor_learning/pending.py` 已迁入 DeepTutor 选项解析；另有辅助 TeachingTurn 与原生测评命令 | 不能再次复制 pending 形成第三份；解析函数存在不等于所有聊天路径都消费它 |
| 偏好 | 已有 InteractionPreferences、临时覆盖、已确认持久偏好及 TA1 溯源 | 自然语言同时表达“以后”和“本题”时，缺统一的不同作用范围表示；持久修改仍须走现有确认流程 |
| 澄清/恢复 | TaskService、ask_user、loop_state、请求收据、revision/取消 | 继续扩展已有恢复协议；需要保存部分理解结果、待解对象以及未完成任务，不能重新解释“第二个” |
| 正式学习与复习 | 当前已包含原生授权、题目/作答/评分及复习适配代码，带独立启用边界 | 不是再建 teaching_tasks 替换它；理解层只提出候选动作，不直接写成绩、掌握或复习队列 |
| 分支隔离 | 前端 tabSessionId、BroadcastChannel 防重；后端按 student/session 查任务 | 不能等同于已实现主对话/侧栏父子分支与共享对象权限；侧栏侧边布局也不等于独立对话 |
| 多维分类 | 当前有路由、教法、困难、偏好等分散字段 | 尚未发现独立、统一、有版本的多维分类协议；先定职责再定标签 |

## 4. 外部源码实际能借鉴什么

### DeepTutor

1. `deeptutor/core/context.py`：`UnifiedContext` 与 `TurnRuntimeContext` 分开，后者持有运行回调、私有模型历史等。适合借鉴“可持久化理解结果不放运行时句柄”的边界；不应为此替换现有 TaskContext 和原生桥接。
2. `deeptutor/learning/pending.py`：区分选项标签映射、提交解析、是否构成真正作答。项目已在 `agents/deeptutor_learning/pending.py` 迁入，SOURCE_NOTICE 指向同一固定提交。应复用现有迁入件并补边界，而不是重新移植。
3. `deeptutor/runtime/capability_routing.py`：`route_explicit_quiz_request` 仅对明确生成题集请求路由；处在 workspace 时不自动切走。这是保守分流的小函数，不是完整输入理解器或多维分类器。项目可借鉴“活动任务承诺优先”。
4. `deeptutor/reading/_grounding.py`：`normalized_with_map` 保留空白折叠后的字符位置，`selection_range` 定位原文。适合局部定位算法；不是中文纠错、否定识别或一般指代消解系统。不要再实现一套与现有 PDF 定位冲突的坐标系统。

DeepTutor 使用 Apache-2.0；直接迁入的新代码仍需记录来源、固定 SHA 和修改边界。上游已有代码也要测，不能将“来自成熟项目”当成正确性证明。

### OpenMAIC

- `lib/server/agent-runtime/user-messages.ts::listAgentUserMessages` 从权威事件恢复 text/materials/elementRefs/courseRefs，避免兼容投影漏掉引用。这支持“保存原始对象引用，而非只保存文字”。
- `ask-user.ts` 明确结束本轮，答案作为下一条消息；本项目已有暂停恢复，优先扩展其结构化数据。
- `resume.ts` 区分 user/toolResult/未完成 assistant，并修复缺失工具结果；源码明确 at-least-once，需要有副作用的工具保持幂等。
- MIT 许可；适合参考协议和恢复语义，不建议把 TS/PostgreSQL 运行时直接迁入 Python/SQLite。

Rasa/Semantic Router/LangGraph 本轮未重新核查源码、版本或许可；不作为必须引入的依赖。本文结论来自本地项目及上述已阅读源码，不依赖附件中网页引用的真实性。

## 5. 附件方案需要修正的地方

1. **独立模块不等于独立状态系统。** 初版理解记录可随已有任务 context/result 和收据持久化；暂不一次新建 turn_understandings、conversation_branches、teaching_tasks、context_references 四套表。确有跨任务长期对象检索或独立侧栏需求时再增加对应存储。
2. **GroundedTurn 必须分阶段构造。** 理解阶段产出对象/任务/约束和待分类字段；分类器只补空缺语义标签；最终验证生成可执行计划。不能要求两个模块各自产出完整解释，也不能让分类结果覆盖已验证的对象身份。
3. **原话、检索查询、执行请求分开。** raw_text 不改；normalized_text 保守规范化；retrieval_query 可附已确认对象与别名；不得把改写文本当用户作答证据。
4. **标签不是授权。** “APPLICATION”“attempt”“困惑”不能自动触发评分、掌握写入、下一目标或持久偏好修改。
5. **对象注册不需要复制教材全文。** 保存可核查 ID、类型、来源和权限绑定；沿用 Q2 SourceRef、教材游标、原生 interaction 身份。assistant_claim/example 需要先有真实记录才可引用，不能给旧文字随意补一个看似确定的 ID。
6. **branch_id/session_version 不能凭空成立。** 当前主要是 session/task revision，加上路径/原生各自的 revision。初版采用明确的多版本快照，不用一个未经实现的全局版本号取代所有 CAS。
7. **不要把“这个实验没控制好”预设为 APPLICATION。** 当前类别还没定，且可能是评价、质疑、寻求核对。先绑定实验、保留具体控制问题未知；认知目标与主意图再按标签定义决定。
8. **不要默认增加两次模型调用。** 简单规则不调用分类 LLM；复杂情况尽量在一次结构化解析中补齐语义标签，再本地验证。BGE 仅作候选，必须用真实标注样本校准拒识阈值；不能把向量分数当正确概率。
9. **不恢复昂贵的回答门禁链。** 输入对象、否定、作用范围、版本与命令校验发生在执行前；继续使用现有回答发布边界，不为本改造额外生成草稿再撤回。

## 6. 两部分如何分开做而不损失效果

一起设计接口，按依赖顺序交付；可以由不同窗口工作，但共享入口与状态文件应由一个集成窗口负责。

```text
输入事件 + 可信状态摘要
    ↓
确定性绑定/规则解析 ──明确──→ 语义字段按需补充
    └─复杂或歧义──→ 一次受限结构化解析（候选ID + 任务 + 语义标签）
    ↓
最终 GroundedTurn + classification（带各自版本和依据）
    ↓
本地验证 → 现有 TaskService/Q3/计划/测评动作适配 → 既有执行器
```

建议最小协议：

| 数据块 | 必须保留的内容 | 写入权 |
| --- | --- | --- |
| envelope | request_id、原文、输入方式、经过服务端验证的对象载荷 | 输入适配器；身份从既有服务端绑定取 |
| state_snapshot | session/task/path/interaction 身份及相关 revision、epoch、当前待答/待澄清状态 | 各现有服务只读投影 |
| references | mention、对象类型、候选/已绑定ID、resolved/missing/ambiguous/partial、依据、引入轮次 | Resolver 提议，服务端核验 |
| tasks | 稳定子任务ID、动作、目标、顺序/依赖、约束、恢复点 | Parser 提议；限制任务数，校验依赖环与冲突 |
| scoped_directives | 本轮/本题/本次安排/会话/长期作用范围，以及否定和条件 | 理解层识别；持久修改另走确认命令 |
| classification | ontology_version、各维度标签、证据原话、来源(rule/model)、unknown/abstain | 分类器补充，不得覆盖可信绑定 |
| execution_decision | 可执行/只读回应/澄清/恢复，允许动作及被拒原因 | 服务端策略；调用原有命令实现 |

多维分类可先讨论四类：请求行为（解释/比较/作答等）、期望认知活动（理解/应用/评价等）、自报困难线索、教学呈现要求。它们必须允许独立为空；“难”可能是自报困惑，不是已经诊断出的知识缺陷。偏好值、掌握证据和状态更新结果不直接塞成分类标签。

分开实现但共用上述输入/输出与样本，最终效果可以基本一致。若各自重读历史、各自消歧、分类器另做自由改写，则容易对象冲突、丢否定、重复模型调用。尚无实测数据支持某种实现顺序能提升多少准确率。

## 7. 接入位置与交付顺序建议

1. 固定标签职责、协议与场景样本：先覆盖动作、对象、约束、作用范围与 unknown；标签表不在本轮定死。
2. 在 TaskService 请求重放/待澄清恢复后，先取可信状态摘要；首次规则理解在 Q5/聊天分流前完成。需要更多上下文时，再复用现有 _context 的已验证对象与快照，不再全量重复读取。
3. 普通 Q3、文本选区、旧 Orchestrator、练习辅导都消费同一理解结果，逐步替换重叠规则；不能只将结果作为提示词附录、同时让各分支重新判定。
4. 独立题卡/复习 API 的显式动作继续走现有强类型命令；可共享规则解析与观测结构，但不得把已明确的点击再送模型分类。
5. 为复杂语句接一个可替换的结构化解析器；给定有限真实候选，未知可拒识。分类器在同一协议上补标签，避免固定双模型串行。
6. 先影子运行：不写偏好、不评分、不移动学习位置；记录与旧决策的差异及分阶段耗时。随后按场景逐步启用，保留原链路开关。

这轮不建议与正在修改同一入口的窗口同时编辑 TaskService/main/agent_loop_service；分类标签、标注集和纯 Resolver/Parser 可以在固定契约后独立推进。

## 8. 只读实证与验收要求

本轮纯函数探针：`.runtime/input-understanding-audit-20261029/probe.py`，输出 `probe-results.json`。无数据库读写、无模型请求、无服务重启。

| 输入/核查 | 实际结果 | 解释 |
| --- | --- | --- |
| 我选 B | B，可提交 | 已迁入函数支持自然语言选项 |
| 为什么 B 不对？ | 能识别标签B，但不可提交 | “提及选项”与“作答”已有区别 |
| B 或 C | 无唯一标签、不可提交 | 能拒绝多选歧义 |
| 我不选 B | B，且可提交 | 已定位纯函数否定边界，需修复/集成保护；不等于已证明页面误评分 |
| 不是 B | 解析出B，但不可提交 | 仅拿 resolve_choice_submission 结果执行也有风险 |
| 先解释 B，再回答原题 | 解析出B，但不可提交 | 支持拒作答，不等于已支持复合任务与恢复 |
| 伪造 target_refs | parse_error | 旧路由已有真实对象校验 |

模式探针中“先讲这个词，再继续原来的题”返回 auto，不包含任务依赖；“以后详细一点，但这一题直接给答案”也返回 auto。模式函数本来只负责教法，不能据此断言整个系统一定丢失请求；证据说明需要统一结构而非扩大一个正则。

后续必须跨真实入口验收：

- 有待答题时“我选 B”只绑定该题；无题/过期题/跨会话题不猜；“我不选B”“B为什么错”不得提交。
- “这个实验没控制好”绑定真实实验，具体控制问题仍未知，不伪造混淆变量。
- “刚才那个例子再讲一次”：唯一真实例子可恢复，两个候选就澄清。
- “先解释这个词，再回到原题”：保存待答题，插问不评分，刷新后可返回。
- “以后详细一点，但这题直接给答案”：区分两种作用范围，长期偏好沿既有确认流程。
- 比较与例子通常是一个任务的回答结构；不同对象/副作用/暂停恢复才拆子任务。
- ask_user 点击/文本恢复、请求重试、取消、revision冲突、任务TTL后历史对象、侧分支只读、来源失效都保留边界。
- A精确直读/B普通检索/C复杂LightRAG的取证路径仍由检索层选择；分类器不能取代证据或把分类失败伪装成“教材不存在”。

性能验收需单列输入理解耗时、LLM额外调用数、升级比例和全回合首Token时间；不能用单纯“意图准确率”代替指代/任务/状态正确率。先建少量高质量边界样本再扩大，不将附件建议的500—800条视为行业硬门槛。

## 9. 本轮边界

只完成本地源码阅读、附件差距核对、纯函数探针与本报告。未修改业务代码、未提交或合并、未改变8000服务和正式数据；没有新分类器、真实LLM/页面对照或分类准确率结论。第三方在线API特性与附件其他项目未作本轮验证。
