# 多维分类器第二轮调研：从“六维标签”到“本体对账 + 消费契约”

日期：2026-10-30。性质：只读源码调研、产品判断与实施建议。不改代码、不跑模型、不标数据、不动 8000 服务与正式库。

上一轮附件方案的出发点是“输入理解层已完成，下一步做多维分类器”。本轮核查后的结论是：**项目缺的不是维度数量，而是维度之间的一本账，以及标签的下游消费者。** 直接按 D1–D6 建六套分类，会把现有 8 套并行词表变成 14 套，模型调用与维护成本上升，教学质量不必然提升。

## 1. 结论摘要

1. **已有的分类体系比方案假设的多。** 输入理解 `Action`（14）、`Constraint`（4）、`ScopedDirective`（8 键）、旧路由 `student_move`（5）/`intent`（5）/`learning_intents`（8）、教学 `strategy`（9）、策略库（13）、`resolve_teaching_mode`（5）、`LearningStage`（7）、`KnowledgeType`（4）、`ErrorType`（4）、`ObjectReference`（13 类）、`StudentState`、`InteractionPreferences`（7）——D1/D4/D5/D6 大部分已有对应物。
2. **分类端口已存在，但没有任何消费者。** `semantic.annotate()` 写入的 `annotations` 在 `GroundedTurn.instructions()`、`final_summary()` 和所有业务分支中都没有被读取；`TaskService` 调用 `understand()` 时也没有传 `classifier`。现在建分类器，等于给一个空管子加压。
3. **真正没有任何字段的只有“认知操作”**（理解/应用/分析/评价/创造）与**“困难定位”**（听不懂 / 分不清 / 不会做 / 记不住 / 太快）。这两项各自对应一个明确的、可验证的教学效果，值得新增。
4. **“学生状态”不应由单句分类得出。** 项目已有 `LearningStage`、`MasteryInteraction`、`LearningEvidence(hints_used, attempt_count, quality)`、`MasteryPathLease`（单写入租约）。状态应读，不应猜。
5. **2026 年的文献在收窄而不是扩张这条路。** 组件准确率与教学效果之间缺少接口验证（2610.15692）；模型间一致性不能当效度（2610.08703）；逐决策打分会被“重复最优动作”刷爆（2610.12125）。评估必须做到决策点 + 轨迹两层，不能只报 F1。
6. **不建议现在引入 LangGraph。** 项目已具备它最值钱的三件事：持久化、恢复、单写入者。引入代价是迁移 `TaskService` 的收据/revision 语义，收益在当前的 1–2 个决策节点上不成立。

## 2. 现状盘点：8 套并行词表，3 套有消费者

核查范围：`project/integration/discrete-math-tutor`（下称 app 根），重点文件见文末“本地证据”。

| # | 体系 | 位置 | 标签 | 是否持久 | 消费者 | 问题 |
|---|---|---|---|---|---|---|
| 1 | 输入理解执行动作 | `models/input_understanding.py` | `Action` 14 / `Constraint` 4 / directive 8 键 / 5 作用域 / `ObjectReference` 13 类 | 是（任务 context） | `decision.decide`、`TeachingTurn`、Q5/选区适配 | 语义标签位 `annotations` 空转 |
| 2 | 旧路由 | `agents/conversation_router.py` | `student_move` 5 / `intent` 5 / `learning_intents` 8 / `missing_slots` 4 | 部分（TaskUnderstanding） | 旧 Orchestrator；新链仅 `legacy_routing` 投影 3 个动作 | 与新链重叠，双份判断 |
| 3 | 教学回合分析 | `agents/adaptive_tutoring.py::analyze_teaching_turn` | `move` 7 / `strategy` 9 / `evidence_mode` 2 / `reuse_evidence` / `invite_check` | 部分（`turn_move`、`last_strategy`、`used_strategies`） | `TeachingTurn`（Q3 主链） | 纯正则；`needs_support` 时盲轮换策略 |
| 4 | 策略库 + 规则选策略 | `agents/teaching_policy.py` | 13 策略 / `difficulty` 3 / `action` 5 / `hint_level` 3 | 否（每次重算） | `teaching_planner`（旧计划器）、`StrategyRouter` | 依赖 `StudentState`，与 3 的 9 策略不是同一套命名 |
| 5 | 教学方式 | `resolve_teaching_mode` | auto/direct/guided/practice/review | 部分（`teaching_mode`） | `agent_loop_service`、`task_execution`、deeptutor 适配 | 与 `constraints`（hint_only/no_questions…）语义交叠 |
| 6 | 掌握路径 | `agents/deeptutor_learning/*` | `KnowledgeType` 4 / `ErrorType` 4 / `LearningStage` 7 / `InteractionStatus` 5 | 是（正式学习记录） | mastery path、复习调度 | 与“本轮教学”分层不清时易被误用 |
| 7 | 学习者状态 | `models/student_state.py` | `emotion` 5 / mastery / confidence / `calibration_gap` / misconceptions / `skill_states` | 是（记忆） | `select_policy`、`StrategyRouter` | 数值为平滑估计，不是本轮事实 |
| 8 | 交互偏好 | `models/interaction_preferences.py` | 7 个 0–1 参数 + 当轮覆盖 | 是（确认后） | `style_instructions` | “术语密度/模态”无对应 |
| 9 | 语义标注端口 | `SemanticAnnotation` | 自由 dimension/label | 是 | **无** | 0 实现、0 消费 |

三个可以直接观察到的后果：

- **同义重复。** “没听懂/换个说法/再简单点”同时被 `DIFFICULTY`、`SIMPLIFY_PATTERN`、`resolve_teaching_mode(guided)`、`input_understanding` 的 `explain_content` 四处识别，四处都可能给出不同结论。
- **哑标签。** `annotate()` 的第三个参数 `missing_dimensions` 在 `service.py` 里恒为 `()`；即使接上分类器，模型也不知道该补哪一维，只能自由发挥。
- **能力推断污染。** `is_difficulty()` 只输出布尔值，却直接推动 `turn_move=needs_support` 与策略轮换；它无法区分“没听懂”和“分不清”，只能靠轮换碰运气。

## 3. 与 D1–D6 的逐项对账

| 提议维度 | 现有对应 | 判断 | 建议处理 |
|---|---|---|---|
| D1 交互意图 | `Action` 14 + `Constraint` 4 + 旧 `learning_intents` 8 | 已有，且执行动作更严谨 | **不新建。** 冻结 `Action` 为执行层唯一词表；`learning_intents` 降级为投影，不再新增第 4 套意图 |
| D2 认知任务 | 无。代码中无 Bloom/认知操作字段 | **唯一真缺口** | 新增 `cognitive_demand`，但只用于“回答结构 + 策略预筛”，不得判对错 |
| D3 学习状态 | `LearningStage`、`StudentState`、`InteractionStatus`、`is_difficulty` 布尔 | 状态已有，**困难定位缺失** | 拆成两件事：状态=读现有快照；困难=新增 `difficulty_locus`。不新建 `stuck` 之类能力标签 |
| D4 内容对象 | `ObjectReference` 13 类 + `KnowledgeType` 4 + PDF 定位/图绑定 | 完备 | **不新建。** 分类器不得生成 ID（现有 `model_reference_not_in_candidates` 已保护，保持） |
| D5 支持需求 | `InteractionPreferences` 7 + `ScopedDirective` 4 约束 + 教学方式 5 | 大部分已有 | **不新建维度。** 缺的“术语密度/辅助模态”按需扩展 `ScopedDirective.key`，不另立分类 |
| D6 教学阶段 | `LearningStage` 7（diagnostic/explain/feynman_check/practice/error_diagnosis/review/completed） | 已有，且带持久化与租约 | **不新建状态机。** 方案的 EXPLORE→…→REVIEW 与现有 7 态近似同构，替换只会丢证据 |

方案里七个问题中，只有第 2 个（“需要哪种认知活动”）和“学生卡在哪一类”需要模型；第 1、5、6、7 个问题的答案已经在状态里，第 3 个应是读状态而非分类。

### 三个具体反例（为什么“九套词表”不够用）

1. **“帮我设计一个心理学实验。”** 现有 `analyze_teaching_turn` 落不到任何分支，最终 `move=explain, strategy=explain`——把“创造”当“讲解”。学生需要的是约束清单（自变量/因变量/控制/伦理）+ 分步设计 + 方案检查。
2. **“我还是分不清信度和效度。”** `is_difficulty` 为真 → `needs_support` → 按 `worked_example→contrast→break_down→prerequisite→hint` 的顺序**盲轮换**。若上一轮刚到 `contrast`，这一轮会跳到 `break_down`，恰好错过学生需要的对比。
3. **“直接给我答案吧”与“这题我不想做了。”** 分别散落在 `NO_QUIZ`、`ALLOW_QUIZ`、`SKIP_CHECK`、`response_style=direct`、`no_full_answer` 里，没有一个字段回答“这一轮该不该以等待学生动作结束”。

## 4. 外部新证据：为什么这条路要收窄

均为 2026 年公开预印本，本轮只读摘要与结论，未复现实验。

| 文献 | 与我们的关系 | 对分类器的直接含义 |
|---|---|---|
| **Do LLM Tutors Actually Teach?**（2610.15692） | 把辅导拆成“学习者状态推断 → 教学动作 → 训练 → 评估 → 学生模拟”的链条，指出**接口**缺少验证，学习增益与迁移证据最薄 | 只提升分类准确率不构成教学改进证据；必须验证“标签 → 动作”这一跳 |
| **Agreement Is Not Validity**（2610.08703） | 五种失败模式编码（uncertainty / misattribution / operator selection / conceptual gap / procedural slip）；人与模型 κ=.524–.597，模型间 κ=.755–.781 | 模型间一致 ≠ 正确；**禁止**把 `confidence` 或“两个模型都这么判”当校准概率 |
| **The learner who does not learn**（2610.12125） | 逐决策打分取平均会被“重复单一最优动作”最大化；微调后指标 +0.05→+0.42，31 名教师盲评 4.46→3.03 | 不要把“每轮教学评分”当优化目标；评估要含轨迹（轮次序列）与重复检测 |
| **Actionable Pedagogical Feedback**（2505.07161） | 一句话常同时承担多个话语功能，单一标签无法表达，遗漏会导致反馈缺失 | 支持“多维度、允许为空”，也提醒：维度再多也表达不了全部功能，要有弃权 |
| **The Assistance Dilemma**（2610.06446） | 掩蔽近迁移后测：把导师话语遮掉后测学生，奖励只来自学生自己的回合；用二元门（事实正确 / 不交出解法）替代连续惩罚 | “不提前给答案”应做成**机器可检查的契约**，不是分类标签；验收看近迁移而非练习正确率 |
| **Withhold the Answer**（2608.12292） | 把“拒绝给答案”实现为每轮可机检的 contract | 同上：`no_full_answer` 已是契约，标签不要重复表达 |
| **DAS2**（2609.12331） | 五种可观察参与状态：engaged / gaming / wheel-spinning / off-task / mixed，用于评估导师 | 状态应可观察、按会话累计；单句只能给“信号”，不能给“状态” |
| **SLOW**（2603.28062） | 指出“诊断、情绪、教学决策被揉在一次生成里”，主张显式学习状态工作区 | 与“分层”判断同向；但它是**模型内推理工作区**，不是外部词表，不能照搬成 6 个分类器 |
| **IntelliCode**（2512.18669） | 中央版本化学习者状态 + `StateGraph` 编排 + **单写入者**策略 | 我们的 `MasteryPathLease` 已是同一思路；这说明“状态集中”比“分类维度多”更关键 |
| **Misconception Diagnosis**（2602.02414） | 误区识别用“生成候选 → 检索 → 重排”，而非让分类器直出结论 | 分类器最多产出“误区候选线索”，不得写 `misconception` |
| **Beyond Helpfulness**（2606.16206） | 八个模型上“解题分”与“教学分”相关仅 0.421 | 分类准确率与教学质量是两条曲线，验收要分开报 |
| **MathTutorBench**（2502.18940） | 用奖励模型区分专家/新手教师回答，覆盖错误定位、纠错、苏格拉底提问、支架 | 可作离线评测参考；其结论不适用于我们的中文心理学教材 |

一句话概括：**2026 年的共识是“把状态、动作、评估的接口做对”，而不是“把输入分得更细”。**

## 5. 设计判断

### 5.1 分层不变，只补一层

现有代码实际是四层，方案的五层可以映射进来，不需要新建第五层：

```
L0 事实层（已有）：envelope / references / tasks / directives / execution_decision
L1 语义标签层（新增，可弃权）：cognitive_demand / difficulty_locus / persistence_signal
L2 状态投影层（已有，只读）：LearningStage / pending / mastery / preferences / plan / lease
L3 决策层（已有，三处）：analyze_teaching_turn / select_policy / StrategyRouter / resolve_teaching_mode
L4 生成层（已有）：prompt_blocks / reply_budget / quality_checker / citation gate
```

L1 之前为空、之后有三层，所以它是唯一值得动的地方。L3 的问题（三套策略词表）应通过**一个只读 façade** 收敛，而不是再加一层。

### 5.2 标签准入四条（不满足就不做）

1. **有消费者**：每个标签必须写清“读它的函数”和“它改变的一个具体输出”；没有消费者的标签只进 shadow 日志，不进 `GroundedTurn`。
2. **可标注**：两名标注者独立标注 ≥40 条，Cohen's κ ≥ 0.6；低于 0.6 说明定义不清，退回改定义，不写模型。
3. **可弃权**：无法判断时允许不输出该维度，**不用 `unknown` 标签充数**。
4. **不得越权**：不得覆盖已校验绑定与约束；不得写成绩、掌握、误区、复习队列、偏好。

### 5.3 V1 只做三个维度

| 维度 | 取值 | 唯一消费者 | 改变什么 | 回退 | 明令禁止 |
|---|---|---|---|---|---|
| `cognitive_demand` | recall / comprehend / apply / analyze / evaluate / create | `analyze_teaching_turn` 的 `strategy` + 回答结构模块 | analyze→先分解变量再解释；evaluate→给评价标准与证据辨析；create→约束清单+分步设计+方案自检；recall→简短+主动回忆 | 现有表层正则（为什么→contrast 等） | 不得据此判对错、不得改掌握度 |
| `difficulty_locus` | comprehension / discrimination / procedure / memory / pace | `TeachingTurn` 的 `needs_support` 分支 + `followup_context.SIMPLIFY` | discrimination→优先 `contrast`（而非盲轮换）；procedure→`worked_example/break_down`；memory→`retrieval_practice`；pace→缩短+分段 | `is_difficulty()` 布尔 → comprehension | 不得写成 `misconception`；“分不清”不等于有误区 |
| `persistence_signal` | attempting / help_seeking / answer_seeking / skip_request / off_task | 回合边界控制（是否以等待学生动作结束） | answer_seeking→按现有约束决定披露，并明确说出限制；skip_request→释放 pending、礼貌收尾、不追题；off_task→不进教材检索 | 现有 `SKIP_CHECK` / `ACKNOWLEDGEMENT` | 不叫 gaming；不进成绩；不跨会话累计成“学生画像” |

**明确不做的四件事：**

- `presentation_need`（术语密度/模态）：`InteractionPreferences` + `ScopedDirective` 已覆盖，新增会与偏好确认流程打架。
- `evidence_need`（是否必须检索教材）：这是**产品政策**，不是单轮语义。30 条自然样本中 9 条走“课堂补充”无来源，属于待决策项，不能靠分类器偷偷决定。
- `mastery` / `misconception`：已有 `LearningEvidence` 与误区管线；分类器只能给候选线索。
- `stuck` / `partial_understanding` 之类能力标签：单句证据不足，`repeated_difficulty` 必须由连续尝试记录推导。

### 5.4 方案里七阶段与现有 `LearningStage` 的对应

| 方案 | 现有 | 说明 |
|---|---|---|
| EXPLORE | `diagnostic` | 已有，且带 `DiagnosticResult` |
| EXPLAIN | `explain` + `feynman_check` | 我们的“复述检查”比方案的 EXPLAIN 更细 |
| PRACTICE | `practice` | 已有，绑定 `MasteryInteraction` |
| FEEDBACK | 无独立态 | 是 `practice` 内的一次评估结果，不该单独成为状态 |
| REMEDIATE | `error_diagnosis` | 已有 `ErrorRecord/ErrorType` |
| CONSOLIDATE / REVIEW | `review` / `completed` | 已有 `RepetitionState` 间隔重复 |

结论：**替换状态机是负收益**。需要补的是“本轮处于哪个状态”的读取投影，而不是新枚举。

### 5.5 教学动作库：不新建 15 个原子动作

方案列出 15 个动作，其中 11 个在现有 13/9 策略库里有对应（direct_explain≈direct_explanation、simplify≈scaffolding/break_down、give_example≈worked_example、compare≈conceptual_comparison、decompose≈break_down、focus/probe≈socratic_questioning、give_hint≈hint/progressive_hinting、diagnose_error≈error_based_learning、correct_misconception≈counterexample/direct_correction、active_recall≈retrieval_practice、check_understanding≈self_explanation、show_source≈教材引用门禁、visualize≈既有可视化工具、navigate≈Q5/reader 动作）。

真正缺的是**同一份 trace**：现在 `analyze_teaching_turn` 的选择、`select_policy` 的建议、`StrategyRouter` 的候选，互不可见。建议加一个只读装配函数（不改三者内部）：

```
build_teaching_plan(turn, snapshot) -> TeachingPlan{
  recommended: [...], chosen: str, alternatives: [...],
  reason: str, source: 'rule'|'labels'|'model', fallback_used: bool
}
```

它只做“调用现有三个函数 + 记录取舍”，可表驱动测试，也可作为标签的消费者和评估的观测点。

### 5.6 LangGraph：现在不引入，给出三条判据

已核实其能力：`StateGraph` + `checkpointer` + `interrupt()` / `Command(resume=...)` + `thread_id` 持久化，支持暂停后恢复（LangGraph 官方文档，本轮通过文档检索核对）。

项目现状：`TaskService` 已有请求重放、`loop_state.pending_tool_call_id`、`resume_understanding`、revision/epoch CAS、`MasteryPathLease` 单写入。这些与 `interrupt + checkpointer + thread_id` 是**同构**的。

引入判据（三条同时成立才考虑）：

1. 策略本身出现 >3 个需要回退/重入的分支节点，且必须在进程重启后从中间节点恢复；
2. 需要跨 worker 的 durable execution，现有 SQLite 收据无法承载；
3. 团队接受把状态所有权从 `TaskService` 迁出（这会重写现有恢复契约）。

当前一条都不成立。用纯函数 + 显式 `TeachingPlan` 数据结构即可，测试成本更低。IntelliCode 的六 Agent 架构是它的问题规模决定的，不是我们的。

### 5.7 固定教材：分类不碰检索，引用仍由服务端校验

- 现有链路：教材检索（精确直读/普通检索/LightRAG）、`citation_index` 位置校验、图绑定、发布前 `quality_checker`。
- 分类器只产出“学生要什么加工”，**不产出“该查哪一段”**；查询仍由 `TaskFrame.query` + 绑定对象决定。
- 三种内容来源的边界（教材事实/教学解释/辅助例子）已在生成层与 `verified_sources` 里实现，标签层不要重复表达。
- 待决策项不要顺手改：概念题是否强制先取教材来源、检索失败是否页面级提示、选区 `==…==` 标记是否清洗。这三条属于产品口径，与本轮分类器解耦。

## 6. 工程落点（文件级）

| 步骤 | 文件 | 改动 | 风险控制 |
|---|---|---|---|
| 1 | `knowledge/semantic_labels.v1.json`（新增） | 维度、取值、消费者、效果、标注指引、反例 | 纯数据，可评审 |
| 2 | `agents/input_understanding/labels.py`（新增） | 规则优先产出标签；只处理高置信、可机检的句式 | 不调模型，不写状态 |
| 3 | `agents/input_understanding/semantic.py::annotate` | 第三参数改为真实 `missing_dimensions`（现在恒为 `()`） | 端口保持“只补语义” |
| 4 | `models/input_understanding.py::SemanticAnnotation` | 增加可选 `value: str \| None`、`abstain: bool`（带默认值） | **不升 `schema_version`**；旧记录可反序列化 |
| 5 | `service.py` | 规则标签先跑；需要语义时与 `resolve()` **合并同一次调用** | 预算：模型调用 0 或 +1，不叠加 |
| 6 | `teaching_planner`/`adaptive_tutoring`/`teaching_policy` | 三个消费者按顺序接线，各自独立开关 | 每个开关可单独回退 |
| 7 | `tests/test_input_understanding_labels.py` + `tests/fixtures/semantic_labels_v1.jsonl` | 标签回归 + 决策点断言 | 与现有 `input_understanding_v1.tsv` 同风格扩展 |

**调用预算硬约束**：现有复杂解析 P95 2.925 秒、首字 P95 6.159 秒，30 次请求中 5 次用了两次调用。再串一次分类器会直接翻倍。规则能判的绝不进模型；必须进模型的与 `resolve()` 同一请求、同一 JSON。

**时间顺序**：`service.understand()` 里标签必须在 `decide()` 之前产出，但**只写 annotations**；`decide()` 不读标签（保持“标签不是授权”）。

## 7. 评估方案

### 7.1 标注单元是“决策点”，不是“句子”

一行样本 = 一个决策点：

```json
{
  "case_id": "S-014",
  "context_ref": "pending_choice|figure_5_2|plan_item_3|none",
  "raw_text": "我还是分不清信度和效度",
  "expected_labels": {"difficulty_locus": ["discrimination"], "cognitive_demand": ["comprehend"]},
  "expected_action_set": ["contrast", "show_source"],
  "forbidden": ["reveal_final_answer", "write_misconception"],
  "next_state": "awaiting_student"
}
```

### 7.2 规模与门槛

| 场景 | 条数 | 说明 |
|---|---|---|
| 概念/原理提问 | 30 | 含“为什么/区别/举例” |
| 困难与追问 | 30 | 含分不清、不会做、换说法、连轮 |
| 题目作答与反馈 | 25 | 含部分正确、禁止给答案 |
| 对象与选区 | 20 | 图、选区、历史例子 |
| 任务切换/边界 | 15 | 跳过、换话题、离题、结束 |
| 合计 | **120** | 每维度 ≥40，双人独立标注 |

门槛：每维 κ ≥ 0.6 才进入模型实现；κ < 0.6 的维度退回改定义或删除。**这是筛选维度的主要手段，比“再想几个维度”有效。**

### 7.3 三层指标

| 层 | 指标 | 不作数的东西 |
|---|---|---|
| 标签层 | 每维 micro-F1、macro-F1、弃权率、关键约束召回（`no_full_answer` 等） | 单模型 `confidence`、跨模型一致率 |
| 决策层 | 与教师标注动作集合的 Jaccard、禁用动作违规率、回退率 | 把“回答更长/更礼貌”当质量 |
| 回合层 | 答案泄露率（红线 0）、连续两轮同策略率、无来源断言率、近迁移完成率、轮次长度分布 | 单轮 LLM-judge 打分 |

### 7.4 反指标与红线

- **答案泄露率**：学生显式禁止时，任何一轮出现完整解答即失败（契约已有，评估要单独统计）。
- **重复解释率**：`used_strategies` 已有最近 6 次记录，可直接算“连续两轮同一策略”。
- **无来源断言率**：与现有 9/30 无来源样本对齐统计，不新增“证据标签”。
- **过度教学率**：只要定义/只要提示，却输出多段讲解 + 练习题。

### 7.5 明确不用的评估方法

1. 单个 LLM judge 的分数当结论（MisconceptDialogue：同一批对话，精确匹配 42.1% vs 校准判官 81.3%）。
2. 多模型一致性当效度（Agreement Is Not Validity）。
3. 把逐决策评分平均后当优化目标（The learner who does not learn）。
4. 只用 F1 证明“分类器有用”（Beyond Helpfulness：解题与教学相关仅 0.421）。

## 8. 风险

| 风险 | 触发条件 | 缓解 |
|---|---|---|
| 标签被当能力判定 | 把 `difficulty_locus=discrimination` 写入画像或降难度 | 标签只在单轮有效；写入需要 `LearningEvidence` |
| 词表继续膨胀 | 每遇到新句式加一个维度 | 准入四条 + registry 版本号，增维需评审 |
| 调用预算失控 | 标签单独调一次模型 | 规则优先；与 `resolve()` 合并；P95 预算纳入验收 |
| 三套策略继续分叉 | 只在其中一处接标签 | 先做 `build_teaching_plan` façade 再接线 |
| 旧链路回归 | 改动 `learning_intents` 语义 | 先把投影保持只读，灰度开关按学生放量 |
| 中文短句歧义 | 省略主语、否定、反问 | 否定与约束仍由规则/契约负责，标签永远不覆盖 |
| 教师权威边界 | 标签影响“是否算掌握” | 禁止写入成绩/复习；由既有授权服务执行 |

## 9. 建议交付序列

**Batch A（1 周，无模型）**：冻结 `semantic_labels.v1.json`（3 维）；建 120 条决策点标注集；出 κ 报告；把 `annotate(missing_dimensions)` 的调用修对。

**Batch B（1 周，影子）**：`labels.py` 规则标签 + 一次合并结构化调用；只在 shadow 记录，不改变任何输出；对比“旧规则结论 vs 标签推断结论”的差异清单。

**Batch C（1–2 周，逐个启用）**：`difficulty_locus` → 策略定向（收益最直接、可回滚）→ `cognitive_demand` → 回答结构 → `persistence_signal` → 回合边界。每个开关单独验收，保留上一批的对照样本。

不做的事：不重构 `TaskService`，不引入 LangGraph，不新建状态表，不动三套策略的内部实现。

## 10. 需要你决定的六件事

1. 是否接受“不建六维、V1 只做三维”，把 D1/D4/D6 继续用现有词表？
   （推荐：接受。否则会出现第 9、10 套并行标签。）
2. `cognitive_demand` 是否纳入 V1？它会改变回答结构，不只是打标签。
   （推荐：纳入，先只接 analyze/evaluate/create 三类，收益最明显。）
3. `persistence_signal` 是否允许影响“这一轮是否以等待学生结束/是否继续追问”？
   （推荐：允许，但不参与“给不给答案”——那由 `constraints` 契约决定。）
4. 是否允许把 `ConversationRouter.learning_intents` 降级为投影？
   （推荐：允许，但先只读投影，灰度观察一个版本再删分支。）
5. 120 条标注由谁做：你 + 一名助教双标，还是你单标 + 抽样复核？
   （推荐：双标 120 条，κ 是最便宜的风险探测。）
6. 概念题是否强制先取教材来源（影响 9/30 无来源样本）？
   （推荐：本批不动，单独立项；它影响时延与产品定位，不该塞进分类器。）

## 11. 本轮边界

- 只读源码与文档；未运行真实模型、未标注数据、未修改业务代码、未提交。
- 外部文献只读 arXiv 摘要与结论，未复现实验；`MRBench`、`LearnLM`、`DeepTutor` 上游线上版本本轮未重新核验，相关判断沿用上一轮本地源码审计。
- LangGraph 能力依据官方文档检索，未在本项目安装或压测。
- 未对 8000 端口服务、正式 SQLite、教材与图谱做任何读写。

## 12. 本地证据（本轮阅读）

- `models/input_understanding.py`：`Action` 14、`Constraint` 4、`ScopedDirective` 8 键、`ObjectReference` 13 类、`SemanticAnnotation`、`GroundedTurn.instructions()`（不含 annotations）
- `agents/input_understanding/{service,semantic,decision,adapters,rules,references}.py`：端口 `annotate(draft, context, ())`；`TaskService` 调用未传 classifier
- `agents/adaptive_tutoring.py`：`STRATEGIES` 9、`analyze_teaching_turn`、`TeachingTurn` 的 `needs_support` 轮换、`used_strategies[-6:]`
- `agents/teaching_policy.py` + `knowledge/teaching_strategies.json`：13 策略库、`select_policy`、`resolve_teaching_mode`
- `agents/strategy_router.py`：TACT 13 动作、规则预筛 + 受限选择
- `agents/conversation_router.py`：`student_move` 5 / `intent` 5 / `learning_intents` 8
- `agents/deeptutor_learning/models.py`：`KnowledgeType` / `ErrorType` / `LearningStage` 7 / `LearningEvidence` / `MasteryPathLease`
- `models/student_state.py`、`models/interaction_preferences.py`、`agents/followup_context.py`
- `tests/test_input_understanding_dataset.py` + `tests/fixtures/input_understanding_v1.tsv`：100 条工程标注的现有格式
- 上一轮：`INPUT_UNDERSTANDING_CLASSIFIER_RESEARCH_20261029.md`、`INPUT_UNDERSTANDING_DEEP_AUDIT_20261029.md`、`INPUT_UNDERSTANDING_SECOND_WAVE_20261030.md`

外部文献（arXiv ID）：

- 2610.15692 Do LLM Tutors Actually Teach?
- 2610.08703 Agreement Is Not Validity
- 2610.12125 The learner who does not learn
- 2505.07161 Actionable Pedagogical Feedback（multifunctionality）
- 2610.06446 The Assistance Dilemma
- 2608.12292 Teaching a LLM Tutor to Withhold the Answer
- 2609.12331 Simulating Disengaged Students（DAS2）
- 2603.28062 SLOW
- 2512.18669 IntelliCode
- 2602.02414 Misconception Diagnosis: Generate, Retrieve, Rerank
- 2606.16206 Beyond Helpfulness
- 2502.18940 MathTutorBench
- 2610.31679 MisconceptDialogue（评估口径影响结论）
