# 第三批：pyBKT、pyKT 与 EduKTM 源码审计

日期：2026-11-01。项目基线：`main @ e5b3c004e8eca02cd124539355ef5fe40866ee4b`。本批逐行读取原讨论稿 **227—402 行**，只做调研与隔离探针，不接入业务、不训练模型、不改正式数据库。

## 结论

**优先保留现有证据门禁和事件事务；pyBKT 适合作为离线可解释基线，再考虑影子运行。pyKT 优先借用数据与评测协议，EduKTM 用于实现交叉对照。三个库都不能替代项目的正式掌握判定。** 当前没有本项目的训练、留出集评测或概率校准结果，不能宣布其中一个模型效果最好。

最值得修正的不是先换一个掌握度公式，而是定义：什么作答有资格进入序列、KC 指什么、预测发生在答案前还是答案后、一次事件是否只更新一次、参数与映射如何版本化。原稿的 `KnowledgeTracingService` 是候选组织方式，不是已经决定新增的服务。

## 1. 固定上游与材料边界

| 仓库 | 本批读取的 commit | 许可证 | 本批定位 |
| --- | --- | --- | --- |
| [CAHLR/pyBKT](https://github.com/CAHLR/pyBKT/tree/dddb7be5702bd749f73a3dcbc9db2f5640f8345e) | `dddb7be5702bd749f73a3dcbc9db2f5640f8345e` | MIT | 参数拟合、两状态过滤、Roster 增量接口 |
| [pykt-team/pykt-toolkit](https://github.com/pykt-team/pykt-toolkit/tree/ccbaf37b07e3e7ff7b2415475b2faacb967d54ea) | `ccbaf37b07e3e7ff7b2415475b2faacb967d54ea` | MIT | 多 KC 展开、序列切分、移位标签、题级评测 |
| [bigdata-ustc/EduKTM](https://github.com/bigdata-ustc/EduKTM/tree/5625056855ffd18c0ad3c052feba4733a386ca01) | `5625056855ffd18c0ad3c052feba4733a386ca01` | Apache-2.0 | 模型实现、输入编码与输出对齐的第二份对照 |

许可证按固定版本的 LICENSE 核验；实际摘取代码时保留版权、许可及所摘文件的第三方归因，不能将主仓库许可自动套到外部数据集、权重或引用代码。本批缓存包含各仓库 LICENSE，没有导入任何真实学生数据。上游分支会变化，以下结论只覆盖所列版本和文件。

原稿对三者基本用途、许可证及 EduKTM 所列模型的描述与所查材料一致。须补充：研究代码库有可复用算法，不等于已有会话事务、并发隔离、取消恢复和证据审计的教学后端。

## 2. 项目现状：哪些能沿用，哪些仍然缺失

| 本地源码 | 已有行为 | 接入 KT 的含义 |
| --- | --- | --- |
| [student_state.py](../../../integration/discrete-math-tutor/models/student_state.py#L76) | `blend_numeric` 默认 `0.6 × old + 0.4 × observation`，步骤默认起点 0.5 | 指数平滑，不是 BKT；0.5 不是数据拟合的先验；不能直接作为 BKT 初始化依据 |
| [exercise_skills.py](../../../integration/discrete-math-tutor/database/exercise_skills.py#L44) | 仅汇总当前映射/题版本下的有效独立规则观测；同题小题只留最新有效记录；标注 `uncalibrated_skill_estimate` | 可复用资格和来源信息；汇总结果已丢掉完整时间序列，不能拿汇总值倒造训练序列 |
| 同一文件 `skill_summary` | `PSYCHOLOGY` 为真时直接返回 `[]` | 心理学课程暂不能沿用这条技能汇总作为现成 KT 数据接口；需要心理学 KC 与评价规则，不是简单更换计算器 |
| [evidence_policy.py](../../../integration/discrete-math-tutor/memory/evidence_policy.py#L33) | attempt、路由置信度、帮助历史与原文门禁；通用判断默认 `ai_provisional` | “原文可追溯且独立”不等于“二元正确性已核验”；还需独立的标签资格判断 |
| [adaptive_tutoring.py](../../../integration/discrete-math-tutor/agents/adaptive_tutoring.py#L549) | Q3 形成性评价写 `ai_provisional`、`independent=False`、`formal_mastery=False` | 不能为扩充样本自动升级成正式训练标签或掌握证据 |
| [models.py](../../../integration/discrete-math-tutor/database/models.py#L266)、[memory_manager.py](../../../integration/discrete-math-tutor/memory/memory_manager.py#L297) | 事件、证据、修订与同轮事务/去重 | 继续作为唯一事实入口；KT 输出是可重建投影，不再建立一条绕过门禁的写库链 |

`StudentState.calibration_gap` 是 confidence 与 mastery 的差，不能当作预测概率已经校准的证据。知识点文本、Q5 目标 ID、练习技能 ID 也不是天然相同的 KC；尤其目标可能随教学路径生成，不能每次生成目标就创建一个训练类别。KC 身份与映射的最终方案留待第六批核对。

## 3. pyBKT：值得复用，但必须明确概率时点

### 3.1 输入与安装：对原稿示例的修正

[数据转换器](https://github.com/CAHLR/pyBKT/blob/dddb7be5702bd749f73a3dcbc9db2f5640f8345e/source-py/pyBKT/util/data_helper.py#L54) 的内部字段是 `user_id`、`skill_name`、`correct`，可用 defaults 映射项目字段；排序列是 `order_id`。原稿写 `student_id` 不意味着库会自动识别此列。适配器必须显式指定映射、稳定顺序和学生边界，不能依赖 CSV 碰巧排好序。

外部 `correct` 接受 -1/0/1，转换成内部 0/1/2，分别是缺测/错误/正确。应在转换前检查类型和值：转换器存在整数转换，项目不能让部分分数或小数被悄悄截断后成为错误标签。现有 `score / 100` 可能有部分分，不能原样喂给二元 BKT。应保留原始分数，另行制定、版本化二元标注规则，或暂不纳入。

[README](https://github.com/CAHLR/pyBKT/blob/dddb7be5702bd749f73a3dcbc9db2f5640f8345e/README.md) 区分 Python 与 C++ 路径，Windows 文档推荐纯 Python。但此 commit 的 [setup.py](https://github.com/CAHLR/pyBKT/blob/dddb7be5702bd749f73a3dcbc9db2f5640f8345e/setup.py) 已声明 Python >=3.10，与 README 的旧要求不一致，且安装脚本先尝试扩展、失败后回退。因此不能仅照 README 宣布本机已支持或已装好；后续应锁定发行版与哈希，在隔离环境实测实际后端。本批没有安装 pyBKT，也没有复现上游速度表。

### 3.2 四种量要分别保存

两状态 BKT 下，令答题前潜在掌握概率为 p，猜对率 G，失误率 S，学习率 T，遗忘率 F：

- 当前题答对概率：`p_correct = p × (1-S) + (1-p) × G`。
- 看见正确答案后的后验：`posterior = p × (1-S) / p_correct`。
- 看见错误答案后的后验：`posterior = p × S / (p × S + (1-p) × (1-G))`。
- 下一步骤前的概率：`p_next = posterior × (1-F) + (1-posterior) × T`。

这些式子要求参数有效、分母非零；实际适配还需处理边界与异常。它们是所查实现的两状态观测/转移解释，不是对学生心理状态的直接测量。

[预测器](https://github.com/CAHLR/pyBKT/blob/dddb7be5702bd749f73a3dcbc9db2f5640f8345e/source-py/pyBKT/fit/predict_onestep.py#L41) 把序列首项设置为先验，后续项由上一条观测的过滤结果经过转移得到。因此 `Model.predict` 当前行的 `state_predictions` 是**看到当前答案之前**的状态预测，不是当前答案更新后的后验。`correct_predictions` 则是相应答对概率，不能换个字段名就称为 mastery。

合成例：p=0.2、G=0.25、S=0.1、T=0.1、F=0。一题正确之前 `p_correct=0.38`，看到正确答案后后验约 0.473684，经过学习转移后下一步约 0.526316；下一步答对概率约 0.592105。若把当前行预测当作更新后的掌握度，会错一轮；若把答对率当掌握率，会混入猜测与失误。

### 3.3 缺测也可能推进状态

[EM 前向实现](https://github.com/CAHLR/pyBKT/blob/dddb7be5702bd749f73a3dcbc9db2f5640f8345e/source-py/pyBKT/fit/EM_fit.py#L167) 对内部 0 不应用答案似然，但步骤之间仍有转移。上述参数下，空步骤之间可从 0.2 到 0.28，再到 0.352。

因此，求提示、跳过、自述懂了或重复投递的空事件，不能只编码 `correct=-1` 就认为“不更新”。对首版二元独立作答基线，应在构造序列前排除不合格事件。若未来要建模讲解带来的学习，须显式设计活动类型与转移含义并单独验证，不能靠空记录暗中增加掌握度。基于步骤的 forget 参数也不能直接当作按真实天数遗忘；时间感知问题留到复习调度批次。

### 3.4 增量接口已经存在，但不是直接可用的事务服务

[Model.fit / partial_fit](https://github.com/CAHLR/pyBKT/blob/dddb7be5702bd749f73a3dcbc9db2f5640f8345e/source-py/pyBKT/models/Model.py#L66) 是参数拟合路径；`partial_fit` 仍处理数据并进入 `_fit`，不是“只更新某学生的一个状态”。不要每个对话轮次拟合一次。

[Roster.State](https://github.com/CAHLR/pyBKT/blob/dddb7be5702bd749f73a3dcbc9db2f5640f8345e/source-py/pyBKT/models/Roster.py#L519) 已有逐次响应接口：`process_data` 默认在答案后追加缺测位置，取最后预测作为下一步状态，值得借鉴其答题后转移处理。需要适配的具体问题：

1. `State.predict` 临时修改共享 `fit_model[skill]` 的 prior/pi_0，成功后恢复，但没有 try/finally。合成异常已验证会留下临时先验，故不宜直接让多个学生共享可变模型实例。
2. 替换先验的条件是 `state_prediction > 0`。合成状态恰为 0 时会沿用拟合先验，边界语义需要修正或在适配层规避。
3. 它不负责项目的事件唯一性、库事务、参数/映射版本、撤销修订和跨进程恢复。默认 mastery 阈值 0.95 也不是本项目正式掌握标准。

建议先复用离线 `Model` 拟合与同参数预测作基准；在线若采用 Roster，应隔离可变状态、补异常恢复与事件幂等验证。若最后选择实现一个很小的纯过滤函数，也必须与锁定上游建立数值对照，并保留归因；这是后续实现选项，不在本批改业务代码。

## 4. pyKT：主要借评测方法，避免多 KC 标签泄漏

[NeurIPS 2022 原论文摘要](https://proceedings.neurips.cc/paper_files/paper/2022/hash/75ca2b23d9794f02a92449af65a57556-Abstract-Datasets_and_Benchmarks.html) 支持原稿的两项主张：错误评测会发生标签泄漏并夸大结果；在其研究设置下，多种深度模型相对早期 DKT 的提升有限。不能推导为“深度模型在本项目一定无用”，也不能把论文数学练习数据的指标当作心理学对话效果。

本批进一步核对了这些实际实现：

- [extend_multi_concepts](https://github.com/pykt-team/pykt-toolkit/blob/ccbaf37b07e3e7ff7b2415475b2faacb967d54ea/pykt/preprocess/split_datasets.py#L101) 把一题多个概念展开，重复其问题、答案等字段，并生成 `is_repeat`。一题同时映射 A/B 且答对，会得到两个相同正确标签，**并不表示人类已分别确认 A/B 都掌握**。
- 同文件 `train_test_split` 与 `KFold_split` 在行级打乱分组。上游预处理的“一行一学生序列”约定非常重要：直接传入项目“一行一事件”会让同学生跨集合。合成反例已验证；这不是声称上游正常入口必然泄漏，而是适配者不能破坏其输入前提。
- [DKT.forward](https://github.com/pykt-team/pykt-toolkit/blob/ccbaf37b07e3e7ff7b2415475b2faacb967d54ea/pykt/models/dkt.py#L25) 用概念与回答编码历史，再输出各概念 sigmoid；[train_model.cal_loss](https://github.com/pykt-team/pykt-toolkit/blob/ccbaf37b07e3e7ff7b2415475b2faacb967d54ea/pykt/models/train_model.py#L55) 针对移位答案训练。[评测器](https://github.com/pykt-team/pykt-toolkit/blob/ccbaf37b07e3e7ff7b2415475b2faacb967d54ea/pykt/models/evaluate_model.py#L121) 选取后续目标概念的概率，监督对象是后续作答结果，不是逐 KC 的独立掌握真值。
- 同评测器还包含 `evaluate_question`、early/late fusion 及按原题分组的预测路径。若项目要借用，必须明确题级分组、历史截止点、目标答案何时可见、mask 与聚合策略；仅复制常规 evaluate 不能自动避免同题多个 KC 之间提前暴露答案。

工程选择：先借输入契约、移位预测、原题分组和评测切分思路；不把整个 PyTorch 训练栈放进 TeachingTurn/AgentLoop。训练工件须绑定 KC/题目词表、数据资格策略、参数及代码版本；新的 KC/题 ID 不能随便重新编号并继续使用旧权重。原稿所列模型可作后续候选，没必要首轮全部训练比较。

## 5. EduKTM：适合第二实现对照，不是掌握服务

[README](https://github.com/bigdata-ustc/EduKTM/blob/5625056855ffd18c0ad3c052feba4733a386ca01/README.md) 确实列出原稿所述 DKT、DKT+、DKVMN、GKT、AKT、LPKT、LBKT，并额外有 KPT/EKPT。本批不据仓库组织名扩展推断其当前机构维护承诺。

[DKT.py](https://github.com/bigdata-ustc/EduKTM/blob/5625056855ffd18c0ad3c052feba4733a386ca01/EduKTM/DKT/DKT.py#L16) 的具体实现使用 RNN；不能仅因名称相同就假设与 pyKT 的 LSTM 版本同构。`process_raw_pred` 从第 2 条实际交互取目标题/标签，与前一步输出对齐；训练使用 BCE，eval 返回 ROC-AUC。这条实现同样没有提供经本项目验证的正式 mastery 真值。

[setup.py](https://github.com/bigdata-ustc/EduKTM/blob/5625056855ffd18c0ad3c052feba4733a386ca01/setup.py) 引入 torch、numpy、pandas、scikit-learn、networkx 等；[顶层 __init__](https://github.com/bigdata-ustc/EduKTM/blob/5625056855ffd18c0ad3c052feba4733a386ca01/EduKTM/__init__.py) 集中导入多种模型。因此，“只复用一个小实现”与“安装整包进入线上依赖”成本不同。优先在独立实验环境交叉检查输入编码、下一题对齐和指标；本批未运行它的训练循环或声称其他模型都已审计。

## 6. 建议的数据合同与验证顺序

以下是工程推论与后续验收条件，不是本批批准实施的新表结构。

1. **先生成可追溯作答序列。** 从原始事件/规则观测取学生、课程、稳定 KC、题/小题/版本、发生顺序、帮助状态、verification、原始评分、二元标签规则及排除原因。序列的独立、正确、可训练三种资格分别判断；人工复核也须有真实复核记录。
2. **首个可比实验保持简单。** 对同一合格留出集比较课程/KC 频率基线、现有平滑估计和标准 BKT。现有估计若不能输出明确的答对概率，就先拟定预测映射，不能直接把两种不同语义的数值比 Brier 分数。小样本 KC 可以共享先验/参数或拒绝输出，不现场拟合四参数并给出确定结论。
3. **分别评估泛化情景。** 新学生按学生分组；已有学生的未来表现按时间前缀；同题重做和同一原题多 KC 作为组处理。不能随机打散事件，也不能把评估目标答案、未来教师反馈或人工结论放入预测历史。每种场景单独报告，不混成一个 AUC。
4. **评估概率与结论两件事。** 概率至少检查 log loss、Brier、可靠性分箱及样本支持，AUC 仅补充排序表现；单类集合不伪报 AUC。校准参数只用训练/验证数据拟合。正式掌握门禁另测误授掌握、证据不足、辅助作答、自述、撤销修订与延迟独立迁移题，不能拿答对预测指标替代。
5. **影子运行先于用户可见替换。** 新估计单独记 `model_version`、映射/资格版本、输入事件及 `prediction_time`，不覆盖既有正式结论。重复事件、乱序、异常和恢复后重放结果须确定；参数切换要从事件重建或明确迁移，不能把旧过滤状态悄悄混入新模型。

冷启动没有脱离数据规模的万能最低题数。尤其标准 BKT 的猜对、失误、先验与学习参数可能用不同组合解释类似作答序列；“程序拟合成功”不能证明参数具有稳定心理学含义。需要报告每 KC 的人数、独立题数、标签分布与不确定性；本项目尚无这些统计，本批不作可训练性结论。

## 7. 可复用清单与完成证据

| 单元 | 建议复用方式 | 必须适配 | 成本判断 |
| --- | --- | --- | --- |
| pyBKT Model + 数据转换 | 离线基线直接使用锁定版本 | 列映射、二元标签、资格过滤、稳定排序、安装后端验证 | 中 |
| pyBKT Roster / 两状态过滤 | 借逐次更新的算法与数值对照 | 共享可变参数、异常恢复、零状态、幂等与持久化 | 中；不可直接套服务 |
| pyKT split / masks / question grouping | 借协议，选择性提取适配 | 一行一学生、同题 KC 分组、历史截止与词表版本 | 中 |
| pyKT DKT、EduKTM DKT | 独立离线实验，必要时交叉核对 | 输入差异、框架依赖、指标语义、权重生命周期 | 中到高；不列首版必需 |
| 项目 LearningEvent / EventEvidence / MemoryRevision | 直接沿用事实与修订链 | 补统一导出合同与投影版本 | 优先 |

隔离缓存位于 `.runtime/layer6-research/round03/`（不入库），保存 20 份所查源文件/许可证及 Git blob 清单；文件字节已与固定树的 blob SHA-1 核对。`probe.py` 仅通过 AST 载入已检查函数，使用现有 NumPy/Pandas 和合成数据，不导入整包、训练模型、调用 API 或触碰学生库。`probe-results.json` 记录 **7 项断言通过**：概率时点区分、空步骤转移、重复空步骤再次转移、Roster 异常未恢复先验、零状态分支、多 KC 重复标签、行级切分输入前提。

这些验证证明所查函数的具体行为，不证明教育有效性、拟合效果或完整包兼容性。pyBKT README 所链接的 EDM 2021 PDF 本次直接获取超时，因此未据该论文内文追加样本量或性能结论；运行语义依据固定源码与合成探针。

本批未实施业务改造、未安装三个库、未训练/校准、未测真实心理学数据、未提交或推送。下一批从原稿 **403 行**开始，审计 FSRS、LangGraph 与项目已有复习调度、持久化和重放边界。
