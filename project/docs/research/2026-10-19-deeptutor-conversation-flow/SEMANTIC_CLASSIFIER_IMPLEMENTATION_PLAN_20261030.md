# 六维语义分类器实施计划（psy-6d-v1）

日期：2026-10-30。分支基线：`codex/input-understanding-v1` 同族工作区。性质：实施计划。前置规格见 `SEMANTIC_ONTOLOGY_V1_SPEC_20261030.md`。

本计划把“六维本体 + 策略词表收口”拆成 5 个可独立回滚的批次。硬约束：不改持久化 schema、不新建状态表、不引入 LangGraph、不新增第二套理解/回答链路。

---

## 0. 范围与非目标

**范围**

1. 策略词表收口为 13 个库 id（本批已完成，见 §1）。
2. 六维本体作为**只读视图**产出并落 shadow 日志。
3. 只对 D2 认知任务、D3 困难定位与参与信号做语义标注（规则优先，必要时与既有解析合并一次模型调用）。
4. 三个消费者按开关逐个接线：策略定向、回答结构、回合边界。
5. 120 条决策点标注集 + 30 条留出集 + 三层指标。

**非目标**

- 不新建 `services/classification/` 包，不复制 `Action`/`ObjectReference`/`LearningStage`。
- 不做掌握度推断、不写误区、不写成绩或复习队列。
- 不改教材检索路径、引用校验、发布门禁。
- 不把 `TeachingStepTool` 的 9 个运行时名改成 13 个（对外接口另批判，见 §6）。
- 不新增 `evidence_need` / `presentation_need` 标签（前者是产品政策，后者由偏好系统承担）。

---

## 1. 已完成（本轮实际改动）

| 文件 | 改动 | 影响面 |
|---|---|---|
| `agents/teaching_policy.py` | 新增 `STRATEGY_ALIASES`（9 条历史名 → 13 库 id）、`canonical_strategy()`、`accepted_strategy_names()`；**删除死代码 `KNOWN_STRATEGIES`** | 无行为变化 |
| `agents/teaching_planner.py` | `ALLOWED_STRATEGIES = strategy_ids()`（13 个库 id，单一来源）；`_validate` 先把别名归一再校验 | 模型可选动作从 8 个旧名变为 13 个规范名；顺带修掉“回退值可能不在白名单”的旧缺陷 |
| `agents/adaptive_tutoring.py` | `STRATEGIES` 保持 9 个运行时名，注释声明其为别名，禁止新增第 5 份表 | 零行为变化 |
| `tests/test_strategy_catalog.py` | 新增 8 项：库唯一性、别名不遮蔽规范 id、运行时名可归一、planner 归一/拒绝未知、死列表不复活 | — |
| `knowledge/semantic_labels.v1.json` | 六维注册表：维度、取值、消费者、标注示例与反例 | 纯数据 |
| `agents/input_understanding/ontology.py` | 六维只读视图 `build()`；`missing_labels()`；`valid_label()`；全部为推导，不调模型 | 无行为变化 |
| `agents/input_understanding/semantic.py` | `annotate()` 传入真实缺失维度；越界标签整批拒绝 | 仅分类端口 |
| `agents/input_understanding/adapters.py` | `final_summary()` 增加 `six_dim`（不暴露 `canonical_id`） | 结果摘要多一个键 |
| `tests/test_ontology_view.py` | 15 项视图测试 | — |
| `tests/test_input_understanding_dataset.py` | 100 条既有样本同时断言六维可构建、`model_calls=0` | — |
| `agents/input_understanding/labels.py` | 规则标签（D2/D3）：具体优先、否定保护、按注册表 cap、`merge()` 校验 | 只在视图层生效 |
| `agents/input_understanding/service.py` | 规则标签在 `resolve()` 之前并入（`SEMANTIC_LABELS_ENABLED`，默认开） | 标签不改变任务/约束 |
| `agents/input_understanding/semantic.py` | `SemanticCandidate.labels`；复杂解析同一次调用产出标签；无效标签丢弃并记 `semantic_label_rejected`；分类端口与规则标签合并 | `model_calls` 上限仍为 2 |
| `tests/fixtures/semantic_labels_v1.jsonl` + `tests/test_input_understanding_labels.py` | 40 条标注 + 10 项行为测试 | — |
| `agents/adaptive_tutoring.py` | P3 三个开关：`LABELS_POLICY`（策略定向）、`LABELS_STRUCTURE`（回答结构）、`LABELS_TURN`（回合边界） | 默认关闭 |
| `scripts/eval_semantic_labels.py` | 离线标签评估（P/R/F1、弃权、逐维） | 只读 |
| `tests/fixtures/decision_points_v1.jsonl` / `holdout_v1.jsonl` | 120 条工程回归 + 30 条留出 | — |
| `tests/test_label_consumers.py` / `tests/test_decision_points.py` | 5 + 4 项 | — |
| `scripts/annotation_agreement.py` | 双人标注 Cohen's κ（逐维/逐标签/完全一致率） | 只读 |
| `tests/test_annotation_agreement.py` | 3 项：完美一致、已知 κ=0.6、case_id 不一致 | — |
| `tests/test_runtime_strategy_parity.py` | 5 项：三套策略路径都能归一到 13 库 id | 锁定 P5 前置不变量 |

**证据**（`.runtime/`）

| 日志 | 内容 | 结果 |
|---|---|---|
| `merge-before-batch.log` | 回滚本轮 3 个文件后运行 106 项 | 25 errors + 2 failures |
| `merge-after-batch.log` | 保留改动运行同一批 + 新增 8 项 | 114 项，25 errors + 2 failures |
| `strategy-merge-tests.log` / `merge-before.log` | 含 `test_memory_personalization`、`test_exercise_skills` 的 90/23 项对照 | 前后均为 20 errors，数量一致 |

失败均来自工作区已删除的 `knowledge/exercises/catalog.json`、`frontend/textbook/*.pdf` 等数据（`practice.question` 返回 404、生成阶段未触发），与本批改动无关；**不能宣称这两组测试通过**，需要恢复数据后重跑。

剩余待办（本批未做）：

- `TeachingStepTool` 的 enum 仍是 9 个运行时名；canonical 双写未做。
- 三套运行时“同一状态同一策略”的对照测试未写。

---

## 2. 数据流

```
输入 → understand()（已有）
        ├─ L0 事实：envelope / references / tasks / directives
        ├─ L1 标签：仅 D2、D3 的 classified 字段（规则优先；必要时与 resolve() 合并一次调用）
        └─ decision.decide()
     → ontology.build(turn, context)            ← 新增，纯函数，六维只读视图
     → final_summary(six_dim=...)               ← 写入结果摘要，供 shadow 与前端观测
     → 既有 TeachingTurn / Q5 / 选区链路
```

六维中 **D1、D4、D5、D6 全部是推导**（`tasks[].action`、`references`、`directives+preferences`、`LearningStage`），**不产生 annotation**。只有 D2 与 D3 的 `self_report / difficulty_locus / engagement` 走分类。

`GroundedTurn` 不新增字段（`StrictModel(extra='forbid')`）；六维视图通过 `final_summary()` 的独立键返回，不进入持久化协议，避免版本迁移。

---

## 3. 批次

### P1 六维视图（已实施）

**已交付**

- `agents/input_understanding/ontology.py`：`build(turn, context)` 返回六维；`missing_labels(turn)` 返回未标注的可分类维度；`valid_label()` 以注册表校验。
  - D1 由 `tasks[].action` 推导（`intent_for()`，含“指向教材对象→textbook_interaction”“有待答题时的提示→exercise_interaction”两条上下文规则）。
  - D2/D3 的 classifiable 字段只读 `annotations`；缺失即弃权，不写 `unknown`。
  - D3 的 `attempt` 读 `tutoring.progress.pending_question` 与 `tutoring.assessment.verdict`；`affect/history` 在 `TaskContext` 无来源，保持 `null`。
  - D5 按“本轮指令 > 偏好”解析；`disclosure` 只由 `constraints` 决定，模式固定为 `constraint`。
  - D6 输出 `stage`（读 `LearningStage`）、`turn_state`、`next`；`closing` 只在 skip 或“要答案但要不到”时触发。
- `knowledge/semantic_labels.v1.json`：六维词表 + 4 个可标注维度及其示例/反例。
- `annotate()` 现在传入真实缺失维度，并拒绝注册表外的维度或取值（`unknown_semantic_label`）。
- `final_summary()` 增加 `six_dim`；不输出 `canonical_id`。

**验收**

- `tests/test_ontology_view.py` 15 项通过。
- 既有输入理解回归 85 项通过（含 100 条工程标注样本逐条构建六维、`model_calls=0`）。
- `tests/test_input_understanding_integration.py` 有 1 项 `retrieval_not_ready` 错误；已用回滚对照确认与本批无关（`ontology-integration-before.log` 同样报错）。

**未做**

- 真实模型下的 30 条同批对照未跑（本批无模型调用，视图为纯函数）。
- 本轮 `answer_length` 指令仍不被规则解析（只有长期偏好会产出该指令），因此 `verbosity.source` 目前只会是 `profile` 或 `null`；优先级规则已有测试，等 P2 解析后才会出现 `turn`。

### P2 标签层（已实施）

**已交付**

- `agents/input_understanding/labels.py`
  - 规则表 17 条，覆盖 `difficulty_locus`（pace/memory/discrimination/procedure/comprehension）、`self_report`、`engagement`、`cognitive_demand`（create/evaluate/analyze/apply/comprehend/recall）。
  - 单标签维度按“具体优先”取第一条命中；认知任务按出现位置排序，最多 3 条（cap 取自注册表）。
  - 否定前缀（不要/别/先别/不用/不必/无需/不想/并非/没有）不产出标签。
  - `merge()` 统一做取值校验、去重与 cap，模型标签只能补空缺。
- `service.understand()`：规则标签在 `resolve()` 之前并入；`SEMANTIC_LABELS_ENABLED=0` 可整体退回无标签（默认 `1`，因为标签只影响视图）。
- `semantic.resolve()`：`SemanticCandidate` 新增 `labels`，与任务解析共用**同一次**模型调用；提示词携带四个标签维度的取值表。
- 无效模型标签的处理：丢弃该条、保留已解析任务，并记 `unresolved=semantic_label_rejected`（不整批回退，标签是建议而非授权）。
- `semantic.annotate()`：分类端口返回的标签与规则标签合并，不再覆盖；仍接收真实缺失维度。

**验收**

- `tests/test_input_understanding_labels.py` 10 项通过；`tests/fixtures/semantic_labels_v1.jsonl` 40 条逐条比对，`quote` 均为原文子串。
- 相关回归 110 项：109 通过，仅 `test_input_understanding_integration` 的 `retrieval_not_ready`（已确认与改动无关）。
- 教学/回答链路同批 106 项：25 errors + 2 failures，与 P1 前完全一致（数据缺失所致）。

**未做 / 未验证**

- **没有跑真实模型**：40 条只验证规则；合并调用的耗时与 `model_calls` 分布未在真实网关上测。
- 提示词新增标签取值表，token 有增加（未量化）。
- 规则对反讽、双重否定、长句嵌套仍可能误标；这些由模型路径或弃权兜底，未做对抗样本。

### P3 消费者接线（已实施）

| 开关 | 消费的标签 | 改动点 | 行为 |
|---|---|---|---|
| `LABELS_POLICY` | D3.difficulty_locus | `TeachingTurn` 策略选择 | discrimination→`contrast`；procedure→`worked_example`；pace→`break_down`；其余保留原轮换（运行时 9 个策略名里没有 retrieval，memory 不硬凑） |
| `LABELS_STRUCTURE` | D2.cognitive_demand | `TeachingTurn.instructions()` | create→约束清单+分步+自查；evaluate→标准+证据；analyze→先分解要素；其余不干预 |
| `LABELS_TURN` | D3.engagement | `TeachingTurn.skip` / `limit_disclosure` | skip→复用既有 skip 路径（释放 pending、`check_skipped`）；answer_seeking 且 `no_full_answer`→说明限制、给下一步 |

**与原计划的偏差**

- 没有新增 `build_teaching_plan` façade：三个消费者各自读 `six_dim`，少一层间接。
- memory 未映射到 `retrieval_practice`：该策略不在 Q3 运行时 9 个名字里，硬映射会让 `TeachingStepTool` 校验失败。
- 未做 off_task→跳过检索：教材检索由既有链路决定，标签层不碰检索（与 §5.7 一致）。

**验收**

- `tests/test_label_consumers.py` 5 项通过：off/on 同快照对照、无标签保持轮换、结构提示只在开关开时出现、skip 释放 pending、answer_seeking 限制话术。
- 默认开关全关；`tests.test_adaptive_tutoring`、`test_teaching_modes` 等 97 项无变化。

### P4 标注集与评估（已实施）

**改动**

- `tests/fixtures/decision_points_v1.jsonl`：120 条工程回归集（标签维度 + 弃权样例）。
- `tests/fixtures/holdout_v1.jsonl`：30 条留出集，写规则时未参考。
- `scripts/eval_semantic_labels.py`：逐维 P/R/F1、support、弃权数、micro/macro。
- `tests/test_decision_points.py`：schema 校验 + 120 条 micro-F1 ≥0.95 门禁；留出集只做 schema 校验，不设门禁。

**实测（`.runtime/eval-labels.log`）**

| 集合 | micro P | micro R | micro F1 | 说明 |
|---|---|---|---|---|
| 120 条工程回归 | 1.00 | 1.00 | 1.00 | 期望值按规则契约标注，只防回归，不代表泛化 |
| 30 条留出 | 0.83 | 0.42 | 0.56 | 逐维：cognitive 0.53、self_report 0.80、difficulty 0.40、engagement 0.67 |

结论：**规则只覆盖显式说法，改写后召回掉到 0.42**。这正是保留模型路径（`resolve` 同一次调用产出标签）的理由；也说明不能把规则命中率当语义准确率。

**未完成**

- 双人标注 κ 未做：本环境只有一名标注者。工具已就绪：
  `python scripts/annotation_agreement.py A.jsonl B.jsonl`，输出逐维/逐标签 κ 与完全一致率；`tests/test_annotation_agreement.py` 用合成数据验证了 κ 计算（含已知 κ=0.6 的算例）。拿到第二份标注文件即可出数，低于 0.6 的维度应退回改定义。
- 动作集合 Jaccard、答案泄露率、连续同策略率未进脚本：前两者属回合层评估，需要真实模型回合；后者可从 `used_strategies` 现有字段统计，但本轮没有真实运行数据。

### P5 收口删除（未执行，门禁未满足）

**已就绪的前置证据**：`tests/test_runtime_strategy_parity.py` 覆盖 5 条消息 × 4 个上一轮策略 × 6 种学生状态，证明 `analyze_teaching_turn`、`select_policy`、`StrategyRouter` 三条路径吐出的策略名**全部能归一到 13 个库 id**，没有第四条词表。这解决了“词表分叉”，但没有解决“行为是否等价”。

| 删除项 | 状态 | 原因 |
|---|---|---|
| `ConversationRouter.learning_intents` 独立调用 | 未删 | 需要“投影 vs 旧结果差异 ≤2%”的真实模型对照，本轮未跑 |
| `analyze_teaching_turn.move` 字段 | 未删 | 被 `invite_check`、prompt 与合成评估共用，删除需同步改 4 处调用与相关测试，收益低 |
| `is_difficulty` 盲轮换 | 保留为兜底 | 与计划一致（标签缺失时仍需轮换） |
| `TeachingStepTool` 9 值 enum | 未改 | 模型可见接口。改成 13 会让模型看到 `conceptual_comparison` 这类新词，`analyze_teaching_turn` 的轮换表仍是运行时 9 个名字，必须同批重写；没有真实模型 A/B 就不能判断是否改善教学 |

结论：P5 的删除项依赖“第二标注者 κ + 真实模型 A/B”，当前只补齐了词表不变量。强行删除会让回滚与旧记录都变复杂。

---

## 4. 数据契约

### 4.1 标签（复用现有结构，不改 schema）

```json
{
  "dimension": "difficulty_locus",
  "label": "discrimination",
  "quote": "我还是分不清信度和效度",
  "source": "rule"
}
```

约束：

- `dimension` 必须属于 `psy-6d-v1` 注册表，且该维度 `classifiable=true`。
- `label` 必须在该维度取值表内。
- `quote` 必须逐字出现在 `raw_text`（`GroundedTurn` 已有校验）。
- 弃权 = 不输出该维度，**不写 `unknown`**。
- 单维最多 3 个标签；总标签数受现有 `max_length=16` 限制。

### 4.2 决策点样本

```json
{
  "case_id": "S-014",
  "context_ref": "pending_choice",
  "raw_text": "我还是分不清信度和效度",
  "expected_labels": {"difficulty_locus": ["discrimination"]},
  "expected_action_set": ["conceptual_comparison", "show_source"],
  "forbidden": ["reveal_final_answer", "write_misconception"],
  "next_state": "awaiting_student",
  "split": "train"
}
```

配额：概念/原理 30、困难与追问 30、作答与反馈 25、对象与选区 20、任务切换/边界 15。

---

## 5. 验收矩阵

| 批次 | 单元 | 集成（受控 HTTP） | 真实模型 | 页面 |
|---|---|---|---|---|
| P1 | 必做 | 30 条同批对照 | 不需要 | 不需要 |
| P2 | 必做 | 40 条标注回归 | 至少 10 条真实调用，记录 `model_calls` | 不需要 |
| P3 | 必做 | 开关 off/on 同快照 | 三类样本各 ≥5 条 | 至少 1 次“分不清→对比”真实回合 |
| P4 | 必做 | 汇总脚本 | 留出集一次 | 不需要 |
| P5 | 全量回归 | 旧路由/计划/Q5/选区 | 冒烟 | 关键页面回归 |

证据分级沿用项目惯例：纯函数结果不等于链路通过，替身回答不等于真实模型，受控 SQLite 不等于正式库。每批必须写明“没验证什么”。

---

## 6. 未决与依赖

1. **概念题是否强制教材来源**（现有 30 条中 9 条无来源）。计划按 D1×D2 分层实现，但需产品确认后才能启用；本计划不默认改变这一策略。
2. **`TeachingStepTool` enum 是否切到 13 个规范名**。它是模型可见接口，切了要同步提示词与受控夹具；建议 P5 再做。
3. **术语密度 / 辅助模态**是否持久化。当前只支持本轮，持久化会动偏好确认流程。
4. **主对话与侧栏的回合状态隔离**。本计划的标签跟随 task 而非 session，但侧栏独立状态需要另立一项。
5. **标注人力**。若只能单人，需按规格 §6.2 报组内一致性，不得声称为人际 κ。

---

## 7. 风险

| 风险 | 触发 | 缓解 |
|---|---|---|
| 六维变成“什么都装” | 新句式就加维度 | 注册表评审 + 准入四条（消费者/可标注/可弃权/不越权） |
| 标签影响成绩 | 把 `difficulty_locus` 写进 `StudentState` | 标签仅单轮；写入必须走 `LearningEvidence` |
| 策略合并改坏模型行为 | enum 与提示词不同步 | P5 双写一版，先观察再切 |
| 调用预算超支 | 标签单独调模型 | 与 `resolve()` 合并；`model_calls` 上限 2 由现有校验兜住 |
| 评估过拟合 | 用同一批调提示 | 30 条留出集隔离 |
| 历史失败被误认为新回归 | 已删除教材/题库导致 20 项失败 | 每批附前后同命令对照日志（本轮已示范） |

---

## 8. 里程碑

| 周 | 交付 | 依赖 |
|---|---|---|
| W1 | P1 视图 + 注册表 + 30 条同批对照（**已完成**：15 项视图测试 + 100 条样本构建通过） | 无 |
| W2 | P2 规则标签 + 40 条回归 + 合并调用预算（**已完成**：10 项 + 40 条标注；真实模型耗时未测） | P1 |
| W3 | P3 三个开关（**已完成**：5 项 off/on 对照） | P2 |
| W4 | P4 120 条标注 + κ + 留出集（**部分完成**：工程回归 1.00、留出 F1 0.56；κ 缺第二标注者） | P3 观测数据 |
| W5 | P5 收口删除（**未执行**：门禁未满足，见 §3 P5） | P4 通过 |

每个里程碑结束写一份执行记录，附日志路径、失败保留、未验证范围。

## 9. 开关与运行手册

| 开关 | 默认 | 作用 | 关闭后 |
|---|---|---|---|
| `INPUT_UNDERSTANDING_MODE` | `off` | `off/shadow/active` 三层 | 走原入口 |
| `SEMANTIC_LABELS_ENABLED` | `1` | 规则标签（D2/D3） | 无标签，六维其余照常推导 |
| `INPUT_UNDERSTANDING_SEMANTIC_ENABLED` | `0` | 复杂解析（含标签，一次调用） | 只用规则 |
| `LABELS_POLICY` | `0` | 困难类型定向选策略 | 保持原轮换 |
| `LABELS_STRUCTURE` | `0` | 认知任务决定回答结构 | 不注入结构提示 |
| `LABELS_TURN` | `0` | skip/求答案影响回合边界 | 只按原正则 |

离线检查：

```
python scripts/eval_semantic_labels.py
python scripts/annotation_agreement.py A.jsonl B.jsonl
python -m unittest tests.test_label_consumers tests.test_decision_points tests.test_ontology_view
```

灰度顺序：先 `SEMANTIC_LABELS_ENABLED` + `INPUT_UNDERSTANDING_MODE=shadow` 观察六维与标签分布；再逐个开 `LABELS_POLICY → LABELS_STRUCTURE → LABELS_TURN`，每开一个保留上一批对照样本。
