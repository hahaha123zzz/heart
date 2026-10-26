# 教学能力首批实施记录

日期：2026-10-26。起始代码：`3a0b0fbcfec54a05102898b1c65660955ee5cb39`。已推进TA0核对、TA1规则/真实联调和TA2辅助证据补强，非整计划完成。未提交、未推送、未切换正式服务。

## 1. TA0核对结果与状态所有权

本地存在大量既有教材删除、其他文档及worker改动。本批没有清理、暂存、回退或覆盖这些内容；仅修改下述四个业务文件、新增专项测试和执行记录。

| 入口 | 当前实现与所有权 | 本批处理 |
| --- | --- | --- |
| 普通聊天/学习路径 | TaskService拥有任务身份、revision、最终提交；Q3调用现有工具和检索；Q5继续拥有其原有路径状态 | 只加入本轮规则与有效偏好，不增加新的学习写入方 |
| 文字选区循环 | SelectionLoopInput拥有选区范围，TaskExecution消费可信范围 | 模式切换不能越过服务端的仅提示范围 |
| 练习辅导 | exercise_task_tutor复用原练习服务；ExerciseHelpRow记录帮助；页面从help_history恢复级别与回答 | 核对并复用三级提示与完整讲解，无新增提示表或重复接口 |
| 辅助教学检查 | TeachingTurn使用已迁入DeepTutor模型/policy，快照经现有任务提交 | 本轮教法要求不送入作答评分，不新增正式掌握更新 |
| ask_user恢复 | 原任务/循环协议继续恢复；本轮提示块经既有循环处理 | 未改暂停恢复协议；Q3任务回归已覆盖，新增模式的真实页面恢复尚未验收 |
| 原生完整应用 | NativeTurnBridge存在，但当前worker未挂载其入口；宿主TaskService/Orchestrator尚未接原生完整学习服务 | 不宣称原生NT3已完成，不进行两套库双写 |

正式学习服务的统一写入与迁移契约仍待原生NT3完成；TA0整体保持进行中。当前改动是可复用的规则与现有宿主消费，不是原生学习迁移交付。

## 2. 本批实现

### 共享本轮教法规则

`agents/teaching_policy.py`增加`resolve_teaching_mode`和`teaching_mode_instructions`，不调用模型、不读写画像。支持明确的直接讲解、引导探索、分步练习、备考复习措辞，并处理常见否定与同句后续切换。

模式只作用于当前消息，不覆盖outline/study/review生命周期，不新增设置字段或数据库。未明确选择时沿用现有策略。备考提示要求区分真实依据与教学建议，禁止凭图谱中心性推断考试分值。

### 当前宿主与旧生成入口消费同一规则

- `agents/agent_loop_service.py`：普通教材问答也注入当前有效偏好，不再只有Q5本次安排分支消费偏好。辅助教学关闭时仍使用共享模式指令，避免依赖该开关才能切换教法。
- `agents/task_execution.py`：旧生成/选区/练习入口消费相同模式；路由遗漏教法时仍能对齐教学动作。“直接解释”会清理路由继承的旧提示范围，随后仍重新应用服务端可信对象的仅提示约束。符合既有直接回答条件时，不额外进入旧规划器。
- `agents/adaptive_tutoring.py`：本轮明确教法优先于默认轮换；直接讲解不主动出检查，服务端工具拒绝登记新检查题。对直接讲解、提示、练习或复习要求不执行上一题评分；原待答题保持不变。明确要求练习可覆盖历史低提问频率；原已确认会话安排的无练习限制仍沿用既有边界。
- 直接讲解不修改持久检查偏好，也未新增“正文不能出现任何问号”的发布限制，避免把教材中的研究问句当成违规而再次生成。

本批主要是项目边界适配，继续调用已迁入DeepTutor模型/policy；没有新建AgentLoop、复制另一份学习服务或声称新函数来自上游。

## 3. 验证

环境：应用目录`.venv-gpu/Scripts/python.exe`，临时测试SQLite。没有迁移正式数据库。

1. 新专项及任务/辅助教学最终复验：**57项通过**，日志`.runtime/teaching-modes/final-policy.log`。包含12项新增测试，涵盖常见否定、后续切换、提示范围、偏好覆盖、待答题保护、不评分、自报不加掌握及模式不跨轮继承。
2. 相关组合：**127项通过**，日志`.runtime/teaching-modes/focused.log`。包含教学模式、任务消费、辅助教学、Q3循环/任务/入口与Q5学习。此运行后仅补了TaskExecution清除旧提示意图及相应测试，受影响集合已由上述57项再次复验；不声称127项是在最终修改后重新全跑。
3. Q3真实LocalAgentLoop配合模型替身专项证明：辅助教学与Q5开关关闭时仍注入当前偏好/直接讲解指令，只有一次生成模型调用。此项是宿主接口测试，不是真实模型或页面验收。
4. `node tests/interaction-style.cjs`通过，验证原偏好确认、单轮消费、冷却、刷新与学生/会话隔离。页面代码未修改，无须重建静态产物。
5. 四个业务文件`git diff --check`通过。

### 保留的六项既有失败

`tests.test_q3_q4_integration`及`tests.test_interaction_style`同组合39项，当前与修改前HEAD模块均出现相同六个失败测试：

- `CitationPersistenceTests.test_completed_loop_persists_cited_pdf_references`：保存引用不符合旧测试期待。
- `HostNavigationTests.test_next_topic_is_not_turned_back_into_clarification`：`retrieval_not_ready`。
- `RegistryIntegrationTests.test_loop_executes_q4_skill_tool_and_keeps_state`：课程技能挂载/授权与测试预期不一致。
- `StyleServiceTests.test_disabling_task_understanding_does_not_drop_confirmed_style`：测试初始化缺少`q5_learning_bindings`表。
- `StyleServiceTests.test_temporary_override_reaches_executor_without_persisting_or_crossing_sessions`：重放结果新增`reader_action_replay`与旧测试严格相等断言冲突。
- `StyleServiceTests.test_two_successful_turns_offer_without_saving_and_replay_the_same_card`：同上。

对照方法：将HEAD的四个受改模块加载到临时目录，通过导入钩子执行同组测试；不替换工作区文件。脚本与日志在`.runtime/teaching-modes/check_baseline.py`、`baseline.log`、`current-compatibility.log`。这只证明六个失败测试在基线也存在，不将其改写为通过；没有混入修复其他窗口工作的改动。

## 4. 首批结束时的边界（后续进展见第5节）

- TA1的规则/宿主接线已落地，但真实模型、浏览器、完整原生回合仍未验收，因此TA1整阶段不勾选完成。
- 当前是有限明确措辞规则，不保证理解所有含糊、引用或复杂多阶段教学要求；没有新增LLM分类来掩盖此边界。
- Q5已确认无练习安排与用户本轮要求练习的完整协调，仍需统一活动/计划服务处理；本批不绕过原安排限制。
- TA2—TA4的正式题目、误解撤销、掌握估计、统一卡片和间隔复习未实施。须接原生NT3的唯一学习写入方，不能在现有辅助快照上再建立正式学习库。
- 尚未运行真实模型和浏览器，没有启停正式服务或更改开关；代码落地不代表当前服务已加载。
- 未将已有大批教材删除、运行产物、其他窗口的worker/图谱修改纳入本次交付。

后续顺序：原生NT3契约稳定 → 同一稳定宿主真实模型/页面验收TA1 → 复用原生题目与证据服务实施TA2 → 卡片与复习接线。不能仅凭本批离线测试宣称全部教学能力完成。

## 5. 第二批：辅助证据、真实回合及页面验证

### 新增与修复

1. 去掉辅助作答记录中固定的`hints_used=1`。原待答题的私有`visual_context`保存已发布的提示、解释、示例及实际教法；有工具记录时以实际教法为准，未使用工具时保留规则建议。未发布/失败的帮助不计数，相同任务发布回执去重。该记录继续由原TaskService提交，不建立新表或第二学习库。
2. 后续辅助作答证据关联实际提示次数、学生原话、暂定评估理由和原文版本/范围。未获提示时计0；无论次数多少，当前辅助证据仍是`host_formative / ai_provisional / independent=false`，不因0提示自动升级为独立掌握。`confidence`保持未提供，不编造可信概率。
3. 补充“第2级提示”“再给一个提示”等明确求助识别；引导请求可邀请一个步骤，纯提示请求不要求学生立即作答。
4. 修复工具过早关闭：明确教材问题要求取证；引导/练习需要真实登记`teaching_step`后再结束工具阶段。新检查还须有核验来源，可复用同一目标的已有来源，不能登记后留下无法核对作答的空证据题目。
5. `teaching_step`补上现有调度器要求的成功工具回执字段，复用既有必需工具机制，不新建另一套工具状态。
6. 发布前拒绝原始DSML/工具协议。只拒绝协议，不实现或执行从回答文本解析出来的伪工具调用。
7. 修复原多句题目校验：规范化后检查完整题目是否位于回答末尾。原逻辑只截最后一句，完整输出多句题目也会失败。保留题后追加答案和替换关键情境的拒绝测试。

涉及业务文件仍为`agents/teaching_policy.py`、`agents/task_execution.py`、`agents/adaptive_tutoring.py`、`agents/agent_loop_service.py`；未修改上游固定源码。新增`tests/test_teaching_evidence.py`，扩展`tests/test_teaching_modes.py`。

### 最终离线验证

应用`.venv-runtime`运行：

```powershell
& .venv-runtime/Scripts/python.exe -B -m unittest tests.test_teaching_evidence tests.test_teaching_modes tests.test_task_execution tests.test_adaptive_tutoring tests.test_q3_agent_loop tests.test_q3_task_loop tests.test_q3_entrypoint tests.test_q5_learning -q
```

**142项通过，0失败**；日志`.runtime/teaching-modes/evidence-regression-final.log`。其中策略/证据/任务/辅助教学专项71项通过，日志`evidence-policy.log`。此前第3节六项兼容失败保持记录，本轮不据此宣称全库回归全绿。

### 真实模型与实际数据库

独立服务`127.0.0.1:8026`；`.runtime/teaching-modes/live/host.sqlite3`及`course.sqlite3`，`LOCAL_AGENT_LOOP_ENABLED=1 / ADAPTIVE_TUTORING_ENABLED=1 / Q5_LEARNING_ENABLED=1`。使用实际固定教材运行时和项目当前真实模型配置；没有替换模型或检索成stub。首次误用`.venv-gpu`缺LightRAG，改用已具备依赖的`.venv-runtime`，没有安装包或改正式环境。

最终运行`75524d82a3`，五轮全部通过：

| 回合 | 结果 | 本次耗时 |
| --- | --- | --- |
| 直接解释教材中的变量区别 | answered，5条正文引用，无新检查 | 8.25秒 |
| 不直接给答案、带我思考 | answered，登记原待答题 | 5.69秒 |
| 只给提示 | answered，保留同一题，不评分 | 1.59秒 |
| 学生作答 | answered，同题暂定partial反馈，消耗待答题 | 3.94秒 |
| 复习信度/效度、不出题 | answered，review教法，无新检查 | 2.62秒 |

以上是单次验收耗时，不是提速对照或性能保证。后四轮显示引用数为0不代表没有内部证据：原题复用已核验来源，仅发布正文实际使用的上标；作答证据另保留来源关联。

对隔离数据库的只读核对通过：作答关联原`question_id`，`hints_used=1`，4条原文来源引用；结果`partial`、`verification=ai_provisional`、`independent=false`、`confidence=null`、`formal_mastery=false`。学生仅写了通用定义，没有回答情境中的具体变量，因此没有被夸大判为完整正确。

证据：`.runtime/teaching-modes/live/75524d82a3-summary.json`、同前缀逐轮请求/响应、`75524d82a3-evidence-check.json`；复现脚本在`.runtime/teaching-modes/check_live.py`和`check_evidence_db.py`。每次运行均使用独立合成学生，无正式学生信息。

### 浏览器验证

Playwright对同一隔离服务和真实历史完成7项检查：历史加载、正文上标引用、无内部协议、刷新后历史完整、刷新零生成请求、刷新前后服务端历史一致、无pageerror。截图及报告为`.runtime/teaching-modes/live/75524d82a3-browser.png`、`75524d82a3-browser.json`。

技能runner试图写只读技能目录发生EPERM，改为直接运行临时脚本并引用已安装Playwright；没有改权限或写技能目录。该浏览器验证为真实历史/引用/刷新，不是浏览器内完整输入五轮，也不代表所有入口已验收。

### 保留的失败与当前边界

- 运行`acc9c73dfd`：工具提前关闭，正文出现原始协议，引导题未登记；整体失败。首次脚本仅凭answered的部分检查过宽，后续已加强，不把这些单项作为通过证据。
- 运行`12eedabb07`：完整多句题目被旧末句校验错误拒绝；整体失败。
- 运行`8fe34c29a0`：题目已登记，但未保留可核验来源，后续只能保留待答而不能评分；整体失败。
- 所有逐轮文件、attempt1—4和各次服务日志保留。最终通过运行没有覆盖上述记录。
- 8026验收服务已停止，8000正式服务未切换，正式数据库和发布状态未改变。
- TA1目前有五轮真实模型与浏览器历史验证，选区/视觉/ask_user的新模式完整联合验收仍未完成。
- TA2仅完成辅助证据补强。正式题卡评分、掌握门槛、误解撤销、统一学习存储与迁移仍待原生NT3；本轮没有双写或绕过该依赖。TA3卡片与TA4正式复习队列未实施。

## 6. 后续TA3展示交付

已继续完成三类卡片的首批实现、原对话保存及历史恢复；最终150项相关测试、两个真实模型回合和10项浏览器检查通过。详细源码、协议、失败和边界见[教学卡片实施记录](TEACHING_CARDS_IMPLEMENTATION_LOG_20261026.md)。本节更新第5节末尾“TA3未实施”的历史状态；正式题卡、原生学习状态统一与TA4复习队列仍未完成。

## 7. TA4回顾建议首批

已接通基于持久进度卡的只读回顾建议，展示原因/历史位置，点击准备重新取证问题；真实验证任务过期清理后建议仍保留。162项相关测试、真实模型与TTL回归、13项桌面/手机浏览器检查通过，详见[回顾建议实施记录](TEACHING_REVIEW_FOLLOWUP_IMPLEMENTATION_LOG_20261026.md)。正式到期调度、延后/完成、复习评分和NT3单一学习写入方仍未接通；本批未提交、未切换正式服务，不标记TA4整体完成。

## 8. TA5多入口联合验收首批

已完成选区分步讲解/追问、ask_user暂停后刷新/点击选项恢复的真实模型及页面联验；发现并修复恢复时未消费当前宿主system提示的问题，保留同任务工具协议与预算。最终131项相关测试、真实模型5次请求、浏览器16项检查通过。完整范围、失败与复现见[多入口验收记录](TEACHING_ENTRYPOINT_ACCEPTANCE_20261026.md)。仍未接正式评分/到期复习，未验收全部视觉/练习/并发矩阵，TA5保持未完成。

## 9. 显式误解更正与删除传播

修复相同已生效误解更正重复写证据、清空后续新摘要的问题，复用原事务及事件返回；新说明和误解重新出现仍允许新更正。51项相关测试通过，包含SQLite并发、真实ASGI及更正/回顾/删除epoch联动。另保留扩展回归中1项旧编排`memory_commit`错误，替换为修改前方法仍复现。详见[更正与删除记录](TEACHING_MEMORY_CORRECTION_LOG_20261026.md)。本轮未跑模型/浏览器，未提交或切换正式服务。
