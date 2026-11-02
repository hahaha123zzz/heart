# 第六层实施计划：学习反馈、证据与学习者状态

日期：2026-11-01。基线：`main @ e5b3c004e8eca02cd124539355ef5fe40866ee4b`。状态：**调研后实施提案；尚未执行改造、迁移、发布或模型训练**。执行前重新核对 HEAD、工作区改动与运行模式，按实际差异调整文件位置，不覆盖用户未提交工作。

依据：[完整调研索引](../research/2026-11-01-layer6-feedback-learner-state/README.md)、[最后一批收束](../research/2026-11-01-layer6-feedback-learner-state/07-final-state-migration-evaluation-audit.md)。原讨论稿 2075 行已读完；文中的目录、技术栈和阈值均按源码核验后取舍，不整体照搬。

## 1. 交付目标与范围

首版打通完整闭环：学生输入 → 绑定真实任务 → 提取候选证据 → 分项评价与资格判断 → 同一业务事务保存评价/修订 → 更新允许的 KC、误解和画像投影 → 提供回顾/复习 → 将带来源的观察交回第三层选择教学动作 → 后续表现可追踪。缺少测量时保留未知，闭环仍可通过解释、澄清或提供可选练习继续。

保留第二层理解与原始输入协议、第三层现有 **13 种策略与唯一最终决策入口**、TeachingTurn、AgentLoop、Q5 和原生学习模式。第六层不成为第二个教学内容生成器或策略决策器。

首版完成状态/证据、心理学 KC 映射、误解修订、画像只读投影、错题与复习衔接及恢复验收。BKT/FSRS 的适配和影子比较在计划内；是否切为默认算法由数据验收决定，未达到条件时保留现有引擎，不能为了宣布接入而替换。

本轮不把 PostgreSQL、Redis、完整事件溯源、LRS、全量深度 KT 或 LangGraph 全站迁移设为前置。不自动推断学生专业/年级/人格或稳定认知能力，不在未实测时宣称改善学习效果。

## 2. 三种路线及推荐

| 路线 | 优点 | 代价／限制 | 选择 |
| --- | --- | --- | --- |
| A. 扩展现有领域合同与事务，算法逐步影子接入 | 保留授权、来源、收据、取消和两种运行模式；变化可分 PR 验证 | 需要梳理旧语义并处理兼容投影 | **推荐** |
| B. 先迁 PostgreSQL＋LangGraph，再建第六层 | 编排和存储体系可以统一规划 | 同时改变框架、数据库、教育语义，回归/回退范围很大；不能自动解决幂等 | 暂不采用 |
| C. 只补日志和一个画像摘要 Prompt | 实现快 | 不能可靠处理逐 KC 评价、修订、独立性、恢复与复习状态 | 不满足目标 |

采用 A 的设计不依赖图框架。未来 B 的单项能力如有明确收益，可以复用相同领域命令，不推翻学习数据。

## 3. 权威与最小数据边界

| 对象 | 唯一权威 | 写入规则 |
| --- | --- | --- |
| 原始消息、作答与任务 | 现有 LearningEvent/对话、LearningTask/TaskRequest、Q5/原生 interaction | 服务端绑定归属、版本与 pending；原作答不由 LLM 修改 |
| 评价与资格 | 经本地验证的分项评价及修订 | 评价者提出结果，代码判断可更新哪些投影；允许 unclear / unavailable |
| 稳定 KC | 版本化课程注册数据与审阅映射 | 候选由模型辅助提出，正式身份/映射由受控数据确认 |
| 正式评价达标 | 当前范围的已核验门禁 | 与路径放行、自述、UI 分数及模型估计分开；KC 尚无合格门禁时为 unknown |
| 误解与画像 | 现有生命周期/修订链＋带来源的查询投影 | 不直接采纳模型“confirmed”；字段各自检查资格 |
| 调度与复习 | 当前选定调度器＋原生复习命令事务 | 一张卡一次事件只更新一次，延期/查看/取消不评分 |
| 最终教学策略 | 第三层统一决策入口 | 消费观察及建议，记录所选策略、实际动作与后续表现的关联 |

### 建议的增量结构

以下为首选实现目标，P2 中用实际约束/旧库升级用例固化 DDL；不先建原稿的十张平行表。

1. **KC 注册与映射**：先用课程内版本化 JSON 配 Pydantic 校验，包含稳定 ID、可观察标准、别名范围、来源、关系、题/小题/标准映射、版本与审阅来源。继续保留内容块 ID、路径 UUID 和原题 ID；它们通过映射相连，不改造成同一种 ID。
2. **评价修订记录**：新增一个专用的追加式 `EvidenceAssessmentRow`（拟名），引用已有原作答事件/证据，不复制原始聊天为第二事实源。保存 student/course、attempt/opportunity、题目与 item family/版本、逐标准 KC 结果、帮助暴露、verification、评价方法/工件、资格决定、revision、supersedes/void 引用及原因。服务端分配 revision；同命令同 payload 返回原结果，不同 payload 拒绝；修订不计为新作答。
3. **KC 投影**：新增 `LearnerKCProjectionRow`（拟名），按 student/course/KC/projector 身份保存当前摘要、输入评价摘要/游标、政策/模型/映射版本和 epoch。保留证据摘要与 BKT 等估计的不同 projector；不把 shadow 估计写回旧 mastery。历史状态变动引用现有 MemoryRevision，并扩展快照范围覆盖新投影。
4. **复习算法数据**：优先在原生已事务化的学习 aggregate 中增加明确版本的 review-item/调度器 payload，保存完整 FSRS Card、Scheduler 配置/版本与日志引用；暂不另建平行复习 API/数据库。一个目标多个检索任务时按 review item 保存状态，兼容原目标级 baseline 状态。

新增记录的唯一约束、外键、范围检查与投影替换必须在事务中落实。不能只用 JSON 里一串 user_id 自证归属；也不能让模型签发 revision、独立性或人工确认身份。目录文件中保留的审阅元数据同样需要真实来源。

## 4. 工作包与依赖

| 工作包 | 内容 | 前置 | 建议 PR |
| --- | --- | --- | --- |
| P0 | 状态语义、字段资格与偏好来源修正 | 当前基线复核 | PR1 |
| P1 | 心理学 KC 与测量映射 | 可与 P0 的资料核对交错进行 | PR2 |
| P2 | 评价合同、修订持久化、显式迁移 | P0＋P1 | PR3 |
| P3 | TeachingTurn/事务/画像/误解闭环 | P2 | PR4 |
| P4 | 错题、回顾、正式复习与卡片身份衔接 | P3 | PR5 |
| P5 | BKT、FSRS 离线/影子适配及比较 | P2；线上复习部分依赖 P4 | PR6 |
| P6 | 迁移/故障/两模式端到端、灰度与验收 | P0—P5 | PR7 |
| L | 可选 LangGraph 持久恢复试验 | P2＋P6 中业务幂等已成立，且有新增恢复需求 | 独立 PR，不阻塞首版 |

每个 PR 包含与该变化对应的契约/行为测试和结果说明。无需等所有数据齐备才修 P0；缺少教师标签时继续完成工程链路，评分保持暂定，不开放未经验证的正式更新。

### P0 / PR1：先纠正已经识别的语义风险

修改范围：现有 [adaptive_tutoring.py](../../integration/discrete-math-tutor/agents/adaptive_tutoring.py)、[宿主 policy.py](../../integration/discrete-math-tutor/agents/deeptutor_learning/policy.py)、[原生 policy.py](../../vendor/DeepTutor/deeptutor/learning/policy.py)、[evidence_policy.py](../../integration/discrete-math-tutor/memory/evidence_policy.py)、[readonly_context.py](../../integration/discrete-math-tutor/memory/readonly_context.py)，并搜索所有公开状态/卡片/前端消费者。

- formal_mastery 使用评价语义；路径能否继续另读 route/learner 来源。保留必要兼容字段，但不继续用模糊布尔值承担两种职责；旧客户端显示与导航都要回归。
- learning_stage、visual achievement 等“独立展示”投影使用统一资格判断；不得因 hints_used=0 就忽略 independent=False、ai_provisional、已公开解释或无效来源。
- 自述、问题和辅助请求不生成能力测量；confidence/metacognition 不再因为 raw 模型字段存在就自动进入长期数值。明确自述信心、模型推断与能力估计的不同来源，不能简单改字段名后保留同样无来源融合。
- 审查偏好所有写入方：若已能保证当前值对应显式确认，就补强该不变量与测试；否则绑定实际确认值/版本，不仅检查历史 item_key。遗留来源不明值标为 legacy/unconfirmed，临时覆盖不落长期。
- 修正文档/注释中“OATutor 排除辅助证据”“EMA 证明策略效果”等过度归因，保留实际版本与弱关联含义。

验收：learner override 允许原路径行为但不授予 assessed mastery；形成性非独立成功不显示独立证明；无能力证据不改长期能力字段；删除/撤回后不从旧偏好或旧 epoch 恢复。两个 policy 副本语义一致。13 种策略、仅提示/不出题约束、既有问答与导航不回归。

### P1 / PR2：建立可审阅的心理学 KC 切片

复用 [teaching_targets.py](../../integration/discrete-math-tutor/knowledge/teaching_targets.py)、[course_navigation.py](../../integration/discrete-math-tutor/knowledge/course_navigation.py)、[exercise_mapping.py](../../integration/discrete-math-tutor/knowledge/exercise_mapping.py) 的来源、指纹和版本思想。新增拟定文件为 `knowledge/courses/experimental-psychology-3/kc_registry.json` 与小型校验/查询适配器，禁止模型直接更改正式注册数据。

- 先审核实验变量相关教材范围与少量 KC，覆盖识别、辨析、解释和方案评价的差异；这是测量切片，不限制系统只支持这些话题。未映射内容仍可正常辅导，能力投影保持未知。
- 保留候选、审阅状态和版本；别名可能一对多，检索 related_to 不作同义。先决关系检查悬空、自指、循环，且不把目录顺序自动当先修。
- 题/标准到 KC 的映射区分被问到与真正被测到；题面、参考答案、rubric、映射任何一项变化，都能使旧评价待复核。
- 教材目标、路径目标与测量身份建立显式关系；合并/拆分不自动搬运概率或正式通过状态。

验收：相同审阅 KC 跨路径可识别，同名异义不误合并；一题多 KC 不重复分配整题成功；无映射/过期映射不投影。输出可供审阅的注册清单、来源及未解决项。正式测量标准需要真实核验；开发 fixture 的 reviewed 标记不冒充教师确认。

### P2 / PR3：评价合同、追加修订与显式迁移

修改范围：[models/evidence.py](../../integration/discrete-math-tutor/models/evidence.py)、[evidence_extractor.py](../../integration/discrete-math-tutor/agents/evidence_extractor.py)、[database/models.py](../../integration/discrete-math-tutor/database/models.py)、[repository.py](../../integration/discrete-math-tutor/database/repository.py)、数据库迁移入口；新增一个薄的评价合同/资格模块与上述两类记录，名称在实现 PR 中固定。

- 合同分别表达输入动作、作答绑定、分项评价、来源核验、独立性、覆盖与允许更新的字段；提供 unavailable/unclear 与拒绝原因，不用一个 confidence 代替全部维度。
- 逐标准保存 raw score / categorical verdict；二元 KT 标签及 FSRS rating 通过版本化适配产生，不截断部分分、不把模糊当错。
- 评价保留 model/规则/提示工件身份、参考答案/rubric/来源版本、原文定位和审阅来源；原始作答引用不可被修订覆盖。人工、规则与 AI 暂定来源不相互冒充。
- 以 request/command key＋payload hash 做收据，保留原 attempt 与机会身份；重评、撤销和投影重建各有类型，不能通过新 ID 变成新测量。
- 显式迁移先输出 dry-run 差异，绑定源库摘要与备份；新增表/可空字段保持旧记录 unknown。create_all 不作为旧库升级器。

验收：旧数据加载、空库/旧库升级、重复执行、约束、失败回滚、跨学生/课程拒绝、同键异内容冲突和评价修订去重。原始消息与旧评价保留；缺来源的旧 mastery 不生成虚假历史。新 schema 必须有可重复升级和兼容读取测试。

### P3 / PR4：接通反馈、投影、误解与第三层

修改范围：[memory_manager.py](../../integration/discrete-math-tutor/memory/memory_manager.py)、[misconception_lifecycle.py](../../integration/discrete-math-tutor/memory/misconception_lifecycle.py)、[misconception_resolver.py](../../integration/discrete-math-tutor/agents/misconception_resolver.py)、[assessment_store.py](../../integration/discrete-math-tutor/integrations/deeptutor/assessment_store.py)、[assessment_commands.py](../../integration/discrete-math-tutor/integrations/deeptutor/assessment_commands.py)、TeachingTurn/AgentLoop 适配与画像查询。

- 在既有工作单元内保存评价修订与受影响投影，扩展 memory_snapshot / MemoryRevision 的覆盖；模型调用在事务外，提交时重新核验任务、来源和 epoch。
- 保留一次模型调用返回候选证据/诊断的现有成本结构。不要为“模块化”额外无条件调用多个模型；候选需经本地合同校验。
- 误解目录与学生实例分开，扩展课程内类型映射；沿用 hypothesis/supported/confirmed/dismissed/resolved 和 reopened 观察。反证按真实任务机会去重，不能只靠引文不同凑票。
- 字段投影保留范围、来源、缺失、时效和版本；“不知道”不显示为零能力。路径 intake 与全局画像不按同名字段直接合并。
- 将当前困难、评价结果、帮助状态、未决误解与证据支持传回第三层；第三层选择策略，保存其决策、实际执行动作和后续观察链接，不宣布因果收益。

验收：输入→评价→状态→策略→后续表现链能追查；同轮事务故障不产生半份画像；同一作答重评只替代当前有效评价，不多计机会；冲突、辅助、自述、撤销与误解复发可解释。未新增第二个最终策略入口。

### P4 / PR5：错题与复习闭环

复用 [review_followups.py](../../integration/discrete-math-tutor/agents/review_followups.py)、[原生 review.py](../../integration/discrete-math-tutor/integrations/deeptutor/review.py)、[review_api.py](../../integration/discrete-math-tutor/review_api.py)、既有学习卡片与 `frontend/learning-review.js`。不新增平行正式复习 API。

- 区分回顾候选、待配置任务、可执行检索和到期调度；无题源时仍可回顾，但不生成正式评分或遗忘事件。
- 错题、复习与评价共用原题、item family、KC 和证据身份；保留新 retrieval episode，不能把复制题生成的新 ID 当作新题迁移。
- 卡片对象按实际检索标准定义，一 KC 多卡有显式映射；声明尚未学习的内容不产生假复习历史。
- start/defer/return/finish 继续受现有授权/版本/收据保护；延期不改变知识状态，finish 必须有本次真实评价。来源失效进入待核验，不记 Again。
- 改目标保持率只重算日程，不伪造学习；取消和中断恢复保持题目、帮助历史与评分身份。

验收：从辅助失败/正式错误到回顾或复习，再到真实作答和后续状态有完整记录；浏览、延期、取消、重复请求均不增加评分；宿主与原生队列一致，原路径位置和模式不会被静默改变。

### P5 / PR6：BKT 与 FSRS 的可替换适配

依据：[BKT/pyKT 审计](../research/2026-11-01-layer6-feedback-learner-state/03-bkt-pykt-eduktm-source-audit.md)、[FSRS/恢复审计](../research/2026-11-01-layer6-feedback-learner-state/04-fsrs-langgraph-recovery-audit.md)。新增离线数据导出/实验入口与小型适配，不把训练放进每轮请求。

**BKT：** 从当前有效、明确二元且满足资格的评价导出序列，保留学生/课程、KC、原题/机会、时间、映射/评分版本与排除理由。分别比较课程/KC 频率基线、可解释基线和 BKT；无足够支持时共享保守参数或拒绝输出，不拟合一个“看起来确定”的个体模型。区分答前 p、答后 posterior、学习转移后 p_next 与 p_correct；保留参数版本与重放输入。pyBKT Model 优先离线使用；如借 Roster，先处理共享 prior、异常恢复及零状态边界。影子结果独立保存，不影响正式掌握。

**FSRS：** 通过既有 RetentionScheduler 适配，将 float epoch 转为明确 UTC 时刻，影子阶段关闭 fuzzing；完整保存 Card/Scheduler 版本与配置。Again/Hard/Good/Easy 来自明示的检索评分政策，不把懂了、跳过、辅助成功编码成成功或失败回忆。明确短期步骤、整天计算与现有同会话保护的差异。旧 stability/difficulty 不直接搬用；有合格历史才重算，无历史按迁移政策冷启动并保留既定到期日。

库版本以调研固定 commit 为参考，实际接入锁定可安装发行版/哈希并重新核验差异和许可证。py-fsrs 基础运行与 optimizer 依赖分开；pyKT/EduKTM 暂不进线上依赖。SOURCE_NOTICE/补丁清单保留原上游 commit 与本地修改，不把 vendor 改动伪装成原始快照。

验收：数值边界、部分/未知排除、乱序与重复事件、序列化、固定时钟重放、撤销后重算、参数切换、不同评分政策和基线对照。只有在同目标留出数据与排期差异审查通过后，才按课程/测试账户切换候选引擎；未通过继续 baseline 并报告原因，不阻塞已完成的证据闭环。

### P6 / PR7：迁移、故障、两模式集成与灰度

借 [learning_migration.py](../../integration/discrete-math-tutor/integrations/deeptutor/learning_migration.py) 的只读快照、候选与收据方式，扩展为本次新增数据的 dry-run/候选核验；不直接启动旧候选的正式切换。覆盖 Q3、Q5 与原生学习/复习路径。

- 新旧读取先做 shadow diff，旧字段只作兼容显示，不作为缺证据 KC 的训练标签。候选对齐学生/课程/目标/位置、原题、评分及来源；不推断旧会话归属、独立性、模型版本或未存在的复习历史。
- 业务提交前后、原生提交后宿主响应丢失、发布后收据保存前、投影提交前、worker 租约到期、删除/取消/过期后注入故障。恢复不能新增重复评价、题目、掌握更新或复习评分。
- 同一源库重复迁移得到相同收据；源摘要变化拒绝覆盖；只迁可解释内容，未映射项有清单。验证备份恢复与读取回退，不能只测空库建表。
- 保留现有 SOURCE_NOTICE、课程独立库、授权及来源复核。并发窗口依靠真实事务/版本，不把 SQLite 上的 with_for_update 或一个进程内锁当成跨进程保证。

验收：选定故障与不变量用例全部通过；可见输出仍对应真实提交收据；两模式端到端能暂停、恢复、纠错、回顾、正式复习；发布、模型与课程开关只按已完成验收的能力启用。

## 5. 测试与评价计划

优先扩展现有测试组：`test_memory_events.py`、`test_memory_jobs.py`、`test_misconception_updates.py`、`test_teaching_memory_corrections.py`、`test_shared_teaching_strategy.py`、`test_runtime_strategy_parity.py`、`test_q3_task_loop.py`、`test_input_understanding_multiturn.py`、`test_native_review.py`、`test_review_authorization.py`、`test_native_learning_migration.py` 及已有浏览器复习脚本。先核对各 fixture 的数据库隔离与项目锁定运行环境，再执行；研究探针不替代这些集成测试。

新增最少但必要的测试集中在 KC 合同、评价修订/资格、投影重建、算法适配和增量迁移。使用临时 SQLite、固定时钟、可控故障、模拟模型；并发/跨进程与浏览器单独作为集成层。真实模型验收沿用户已选官方 deepseek-flash 的隔离配置，凭据不入库、不写报告，人工复核评价结果；本计划没有运行模型调用。

| 验收层 | 必测内容 | 放行条件 |
| --- | --- | --- |
| 硬不变量 | 自述不授掌握；不合格证据不改能力；身份/版本/来源无效拒绝；重复只生效一次；取消/删除后不回写 | 选定工程用例全部通过，违规写入为 0；这是用例验收，不宣称真实世界零风险 |
| 交互兼容 | 两课程、宿主/原生、输入理解 off/shadow/active、13 策略、仅提示/不出题、待答绑定 | 无已知关键回归，旧客户端兼容或有明确字段迁移 |
| 评价质量 | 盲标作答动作、独立性、逐标准/KC 结果、误解候选与允许更新 | 人工仲裁金标准；报告各类支持数、弃权覆盖、误更新/误报与一致性，不用单个准确率掩盖高风险错误 |
| 概率模型 | 同一预测目标、学生/时间/原题组切分、训练/校准/评估隔离 | Brier/log loss/校准及 AUC 与基线比较；数据不足或退化时不切默认 |
| 复习与效果 | 同日/间隔检索、错误修复、评分政策、来源变化与工作量；独立前后测/延迟测 | 工程排期确定性先过；学习收益须真实试验另证，完成率或 AUC 提升不替代 |

[psychology_evidence_gate.json](../../integration/discrete-math-tutor/tests/data/answer_flow/psychology_evidence_gate.json) 的 8 个用例只能作为工程回归，不能改个字段就叫教师金标准。新增语料区分合成、人工工程标注、真实教师盲标及仲裁；unknown / unavailable 显式编码。`annotation_agreement.py` 的缺失/空集合与未定义 κ 行为要适配标注合同，不无条件套用 0.6 阈值。

不预报一个未经基线验证的 F1/AUC 放行数字。P1/P2 形成初始金标准后、模型试验前固定误报/漏报容忍度和比较方法；若没有真实教师资源，继续交付工程闭环，但正式自由回答能力判定保持 ai_provisional，不声称课程已学会。

## 6. 迁移、开关与回退

- 单独控制第六层读取、评价投影、BKT shadow、FSRS shadow/active 等能力；尽量复用现有模式开关，新增开关必须对应真实可独立回退能力，避免配置组合失控。
- 旧记录可读，旧估计有 legacy 来源；新写入使用当前合同，候选构建不自动激活。切换只读视图与切换算法分别发布。
- 原生 aggregate 新增字段前检查旧写入者的兼容性：当前部分模型 extra=ignore，旧版本可能在读写时丢掉新 payload。使用 writer/schema 版本围栏并停止不兼容写入者；不能把“回退旧二进制”当作安全回退方式。
- 回退使用兼容新 schema 的代码关闭新读/写投影或新调度器，恢复 baseline 读取；保留新增原始事件、评价修订和审计，不删记录凑回旧数值。必要的库恢复从备份/收据对账演练，不能在线盲目 downgrade。
- 删除、撤销与 epoch 变化同时影响背景任务、图检查点、影子估计、检索缓存及迁移候选；失效来源不得从备份被默认为当前有效。
- 正式库 DDL、生产切换、合并与 push 在未来执行任务中处理。本轮仅形成可审阅计划，历史第三层的发布操作不视为本轮已经执行。

## 7. 可选 LangGraph 试验与后续研究

仅在需要比现有暂停/恢复更细的进程崩溃恢复时，复用现有领域命令做一个最小持久 saver 图：准备已持久化题目 → interrupt 等回答 → 核验当前身份/来源/epoch → 提交幂等评价命令。节点重跑不得重新随机出题或重复应用同一评分。thread_id/namespace 只作游标，不作权限凭证；业务库与 saver 不能假定原子。

分别在提交前、提交后检查点前、恢复期间取消/删除、同任务并发恢复时终止进程并重启。通过后比较真实收益、额外依赖与运维成本，再决定是否扩大。pyKT/EduKTM、模型融合、参数个体化和跨课程迁移放在有合格数据后的研究队列，不能取代首版闭环验收。

## 8. 完成定义与当前起点

实施完成应具有：可重查的反馈与评价修订；稳定 KC 与测量范围；受资格约束的能力/误解/画像；可用的回顾/复习与真实检索日志；同任务与跨会话恢复；保持第三层唯一决策权；所有新增数据可迁移、撤销、重建并通过既定测试。

算法是否成为默认与是否证明学习增益单独报告。若 BKT/FSRS 仅停留在影子阶段，应明确已交付适配和比较能力、尚未切默认；不能把这个状态叫已验证的个性化教学效果。

**建议实际开发从 PR1 开始**：先补 formal_mastery、independently_demonstrated、画像字段与偏好来源的回归用例，再修改共享语义与两模式适配；同时准备 PR2 的课程 KC 审阅材料。每个阶段结束将代码差异、测试证据、未验证内容与下一阶段依赖写入项目文档。
