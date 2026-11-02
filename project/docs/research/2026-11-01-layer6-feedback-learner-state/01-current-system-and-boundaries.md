# 第 01 批：项目现状与第六层边界

日期：2026-11-01。基线 `e5b3c004e8eca02cd124539355ef5fe40866ee4b`。原稿正文读取 1—87 行；为开展下一批，另已读 88—226 行。本文是静态源码盘点，不是完整第六层验收或实施批准。

## 首轮结论

第六层应围绕“哪些已发生的交互能成为何种学习证据、能更新哪类状态”展开。项目已经具有事件、证据、修订、误解、短期反馈、正式路径和复习模型，不能把原稿中的模块清单直接翻译成六套新服务和新表。

当前最值得继续研究的是不同入口之间的**证据语义和状态权威**。并不是所有名为 mastery 的数字、understood 的标记或 LearningEvidence 的对象都表示同一种学习结论。下列为已读代码事实，未证明所有入口均完整使用了这些能力。

## 已有能力与可复用位置

代码链接相对当前目录，均对应上述基线；函数/类名用于后续定位。

| 原稿子系统 | 现有源码及已核行为 | 后续要补的核对 |
| --- | --- | --- |
| 反馈识别 | [learning_feedback.py](../../../integration/discrete-math-tutor/agents/learning_feedback.py)、[adaptive_tutoring.py](../../../integration/discrete-math-tutor/agents/adaptive_tutoring.py) 已区分困难、自述、插问、作答，辅助评分核验 student_quote 来自当前输入 | 不同入口的“跳过、未作答、问提示、部分正确”能否投影到相同的证据资格 |
| 学习证据 | [evidence_policy.py](../../../integration/discrete-math-tutor/memory/evidence_policy.py) 的 assess_attempt/source_quote/project_state；[models.py](../../../integration/discrete-math-tutor/database/models.py) 已有 LearningEventRow、EventEvidenceRow | 不能只凭字段同名合并；需明确独立性、核验方式、可更新状态以及来源版本 |
| 任务与短期状态 | [learning_tasks.py](../../../integration/discrete-math-tutor/database/learning_tasks.py) 已有 claim、guard、replay、cancel；TeachingTurn 保存原题、辅助次数、策略收据和反馈 | 新反馈事件需要接入原任务/版本/epoch，不另造一套“等待回答”的事实源 |
| 掌握相关状态 | [student_state.py](../../../integration/discrete-math-tutor/models/student_state.py) 的旧数值状态；[exercise_skills.py](../../../integration/discrete-math-tutor/database/exercise_skills.py) 的结构化小题技能估计；[q5_learning.py](../../../integration/discrete-math-tutor/agents/q5_learning.py) 的教学路径与理解标记；[assessment_store.py](../../../integration/discrete-math-tutor/integrations/deeptutor/assessment_store.py) 的宿主审核适配 | 谁提供预测、谁记录观察、谁允许正式推进，必须分别列清，不能直接选一个数字作总掌握度 |
| 误解与画像 | [misconception_lifecycle.py](../../../integration/discrete-math-tutor/memory/misconception_lifecycle.py) 有支持、反证、冲突和复开；[readonly_context.py](../../../integration/discrete-math-tutor/memory/readonly_context.py) 仅使用显式来源的偏好，未知专业/年级/基础保留缺失 | 元认知、信心、情绪与稳定能力是否有独立的观测定义，不能由聊天语气补造 |
| 复习与下一轮教学 | [scheduler.py](../../../integration/discrete-math-tutor/agents/deeptutor_learning/scheduler.py) 已有 RetentionScheduler、SpacedRepetitionScheduler、RepetitionState；[review_followups.py](../../../integration/discrete-math-tutor/agents/review_followups.py) 已有复习候选；[teaching_strategy.py](../../../integration/discrete-math-tutor/agents/teaching_strategy.py) 是第三层共用政策 | 调度算法尚未在本批审完；不能把现有调度器直接称为 FSRS，下一动作也不能越过第三层重新决定讲法 |

## 已确认的四组边界

### 1. 任务完成、听懂自报、能力估计与正式掌握分别存在

LearningTaskRepository 的 ready/completed/failed 等状态是执行事实。Q5ProgressRow 的 explained/understood 是教学路径字段；Q5LearningService.mark_understood 的教材导航分支返回 mastery=false。不能仅凭“继续下一节”推导已经通过测评。

TeachingTurn._assess 对辅助题记录 ai_provisional、host_formative、independent=false，保留原题身份、学生原句、来源及帮助记录；其学习证据/作答列表有 40 条上限。这不是自动进入正式掌握库的完整长期证据流。不得通过把这些记录改名为“正式测量”来打通第六层。

原生 [assessment_commands.py](../../../integration/discrete-math-tutor/integrations/deeptutor/assessment_commands.py) / assessment_store 还有 reviewed_key、reviewed_rubric 等审核语义。具体正式入口的全链路资格与撤销传播留待后续专批，不能把所有 Q5 行为笼统等同为已审核测评。

### 2. 当前数值融合不是 BKT

StudentState.blend_numeric 按 `alpha * 新值 + (1-alpha) * 旧值` 更新数字；evidence_policy.project_state 的调用使用 alpha=.4，并在证据不合资格时冻结 mastery/steps_mastery。这里没有在该函数中看到 BKT 的先验、学习转移、guess/slip 及观测似然更新，不能改个名称就称“已接入贝叶斯追踪”。

结构化小题投影已明确输出 uncalibrated_skill_estimate，使用 .6/.4 融合独立规则观测。StudentState 的 .5 初始值同样不能被解释为测得“50% 掌握”；默认 confidence 与 mastery 的差值也不自动证明学生过度自信。

project_state 对 confidence/metacognition 的更新规则与 mastery 不完全相同。是否存在足够来源、实际调用传入了什么值，需要逐入口审计，本轮不凭函数签名断言已经发生错误画像。

### 3. 已有事件与证据表，应先扩展契约

LearningEventRow 已以 student_id/source_key 去重；EventEvidenceRow 以 event_id/observation_key 去重并关联旧 evidence，保存 verification、independent、source_quote；MemoryRevisionRow 关联事件的前后状态。

[MemoryManager.commit_learning_turn](../../../integration/discrete-math-tutor/memory/memory_manager.py) 已处理 guard、版本冲突、原始对话链接、证据去重、状态修订和后台记忆作业。不能按原稿后续章节标题假设项目还没有 learning_events，再新建同名或并行事实源。现有表也不能仅凭名称被称为完整不可变事件溯源系统，尤其还需要审计删除/纠错、撤销和跨投影重算。

部分学习表使用知识点字符串或路径内 objective_id，尚不能据此确认已有全局、跨教材版本稳定的心理学 KC 目录。这是后续数据映射的重点；并不意味着所有记录已串课。[database.py:course_database_url](../../../integration/discrete-math-tutor/database/database.py) 已要求心理学课程使用独立课程数据库，导出分析时仍需保留课程身份。

### 4. 第三层已经有策略反馈，不能再建第二个最终策略权威

TeachingTurn 的 strategy_history 将同目标反馈关联到已发布策略，明确记录 self_report/ai_provisional 与 causal_effect=false。旧 [strategy_memory.py](../../../integration/discrete-math-tutor/database/strategy_memory.py) 也把数值变化标为关联观察，不证明教学策略的因果效果。

第六层可提供“本次困难未解除、某 KC 缺少独立证据、已有复习候选”等状态输入；最终讲法应继续由第三层在约束与执行预算内决定，避免反馈服务和策略器分别写一个互相覆盖的 next_action。

## 复用建议与当前不应定案的事项

推荐优先研究“统一证据封装与资格映射＋现有存储的只读投影”，复用现有事务、收据、审核及遗忘接口。随后在离线副本上比较 BKT/现有启发式，待证据足够再决定运行模型。另建一套总 learner_state 库虽表面简单，会增加同步、撤销和权威冲突；立即替换整个编排框架也不能替代这些数据语义工作。

已有迁入 [DeepTutor 源码声明](../../../integration/discrete-math-tutor/agents/deeptutor_learning/SOURCE_NOTICE.json)：固定 commit `6cf793bd868ba5ecbe64722936d4be8fab5a01df`、Apache-2.0、列明原始文件哈希。应先研究现有适配与原生能力，不再机械复制同一套 learning 模型。调度器、正式评分和回放语义仍需逐批核对，许可证声明也不意味着任何上游模块可无适配替换宿主。

后续设计的建议接缝如下，**是逻辑目标，尚未表示这些分支已经统一实现**：

```mermaid
flowchart LR
  A[原始交互与任务身份] --> B[行为分类与证据资格]
  B --> C[可追溯观察或弃权]
  C --> D[不同目的的状态投影]
  D --> E[第二层与第三层读取]
  C --> F[独立审核及正式掌握门禁]
  F --> D
```

## 本批验证与下一步

本批未调用模型、未读取真实学生数据、未启动应用或复现学习效果。静态源码证据不代表每条入口的运行验收；此前第三层的 98 份快照回放不能充作第六层 KC/正确性标注真值。

第 02 批重点核验 Dialogue-KT 的可复制代码、逐回合时序、整轮正确性与多 KC 的区别，并用无模型合成探针检验关键函数。第 03 批再进入 BKT 概率对象与拟合要求，暂不确定最终算法栈。
