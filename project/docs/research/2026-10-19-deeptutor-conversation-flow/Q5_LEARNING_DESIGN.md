# Q5 学习计划与掌握评估设计

日期：2026-10-19。设计 worktree：`E:\项目\heart-worktrees\q5-learning-design`；分支：`codex/q5-learning-design`；基线：`20ae6a7`（`codex/integration-q1-q4` 最新提交）。

本文只做设计，不写业务代码，不表示任何功能已经实现或通过验收。源码依据：

- 本项目 `IMPLEMENTATION_PLAN.md` Q5.7—Q5.12（主工作区最新未提交版本）。
- 本项目 `TEACHING_LOOP_GAP_AUDIT.md`。
- 本项目 `Q3_INTERFACE_CONTRACT.md`、`Q2_NAVIGATION_STAGE.md`。
- 本项目 `models/student_state.py`、`models/lesson_plan.py`、`agents/lesson_planner.py`、`knowledge/course_navigation.py`、`agents/agent_loop_service.py`、`database/models.py`、`database/learning_tasks.py`。
- 固定上游 `D:\deeptutor`，提交 `6cf793bd868ba5ecbe64722936d4be8fab5a01df`：`learning/policy.py`、`learning/models.py`、`learning/service.py`、`learning/scheduler.py`、`learning/pending.py`、`capabilities/mastery/*`、`services/courses_state.py`。

---

## 1. 设计结论先行

Q5 要解决的核心不是“再做一个聊天页”，而是把**教材导学、目标路径、正式掌握、复习和课程交接**分成可区分的状态，并让 Q3 的同一个本地循环按这些状态执行。

四条硬边界：

1. **教材章节顺序不是掌握路径。** Q2 的 `textbook_heading_order` 只表示已发布目录的真实顺序，不证明概念先后关系，也不产生掌握分。
2. **“我懂了”不是掌握。** 它最多记录为学习者自述/已讲解覆盖；正式掌握只由符合门槛的独立证据或明确的教学审核产生。
3. **出题不是每轮必做。** 只讲解、只讨论、只问课程安排都可以正常结束；正式题目的“出题”是当轮最后动作，下一轮消费已保存的作答。
4. **DeepTutor 的算法可以复用，账户/会话/存储不能复制。** 目标、题目、证据、复习和路径都写入本项目数据库；不引入第二套 DeepTutor 账户、会话或 JSON 学习库。

---

## 2. 现状与上游能力盘点

### 2.1 本项目已有

| 现有能力 | 位置 | 对本设计的含义 |
| --- | --- | --- |
| 任务身份、revision、request 收据、取消、澄清 | `database/models.py` 的 `LearningTaskRow`/`TaskRequestRow`，`database/learning_tasks.py`，`agents/task_service.py` | Q5 的命令和作答必须挂在这些身份上，不另建任务系统 |
| 本地循环、工具协议、事件、暂停接续 | `agents/agent_loop.py`、`tool_protocol.py`、`tool_dispatch.py`、`ask_user_contract.py`、`loop_events.py` | Q5 只提供目标、状态和工具；循环仍由 Q3 执行 |
| 教材目录、章节、知识点标题、PDF 位置 | `knowledge/course_navigation.py`、`knowledge/course.py`、`knowledge/pdf_reader.py` | 教材导学路径的权威来源；Q5 不复制目录 |
| 通用学生状态、证据、误解、教学计划 | `models/student_state.py`、`models/evidence.py`、`database/repository.py` | 可继续作为通用学习事实；Q5 需要目标/路径维度的新表或关联 |
| 练习提交、草稿、求助 | `ExerciseSubmissionRow`/`ExerciseDraftRow`/`ExerciseHelpRow` | 教材练习的既有事务边界；不能与掌握题重复记分 |
| 页面、SSE、任务结果 | `main.py`、`TaskService`、`agent_loop_service.py` | Q5 事件要映射到现有 progress/done/error 与任务结果 |

本项目目前**没有**：目标驱动的长期路径、路径级 revision、模块/目标两级结构、题目交互状态机、正式掌握门槛、复习队列、路径切换/离开、教师审核、课程交接对象。不能把 `LessonPlan` 的 3—5 个步骤直接当作 Q5 的完整路径。

### 2.2 DeepTutor 已有且可复用

| 上游实现 | 可复用内容 | 迁移边界 |
| --- | --- | --- |
| `learning/models.py` | `KnowledgeType`（memory/procedure/concept/design）、`LearningModule`/`KnowledgePoint`、`LearnerProfile`、`LearningProgress`、`PendingQuestion`、`MasteryInteraction`、`LearningEvidence`、`RepetitionState`/`ReviewTask`、`MasteryEvent`、`PathLease` | 字段和状态机可作为设计基线；存储改为本项目数据库，`book_id`/账户语义要替换 |
| `learning/policy.py` | 硬门槛：memory/procedure 0.9；concept/design 定性通过；`next_objective` 优先级：待答题 → 到期复习 → 有序未掌握目标 → 延后回退 → 完成；`is_mastered`/`mastery_source`/`map_summary`/`objective_report`；视觉任务独立证据 | 算法可原样复用；目标 ID、来源和知识类型要由本项目提供；路径完成语义要按本项目修正 |
| `learning/service.py` | 目标身份分配、局部替换模块、题目登记/作答/评分、证据关联、定性评估、作废/纠正、延后、复习重算、路径概览 | 事务和锁改为本项目 SQLAlchemy/任务边界；不复制 JSON 文件存储 |
| `learning/scheduler.py` | 间隔复习、稳定性/可提取性、到期队列、证据回放 | 可复用纯计算；时钟、时区和“到期只是提醒不是许可”的语义保留 |
| `learning/pending.py`、`question_card.py` | 选项标签/正文分离、选择题稳定映射、公开题卡不包含答案键、题号/尝试次数 | 可复用；前端卡片要接现有页面 |
| `capabilities/mastery/mode.py` | outline/study/review 三模式；模式可中途切换；工具按调用时模式拒绝；outline 才能改大纲；review 只考已掌握 | 可直接作为 Q5 模式语义；工具挂载改为 Q4 的按场景挂载 |
| `capabilities/mastery/tools.py` | `mastery_status/quiz/grade/assess/skip_question/repair_question/defer_objective/build/mode/profile/revise/paths/switch/leave` 的完整语义 | 保留工具名以便台账兼容；适配本项目 `ToolContext`、路径/来源、权限和事件 |
| `capabilities/mastery/loop.py` | 每轮先读 `mastery_status`；出题即结束本轮；未出题不得假装出题；插问保留待答题；模式/路径绑定工具先执行 | 循环本身由 Q3 拥有；只迁入提示策略、状态种子和绑定语义 |
| `services/courses_state.py` | 课程资源、路径、大纲覆盖、下一单元、问题库弱项、阅读工作区的聚合 | 只复用聚合思路；课程/资源身份改为本项目 `knowledge/course`、发布版本和阅读器 |

### 2.3 需要本项目适配，不能原样搬运

- 账户/会话/工作区：上游 `LearningStore`、`SessionStore`、`PathService`、多用户目录不能进入本项目主链。
- `book_id`/`topic_source`：改为本项目 `course_id`、`path_id`、Q2 `SourceRef`、教材版本和 PDF 定位。
- 评分：上游通用定性 `mastery_assess` 不足以覆盖心理学 rubric、教师审核、提示/独立作答区分；Q5.4 必须增加本项目审核接口。
- 视觉题：上游 `visual_practice` 的 KB/asset 语义要改成 Q2 原图、文档版本、页码/区域和引用核验。
- 课程交接：上游 `course_study` 的推荐/交接要改成“实际传递课程、路径、目标、有效来源和阅读位置”，且返回原任务可继续。
- 事件：上游 mastery event 要映射到本项目任务事件/结果，不新建第二套会话事件库。
- 前端：现有页面已有任务、卡片、引用和阅读器；不替换整个网页，只增加路径/题卡/模式/审核视图。

### 2.4 明确不做

- 不把教材章节目录自动变成掌握路径，也不因“学完第一章”自动创建 Mastery 计划。
- 不把“我懂了”“讲过了”“看完视频”“课程已覆盖”写成正式掌握。
- 不每轮强制出题；不在只讲解请求中强行测评。
- 不把答案键、参考解释、隐藏评分标准放进题卡/事件/模型可见正文。
- 不复制 DeepTutor 账户、会话、伙伴/IM、完整应用容器、上游 JSON 学习库。
- 不在 Q5 做 Q6 的可视化/动画/音频；不接管 Q2 的解析/索引/检索内部实现。
- 不实现完整 LMS（班级、教务、成绩单发布）；只做本项目的学生学习路径、评估和教师审核接口。

---

## 3. 两类路径与四种状态

### 3.1 路径类型

| 类型 | 用途 | 目标来源 | 是否产生掌握 |
| --- | --- | --- | --- |
| `textbook_navigation` | “学习第一章”“下一节/下一知识点”的连续导学 | Q2 已发布目录/正文标题，`path_kind=textbook_heading_order` | **不产生**。只记录已讲解/自述覆盖/阅读位置 |
| `mastery_goal` | 按目标设计的模块/知识点路径，正式评估与复习 | Q5 计划生成，模块/目标绑定 Q2 来源 | 产生，但必须过类型门槛 |
| `course` | 课程页/课程交接后的学习容器 | 本项目课程绑定 + 选定的路径/阅读工作区 | 由绑定的路径类型决定；课程“覆盖”本身不等于掌握 |

一个学生会同时拥有多条路径。`session_id` 只绑定“当前活动路径”，路径本身的生命周期长于会话；`path_id` 是稳定身份，不因会话重建而重建。

### 3.2 四种状态必须分开

| 状态 | 含义 | 写入者 | 是否可推进 |
| --- | --- | --- | --- |
| `explained` | 本轮实际讲解了该目标，记录讲解摘要和来源 | `mastery_note_explained` 或教学记录 | 只影响教学连续性，不推进掌握 |
| `covered` | 学生/课程明确表示“已覆盖/已看过/我懂了” | 学生自述、课程覆盖操作 | 只影响路径显示；不等于掌握 |
| `mastered` | 通过该知识类型的硬门槛，且证据独立、来源有效 | 评分/定性评估/教师审核 | 可推进；mastery_source 必须可追溯 |
| `due_review` | 已掌握目标到期需要复习 | 复习调度器 | 不否定已掌握，但路径“下一步”优先复习；到期不是强制复习课 |

“我懂了，下一部分”在 `textbook_navigation` 中表示“继续导学”，不是 `mastered`。在 `mastery_goal` 中，它只能触发一次检查建议；是否推进由 `next_objective` 和门槛决定，不能由这句话直接写掌握。

---

## 4. 学习计划生成（Q5.7）

### 4.1 输入与首次需求了解

生成计划前按顺序读取：

1. 已选课程/教材/资料（Q2 发布版本、`SourceRef`、可用性）。
2. 已有 `LearnerProfile`（跨会话）。
3. 当前路径/会话绑定（是否已有计划、当前目标、模式）。
4. 用户本次目标文本和课程/阅读位置。

只对**材料看不出来、且影响计划**的信息做一次简短 intake：

- 已有基础（`prior_knowledge`）
- 完成目标（`target_level`）
- 可用时间（`time_budget`）
- 教学偏好（`preferences`）
- 顺序偏好（`teach_first` / `probe_first`）

规则：

- 先读材料，再问人；问题要围绕“这份材料对这个人意味着什么”，不能每次背同样四条。
- 已有画像字段不重复问；用户只回答一部分也接受，不为了凑齐四问而追问。
- 用 `ask_user` 做澄清，最多一轮；问题卡 1—4 个问题，允许自由文本。
- 用户拒绝回答时，说明将按保守估计开始，后续可修正；不得编造画像。
- 画像写入 `mastery_profile`（合并写入），一次更正不得覆盖其他字段。

### 4.2 计划结构

```text
LearningPath
  path_id, student_id, course_id, kind, name, goal, status, revision
  source_scope, created_at, updated_at
  modules[LearningModule]
    module_id, order, name, objective, pass_threshold
    objectives[LearningObjective]
      objective_id, name, knowledge_type, prerequisite_ids,
      topic_source_ids, required_visual_tasks, order
```

硬约束：

- `module.objective` 是一句“学完能做什么”的能力句，不是章节名。
- `objective.name` 是可观察目标，禁止“了解/理解”这类不可观察词；类型必须显式。
- 每个目标至少绑定一个**可用**的 Q2 来源/资料范围；来源可以是章/节/文档/页码范围，不能是编造的 `node_id`。
- 模块/目标围绕目标组织，不能把教材目录照抄成模块；多份资料按主题合并，不能一份资料一个模块。
- 先修关系必须是有向无环图；删除/改写目标时要检查被依赖关系。
- 计划规模受时间预算约束；默认 3—8 个模块、每模块 2—6 个目标，具体上限由实现配置，不把简单目标拆成大量重复练习。
- 目标 ID 稳定；重写目标产生**新 ID**，不继承旧掌握。模块 ID 在局部修改中保持不变。

### 4.3 计划生成流程

1. `outline` 模式读取 `mastery_status`：`empty` 表示从零起草；`active` 表示已有计划，进入“修改”而不是重建。
2. 读取材料并生成候选模块/目标（模型生成，但 schema 和来源引用受服务端校验）。
3. 服务端校验：类型、目标句、来源存在/版本、先修 DAG、重复/近重复、资料覆盖、时间预算。
4. 生成路径 `revision=1`（或递增），写入 `learning_path_revisions` 和路径表；不立即进入正式学习。
5. 向学生展示：每个模块做什么、为什么这个顺序、覆盖哪些资料、预计负担；请学生反馈。
6. 反馈后用 `mastery_revise` 做局部修改；全部认可后标记 `plan_confirmed=true`，再显式 `mastery_mode=study` 开始。
7. 已有计划每轮只读取，不每轮重建；只有用户明确“换目标/重新设计”才 `mastery_build(mode=replace)`，并产生新路径/新目标身份与明确重置说明。

### 4.4 计划展示/确认状态

- `draft`：已生成，未确认；可修改，不可产生正式掌握。
- `confirmed`：学生认可；可进入 study/review。
- `revising`：正在局部修改；保留已确认版本，修改成功后新 revision 生效。
- `archived`：不再活跃；保留全部证据，可恢复。
- `complete`：目标全部满足且无延后目标；到期复习单独显示，不把“有复习”写成“没学完”。

服务端必须保存“学生认可”的事件与 revision；不能以模型自述“学生同意了”代替确认。

---

## 5. 路径、当前目标与下一目标（Q5.8）

### 5.1 目标选择顺序

`next_objective` 采用确定性优先级（复用上游 `policy.next_objective` 语义）：

1. **待答题**：有 `awaiting_answer`/`answered` 交互时，先批改或处理，不跳到新目标。
2. **到期复习**：有到期项且未被延后时，优先复习；复习是提醒，不是强制整节课。
3. **有序未掌握目标**：按模块 order、目标 order 找第一个未掌握目标；已掌握目标跳过（test-out/压缩路径）。
4. **延后目标回退**：没有其他可学目标时，回退到最早延后的目标，并明确“这是延后项”，不能标掌握。
5. **完成/复习待办**：没有未掌握、没有待答、没有未处理延后目标时，目标可标 `objectives_complete`；若仍有到期复习，`next_step` 仍返回 `review`，UI 分开显示“目标完成/复习到期”，不显示“无复习的全部掌握”。

`NextStep` 至少返回：`action`、`module_id/name`、`objective_id/name/type`、`status`、`gate`、`mastery`、`threshold`、`reason`、`forgetting_risk`、`pending_question`、`path_revision`。

### 5.2 模式

| 模式 | 用途 | 允许 | 禁止/边界 |
| --- | --- | --- | --- |
| `outline` | 设计/修改计划 | `mastery_build`、`mastery_revise`、`mastery_profile`、`mastery_mode` | 不正式出题、不评分、不产生掌握 |
| `study` | 沿计划学习 | 讲解、`mastery_note_explained`、`mastery_quiz/grade/assess`、跳题/延后/纠错 | 不改大纲；要改先切 outline |
| `review` | 重测已掌握内容 | 对已掌握目标出题/评分/定性复核 | 不教新目标；要前进先切 study |

模式是会话/轮次状态，不是路径属性；可以中途切换，切换后同一轮即可使用新模式的工具。切换必须告知学生，并持久化到会话绑定；刷新后恢复。

### 5.3 教学策略

- `probe_first`：未触碰目标先做简短探查/测试，允许 test-out；不能因为“看起来会”跳过证据。
- `teach_first`：先按学生要求讲解，再安排检查；讲解本身不算掌握。
- 学生明确只讲解：允许只讲解并记录 `explained`，不强制出题；下一轮仍可建议检查，但不能把未测写成掌握。
- 到期复习：默认在 `study` 的 `next` 中提示，只有学生要求或切到 `review` 才做复习课；不把提醒强制变成复习。
- 当前状态 + 学生选择共同决定下一动作：学生说“继续/下一部分”优先看 `next`，学生说“先讲/别考”优先讲解，学生说“测一下”进入评估；冲突时以学生明确请求为当前轮目标，但不越过硬门槛。

### 5.4 当前目标与路径位置

- `LearningTarget` 是 Q3 循环的单轮目标；Q5 的 `objective_id` 是长期身份。二者不能混用。
- 目标必须带 `path_id`、`path_revision`、`source_scope`、`objective_id`、`chapter_id/section_id`（可空）、`version`。
- `session_id` 绑定 `active_path_id`、`active_objective_id`、`mode`、`teaching_strategy`；刷新/重连先读绑定，不靠上一轮模型文本猜位置。
- 阅读器位置与掌握状态独立：阅读位置可以影响“从哪页继续”，不能自动推进掌握。

---

## 6. 教学循环、插问与恢复（Q3/Q5 边界）

Q5 不实现第二个 AgentLoop。Q3 负责：单轮探索→工具→继续→收尾、预算、取消、暂停、事件、ask_user 暂停接续。

Q5 在 Q3 上的挂载点：

1. **循环前**：Q5 解析/加载路径绑定，给出 `LearningTarget`、模式、当前目标、来源范围；Q5 `LearningNavigator.resolve` 先于检索。
2. **工具上下文**：`ToolContext.state` 注入 `learning_scope`、`path_id`、`path_revision`、`objective_id`、`mode`、`interaction_id`、`deferred_loader`（如需要）。
3. **工具结果**：Q5 工具写入路径/题目/证据/复习；Q3 只把 `ToolResult` 转成 role=tool、事件和暂停。
4. **循环后**：Q3 质量/引用检查通过才发布；Q5 不因模型生成成功就写掌握。保存失败/取消/质量拒绝不得推进状态。
5. **插问**：学生中途问别的，Q3 正常回答；Q5 保留当前目标、待答题、模式和路径。回答后回到原任务，不重新出题、不重复评分。
6. **刷新/恢复**：只从保存的 Q3 `loop_state` + Q5 绑定/交互恢复；未保存的执行明确失败，不静默重跑。

插问的三条禁止：

- 把插问当成新任务重新开始，丢失原待答题。
- 学生回答后重复出同一题或重复记分。
- 学生问课程安排时，模型自述“已切换/已掌握”而不写服务端状态。

---

## 7. 路径生命周期与局部修改（Q5.9）

### 7.1 生命周期

| 动作 | 语义 | 结果 |
| --- | --- | --- |
| `list_paths` | 列出学生路径、模块/目标计数、已掌握、到期复习、当前活动 | 只读；不改变绑定 |
| `switch_path` | 会话切到另一路径 | 释放原路径租约，获取新路径租约，更新会话绑定；失败保持原路径 |
| `leave_path` | 会话脱离命名路径，回到会话自有草稿路径 | 原路径进度保留，可恢复；不删除 |
| `resume_path` | 刷新/下一轮恢复活动路径 | 读绑定；路径不存在/被删返回明确错误 |
| `archive_path` | 学生归档 | 不删除证据；默认不在活动列表置顶 |
| `delete_path` | 学生明确删除 | 级联删除该路径的交互/证据/复习/修订；需要二次确认；与其他路径共享的通用证据不误删 |
| `re_target` | 换目标/重新设计 | 新 `path_id` 或新目标 ID；写明哪些进度重置；不静默清空已掌握成果 |

### 7.2 局部修改

- `mastery_revise` 只改一个模块内部的知识点：重述、改类型、增加、删除。
- 模块 `objective` 不变；修改后的每个目标必须仍然服务于该模块 objective；超出范围时明确建议 `mastery_build` 重新设计，不悄悄扩宽。
- 已掌握目标**禁止重写/删除**；需要变更时新增目标，保留已挣得的成绩。
- 重写目标产生新 ID；旧目标的证据、复习状态不迁移到新 ID；返回 `progress_reset` 说明。
- 删除目标前检查先修依赖；被其他目标依赖时拒绝并列出依赖者。
- 基础/时间变化后可以调整计划；未变化模块/目标的证据、来源、复习状态保留。
- 每次修改写 `path_revision` 和修订记录（who/when/reason/diff），使用乐观并发；revision 过期返回冲突，不覆盖。

---

## 8. 完整题目交互与纠错（Q5.10）

### 8.1 交互状态机

```text
registered -> awaiting_input -> answered -> graded
      |              |             |
      +--------------+-------------+--> abandoned
```

- `registered`：题目已登记，答案键/解释/选项在服务端。
- `awaiting_input`：题卡已实际呈现；本轮结束。
- `answered`：学生作答已保存（卡片或普通消息），等待评分；刷新不重出、不要求重答。
- `graded`：已评分并写入证据/复习；终态保留用于幂等重试。
- `abandoned`：学生明确跳题或题目不可恢复；不产生掌握/错误证据。

### 8.2 出题规则

- `mastery_quiz` 一次调用同时登记题目和呈现卡片；**出题是本轮最后动作**，同一轮不再计划其他工具/长文。
- 题目必须自包含：题干含必要数据/图表/情境；选择题选项用 `{label, body}`，标签稳定；正确答案不得出现在题干/选项/解释/事件中。
- 选择题选项在呈现前可稳定打乱；保存映射；评分按标签/正文解析，不按模型记忆的字母。
- `expected_answer`、`explanation`、评分标准是服务端字段；模型/题卡/事件只看到公开部分。
- 只讲解/讨论轮不出题；不要用正文里的 1./2./3. 冒充题卡，也不要用 `ask_user` 代替正式题。

### 8.3 作答、评分与幂等

- 学生作答作为下一条消息；Q5 从持久化交互读取 `learner_answer`/`question_id`，不要求模型复述答案。
- 评分必须确定性：选择题精确映射；短答精确/有限模糊；开放题按已声明规则/关键词/教师 rubric；不能用“模型觉得对”直接写掌握。
- 同一 `interaction_id + submission_id` 重复提交返回同一结果（`replayed=true`），不重复写证据/复习/题库。
- `graded` 后再次评分返回“已评分”，不重复记分；错误答案键先修复再评分。
- 取消/失败/质检拒绝：不产生新证据；已保存的作答保留，任务可恢复。

### 8.4 跳题、延后、纠错

| 动作 | 影响 | 不影响 |
| --- | --- | --- |
| `skip_question` | 当前题 `abandoned`；不出掌握/错误证据；可换题继续同一目标 | 不跳知识点、不授予掌握、不清除已挣证据 |
| `defer_objective` | 目标标记 defer；`next` 优先其他目标；无其他目标时回退到它 | 不标掌握、不写 learner override |
| `repair_question(void)` | 作废该题/尝试；从掌握、错误、复习、题库错题集移除/重算 | 不删除其他题或其他目标证据 |
| `repair_question(correct)` | 写正确 key，重判已保存作答，重算证据/复习 | 不静默保留旧错误结论 |
| 教师/学生申诉 | 走审核，记录 actor/reason | 申诉本身不是掌握证明；手工覆盖需独立来源 |

纠错必须触发关联证据、复习队列、路径状态的**重算**，不能只改题卡文本。作废/纠正后返回新的 `next`、`mastery`、`review`。

---

## 9. 掌握门槛与复习（Q5.11）

### 9.1 按知识类型

| 类型 | 门槛 | 证据 |
| --- | --- | --- |
| `memory` | 定量：近期加权正确率 ≥ 0.9（默认；可配置但需版本化） | 独立作答、无提示、答案键已核验 |
| `procedure` | 定量：同上，强调步骤/应用 | 独立作答、可含多步题；步骤错误可解释但不放宽 |
| `concept` | 定性：学生用自己的话解释，教师/审核按 rubric 通过 | Feynman 式解释 + 来源；不能用选择题高分替代 |
| `design` | 定性：开放判断/方案，按 rubric 与教师审核 | 设计说明、取舍、证据；不能用通用文字分替代 |

- 视觉任务（identification/relationship/table_graph/comparison）是目标级额外门槛：`required_visual_tasks` 必须由独立、来源核验、无提示的视觉证据满足。
- 通用文字高分不能替代原图理解；未看图/图不可读/关键标签不可辨时不得产生负面掌握，也不得宣称已掌握。
- `mastery_source` 至少区分 `system`（评估证据）与 `learner`（学生明确自述覆盖）；两者不能混写。正式完成/证书只认 `system`，除非产品明确允许自述路径。

### 9.2 证据资格

一条证据要计入掌握，至少满足：

- 目标/路径/学生身份正确；`path_revision` 当前或可重放。
- 来源有效：Q2 来源版本未失效、原文可定位；引用/原图未被删除。
- 答案键有效：题目未作废、key 已核验；选择题映射可解析。
- 独立性：无提示、非刚看完答案的即时重复、非辅助练习；提示/辅助练习单独记录为 `guided`。
- 评分确定性/审核：定量由规则；定性由 rubric + 教师/审核，不由助教自述。
- 幂等：同一 attempt 只写一次证据；重放不重复加权。

不满足时：返回 `ungraded`/`not_counted`，保留交互，不形成负面掌握；明确告诉学生缺什么（来源、图像、key、审核）。

### 9.3 复习与完成

- 复习调度复用上游 SRS：初始状态、间隔、稳定性/可提取性、到期队列、失败重排；时区/时钟由本项目配置。
- 到期复习是提醒，不是强制复习课；学生可以指定复习已掌握的其他内容（review 模式）。
- 掌握目标的复习失败不直接抹掉 mastered；更新复习状态/风险，必要时回到 learning，但保留历史证据与来源。
- 延后目标在“没有其他可学目标”时回退；不能因延后而标完成。
- 路径完成条件：所有目标 mastered（含视觉要求），无待答交互，无未处理延后目标；到期复习可以存在，但 UI 必须分开显示“目标完成/复习待办”，不能说“全部掌握且无复习”。
- `complete` 是计算结果，不是模型一句话；完成后仍可复习/重开目标（新 revision/新 ID）。

### 9.4 心理学 rubric 与教师审核（本项目新增）

- 上游定性 `mastery_assess` 只提供通用通过/不通过；Q5.4 需要本项目 rubric：概念准确性、变量/设计、证据引用、范围限制、表达完整性。
- 教师审核是独立 actor/事件：`teacher_review` 记录审核人、rubric 版本、结论、理由；学生自述/普通日志不能替代。
- 提示/独立作答分开：使用提示的作答可记录练习，但不计独立掌握；教师可审核“提示后独立复述”的特定场景，但必须显式标记。
- 教师驳回/要求补充不写负面掌握，只保留待审/补充状态；只有明确“错误且证据有效”才写负面证据。

---

## 10. 课程/阅读/学习交接（Q5.12）

### 10.1 交接对象

```text
CourseHandoff
  handoff_id, student_id, course_id, path_id, objective_id,
  target: LearningTarget, source_refs: list[SourceRef],
  reader_location: {document_id, version, chapter_id, section_id, page, selection?},
  mode, task_id, path_revision, created_at
```

### 10.2 交接规则

- 课程推荐/路径推荐只是候选；交接成功的判据是目标、路径、来源、阅读位置**实际传入**执行能力，并且执行能力校验通过。
- 交接前校验：课程绑定存在、路径属于该学生、目标属于路径、来源版本有效、阅读位置属于该文档/版本。
- 交接后返回原活动任务仍可继续；不因打开阅读器/课程页丢失原任务、待答题或路径绑定。
- 课程“覆盖”由学生明确操作；覆盖不等于掌握，不自动写 mastered。
- 阅读器定位与掌握独立：定位到某页只影响上下文，不产生证据；从阅读器发起的解释/题目仍走 Q3/Q5 同一任务身份。
- 无课程/无路径/来源失效时明确缺口，不用推荐文字或空页面冒充交接成功。

### 10.3 返回语义

- 从阅读器/课程页返回：恢复原 `task_id`、`path_id`、`objective_id`、`mode`、待答交互；不新建无关会话。
- 交接失败：返回 `handoff_unavailable` + 原因（无课程、路径不存在、来源失效、位置不匹配）；不推进路径。
- 交接成功事件：写入任务结果/事件，包含 `path_id`、`objective_id`、`source_refs`、`reader_location`，供页面和审计。

---

## 11. “学习第一章 → 我懂了 → 下一部分”端到端设计

这是 Q2/Q3/Q5 的联合场景，不是 Q5 单独完成。

### 11.1 第一轮：学习第一章

1. 学生：“我想要学习教材第一章的内容。”
2. Q2 `course_navigation.resolve` 解析章号/章名，返回 `status=ready`、`path_kind=textbook_heading_order`、第一个真实教学点、章节/小节/版本/页码。
3. Q3 创建/复用任务，`LearningNavigator.resolve` 先于检索；检索只在该章/节范围，返回带项目来源身份的 `SourceRef`。
4. Q5 不创建 mastery path；只创建/复用 `textbook_navigation` 绑定，记录 `path_id`（导航路径）、目标、阅读位置。
5. 模型讲解；Q3 质量/引用检查通过后发布；Q5 记录 `explained`（可选），不写 `mastered`。
6. 结果包含：目标名称、章节/小节、来源、页码/PDF 定位、下一步建议。

### 11.2 第二轮：“我懂了，下一部分”

1. Q3 恢复同一任务/路径绑定，读取 Q2 当前目标。
2. Q5 记录学生自述 `covered/understood`（独立事件，不是掌握），按 Q2 目录顺序计算下一个目标；不因“我懂了”直接跳章。
3. 如果没有下一个目标：返回“本章/本节已到末尾”，提供下一节/下一章/复习选项；不伪造下一知识点。
4. 如果用户说“测一下我是否掌握”：Q5 说明当前是教材导学路径，正式掌握需要目标路径；提议建立/绑定 mastery path（Q5.7 intake），学生确认后才创建；不偷偷把导学路径改成掌握路径。
5. 如果用户要求“下一部分”但当前有待答题/未完成交互：先处理待答题或明确保存/跳过；不丢失题目。

### 11.3 刷新、重复与取消

- 刷新：从任务 `loop_state` + Q5 绑定恢复同一目标/路径/待答题；不重新解析成新目标。
- 重复“下一部分”：同一 request_id 幂等；新 request_id 但目标已推进时返回当前目标，不重复推进。
- 取消：Q3 取消到达实际执行；Q5 不写新证据/不推进；已保存讲解保留，待答题保留。
- 教材换版/来源失效：返回 `source_unavailable`，要求重新选择/重建索引；不把旧版本内容当当前教材。

### 11.4 与 mastery path 的衔接

- 学生从导学转为正式掌握：创建 `mastery_goal` 路径，目标来自材料 + 学生目标；可把已讲解的 Q2 目标作为 `topic_source_ids`/起点，但不继承掌握。
- 已讲解/已覆盖只影响起点建议；正式掌握仍需评估。
- 如果学生只想继续导学，不创建掌握路径，不产生掌握分；这是正常路径，不是降级。

---

## 12. 与 Q2/Q3/Q4 的职责边界

| 模块 | Q5 依赖 | Q5 不负责 |
| --- | --- | --- |
| Q2 | 已发布目录、章节/小节、来源版本、页码、原图、检索接口 | 解析/摄取/索引内部实现；不复制目录；不伪造来源 |
| Q3 | 本地循环、工具调度、ask_user 暂停、事件、取消/恢复、任务身份 | 另建 AgentLoop；另建任务/事件系统；模型调用编排 |
| Q4 | 工具注册/授权视图/schema/deferred 加载 | 复制工具协议；越过 Q4 授权直接执行工具 |
| Q5 | 路径/目标/模式/题目/证据/复习/交接状态 | Q6 多媒体；Q2 检索内部；完整 LMS |

---

## 13. 设计状态与待实现

| 项目 | 状态 |
| --- | --- |
| 上游 mastery 模型/策略/题目/复习语义盘点 | 已完成（源码级阅读，未运行上游测试） |
| 本项目 Q5 数据结构、持久化、接口、失败语义 | 本文 + `Q5_INTERFACE_CONTRACT.md` 定义 |
| Q5.7—Q5.12 验收矩阵 | `Q5_ACCEPTANCE.md` 定义 |
| 业务代码、数据库迁移、工具实现 | **未实现** |
| 真实模型/页面/并发/删除/换版验证 | **未执行** |

本设计不能作为“Q5 已完成”的证据；后续实现必须按验收矩阵逐项产生真实证据。
