# Q5 学习计划与掌握评估接口契约

日期：2026-10-19。设计 worktree：`E:\项目\heart-worktrees\q5-learning-design`；分支：`codex/q5-learning-design`；基线：`20ae6a7`。

本文定义 Q5 与 Q2/Q3/Q4 的项目内部接口、数据结构、持久化、幂等、权限和失败语义。**主体仍是实现前设计；2026-10-20 首批只实现计划/确认/讲解/位置推进/恢复/切换与 Q3/Q4 工具接入，见 [Q5_IMPLEMENTATION_LOG.md](Q5_IMPLEMENTATION_LOG.md)。** 任何实现不得把整轮请求交给 `DeepTutorApp`、`TurnApplicationService` 或独立 DeepTutor 服务。

配套：[Q5 学习设计](Q5_LEARNING_DESIGN.md)、[Q5 验收矩阵](Q5_ACCEPTANCE.md)、[Q3 接口契约](Q3_INTERFACE_CONTRACT.md)、[Q2 导航检查点](Q2_NAVIGATION_STAGE.md)。

---

## 1. 权威边界

| 数据/动作 | 权威 |
| --- | --- |
| 学生、账户类型、删除 | 本项目 `students` / `AccountManager` |
| 任务、revision、request 幂等、取消/恢复 | 本项目 `learning_tasks` / `task_requests` / `TaskService` |
| 课程、教材目录、章节/小节、版本、页码、原图 | Q2 `knowledge/course*`、发布清单、`SourceRef` |
| 工具注册、schema、授权视图、deferred 加载 | Q4 `agents/tools/*` |
| 单轮循环、工具调度、ask_user 暂停、事件 | Q3 `agents/agent_loop.py`、`tool_dispatch.py`、`ask_user_contract.py`、`loop_events.py` |
| 学习路径、模块/目标、模式、题目、作答、证据、复习、教师审核 | Q5（本项目新增，落本项目数据库） |
| 对话正文、消息与页面状态 | 本项目会话/任务数据，不建 DeepTutor 账户副本 |

Q5 不允许直接读写 DeepTutor 的 `data/users`、`LearningStore` JSON、原生会话/账户/知识库目录。

---

## 2. 身份与作用域

```python
@dataclass(frozen=True)
class LearningScope:
    student_id: str
    course_id: str = ""
    path_id: str = ""
    session_id: str = ""
    task_id: str = ""
    request_id: str = ""
    actor: Literal["student", "teacher", "system"] = "student"
    # Q4 授权范围，不是模型可写参数
    grants: frozenset[str] = frozenset()
```

约束：

- `student_id`、`path_id`、`task_id` 只能由服务端任务上下文注入，不能来自模型参数。
- 学生只能访问自己的路径；教师只能访问被分配/授权的学生路径；`system` 只用于复习调度/一致性重算，不能冒充学生作答。
- `path_id` 属于 `student_id`；`objective_id` 属于 `path_id`；`interaction_id` 属于 `path_id`，跨层不一致直接拒绝。
- `course_id` 可空；空表示独立目标路径，不等于“无权限”。

---

## 3. 核心数据结构

以下为设计形状，字段名用于后续实现/迁移对齐；Pydantic/SQLAlchemy 具体类型在实现时固定。

### 3.1 路径、模块、目标

```python
PathKind = Literal["textbook_navigation", "mastery_goal", "course"]
PathStatus = Literal["draft", "confirmed", "active", "archived", "complete"]
KnowledgeType = Literal["memory", "procedure", "concept", "design"]

@dataclass
class LearningPath:
    path_id: str
    student_id: str
    course_id: str = ""
    kind: PathKind = "mastery_goal"
    name: str = ""
    goal: str = ""
    status: PathStatus = "draft"
    revision: int = 1
    source_scope: dict = field(default_factory=dict)
    plan_confirmed: bool = False
    created_at: float = ...
    updated_at: float = ...

@dataclass
class LearningModule:
    module_id: str
    path_id: str
    order: int
    name: str
    objective: str          # 一句能力句，不是章节名
    pass_threshold: float = 0.7

@dataclass
class LearningObjective:
    objective_id: str
    path_id: str
    module_id: str
    order: int
    name: str
    knowledge_type: KnowledgeType
    prerequisite_ids: list[str] = field(default_factory=list)
    topic_source_ids: list[str] = field(default_factory=list)
    required_visual_tasks: list[
        Literal["identification", "relationship", "table_graph", "comparison"]
    ] = field(default_factory=list)
    # 来源是项目 Q2 的 SourceRef/文档范围，不是上游 node_id
    source_scope: dict = field(default_factory=dict)
```

- `path_id` 稳定；`path_revision` 每次计划/目标结构变更递增。
- `objective_id` 在路径内稳定；重写目标产生新 ID，不继承旧证据。
- `module.objective` 在局部修改中保持不变；超过该句范围的修改必须新建路径/目标。
- `topic_source_ids` 是课程/资料出处；不证明事实正确，也不等于检索权限。

### 3.2 学习者画像与会话绑定

```python
@dataclass
class LearnerProfile:
    student_id: str
    prior_knowledge: str = ""
    target_level: str = ""
    time_budget: str = ""
    preferences: str = ""
    teaching_strategy: Literal["probe_first", "teach_first"] = "probe_first"
    notes: str = ""
    updated_at: float = ...

@dataclass
class PathBinding:
    student_id: str
    session_id: str
    active_path_id: str = ""
    active_objective_id: str = ""
    mode: Literal["outline", "study", "review"] = "study"
    teaching_strategy: Literal["probe_first", "teach_first"] = "probe_first"
    revision: int = 1
    updated_at: float = ...
```

- 画像合并写入；一次更正不清空其他字段。
- 绑定是会话级“当前活动路径”，不是路径属性；路径可跨会话，绑定可切换/离开。
- `mode` 与 `teaching_strategy` 分离：模式是本次坐着做什么，策略是目标怎么教。

### 3.3 当前目标与下一目标

```python
@dataclass(frozen=True)
class LearningTarget:
    target_id: str
    name: str
    path_id: str = ""
    objective_id: str = ""
    chapter_id: int | None = None
    section_id: int | None = None
    source_scope: dict = field(default_factory=dict)
    reason: str = ""
    version: str = ""
    path_kind: PathKind = "mastery_goal"

@dataclass(frozen=True)
class NextStep:
    action: Literal[
        "answer_pending", "review", "probe", "teach", "practice",
        "assess", "complete", "outline_required", "clarify"
    ]
    path_id: str = ""
    module_id: str = ""
    module_name: str = ""
    objective_id: str = ""
    objective_name: str = ""
    knowledge_type: str = ""
    status: Literal["new", "learning", "mastered"] | str = ""
    gate: Literal["qualitative", "quantitative"] | str = ""
    mastery: float = 0.0
    threshold: float = 0.0
    reason: str = ""
    forgetting_risk: float = 0.0
    pending_interaction_id: str = ""
    path_revision: int = 0
```

`next_objective` 的优先级必须固定：待答题 → 到期复习（排除延后）→ 有序未掌握 → 延后回退 → 完成/空路径。不能由模型自由选择下一目标。

### 3.4 题目与交互

```python
InteractionStatus = Literal[
    "registered", "awaiting_input", "answered", "graded", "abandoned"
]

@dataclass
class LearningQuestion:
    question_id: str
    objective_id: str
    path_id: str
    prompt: str
    question_type: Literal["choice", "short", "open"]
    options: list[dict] = field(default_factory=list)  # {label, body}
    # 以下字段只存在服务端，不进入公开卡片/事件/模型正文
    expected_answer: str = ""
    accepted_answers: list[str] = field(default_factory=list)
    explanation: str = ""
    rubric: dict = field(default_factory=dict)
    visual_context: dict = field(default_factory=dict)
    difficulty: str = ""
    created_at: float = ...

@dataclass
class LearningInteraction:
    interaction_id: str
    path_id: str
    objective_id: str
    question: LearningQuestion
    status: InteractionStatus = "registered"
    session_id: str = ""
    task_id: str = ""
    turn_id: str = ""
    learner_answer: str = ""
    answer_source: Literal["card", "composer", "teacher", ""] = ""
    result: dict = field(default_factory=dict)
    created_at: float = ...
    updated_at: float = ...

    def public_card(self) -> dict:
        """只返回 prompt/options/visual public 字段；不含答案键/解释/rubric。"""
```

公开题卡禁止包含：

- `expected_answer`、`accepted_answers`、`explanation`、`rubric`、评分内部字段。
- 未核验的答案线索/遮罩/区域；不可读图像的“猜测”。
- 其他学生的作答、教师内部备注。

### 3.5 作答、证据、复习、审核

```python
@dataclass
class LearningAttempt:
    attempt_id: str
    interaction_id: str
    path_id: str
    objective_id: str
    submission_id: str        # 幂等键；同一作答只记一次
    answer: str
    is_correct: bool | None
    result: Literal["correct", "incorrect", "partial", "ungraded", "voided"]
    independent: bool = True
    hints_used: int = 0
    visual_task: str = ""
    visual_context: dict = field(default_factory=dict)
    graded_by: Literal["deterministic", "rubric", "teacher", "system"] = "deterministic"
    voided: bool = False
    void_reason: str = ""
    created_at: float = ...
    graded_at: float | None = None

@dataclass
class ObjectiveEvidence:
    evidence_id: str
    attempt_id: str = ""
    student_id: str
    path_id: str
    objective_id: str
    source_kind: Literal[
        "quiz", "qualitative", "review", "visual", "teacher_review", "explained"
    ]
    result: Literal["correct", "incorrect", "partial", "passed", "failed", "not_counted"]
    quality: float | None = None
    independent: bool = True
    hints_used: int = 0
    source_refs: list[dict] = field(default_factory=list)
    rubric_version: str = ""
    verification: Literal["verified", "provisional", "rejected"] = "verified"
    created_at: float = ...

@dataclass
class ReviewState:
    objective_id: str
    path_id: str
    due_at: float
    interval_index: int = 0
    stability: float = 0.0
    retrievability: float = 1.0
    desired_retention: float = 0.9
    consecutive_correct: int = 0
    consecutive_wrong: int = 0
    lapse_count: int = 0
    last_review_at: float | None = None
    last_scheduled_at: float | None = None

@dataclass
class TeacherReview:
    review_id: str
    path_id: str
    objective_id: str
    interaction_id: str = ""
    reviewer_id: str
    rubric_version: str
    verdict: Literal["pass", "fail", "needs_revision"]
    comments: str = ""
    created_at: float = ...
```

**证据与现有 `evidence` 表的关系**：不把路径/目标语义硬塞进旧表。新增 `learning_objective_evidence` 关联表，`evidence_id` 可关联现有 `evidence.id` 或独立 UUID；旧 `EvidenceRow` 继续服务通用记忆/误解。一个 attempt 最多生成一条有效 objective evidence；作废/纠正要重算关联。

---

## 4. 持久化设计

### 4.1 新表

| 表 | 主键/唯一约束 | 作用 |
| --- | --- | --- |
| `learning_paths` | `path_id`；`(student_id, status)` 索引 | 路径身份、目标、revision、状态 |
| `learning_modules` | `module_id`；`(path_id, order)` | 模块与能力句 |
| `learning_objectives` | `objective_id`；`(path_id, module_id, order)` | 目标、类型、先修、来源、视觉要求 |
| `learning_path_revisions` | `revision_id`；`(path_id, revision)` 唯一 | 计划修订快照/diff/actor/reason |
| `learning_path_bindings` | `(student_id, session_id)` 唯一 | 活动路径/目标/模式/策略 |
| `learning_path_leases` | `path_id` 唯一 | 同一路径单写者租约（task/turn/expiry） |
| `learning_task_links` | `task_id` 唯一 | 任务→路径/目标/模式/revision/交互 |
| `learning_interactions` | `interaction_id`；`(path_id, status)` 索引 | 题目交互状态机；答案键服务端 |
| `learning_attempts` | `attempt_id`；`(interaction_id, submission_id)` 唯一 | 每次作答；幂等/作废/独立/提示 |
| `learning_objective_evidence` | `evidence_id`；`attempt_id` 可空 | 目标级有效证据；与旧 evidence 关联 |
| `learning_review_states` | `objective_id` 唯一 | 间隔复习状态/到期 |
| `learning_commands` | `(student_id, command_id)` 唯一 | 非任务型/计划型命令幂等收据 |
| `learning_teacher_reviews` | `review_id`；`(path_id, objective_id)` 索引 | 教师/rubric 审核 |
| `learning_handoffs` | `handoff_id`；`(task_id, path_id)` | 课程/阅读交接记录（可重建的投影） |

### 4.2 与现有表的关系

- `learning_tasks`/`task_requests` 仍是任务与 HTTP 幂等权威；`learning_task_links` 只扩展学习维度，不复制任务。
- `evidence`/`event_evidence` 保留通用证据/观察；`learning_objective_evidence` 只增加目标/路径关联，不改写旧记录。
- `ExerciseSubmissionRow`/`ExerciseDraftRow`/`ExerciseHelpRow` 是教材练习事务；掌握题不得复用其 `request_id` 记分。可在 `learning_attempts` 保存 `source_question_id` 关联，但一次作答只在一个系统形成有效事实。
- `TeachingPlanRow`/`LessonPlan` 是旧的 3—5 步课时计划，不是 Q5 长期路径；实现时保留兼容读取，不把旧 `steps_mastery` 自动升级为 Q5 掌握。
- `StudentState` 继续作为通用学生状态/上下文；Q5 的 `mastery_levels`/qualitative gate/review 以新表为准，不能两套都写。
- 删除学生：所有新表 `ON DELETE CASCADE`；路径删除级联交互/证据/复习/修订；共享通用 `evidence` 不误删。
- 记忆 epoch/教材版本：每次读写路径、题目、证据、复习时校验 `memory_epoch`/`document_version`；失效返回 `source_unavailable`/`memory_deleted`。

### 4.3 迁移原则

- 新表迁移只新增，不覆盖正式数据库；先在隔离数据库验证。
- 旧学习记录不静默转成 Q5 掌握；可标记为 `legacy_textbook_navigation` 或只读参考。
- 不导入 DeepTutor 账户/会话/JSON 学习库。
- 版本化 `policy_version`/`rubric_version`/`scheduler_version`；算法变更可重放/重算，不混用旧结论。

---

## 5. 服务接口

以下为 Q5 内部服务契约；具体类名实现时可调整，但输入/输出语义必须保持。

### 5.1 `Q5LearningService`

```python
class Q5LearningService:
    def get_binding(scope: LearningScope) -> PathBinding: ...
    def list_paths(scope: LearningScope) -> list[PathSummary]: ...
    def next_step(scope: LearningScope) -> NextStep: ...
    def get_path(scope: LearningScope, path_id: str) -> LearningPathView: ...

    # Q5.7
    def build_plan(scope, command: BuildPlanCommand) -> PlanResult: ...
    def revise_module(scope, command: ReviseModuleCommand) -> PlanResult: ...
    def confirm_plan(scope, command: ConfirmPlanCommand) -> PlanResult: ...

    # Q5.8/Q5.9
    def set_mode(scope, mode: str, reason: str = "") -> ModeResult: ...
    def set_profile(scope, patch: LearnerProfilePatch) -> LearnerProfile: ...
    def switch_path(scope, path_id: str) -> BindingResult: ...
    def leave_path(scope) -> BindingResult: ...
    def archive_path(scope, path_id: str) -> PathResult: ...

    # Q5.10
    def register_question(scope, command: RegisterQuestionCommand) -> InteractionView: ...
    def save_answer(scope, interaction_id: str, submission_id: str, answer: str,
                    source: str = "card") -> InteractionView: ...
    def grade(scope, interaction_id: str, submission_id: str = "") -> GradeResult: ...
    def assess(scope, objective_id: str, passed: bool, feedback: str,
               rubric: dict | None = None) -> AssessmentResult: ...
    def skip_question(scope, interaction_id: str, reason: str = "") -> GradeResult: ...
    def defer_objective(scope, objective_id: str, reason: str = "") -> NextStep: ...
    def repair_question(scope, interaction_id: str, action: str,
                        expected_answer: str = "", reason: str = "") -> RepairResult: ...

    # Q5.12
    def handoff(scope, handoff: CourseHandoff) -> HandoffResult: ...
```

### 5.2 命令对象

所有写命令必须带：

```python
@dataclass(frozen=True)
class CommandEnvelope:
    command_id: str          # 全局/会话内幂等键；任务内可等于 request_id
    student_id: str
    session_id: str
    task_id: str = ""
    path_id: str = ""
    base_revision: int = 0   # 乐观并发；0 表示新路径
    actor: str = "student"
```

- `command_id` 重复：返回第一次结果，`replayed=true`，不重复写。
- `base_revision` 不匹配：`path_conflict` + 当前 revision，不覆盖。
- 同一 `task_id` 的撤销/取消由 Q3 `TaskCancellationRegistry`/任务状态兜底。

### 5.3 `Q5Navigator`（实现 Q3 `LearningNavigator`）

```python
class Q5Navigator:
    def resolve(*, message, student_id, session_id,
                current_target: LearningTarget | None,
                context) -> NavigationDecision: ...
    def search(*, target: LearningTarget, query: str, limit: int,
               preferred_types: tuple[str, ...] = ()) -> list[SourceRef]: ...
```

`resolve` 规则：

- 绑定为 `textbook_navigation`：委托 Q2 `course_navigation.resolve`，保留 `path_kind=textbook_heading_order`、版本、位置。
- 绑定为 `mastery_goal`：读取 `next_step`；学生显式切换/下一目标/复习时更新绑定；不猜目标。
- 绑定为 `course`：先解析课程→路径→目标→来源/阅读位置；缺一返回 `clarify` 或 `handoff_unavailable`。
- 多候选/歧义：返回 `clarify` + 候选，不检索、不写状态。

`search` 只按 `target.source_scope` 调 Q2；Q5 不实现解析/索引/重排。

---

## 6. 与 Q3 的接口

### 6.1 循环前

Q3 `LoopRequest` 增加/复用：

```python
target: LearningTarget
navigation: Q5Navigator
tools: ToolRegistry              # Q4 ScopedToolRegistry
context: ToolContext             # Q3 现有
```

Q5 负责在 `LoopRequest` 构造前：

- 校验任务身份、路径绑定、revision、mode。
- 生成 `LearningTarget`（当前/下一目标/复习目标）。
- 构造 Q4 `ScopedToolRegistry`，只挂载当前模式/角色/课程/资源允许的工具。
- 把 `LearningScope`、`path_id`、`path_revision`、`objective_id`、`mode`、`interaction_id`、`deferred_loader` 注入 `ToolContext.state["learning"]`。

### 6.2 工具上下文

`ToolContext.state["learning"]` 设计：

```python
{
  "scope": LearningScope,
  "path_id": "...",
  "path_revision": 7,
  "objective_id": "...",
  "mode": "study",
  "interaction_id": "...",
  "teaching_strategy": "probe_first",
  "source_index": {...},          # Q2 来源索引，只读
  "deferred_loader": ...,         # 如挂载 deferred 工具
}
```

工具只从 `state["learning"]` 取服务端值；模型参数中的 `path_id`/`objective_id` 只能作为选择/校验输入，不能创建权限。

### 6.3 循环后

- Q3 负责质量/引用门禁、事件、`task_requests` 收据、取消/暂停。
- Q5 工具在调用时同步写路径/题目/证据；循环结束后不因“回答生成成功”补写掌握。
- 如果 Q3 质量拒绝/循环失败：Q5 不推进 `path_revision`、不写新证据；已登记的交互保留，可恢复/重试。
- 如果保存 Q5 状态失败：整个任务返回 `learning_persist_failed`，不发布“已完成/已掌握”。

### 6.4 事件映射

Q5 事件建议：

```text
learning.plan_started / plan_updated / plan_confirmed
learning.mode_changed
learning.path_switched / path_left
learning.question_registered / question_posed
learning.answer_saved / graded / assessment_recorded
learning.objective_deferred / question_repaired / question_skipped
learning.review_scheduled / review_due
learning.handoff_ready / handoff_failed
```

映射到 Q3 现有事件/SSE：

- 工具调用/结果仍走 Q3 `tool_call`/`tool_result`。
- 题卡走 `wait_for_input`/`ask_user` 兼容形状；Q5 `pending_interaction` 带 `interaction_id`、`path_id`、`objective_id`、`path_revision`。
- 页面现有 progress/done/error 继续可用；不新增第二套 SSE 通道。

---

## 7. 与 Q4 的接口

### 7.1 工具名与授权

保留上游工具名，便于 100 工具台账逐项迁移：

| 工具 | 作用 | Q4 scope | 备注 |
| --- | --- | --- | --- |
| `mastery_status` | 读路径/下一目标/待答/复习/地图 | `learning:read` | 每轮先读/用服务端快照 |
| `mastery_paths` | 列路径 | `learning:read` | 只列有目标路径 |
| `mastery_profile` | 合并画像 | `learning:plan:write` | 只写学生亲口信息 |
| `mastery_build` | 新建/替换/追加计划 | `learning:plan:write` | outline 模式；replace 新 ID |
| `mastery_revise` | 局部改模块 | `learning:plan:write` | 模块 objective 不变；已掌握禁改 |
| `mastery_mode` | 切 outline/study/review | `learning:mode:write` | 持久化；同轮生效 |
| `mastery_quiz` | 登记+呈现题卡 | `learning:attempt:write` | 本轮最后动作 |
| `mastery_grade` | 确定性评分 | `learning:attempt:write` | 幂等；答案键服务端 |
| `mastery_assess` | 定性评估 | `learning:assessment:write` | concept/design；rubric |
| `mastery_note_explained` | 记录讲解 | `learning:explain:write` | 不授予掌握 |
| `mastery_skip_question` | 跳当前题 | `learning:attempt:write` | 不跳目标 |
| `mastery_repair_question` | 作废/纠错 | `learning:repair:write` | 重算证据/复习 |
| `mastery_defer_objective` | 延后目标 | `learning:plan:write` | 不标掌握 |
| `mastery_switch` | 切路径 | `learning:path:write` | 需租约；失败保持原路径 |
| `mastery_leave` | 离开路径 | `learning:path:write` | 原路径保留 |
| `read_source` | 读 Q2 来源 | `learning:source:read` | Q4/Q3 只读代理 |

`mastery_*` 由 Q4 `ExtensionFlags.mastery_mode` / `mastery_path` 激活后挂载；Q4 `ScopedToolRegistry` 只暴露当前模式允许的工具（或工具内按模式拒绝，二选一，不能两套不一致）。Q4 `ToolGrant` 默认拒绝，显式授予上述 scope。

### 7.2 工具参数注入

Q4 `AuthorizationProxy`/Q3 `ToolContext` 注入：

```python
_mastery_path_id
_mastery_objective_id
_mastery_session_mode
_session_id / _task_id / _turn_id
_learning_scope
_bind_active_path / _bind_active_mode
_end_turn_on_card
```

模型只提供业务参数（题目、答案、模块、目标 ID 等）；路径/模式/权限/租约由服务端注入。答案键/解释/rubric 为 `sensitive`，不进入事件。

### 7.3 工具失败

- 未挂载/未授权：Q4 拒绝，不执行，不补权。
- 模式不匹配：工具返回“需要切到 X 模式”，同轮可 `mastery_mode` 后重试；不能静默放行。
- 路径租约冲突：返回 `path_busy`，不重试写；提示稍后/切回。
- 题卡呈现失败：整个出题失败，不能只发一句“我们来做题”结束。

---

## 8. 与 Q2 的接口

### 8.1 `SourceRef`

Q5 只消费 Q3/Q2 的项目来源，不复用上游 `node_id`：

```python
@dataclass(frozen=True)
class SourceRef:
    source_id: str
    document_id: str
    version: str
    chapter_id: int | None
    section_id: int | None
    page: int | None
    text: str
    quote: str
    image_refs: list[dict]
    location: dict
```

`source_id`/`document_id`/`version` 必须来自本项目发布清单；`text`/`quote` 必须可回原文；`image_refs` 带页码/区域/原图路径。

### 8.2 Q5 对 Q2 的要求

- `resolve` 先于检索；目标确定后，`search` 只在该目标 `source_scope` 内。
- 返回 `path_kind`、目标版本、阅读位置；Q5 用这些做路径绑定/交接。
- 教材换版/索引未就绪：返回明确状态，不用空结果声称“教材没有内容”。
- Q5 不解析 DOCX/PDF、不重建索引、不猜章节顺序。

---

## 9. 课程/阅读交接接口

```python
@dataclass
class CourseHandoff:
    handoff_id: str
    student_id: str
    course_id: str
    path_id: str
    objective_id: str
    target: LearningTarget
    source_refs: list[SourceRef]
    reader_location: dict       # document_id/version/chapter/section/page/selection
    mode: str
    task_id: str
    path_revision: int
```

`handoff()` 必须：

1. 校验课程/路径/目标/来源/阅读位置全部属于当前学生且版本有效。
2. 写入 `learning_handoffs`（可重建投影）和任务事件。
3. 返回实际加载的 target/source/位置；失败返回 `handoff_unavailable` + 原因。
4. 不因为推荐文字/按钮点击就标记成功；页面必须能打开对应目标/阅读位置。
5. 返回原任务时恢复 `task_id`/`path_id`/`objective_id`/`mode`/待答交互。

---

## 10. 幂等、并发与租约

### 10.1 幂等键

| 动作 | 幂等键 | 重复结果 |
| --- | --- | --- |
| 任务初始/追问 | `(student_id, session_id, request_id)`（现有 `task_requests`） | 返回原结果，不重新执行 |
| 计划命令 | `(student_id, command_id)`（`learning_commands`） | 返回原结果，`replayed=true` |
| 题目登记 | `command_id` + `path_revision` | 同题返回原 interaction；不得重复登记 |
| 作答 | `(interaction_id, submission_id)` | 返回原 attempt/结果，不重复证据 |
| 评分 | `interaction_id` + `submission_id`/终态 | 已 graded 返回原结果，不重复记分 |
| 修复/作废 | `command_id` + `interaction_id` | 返回原修复结果，不重复重算 |
| 复习证据 | `evidence_id`/`attempt_id` | 重放不重复加权 |

### 10.2 并发

- 路径单写者租约：`learning_path_leases` 每 `path_id` 一行，绑定 `task_id`/`turn_id`/`expires_at`；Q3 任务取消/崩溃后租约可过期回收。
- 计划修改用 `path_revision` CAS；两个窗口同时改同一路径，后到者 `path_conflict`。
- 题目交互用状态机 CAS：`awaiting_input -> answered` 只能一次；重复作答返回已保存。
- 评分事务：读取 interaction（锁）→ 校验状态/答案键 → 写 attempt/evidence/review → 更新 interaction `graded`；全在一个事务。
- 复习调度重算以 `policy_version`/`scheduler_version` 为准；并发重放不重复推进 interval。

### 10.3 取消/失败

- 取消：不再生成新回答/不写新证据；已登记题目/已保存作答保留，路径 revision 不变。
- 工具失败：返回结构化失败；不自动重试写操作；相同失败调用不无限重试。
- 模型/循环失败：任务 `loop_failed`；不把半成品回答写成掌握。
- 保存失败：`learning_persist_failed`；不发布完成态。
- 来源/版本失效：`source_unavailable`；不形成负面掌握。
- 删除/epoch：`memory_deleted`；不恢复旧状态。

---

## 11. 权限与安全

| 能力 | student | teacher | system |
| --- | --- | --- | --- |
| 读自己的路径/题目/证据 | 允许 | 被授权学生可读 | 内部一致性重算 |
| 建/改自己的计划 | 允许（需确认） | 不代写学生计划 | 迁移/修复需审计 |
| 作答自己的题 | 允许 | 不代答（审核除外） | 不冒充作答 |
| 评分 | 允许触发规则评分 | 可按 rubric 审核 | 复习/重算 |
| 读答案键/隐藏解释 | 不允许 | 审核需要时最小披露 | 服务端内部 |
| 跨学生/跨路径 | 拒绝 | 仅授权范围 | 拒绝 |
| 删除/遗忘 | 学生明确操作 | 管理员清理测试账户 | epoch 失效 |

安全要求：

- 答案键/参考解释/rubric 不进入模型可见正文、题卡、tool_call 事件、日志或任务结果公开部分。
- 事件只发 tool 名、脱敏参数、success、source 数、简短摘要；不发学生私有草稿/完整思考。
- 未授权工具不执行、不自动补权；Q4 默认拒绝。
- 所有写操作带 actor/reason/审计；教师审核最小披露。

---

## 12. 失败语义

| 代码 | 触发 | 是否写状态 | 页面/模型行为 |
| --- | --- | --- | --- |
| `path_not_found` | path_id 不存在/不属于学生 | 否 | 提示选择/新建路径 |
| `path_conflict` | base_revision 过期 | 否 | 返回当前 revision，提示刷新 |
| `path_busy` | 路径被另一任务租约占用 | 否 | 可重试；不并发写 |
| `outline_required` | 没有已确认计划却要 study/review | 否 | 回 outline 建/确认计划 |
| `objective_not_found` | 目标不在路径 | 否 | 刷新 `mastery_status` |
| `mode_not_allowed` | 工具不属于当前模式 | 否 | 提示切模式，不执行 |
| `interaction_conflict` | 已有待答/已评分交互 | 否 | 返回当前 interaction |
| `answer_unreadable` | 选择题答案无法映射到唯一选项 | 否（不判错） | 要求澄清/重选 |
| `source_unavailable` | 来源/版本/页码失效 | 否 | 明确缺口；不形成负面掌握 |
| `visual_unverified` | 图像/标签/答案线索未核验 | 否 | 标辅助/未评分；不写掌握 |
| `ungraded` | key 不确定/开放题无 rubric | 否 | 保留交互，等待审核/修复 |
| `question_voided` | 题目被判无效 | 重算 | 移除错误证据；返回新 next |
| `duplicate_submission` | 同一 interaction/submission | 返回原结果 | `replayed=true` |
| `cancelled` | 任务取消 | 不推进 | 不再生成/记分 |
| `memory_deleted` | 记忆 epoch/删除失效 | 不回写 | 重新建立任务/路径 |
| `forbidden` | 越权/跨学生/未授权工具 | 否 | 拒绝并审计 |
| `handoff_unavailable` | 课程/路径/来源/位置不完整 | 否 | 明确原因，不假装成功 |
| `learning_persist_failed` | 数据库/事务失败 | 回滚 | 不发布完成/掌握 |
| `loop_failed` | Q3 循环失败 | 不推进 | 真实失败；可恢复已保存状态 |

“不写状态”不等于“什么都不记录”：失败/拒绝可以写任务事件/审计，但不得写掌握、掌握证据或复习推进。

---

## 13. 兼容与迁移

- `LessonPlan`/`TeachingPlanRow`：保留旧课时计划的读取/展示；不自动升级为 Q5 路径。
- `StudentState.mastery`/`steps_mastery`：保留通用上下文；Q5 掌握以 `learning_objectives` + `learning_objective_evidence` 为准，避免两套分数同时推进。
- `ExerciseSubmissionRow`：教材练习继续用现有事务；掌握题用 `learning_interactions`/`learning_attempts`。如需要关联，只存 `source_question_id`/`source_version`，不复制评分。
- 通用 `evidence`：继续服务记忆/误解；Q5 通过 `learning_objective_evidence` 关联，不重写旧行。
- DeepTutor 数据：不导入账户/会话/JSON 学习库；如需迁移旧自建数据，单独脚本、只读、可回滚，不覆盖正式库。
- 功能开关：`Q5_LEARNING_ENABLED`（默认关闭）与 `Q5_MASTERY_MODE`（off/shadow/on）；shadow 只记录不发布，便于对照。实际实现时再定名。

---

## 14. 明确未实现

- 本文所有表、服务、工具、事件、迁移脚本均未创建。
- 没有运行真实模型、浏览器、并发/取消/删除/换版测试。
- 没有把上游 mastery 代码复制进本项目，也没有修改 Q2/Q3/Q4 业务代码。
- 任何实现必须按 `Q5_ACCEPTANCE.md` 逐项产生证据；设计完成不等于 Q5 完成。
