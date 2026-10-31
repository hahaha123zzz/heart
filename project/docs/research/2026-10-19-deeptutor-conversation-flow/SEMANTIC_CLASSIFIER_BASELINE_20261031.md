# 六维语义分类器：阶段 A 基线与评测冻结（2026-10-31）

工作区事实：`codex/ta5-acceptance-20261029 @ a9725fbc0f88689f858f553c22dd3e3373c647ac`。
**不是干净基线**：8 项已跟踪文件被修改、20 项未跟踪（本轮代码 + 文档 + 证据）；工作区无已跟踪删除。

## 1. 盘点边界

| 类别 | 内容 | 处置 |
|---|---|---|
| 本轮代码（已跟踪改动） | `agents/adaptive_tutoring.py`、`agents/input_understanding/{service,semantic,adapters}.py`、`agents/teaching_{policy,planner}.py`、`tests/test_input_understanding_{dataset,rules}.py` | 本次工作基线，勿回滚 |
| 本轮新增 | `knowledge/semantic_labels.v1.json`、`agents/input_understanding/{ontology,labels}.py`、`scripts/{eval_semantic_labels,annotation_agreement}.py`、7 个测试文件、3 个 fixtures | 同上 |
| 本轮文档 | `SEMANTIC_CLASSIFIER_*`、`SEMANTIC_ONTOLOGY_V1_SPEC_*`、`SESSION_HANDOFF_PROMPT_*`、本文件 | 只读参考 |
| 数据缺失 | `knowledge/exercises/catalog.json`、`frontend/textbook/manifest.json` 不在 HEAD、也不在磁盘（导入产物，非用户删除） | 不恢复、不改测试；相关失败如实记录 |
| 运行产物 | `.runtime/baseline-20261031/` | 不进 Git |

更正：上一份交接提示称“教材/题库被删除”。本次核对为**从未存在于 HEAD 的导入数据未就绪**，不是本轮或用户删除。后续描述以本文件为准。

## 2. 命令与退出码

| 命令 | 退出码 | 结果 | 日志 |
|---|---|---|---|
| `python -m unittest` 7 个分类器模块（50 项） | 0 | OK | `baseline-20261031/classifier.log` |
| `python -m unittest` adaptive + teaching_modes + context_sufficiency（67 项） | 0 | OK | `baseline-20261031/teaching.log` |
| `python -m unittest` memory_personalization + exercise_skills + input_understanding_integration（38 项） | 1 | 21 errors | `baseline-20261031/known-failures.log` |
| `python scripts/eval_semantic_labels.py` | 0 | 见 §3 | `baseline-20261031/eval.log` |

分类器 50 项构成：视图 15、标签 10、消费者 6、决策点 3、策略 8、κ 3、三路径对照 5。

## 3. 评测复现

120 条工程回归：micro P/R/F1 = 1.00/1.00/1.00（support 120，弃权 364）。期望值按规则契约标注，**只能防回归，不能当泛化**。

30 条留出：

| 维度 | P | R | F1 | support | 弃权 |
|---|---|---|---|---|---|
| cognitive_demand | 0.80 | 0.40 | 0.53 | 10 | 19 |
| self_report | 1.00 | 0.67 | 0.80 | 3 | 27 |
| difficulty_locus | 0.67 | 0.29 | 0.40 | 7 | 22 |
| engagement | 1.00 | 0.50 | 0.67 | 4 | 26 |
| micro | 0.83 | 0.42 | 0.56 | 24 | 94 |

与原报告一致（F1 0.56、difficulty 0.40），复现成立。

## 4. 已核实的失败

21 项错误分两类，全部与本轮代码无关：

1. **20 项数据未就绪**：`test_exercise_skills`（15）因 `practice.question` 404（题库导入未执行）；`test_memory_personalization`（5）因教材来源缺失导致生成阶段未触发（`llm.messages` 为空）。
2. **1 项检索未就绪**：`test_input_understanding_integration::test_active_input_keeps_learning_writes_owned_by_host_commands`，`retrieval_not_ready`。

本轮未通过改测试、恢复数据或改写历史结果来消除这些失败。

## 5. 数据版本与快照

清单：`.runtime/baseline-20261031/manifest.json`（路径 + sha256）。关键值：

| 文件 | sha256 |
|---|---|
| `knowledge/semantic_labels.v1.json` | `615ab097256d7b4387aec499f9247e20873ba51ffb2c01e9e4c3fcbbd6dce5e6` |
| `tests/fixtures/semantic_labels_v1.jsonl` | `ee541fc483577670bb3e132e5f1767c47c469f248d29abe80dd84529cee411f9` |
| `tests/fixtures/decision_points_v1.jsonl` | `4b1c928fea9244b3b6b9bcffeaa0f877f60864fa67a5ad47ca1659f240bdd3d3` |
| `tests/fixtures/holdout_v1.jsonl` | `52e5494d042e50644175573cc55c32693a793f2762f49df3cad495b7c9b61b1b` |

代码哈希见清单。后续每次改动需在此追加一行“文件 → 新 sha256 → 改动原因”。

## 6. 数据划分（冻结）

| 集合 | 用途 | 能否当泛化指标 |
|---|---|---|
| `semantic_labels_v1.jsonl`（40） | 规则开发集，规则按其句式编写 | 否 |
| `decision_points_v1.jsonl`（120） | 工程回归契约 | 否 |
| `holdout_v1.jsonl`（30） | 曾用于错误分析，**已污染** | 否；只能作错误类别来源 |

**独立盲测集尚未建立。** 建立规则：由未参与规则编写的人从真实学生输入抽样，先冻结标签注册表与代码 sha256 再标注；标注前不得查看规则。

## 7. 未验证

- 真实模型、页面、受控 HTTP、同快照 off/on 对照均未执行。
- 双人 κ 无第二份标注文件。
- 回合层指标（答案泄露率、连续同策略率、动作集合 Jaccard）无真实回合数据。
- 本轮未声称任何教学效果提升。

## 8. 阶段 B 追加（冻结之后）

改动仅一处代码 + 新增测试与文档：

| 文件 | 变更 | 新 sha256 |
|---|---|---|
| `agents/input_understanding/labels.py` | `混淆` 收窄为动词用法（修名词“混淆变量”误报） | `de867d94c8df4a82e80e5f52e2191056cd30eafff7367f7eeadd2da0e7a34cf3` |
| `tests/fixtures/label_regressions_v1.jsonl` | 4 条名词/动词回归 | `9d7c925ea1c91f68c74e198967f9c06c8f66e66ee9c2ea0a9fb898c8ab0dc90f` |
| `tests/test_label_regressions.py` | 1 项 | `684c493e66f3dccc77fb4f6337db76d1403976933ae5969ab824128b2c7f6fd2` |
| `tests/test_semantic_boundaries.py` | 8 项边界 | `d07b9459daa564d5b6ab53d61376e4993f0537d059c46da144c04a62f0496ea0` |

注册表、两个数据集未改，sha256 与 §5 相同。

复评结果：分类器 59 项通过、教学 67 项通过；留出 micro F1 0.56→0.57（P 0.83→0.91，R 不变 0.42），`difficulty_locus` F1 0.40→0.44。120 工程回归仍 1.00。详细分析见 `SEMANTIC_LABEL_ERROR_ANALYSIS_20261031.md`，标注规范见 `SEMANTIC_LABEL_GUIDE_20261031.md`。

结论：只修误报，不追召回；14 条改写漏检留给模型路径，不写进正则。

## 9. 阶段 C 追加（真实模型 + 教材）

| 文件 | 变更 | sha256 |
|---|---|---|
| `scripts/accept_semantic_labels_live.py` | 新增：进程内 HTTP、独立 DB、三组开关 off/on 对照 | `5bce061c781429f4b4827d9aa518a50ece3cac968639316af1988f7258f5c637` |

生产代码在 B 之后未再改动。证据：`artifacts/semantic-live-*.json`、`.runtime/baseline-20261031/live*-*.log`；分析见 `SEMANTIC_CLASSIFIER_STAGE_C_LIVE_20261031.md`。

要点：策略开关 5/5 变为 `contrast`；结构开关 5/5 answered（off 4/5，1 例 `quality_rejected`）；回合开关 3/3 skip 变为 `check_skipped`；教材首轮引用 1–4 条。样本小，不作效果声明。

## 10. 学习 Agent 模式借鉴后的改动（2026-10-31）

| 文件 | 变更 | 新 sha256 |
|---|---|---|
| `agents/adaptive_tutoring.py` | 增加 `state['decision']` 决策记录；困难轮次防重复（最近两轮同策略则换候选） | `01a2c390519aa0a47a42f3d985a130bd660a370ae35842bde2e20bfbdf5f07d5e` |
| `tests/test_teaching_decision.py` | 4 项（来源、版本、防重复、非困难轮次不干预） | `57bc081b7caa51add0cc96763989412dd217344475a4be134406fb123d7742dd` |

复测：`LABELS_POLICY` on 由 5/5 `contrast` 变为 4/5 `contrast` + 1 `worked_example`（该例上一轮已用 contrast），off 不变。分类器 63 项、教学 67 项通过。

未采用：envelope 剥离（现有门禁用正则拒绝 `DSML/tool_call`，比剥离更安全）。

详见 `LEARNING_AGENT_PATTERNS_20261031.md`。
