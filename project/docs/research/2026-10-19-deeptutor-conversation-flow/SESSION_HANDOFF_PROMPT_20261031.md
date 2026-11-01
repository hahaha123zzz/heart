# 会话迁移提示词（2026-10-31）

把下面整段复制到新会话即可接手。不要在迁移时重述调研结论，先按“§6 第一个动作”验证环境。

---

你是这个仓库的接手工程师。任务：继续完成“心理学教材学习 Agent 的六维语义分类器（psy-6d-v1）”剩余工作。

## 1. 项目事实

- 仓库根：`E:\项目\heart`；应用根：`E:\项目\heart\project\integration\discrete-math-tutor`（下文路径都相对应用根）。
- 当前分支 `codex/ta5-acceptance-20261029`，HEAD `a9725fb`，**有 26 项未提交改动**。不要 `git checkout`、`git stash`、`git reset`、不要合并 main。
- 未提交内容包括：本轮 P1–P4 改动、新建文件，以及工作区里已被删除的教材/题库数据（`frontend/textbook/*.pdf`、`knowledge/exercises/catalog.json` 等）。**那些删除不是本轮的**，恢复前先问用户。
- Python 运行环境：`.venv-runtime\Scripts\python.exe`。**没有 pytest**，全部用 `python -m unittest`。
- 不要碰 8000 端口服务、正式 SQLite、教材与图谱；验证一律用隔离端口和独立库。

## 2. 已完成的工作

设计文档（都在 `project/docs/research/2026-10-19-deeptutor-conversation-flow/`）：

- `SEMANTIC_CLASSIFIER_RESEARCH_20261030.md`：为什么不做“六维分类器 + 新链路”，以及 2026 文献依据。
- `SEMANTIC_ONTOLOGY_V1_SPEC_20261030.md`：六维本体、旧词表映射、迁移批次。
- `SEMANTIC_CLASSIFIER_IMPLEMENTATION_PLAN_20261030.md`：P1–P5 实施计划、验收、开关手册。

代码（全部已落地，未提交）：

| 文件 | 作用 |
|---|---|
| `knowledge/semantic_labels.v1.json` | 六维注册表，标签取值的唯一权威 |
| `agents/input_understanding/ontology.py` | `build(turn, context)` 六维只读视图；`missing_labels()`；`valid_label()` |
| `agents/input_understanding/labels.py` | 规则标签（17 条规则）+ `merge()` 去重/限条/校验 |
| `agents/input_understanding/service.py` | 规则标签在 `resolve()` 前并入，受 `SEMANTIC_LABELS_ENABLED` 控制 |
| `agents/input_understanding/semantic.py` | `SemanticCandidate.labels`（与任务解析同一次模型调用）；无效标签丢弃并记 `semantic_label_rejected`；分类端口与规则标签合并 |
| `agents/input_understanding/adapters.py` | `final_summary()` 增加 `six_dim`（不含 `canonical_id`） |
| `agents/adaptive_tutoring.py` | P3 三个消费者开关；`LOCUS_STRATEGY`；`STRUCTURE_NOTES`；`limit_disclosure` 优先于 `full_note` |
| `agents/teaching_policy.py` | `STRATEGY_ALIASES`、`canonical_strategy()`、`accepted_strategy_names()`；删除死代码 `KNOWN_STRATEGIES` |
| `agents/teaching_planner.py` | `ALLOWED_STRATEGIES = strategy_ids()`（13 库 id 为唯一来源），校验前归一 |

数据与工具：

- `tests/fixtures/semantic_labels_v1.jsonl`（40 条标注）、`decision_points_v1.jsonl`（120 条工程回归）、`holdout_v1.jsonl`（30 条留出）。
- `scripts/eval_semantic_labels.py`：逐维 P/R/F1、support、弃权。
- `scripts/annotation_agreement.py`：双人 Cohen's κ（逐维/逐标签/完全一致率）。

测试：

- `tests/test_ontology_view.py` 15 项、`test_input_understanding_labels.py` 10 项、`test_label_consumers.py` 6 项、`test_decision_points.py` 4 项、`test_strategy_catalog.py` 8 项、`test_annotation_agreement.py` 3 项、`test_runtime_strategy_parity.py` 5 项。
- 最新相关回归 **94 项全过**（日志 `.runtime/final-round.log`）。
- 宽回归 209 项：25 errors + 2 failures，**与改动前完全一致**，全部来自已删除数据。

关键实测数字：

- 120 条工程回归集 micro-F1 = 1.00（期望值按规则契约标注，只防回归）。
- **30 条留出集 micro-P 0.83 / R 0.42 / F1 0.56**；`difficulty_locus` 只有 0.40。规则不泛化，改写后必须靠模型路径。
- 留出集已知误报：“为什么会有混淆变量”被判成 `discrimination`。

## 3. 不可破坏的约束

1. **六维是只读视图，不是新表、不是新枚举存储。** 不要改 `GroundedTurn` 的 `schema_version`，不要给 `TaskContext` 加字段。
2. **注册表是标签唯一权威。** 新标签必须先进 `semantic_labels.v1.json` 再由 `ontology.valid_label()` 校验；未知维度/取值一律拒绝。
3. **D1/D4/D5/D6 全部推导，不产生 annotation。** 只有 D2 与 D3 的 `self_report`/`difficulty_locus`/`engagement` 可分类；缺数据写 `null`，禁止补 `unknown`。
4. **标签不得写成绩、掌握度、误区、复习队列、偏好；不得覆盖已校验的对象绑定与约束。** 披露与否只由 `constraints` 决定。
5. **模型调用不得增加。** 复杂解析已经存在；标签必须与 `resolve()` 同一次调用产出。`model_calls` 上限 2 由现有校验兜住。标签无效时丢那一条、保留已解析任务，不要整批回退。
6. **13 个策略 id 是唯一权威**（`knowledge/teaching_strategies.json`）。9 个运行时名只是别名。**不许新增第 5 份策略表**，`tests/test_strategy_catalog.py` 会拦。
7. `TeachingStepTool` 的 enum 仍是 9 个运行时名 —— 这是**故意保留**的，别顺手改成 13。
8. **不要新建第二套 AgentLoop / 分类服务包 / 状态表。** 不要引入 LangGraph。
9. 侧栏与主对话的标签跟随 task，不跟 session；不要把侧栏提问计入掌握证据。
10. 现有“回答发布门禁”“引用校验”“教材来源”不要绕过，也不要为分类器新增门禁。

## 4. 测试与已知失败

```powershell
cd E:\项目\heart\project\integration\discrete-math-tutor
.\.venv-runtime\Scripts\python.exe -m unittest tests.test_label_consumers tests.test_decision_points tests.test_input_understanding_labels tests.test_ontology_view tests.test_strategy_catalog tests.test_annotation_agreement tests.test_runtime_strategy_parity
```

**已知失败（不要当成回归）**：

- `tests.test_memory_personalization`（5 项）、`tests.test_exercise_skills`（15 项）：教材/题库数据被删，`practice.question` 404、生成阶段未触发。
- `tests.test_input_understanding_integration::test_active_input_keeps_learning_writes_owned_by_host_commands`：`retrieval_not_ready`，检索索引未就绪。
- 判定方法：用 `git checkout -- <被改文件>` 回滚后跑同一命令，失败数应不变（曾验证 25 errors + 2 failures 前后一致）。**回滚前先备份到 `$env:TEMP`，跑完立刻恢复。**

## 5. 未完成与门禁

| 项 | 状态 | 解锁条件 |
|---|---|---|
| P4 双人 κ | 工具就绪，无数据 | 用户提供第二份标注文件 → 跑 `scripts/annotation_agreement.py`；κ<0.6 的维度退回改定义，不要加规则 |
| P3 真实模型对照 | 只有开关级单测 | 用户许可调用模型：15 条“分不清”样本 `LABELS_POLICY` off/on 各跑一遍 |
| P5 删除 `learning_intents` 独立调用 | 未做 | “投影 vs 旧结果差异 ≤2%”的真实对照 |
| P5 删 `analyze_teaching_turn.move` | 未做 | 需同步改 4 处调用与测试，收益低，建议再做产品判断 |
| P5 `TeachingStepTool` 改 13 个规范名 | 未做 | 真实模型 A/B；改后 `analyze_teaching_turn` 的轮换表也要一起改写 |
| 回合层指标（Jaccard、答案泄露率、连续同策略率） | 未做 | 需要真实回合数据 |

## 6. 你的第一个动作

1. 跑 §4 的命令，确认 94 项通过；再跑一次受影响面较大的：
   `.\.venv-runtime\Scripts\python.exe -m unittest tests.test_adaptive_tutoring tests.test_teaching_modes tests.test_context_sufficiency`
2. 读 `SEMANTIC_CLASSIFIER_IMPLEMENTATION_PLAN_20261030.md` 的 §9（开关手册），确认你没有打开任何 `LABELS_*`。
3. 向用户报告：当前状态、已知失败、下一步需要他提供什么（第二份标注文件 / 真实模型许可）。

## 7. 工作方式要求

- 每次改代码先说明要动的文件与回滚方式；新行为必须有测试；不能只跑新测试就宣称通过。
- 报告要区分：单测通过 / 受控 HTTP / 真实模型 / 页面验收。没跑的就说没跑。
- 性能与准确率不要用不同库、不同会话或不同题目冒充 A/B。
- 文档写进 `project/docs/research/2026-10-19-deeptutor-conversation-flow/`，命名沿用大写主题 + 日期。
