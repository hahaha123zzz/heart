# 六维本体 V1（psy-6d-v1）：替换方案、映射表与迁移顺序

日期：2026-10-30。性质：实施规格（spec），不改代码。前置：`SEMANTIC_CLASSIFIER_RESEARCH_20261030.md`。

## 0. 已定事项与本轮推荐

| 问题 | 决定 |
|---|---|
| 维度数 | **六维**，作为唯一对外本体；现有 8 套词表降为投影并分批删除 |
| `cognitive_demand` | **纳入，全 6 值**（理由见 §5） |
| `persistence_signal` / 回合边界 | **允许影响“是否继续追问、是否收尾”**，仍不参与“给不给答案” |
| `learning_intents` 降级 | 推荐：先只读投影，一个版本后删分支（§6.1） |
| 标注方式 | 推荐：双标 120 条；单人则自标 + 72 小时后 20% 盲重标 + 30 条留出集（§6.2） |
| 教材来源 | 推荐：按 D1×D2 分层强制，不新增“证据标签”（§6.3） |

一条硬约束：**六维是视图（view），不是新表、不是新枚举存储。** `GroundedTurn` 已随任务上下文持久化，`LearningStage` 有 `_STAGE_LEGACY` 历史映射，`Action` 被 14 值校验与 `decide()` 约束。直接改枚举会让旧记录读不出来，也会让回滚失效。

## 1. 六维定义（权威表）

`ontology_version = "psy-6d-v1"`。每个维度标注**来源**（read 状态 / derive 规则 / classify 模型）与**写入权**。

### D1 交互意图 `request_intent`

| 取值 | 允许的执行动作（`Action`） | 触发示例 |
|---|---|---|
| `knowledge_query` | explain_content, compare_content, discuss_claim | 什么是自变量；为什么随机分配能减少干扰 |
| `learning_support` | explain_content + 呈现指令 | 讲简单点；换个例子；画个图 |
| `exercise_interaction` | submit_student_answer, request_practice, provide_hint | 我选 B；出一道题；给点提示 |
| `repair` | discuss_claim, provide_hint, explain_content | 我还是分不清；我觉得这个实验没控制好 |
| `learning_management` | resume_pending_question, resume_learning_activity, propose/revise/confirm_learning_plan, switch_learning_target | 回到刚才那道题；继续学习安排 |
| `textbook_interaction` | explain_content / compare_content + 教材对象绑定 | 解释我圈选的这段；这张图什么意思 |
| `session_control` | propose_preference_change（+ 作用域指令） | 以后都讲详细点；接下来只讲不考 |
| `unclear` | clarify_reference | 这个再讲一下（无唯一对象） |

- **来源**：`derive`。由已校验的 `tasks[].action` + `directives` + `references.kind` 反推，**不调模型**。
- **写入权**：无。D1 是 `Action` 的上位分类，不是新权限。
- **作用**：① 校验新增动作必须归属某个 D1（防止再长出第 15 个 `Action`）；② 跨入口一致性（Q3/选区/Q5/旧路由对同一句话给出同一个 D1）；③ 作为教材来源策略的输入（§6.3）。

### D2 认知任务 `cognitive_demand`

| 取值 | 学生要做的加工 | 回答结构 | 策略倾向 |
|---|---|---|---|
| `recall` | 回忆定义、列特征 | 简短事实 + 一次主动回忆 | retrieval_practice |
| `comprehend` | 解释、说原理、做比较 | 定义→机制→关系 | direct_explanation / conceptual_comparison |
| `apply` | 用概念判断具体情境 | 情境→判断→依据 | worked_example / guided_revision |
| `analyze` | 找变量、拆结构、找缺陷 | 先分解要素，再逐项说明 | socratic_questioning / scaffolding |
| `evaluate` | 判断设计是否合理 | 评价标准→证据→结论 | counterexample / conceptual_comparison |
| `create` | 设计方案、提出改进 | 约束清单→分步设计→方案自检 | scaffolding + 清单 |

- **来源**：`classify`（规则优先，模型兜底）。**唯一真正新增的枚举。**
- **多标签**：允许，按任务顺序排列，≤3 个（“分析这个实验并提改进”= analyze + evaluate + create）。
- **弃权**：允许缺失，不写 `unknown`。
- **写入权**：只能选“回答结构 + 策略候选”，不得判对错、不得写掌握。

### D3 学习状态 `learner_state`（结构体，不是单标签）

| 字段 | 取值 | 来源 | 说明 |
|---|---|---|---|
| `attempt` | none / awaiting / correct / incorrect / partial | **read** | 来自 `MasteryInteraction`/评估结果，不猜 |
| `self_report` | none / confused / stuck / understood | classify | 只记录“学生自己说的”，不升级为诊断 |
| `difficulty_locus` | comprehension / discrimination / procedure / memory / pace | classify | 替代 `is_difficulty` 布尔 |
| `engagement` | engaged / help_seeking / answer_seeking / skip / off_task | classify | 单轮**信号**，跨轮才可累计 |
| `affect` | neutral / confused / frustrated / bored | **read** | `StudentState.emotion`，非心理诊断 |
| `history` | first / repeat / regressed | **read** | 由 `LearningEvidence`(attempt_count, hints_used) 推导 |

- `repeated_difficulty` 不在此列：它必须由 `history=repeat` + 连续失败证据推导，不能由一句话分类。
- **写入权**：`difficulty_locus` 与 `engagement` 只影响本轮策略与回合边界；写成绩/复习一律走既有授权服务。

### D4 内容对象 `content_target`

- **来源**：`read`。直接使用已校验的 `ObjectReference`（13 类）+ `KnowledgeType`（4 类）。
- 追加两个只读聚合：`knowledge_point_id`、`chapter_id/section_id`。
- **写入权**：无。分类器不得生成 ID、页码、题目编号（`model_reference_not_in_candidates` 已保护，保持）。
- 本维度**不做任何模型判断**。

### D5 支持需求 `support_need`（解析结果，不是分类）

| 控制项 | 取值 | 合并优先级（高→低） |
|---|---|---|
| `verbosity` | short / normal / long | 本轮指令 > 本题 > 本次安排 > 已确认偏好 |
| `terminology` | casual / normal / professional | 同上；本轮新增，暂不持久化 |
| `guidance` | direct / light / strong | 本轮指令 > 教学方式 > 偏好 |
| `examples` | none / one / many | 同上 |
| `modality` | text / table / diagram / interactive | 本轮新增，暂不持久化 |
| `disclosure` | full / hint_only / no_answer / verdict_only | **只由约束决定**，不由偏好标量决定 |
| `difficulty` | unknown / easier / harder | 只读证据；不改持久难度 |

- **来源**：`resolve`（`InteractionPreferences` + `ScopedDirective` + 本次安排）。
- **关键**：`disclosure` 是契约（`no_full_answer` / `hint_only` / `verdict_only`），不是分类标签。任何标签都不能放宽它。
- 术语密度与模态先只支持 `scope=turn`，避免动现有偏好确认流程。

### D6 教学阶段 `teaching_stage`

| 字段 | 取值 | 来源 |
|---|---|---|
| `stage` | diagnostic / explain / feynman_check / practice / error_diagnosis / review / completed | **read**（`LearningStage`） |
| `turn_state` | awaiting_student / explaining / practicing / closing | derive |
| `next` | continue_pending / advance / close | derive |

- 方案里的 EXPLORE→CONSOLIDATE→REVIEW 与现有 7 态同构，**不新建状态机**；`turn_state` 只表达“本轮怎么结束”。
- `closing` 的合法触发：`engagement=skip`、`engagement=answer_seeking` 且披露被禁止、任务完成。这条就是你说的“允许 persistence_signal 影响回合边界”。

## 2. 现有 8 套词表 → 六维的替换映射

| 现有 | 现规模 | 归入 | 处置 | 批次 |
|---|---|---|---|---|
| `Action` | 14 | D1 的执行投影 | **保留**，新增“必须归属某 D1”校验 | B1 |
| `Constraint` | 4 | D5.disclosure | 保留（契约），不再另设同义标签 | B1 |
| `ScopedDirective` | 8 键 | D5 | 保留（存储），D5 是每轮解析视图 | B1 |
| `ObjectReference.kind` | 13 | D4 | 保留，只读 | — |
| `ConversationRouter.student_move` | 5 | D3.attempt / D3.engagement | 投影，后删 | B4 |
| `ConversationRouter.intent` | 5 | D1 | 投影，后删 | B4 |
| `ConversationRouter.learning_intents` | 8 | D1 的二级 | 降为只读投影，B4 删分支 | B2/B4 |
| `analyze_teaching_turn.move` | 7 | D1 + D3 | 删除字段，保留 `strategy` | B4 |
| `analyze_teaching_turn.strategy` | 9 | 13 策略库 | 别名合并（见 §3） | B3 |
| `is_difficulty` 布尔 | 1 | D3.difficulty_locus | 降为兜底（`locus` 缺省时按 comprehension） | B2 |
| `teaching_policy.KNOWN_STRATEGIES` | 8 | 13 策略库 | **死代码，删除** | B4 |
| `teaching_planner.ALLOWED_STRATEGIES` | 8 | 13 策略库 | **合并**（与库不一致，见 §3） | B3 |
| `resolve_teaching_mode` | 5 | D5.guidance + D5.disclosure | 保留为解析器，输出进 D5 | B1 |
| `InteractionPreferences` | 7 | D5 存储后端 | 保留不动 | — |
| `LearningStage` | 7 | D6.stage | 保留，只读 | — |
| `StudentState.emotion` | 5 | D3.affect | 保留，只读 | — |
| `SemanticAnnotation` | 自由键 | D2 / D3 | **复用**：dimension=六维名，label=取值，quote=原话 | B1 |

## 3. 四处已经分叉的策略表（这是“效果上不去”的真实原因之一）

同一个“教学动作”概念，仓库里有 4 份互不完全一致的清单：

| 位置 | 数量 | 特征 |
|---|---|---|
| `knowledge/teaching_strategies.json` | 13 | 最全（TACT），含 `socratic_questioning`、`counterexample`、`self_explanation`、`retrieval_practice`、`summary`、`guided_revision` |
| `agents/strategy_router.py::MOVE_ACTION_DEFAULTS` | 13 | 与库一致 |
| `agents/adaptive_tutoring.py::STRATEGIES` | 9 | `explain/worked_example/contrast/break_down/prerequisite/guided_practice/feedback/transfer/hint`，并且是 `TeachingStepTool` 的**对模型公开枚举** |
| `agents/teaching_planner.py::ALLOWED_STRATEGIES` | 8 | 含 `error_based_learning`、`progressive_hinting`，**这两个不在库中** |
| `agents/teaching_policy.py::KNOWN_STRATEGIES` | 8 | 无任何调用方 |

后果：同一个学生状态，“该用对比还是该用反例”在不同运行时里得到不同答案；模型看到的可选动作在 Q3 与旧计划器里不同。

**收敛方案**：以 13 库为唯一权威；9 与 8 都是别名。

| 旧值 | 权威值 |
|---|---|
| explain | direct_explanation |
| contrast | conceptual_comparison |
| break_down | scaffolding |
| prerequisite | scaffolding（前置补充，附 note） |
| guided_practice | socratic_questioning |
| feedback | guided_revision（部分正确）/ direct_correction（明确错误） |
| hint | hint |
| error_based_learning | counterexample |
| progressive_hinting | hint（`hint_level` 区分层级） |
| worked_example / transfer | 同名保留 |

迁移时**不要一次改运行值**：先加 `canonical_strategy` 字段并双写，消费者切到 canonical，最后统一输出。`TeachingStepTool` 的 enum 属于对模型公开接口，需与迁移同批发布，否则模型会输出旧值被拒绝。

## 4. 六维落在哪里（零 schema 变更）

```
agents/input_understanding/ontology.py   # 新增：build(turn, snapshot) -> SixDim（纯函数）
knowledge/semantic_labels.v1.json        # 新增：六维注册表（取值/消费者/效果/反例/标注指引）
agents/input_understanding/labels.py     # 新增：规则优先的 D2/D3 标签
models/input_understanding.py            # 不改字段；SemanticAnnotation 已够用
```

- `SemanticAnnotation(dimension, label, quote, source)` 恰好承载“维度 + 取值 + 原话依据 + 规则/模型”。六维名直接作为 `dimension`，`ontology_version="psy-6d-v1"`。
- D1/D4/D5/D6 是**推导视图**，不产生 annotation（没有原话依据的推断不该伪装成标注）。
- `SemanticAnnotation` 如需数值，用 `label` 编码（如 `locus:discrimination`），避免改 schema。
- `understand()` 里 `annotate(draft, context, ())` 的第三参数必须传真实缺失维度，否则模型只能自由发挥。

## 5. 效果从哪里来（按收益排序）

不讲预测数字，只给可验收的因果链：

1. **`difficulty_locus`**（收益最直接）：修掉“分不清→盲轮换”。验收：discrimination 样本首轮 `conceptual_comparison` 命中率 ≥80%；连续两轮同策略率下降。
2. **`cognitive_demand`**（回答结构）：修掉“设计实验被当讲解”。验收：create/evaluate 样本包含约束清单或评价标准的比例 ≥80%；`create` 样本意外走 `explain` 的比例 ≤10%。
3. **`engagement` + `turn_state`**（回合边界）：修掉“不想做了还被追题”“要答案还被绕”。验收：skip 样本 100% 收尾且不再出题；answer_seeking 且禁止披露时 0 次泄露。
4. **D5 解析**：修掉“直接给答案”和“只给提示”同时出现时的前后矛盾。验收：冲突指令样本 0 次越权披露。
5. **D1 白名单**：修跨入口不一致。验收：同一句话在 Q3/选区/Q5 三个入口得到同一 D1 ≥95%。
6. **D4**：本来就对，只做只读聚合，不动。

`cognitive_demand` 的取舍：它主要改善**回答结构**而非路由，所以不要指望它提升“意图准确率”。它值钱的地方是 create/evaluate 两类今天完全没有分支。全 6 值都标，但**只先接 analyze/evaluate/create 三个消费者**，其余靠现有表层规则兜底——这样收益确定、回归面最小。

## 6. 三个待定项的推荐

### 6.1 `learning_intents` 降级（推荐：分两步）

第一步（B2）：`learning_intents` 只由 D1 投影生成，不再单独调模型；旧 Orchestrator 读投影，行为不变。
第二步（B4）：确认投影与旧结果差异清单后可删分支。
理由：一次性删除会同时改动旧 Orchestrator 的输入契约，而它目前是 Q3 之外唯一的兜底路径。

### 6.2 标注（推荐：120 双标 + 30 留出）

- 120 条决策点，双人独立标注，报每维 Cohen's κ；κ<0.6 的维度退回改定义或删除。
- **另留 30 条永不参与调提示**，只用一次最终验收；否则“效果好”只是对标注集过拟合。
- 只能单人时：自标 120 条 + 72 小时后盲重标 20%，报**组内**一致性（≥0.7），并明确写“这不是人际 κ”。
- 顺序建议：先标 `difficulty_locus` 与 `cognitive_demand`（两者决定 80% 的效果），其余四维靠读取/推导，几乎不需要标注。

### 6.3 教材来源（推荐：按 D1×D2 分层，不加新标签）

| 情形 | 来源要求 |
|---|---|
| D1=knowledge_query 且 D2∈{recall, comprehend} | **必须先取教材来源**；取不到就明说，不用课堂补充冒充 |
| D2∈{apply, analyze, evaluate, create} | 允许 blended，但必须逐条标注“教学示例/非教材原文” |
| D1=textbook_interaction | 必须绑定对象并给出精确位置 |

这条直接决定现有 9/30 无来源样本的处置，且不需要新增 `evidence_need` 标签——它由 D1、D2 两个已有维度决定。这是六维本体顺带解决的一个产品口径问题。

## 7. 迁移批次（每批可单独回滚）

**B1 视图层（不改行为）**
新增 `ontology.py` + 注册表；六维从现有状态推导；写入 shadow 日志；`annotate` 修参数。验收：同一批样本上六维稳定、无模型调用、旧输出逐字节一致。

**B2 接入 D2 / D3**
规则标签优先，模型与之合并同一次结构化调用（禁止串行第二次调用）。只接 `difficulty_locus` → 策略定向、`cognitive_demand` → 回答结构。验收：§5 的 1、2 两条 + 0 越权。

**B3 合并策略表**
13 为权威，9/8 变别名；`canonical_strategy` 双写；`TeachingStepTool` enum 同步。验收：三套运行时对同一状态给出同一 canonical。

**B4 删除重复**
删 `KNOWN_STRATEGIES`、`analyze_teaching_turn.move`、`learning_intents` 独立调用、`is_difficulty` 的盲轮换分支（保留函数兜底）。验收：全量回归 + 30 条留出集。

## 8. 风险

| 风险 | 缓解 |
|---|---|
| 六维变成“什么都装” | 每维必须有唯一消费者；注册表评审才可增取值 |
| `Action` 与 D1 双写不一致 | B1 起加“Action 必须属于 D1”的校验，测试覆盖 14 个动作 |
| 策略表合并改变模型可选动作 | 与 `TeachingStepTool` 同批发布；先双写再切换 |
| 标注集成为调参集 | 30 条留出集隔离；提示词只用 120 条 |
| 回合边界被滥用成“赶学生走” | `closing` 只允许三种触发，且必须给下一步建议 |
| 模型调用超预算 | D2/D3 与既有 `resolve()` 合并；P95 首字预算沿用现有门禁 |

## 9. 本轮边界

只产出规格与取舍，未改代码、未跑模型、未标注。§3 的策略表不一致来自源码直读；若要据此删除，需先补一份“三套运行时同状态对照”的测试，否则无法证明合并无回归。
