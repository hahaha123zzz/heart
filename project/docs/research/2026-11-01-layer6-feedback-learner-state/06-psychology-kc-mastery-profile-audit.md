# 第六批：心理学 KC、掌握门禁、误解生命周期与画像投影

日期：2026-11-01。项目基线：`main @ e5b3c004e8eca02cd124539355ef5fe40866ee4b`。逐行读取原稿 **1044—1365 行**。本批核对知识体系、BKT 示例、误解状态与学习画像，仍只做调研，不改业务实现或正式数据。

## 结论

**先建立课程内稳定的“可观察能力—测量标准—证据”映射，再接概率算法。** 现有教材标题、路径目标、知识状态文本键和练习技能并不是同一种身份。原稿的唯一 KC ID 方向值得保留，但不能把所有节点改名后便认定它们已经统一。

本项目已经有定性/定量掌握门禁、学习者主动放行、误解反证与重新打开、只读偏好投影。优先复用这些边界。新发现的两个风险是：`formal_mastery` 调用了允许学习者放行的 `is_mastered`；阶段标签可把元数据标为非独立的形成性成功显示为 independently_demonstrated。它们属于需要后续修正的语义/投影问题，不是本批已经确认发生的线上误授掌握事件。

## 1. 稳定 KC 不是教材目录，也不是路径目标

### 1.1 当前身份实际分布

| 身份／源码 | 现在表示什么 | 能否直接作为全课程 KC |
| --- | --- | --- |
| [course_config.py](../../../integration/discrete-math-tutor/knowledge/course_config.py) | 默认课程为 experimental-psychology-3，另有 discrete-math | 课程命名空间可以复用；不能因此把原稿的整个心理学学科树都视为已导入内容 |
| [teaching_targets.py](../../../integration/discrete-math-tutor/knowledge/teaching_targets.py)、[course_navigation.py](../../../integration/discrete-math-tutor/knowledge/course_navigation.py) | 从原件标题层级和实际块范围提取教学目标，编号正文不自动当标题；导航绑定来源版本 | 是可追溯的内容范围，不自动等于可测量技能；同一标题可涉及多个能力，能力也可能跨多个块 |
| [Q5ObjectiveRow](../../../integration/discrete-math-tutor/database/q5_learning.py#L60)、[目标创建](../../../integration/discrete-math-tutor/agents/q5_learning.py#L295) | 路径中目标的 UUID、顺序、先决目标与来源 | UUID 标识一次路径目标，不保证跨路径同一概念仍用同一 ID |
| [TeachingTurn._fresh](../../../integration/discrete-math-tutor/agents/adaptive_tutoring.py#L459) | 以环境课程值与 topic 文本生成截短哈希 | 文本一致时稳定；别名不同会产生不同 ID，且不是教材语义版本或教师核验过的 KC |
| [KnowledgeStateRow](../../../integration/discrete-math-tutor/database/models.py#L93) | 学生＋knowledge_point 文本唯一的旧状态 | 可以保留兼容映射，不能假定同义词已合并或章节内同名已消歧；课程隔离另由现有数据库边界处理 |
| [exercise_mapping.py](../../../integration/discrete-math-tutor/knowledge/exercise_mapping.py) | 服务器维护题目/小题到技能的指纹与版本映射 | 结构值得复用；**心理学模式 resolve_mapping 直接返回 None**，目前不能当作现成心理学 KC 注册表 |
| [concept_aliases.py](../../../integration/discrete-math-tutor/knowledge/concept_aliases.py) | 检索用关联术语，当前主要是离散数学术语 | 文件已说明欧拉图与欧拉回路是检索关联，不是同一对象；检索扩词不能自动用于合并学生能力 |

合成探针确认：同课程下“自变量”和“实验自变量”通过真实 `_fresh` 得到不同目标 ID。这说明文本哈希是标识手段，不是概念消歧。当前 Q5 的路径 UUID 和教学哈希均有各自用途，不应删除它们去强行替代 KC。

### 1.2 候选 KC 合同

建议把以下关系明确记录，具体文件/表结构留到第七批：

- 稳定课程内 KC 身份：名称与别名可改，身份不随目录移动改变。可用无语义 ID 配显示名称/slug；原稿的点分路径也可作为名称，但章节重组时不能随意重命名身份。
- 可观察能力与评价标准：要能描述学生在什么任务、什么条件下做出什么表现，而不是仅写“自变量”。保留核验者、版本与课程范围。
- 教材与教学目标映射：指向已验证文档/块/范围及版本；一个内容块、一个路径目标都可以映射多个 KC，但不因此自动生成多条成功测量。
- 题目/小题/标准映射：分开 target KC 与实际 evaluated KC，并绑定题目、rubric、评分政策和映射版本。前者是出题意图，后者才是本次证据覆盖。
- 关系类型：belongs_to、prerequisite、related_to、alias、supersedes 分开。先修关系不是目录顺序，关联不是同义；合并或拆分 KC 时保留历史映射与重算政策，不平均两份旧掌握值。

未知 KC 可以保留为待审候选，但不能由对话词语直接升级到正式注册表或授予掌握。别名歧义、跨章同名、版本失效和多 KC 覆盖不足时允许不投影。

### 1.3 心理学首批候选怎样写得可测

本地教材 [chapter_01/text.txt](../../../integration/discrete-math-tutor/knowledge/courses/experimental-psychology-3/chapters/chapter_01/text.txt#L229) 已有操纵自变量、控制影响结果因素的相关论述，可以作为注册候选的来源起点；本批没有完成全书 KC 标注，也没有审核新的正式题库。

| 原稿概念 | 更适合验证的候选能力 | 需要的评价边界 |
| --- | --- | --- |
| 自变量 | 在明确实验情境中识别研究者操纵的因素并说明依据 | 不只匹配“主动改变”几个字；题目情境与研究设计要适用 |
| 因变量 | 指出该情境实际测量的反应/结果指标，并与操纵因素区分 | 题干是否足以确定测量指标；不能因为同时提到自变量就给两项成功 |
| 额外变量／混淆 | 指出可能影响结果的因素，说明何时会妨碍解释 | 先核实教材对额外、控制、混淆等术语的具体用法，不按词面互换 |
| 控制方案 | 按给定 rubric 评价某种控制安排是否解决具体问题 | 多标准分项评价；“举出了控制方法”不等于完整实验设计能力 |

以上是待教师/教材核验的测量定义，不是已创建的新 KC 或保证有效的题目。自由解释、辨析例子和设计方案的表现需分别观察；“能复述定义”不能直接覆盖“能在新实验里正确使用”。

## 2. 外部成熟实现：复用身份与内容建模，保留本项目学习者证据链

### 2.1 DataShop：KC 模型是任务步骤与技能的映射

CMU 的 [DataShop 官方 KC 建模说明表](https://pslcdatashop.web.cmu.edu/downloads/DataShopCheatSheet.pdf) 将 transaction、step、observation、opportunity 和 KC model 分开：一个步骤可以关联多个 KC，一次观察不等于每一次提示/错误/正确交互各算一份独立机会。该表是历史版本的建模说明，不是本项目当前算法规范。

这支持我们把“每条聊天消息”与“独立测量机会”分开，并将不同 KC 划分作为可比较的模型假设。它并不证明某个心理学 KC 列表正确。本次网页直接读取返回 403，以上依据官方域名检索能获取的文档文本；没有读取被阻止的正文页或复现 DataShop 工作流，也不采用其提示计错定义来替代本项目资格政策。

### 2.2 Oppia：技能、误解目录、题目关联和版本各有身份

固定 [oppia/oppia @ 0538628a88da77478174636b85bff9c834492329](https://github.com/oppia/oppia/tree/0538628a88da77478174636b85bff9c834492329)，Apache-2.0。沿用第五批固定版本，新增审查以下部分：

- [Skill](https://github.com/oppia/oppia/blob/0538628a88da77478174636b85bff9c834492329/core/domain/skill_domain.py#L819) 将 skill_id、可观察行为描述、rubrics、内容、先决技能、版本与各子结构 schema 版本分别保存。`superseding_skill_id` 和 `all_questions_merged` 表达技能合并与题目迁移进度，说明改身份不是简单改名称。
- [Misconception](https://github.com/oppia/oppia/blob/0538628a88da77478174636b85bff9c834492329/core/domain/skill_domain.py#L460) 是技能目录中的内容对象，包含局部 ID、名称、给作者的说明、反馈与 must_be_addressed；它不是某学生已经存在误解的断言。
- [Question](https://github.com/oppia/oppia/blob/0538628a88da77478174636b85bff9c834492329/core/domain/question_domain.py#L304) 保存 linked_skill_ids 和不适用的技能误解 ID；校验拒绝空技能关联与重复 ID。其误解关联使用 skill_id 与 misconception_id 组合范围，不让一个泛化的 concept_confusion 到处指同一对象。
- [AnswerGroup](https://github.com/oppia/oppia/blob/0538628a88da77478174636b85bff9c834492329/core/templates/domain/exploration/answer-group.model.ts) 可把特定答案规则关联到技能误解。仍需注意第五批已查的首匹配规则语义，目录存在某误解不代表每次错误都命中它。

最值得借的是领域合同、校验约束和迁移关系。项目已有 Python/Pydantic、来源证明及事件仓储，宜按这些约束补最小注册数据/适配；不直接导入 Oppia 的完整领域模块和存储依赖。本批缓存固定源文件与许可证供审计，尚未摘取进业务代码。

## 3. 掌握有四种语义，不能共用一个布尔值

| 量／状态 | 当前实际含义 | 后续输出建议 |
| --- | --- | --- |
| StudentState.mastery、skill_summary 的估计 | 旧平滑估计或未校准技能估计 | 标记估计方法和来源，不写成 BKT 或正式概率 |
| BKT p、DKT 后续答对率、FSRS 回忆率 | 不同模型、不同预测对象与时点 | 继续按第三、四批分别保存语义与版本，不彼此代替 |
| is_assessed_mastered | 读既存定量/定性状态及必要视觉任务的评价门禁 | 只描述当前策略下通过评价；真实资格仍需写入路径保证 |
| is_mastered / learner override、Q5 understood | 允许路径推进，或学习者声明理解 | 暴露 learner 来源／understood，不冒充正式评价通过 |

原稿 BKT 示例算术成立：p=0.6、G=0.2、S=0.1、T=0.15 时，答对概率为 0.62，答对后后验约 0.870968，学习转移后约 0.890323。最后一个值是模型下的下一步潜在掌握估计，**不自动使正式门禁通过**。这些参数仍只是演示。部分正确、不确定评价和辅助作答的资格处理先于二元更新；不重复实现第三批已审计的参数拟合/校准问题。

### 3.1 项目实际门禁与数值

[policy.py](../../../integration/discrete-math-tutor/agents/deeptutor_learning/policy.py#L82) 的 `is_assessed_mastered` 先检查 required_visual_tasks；CONCEPT / DESIGN 读取 qualitative_mastery 布尔值，MEMORY / PROCEDURE 读取 mastery_levels 是否达到 0.9。定性通过在 display_mastery 显示为 1.0，这只是显示约定，不能解释成概率 100%。0.9 也只是当前工程门槛，本批没有验证它对心理学的测量效度。

原生 [mastery.py](../../../vendor/DeepTutor/deeptutor/learning/mastery.py) 使用最近至多五次结果的加权正确率，一次全对封顶 0.5、两次全对封顶 0.8，三次全对即可达到 1.0；这不是 BKT，也不是对真掌握置信区间的估计。`LearningService.calculate_mastery` 过滤 voided 与非独立 quiz_attempts，但纯计分函数本身不负责题目归属、来源或样本去重。因此不能只根据输入一个 bool 列表就确认整个课程达标。

原生宿主 [assessment_store.py](../../../integration/discrete-math-tutor/integrations/deeptutor/assessment_store.py#L175) 另查 rubric、答案、来源和帮助记录，并在辅助评价时保留原掌握状态，这一层应继续复用；纯 policy 中读取到 True 不代表 policy 自己重新核验过所有事实。

### 3.2 路径放行与正式掌握字段的语义风险

`mastery_source` 在评价门禁未过但存在 learner_mastery_overrides 时返回 learner；`is_mastered` 因而可以为 True，而 `is_assessed_mastered` 为 False。这是上游明示的路径放行设计，并非两函数应当相同。

本地 [TeachingTurn._sync](../../../integration/discrete-math-tutor/agents/adaptive_tutoring.py#L484) 却把 `is_mastered` 写入名为 `formal_mastery` 的字段。探针确认上述两函数能分歧，因此这个字段的命名/来源在进入第六层画像时应修正或细分。**没有据此证明受管 Q3 线上路径已经接受 learner override**；其实际可达性、报表消费者与迁移影响仍需在实施轮回归核对。

[Q5 mark_understood](../../../integration/discrete-math-tutor/agents/q5_learning.py#L525) 已明确返回 mastery=False，普通路径可推进教学位置、textbook_navigation 分支只标记 understood 并要求后续导航。应沿用这种区分，不能把“章节讲完”“用户说懂了”“允许继续”汇总成正式学会。

### 3.3 阶段标签也存在独立性差异

`learning_stage` 的定性分支以 result=correct 且 hints_used=0 判为 independently_demonstrated，未同时检查 `visual_context.independent` 和 verification。用真实 LearningEvidence 结构构造 source=host_formative、independent=False、ai_provisional 的无提示正确事件，实际函数仍返回 independently_demonstrated。

这与 [Q3 形成性记录](../../../integration/discrete-math-tutor/agents/adaptive_tutoring.py#L561) 明确写非独立的语义不一致。它不证明正式门禁同时被改写，但会影响阶段、画像或建议的可信度。后续应统一“独立展示”判据，保留 assisted / provisional 的显示与策略含义，不能只修 formal_mastery 字段就宣告完结。

## 4. 误解目录和学生误解实例要分开

### 4.1 当前已有能力与实际缺口

[models/misconception.py](../../../integration/discrete-math-tutor/models/misconception.py) 的 CANONICAL_TYPES 混合心理学与离散数学；已有信度/效度、相关/因果、自变量/额外变量等类型，但原稿示例“自变量/因变量混淆”没有对应的专门注册项。`normalize_type` 主要做别名规范化，不等于对未知类型的课程白名单校验。

[通用 lifecycle](../../../integration/discrete-math-tutor/memory/misconception_lifecycle.py) 允许候选合并与本地状态迁移；[原生 assessment_commands.py](../../../integration/discrete-math-tutor/integrations/deeptutor/assessment_commands.py) 对 hypothesis 命令则要求类型在 CANONICAL_TYPES。两入口的类型政策不同，不能只在 Prompt 加一个标签就认为各模式都支持了它。

建议课程内目录描述：误解身份/版本、相关 KC、适用任务、典型错误模式、反例与辨析证据、可选反馈、来源与核验者。学生实例描述：学生/课程/KC 范围、目录引用、支持/反证事件、当前状态、状态变更来源。目录内容不含对某学生的永久判断；一个通用的 concept_confusion 不足以标识具体混淆。

### 4.2 原稿状态与现有实现的映射

| 原稿建议 | 现有表示 | 建议 |
| --- | --- | --- |
| candidate | hypothesis，随后可到 supported | 不新建同义枚举；保留支持程度与来源 |
| confirmed | confirmed：计数/信心阈值结果 | 加上确认机制语义，不能把当前工程阈值称为教师确认或可靠诊断 |
| resolving | 纠正提议、pending 反证观察 | 先用修复活动/观察记录表达，是否独立状态需看真实消费者需求 |
| resolved | resolved | 依据后续反证处理，保留过去事实，不删除错误历史 |
| recurring | reopened 观察，重新进入 hypothesis / supported | 作为复发事件与计数投影，不立即新增持久状态值 |
| 原稿未列 | dismissed | 必须保留：原判断被推翻，与“原误解存在但学生已纠正”不同 |

### 4.3 继续复用现有反证、冲突与事务

现有 lifecycle 有以下具体规则：校验当前学生/知识点的实例、原文与独立作答；同轮支持与反证或相反纠正意图冲突时保留状态；confirmed 不因自动 dismiss 提议直接取消；rule_verified 决策可一条反证解除，AI 暂定反证需两个不同引文 hash；已 resolved/dismissed 再出现支持会记录 reopened，并重新计数。

[repository.misconception_counter_votes](../../../integration/discrete-math-tutor/database/repository.py#L643) 在支持、冲突或另一纠正意图出现后清空连续反证票；记录保留用于审计。反证 quote hash 去重不等于独立任务数验证：同一题答案改写两次仍可能是同一测量，固定模板在不同有效题中也可能字面相同。因此需要在 KC/测量合同里补原题与机会身份，不能把“两个不同句子”说成教育上充分的纠正证明。

支持证据的状态阈值同样是工程政策，已在第五批验证，不重复宣称诊断准确率。后续应区分真实概念混淆、表达不清、记忆失误、来源/题目错误及证据不足；不把每个 incorrect 都永久写成误解。新情境的独立反证可作为后续验收方向，不能为了凑票重复提同一题。

## 5. 学习画像应是有范围、有来源的多个投影

原稿五部分可以保留为查询视图，而不是一份让模型整体重写的 JSON：

| 投影 | 适合的数据来源 | 不允许的自动推断 |
| --- | --- | --- |
| 目标与进度 | 当前授权路径、教材位置、用户明确目标 | 导航结束即全章掌握 |
| 能力与测量支持 | 合格评价、KC 映射、模型/政策版本、样本支持 | 将未校准分数直接标成正式掌握概率 |
| 误解与修复 | 有来源的候选、支持/反证及修订记录 | 一次错误扩展成稳定能力或人格标签 |
| 行为统计 | 按任务/会话的独立尝试、帮助暴露与实际机会数 | 用提示次数单独断言“依赖性”；用停留时长判断不理解 |
| 交互偏好 | 明确用户变更与本轮覆盖 | 因一次求例子就永久修改风格；把偏好说成已证实最有效学习方式 |

行为比率必须带分母、时间范围与缺失说明，例如“本阶段 3 次可观测独立机会中有 1 次使用帮助”，而非一个无法解释的 hint_dependency=0.8。强制提供提示、页面自动展示答案、重复投递与无效来源应与主动求助区分。

当前有两个不同的 LearnerProfile：

- [models/learner_profile.py](../../../integration/discrete-math-tutor/models/learner_profile.py) 保存跨会话 preferences、learning_behavior、teaching_effectiveness；其中 effectiveness 是 EMA/弱关联权重，不能证明策略因果收益。
- [deeptutor_learning/models.py](../../../integration/discrete-math-tutor/agents/deeptutor_learning/models.py) 的路径画像包含 prior_knowledge、target_level、time_budget、自由文本 preferences 等输入。这些是该路径的学习者陈述，不自动成为全课程客观能力证据。

两者既不同存储范围，也不同字段语义。不能直接按字段名合并，或把路径 intake 的 prior_knowledge 当作已测先修能力。

[ReadonlyMemoryContext](../../../integration/discrete-math-tutor/memory/readonly_context.py) 按偏好键过滤，仅输出在 MemoryChangeRow 中具有 explicit_user 来源历史的受支持偏好；每次重读，profile 部分对于专业、年级、先验知识保持 missing。隔离内存 SQLite 验证：AI 来源的偏好不会输出，显式记录删除后也不会从仍含旧值的 profile 恢复；未证实的基础资料不补造。

还需注意：这里查的是 distinct item_key，再读取 profile 中的当前值，并未绑定具体确认值/修订。合成替换当前值后，旧显式键仍会放行这个新值，因此“键有显式历史”不等于“当前值已被明确确认”。是否可能由未授权路径覆盖还需追踪写入方；本批不据此断言已经发生。

这是可复用的读取边界，但它尚不是统一能力/误解画像接口。未来如需让第二、三层读取更多内容，应继续按学生/课程/KC 与当前版本授权投影，并带来源、缺失和时效；不要绕过只读边界去调用可能同步索引或写回的总览函数。第三层继续唯一选择最终教学策略，第六层只提供可解释的观察与建议。

## 6. 后续实施前的最小验收与依赖

1. 先选实验心理学的一小段教材范围，审核候选 KC、别名及可观察标准；先验证“定义辨认、情境识别、对比解释、设计评价”是否需拆分，不承诺把全心理学树一次建完。
2. 统一内容位置、路径目标和测量 KC 的映射，覆盖同义、同名异义、一题多 KC、KC 合并/拆分、题目与教材版本变化。失败时保留候选与原因，不把旧成绩自动迁给新身份。
3. 分离路径放行、评价达标、显示估计与模型概率；核对 formal_mastery 和 learning_stage 的消费者，测试 learner override、形成性辅助成功与 necessary visual tasks。
4. 沿用误解事件与事务，验证同题重复、不同题同措辞、相反证据、confirmed 驳回、resolved 复发、来源错误和修订重算。教师确认身份与自动阈值明确区分。
5. 查询画像时验证跨课程/会话范围、缺少证据、用户删除/撤回、偏好临时覆盖和路径 intake。继续保留原始事件，长期投影可重建。

本批未确定最终 KC 清单、参数、模型融合、数据库 schema 或新增服务；后续实现仍需经过这些资料与测量验证。原稿关于 BKT 与深度 KT 不宜简单平均的提醒可保留，具体融合只有离线同目标校准数据后才有讨论基础。

## 7. 本批验证与限制

隔离缓存 `.runtime/layer6-research/round06/`（不入库）保存 4 份 Oppia 固定源文件/许可证及 Git blob 清单，字节哈希已核对。`probe.py` 使用检查过的本地纯函数、AST 提取方法、模拟仓储和临时内存 SQLite，共 **16 项具名探针通过**：

- learner 放行不等于 assessed mastery；概念数值 1 不替代定性门禁；定性显示 1 是政策；必要视觉任务可阻止评价门禁；三次正确可得到当前分数 1；形成性非独立元数据与阶段标签可不一致。
- 真实 _fresh 对同课程不同别名生成不同 ID；相同反证引文不增加票、不同反证可解除、重新打开记录与状态区分、confirmed 驳回需复核、自述不能当反证。
- 只读偏好按显式键历史过滤、缺失画像不补造、显式变更记录删除后不恢复旧偏好；键历史检查不绑定当前值的确认来源。

生命周期探针使用模拟仓储，未重跑完整事务故障测试；只读投影使用合成数据和临时数据库，未访问正式学生库。首次 AST 探针缺少新建语句的行号元数据，修正隔离脚本后重跑通过，未更改业务文件。Oppia 只做静态领域审计，未启动其应用；没有心理学真实学生评价、准确率、概率校准或学习增益结论。

下一批从原稿 **1366 行**开始，研究复习/错题、任务/知识/会话状态、事件与数据库组织、迁移和回放。当前身份与状态语义发现将作为第七批的数据合同输入。本批未提交或推送。
