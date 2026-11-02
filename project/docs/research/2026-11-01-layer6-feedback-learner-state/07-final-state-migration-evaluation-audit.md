# 最后一批：复习、状态、事件迁移与评测收束

日期：2026-11-01。项目基线：`main @ e5b3c004e8eca02cd124539355ef5fe40866ee4b`。按用户要求，将原计划第七、八批合并；本次逐行读取原稿 **1366—2075 行**，至此全文 2075 行已读。前六批结论仍有效，以下补充最终数据与实施边界。本批不实施业务改造。

## 1. 最终选型结论

**采用“现有回合链路＋受约束评价修订＋可重建 KC 投影＋现有复习入口”的渐进改造。** 首版覆盖反馈、评价、状态、误解、画像、复习与恢复的完整闭环；算法切换通过离线/影子验收，不能成为修正现有语义问题的等待条件。

| 项目／技术 | 最终建议 | 首版具体边界 |
| --- | --- | --- |
| TeachingTurn / AgentLoop / 第二层理解 / 第三层决策 | 继续沿用 | 第六层提供证据与状态观察；13 种教学策略保持现有统一入口 |
| 现有 SQLAlchemy、SQLite、事件/修订/任务收据 | 继续沿用并补显式迁移 | 新增结构按已确认缺口设计，不按原稿十张表逐项重建 |
| Dialogue-KT | 借标注、候选 KC 约束和时间切片思路 | 不搬训练栈，不把数学对话自动标签当心理学金标准 |
| pyBKT | 离线可解释基线，达标后影子估计 | 参数拟合与学生状态过滤分开；不直接覆盖正式掌握 |
| py-fsrs | 通过 RetentionScheduler 做影子适配 | 明确评分、卡片身份、UTC 与随机性；沿用已有正式排期，验收后再切换 |
| pyKT / EduKTM | 后续离线比较 | 首版不训练全模型列表，不增加线上深度学习依赖 |
| Oppia | 借技能/误解目录、题目映射与版本约束 | 选择性实现领域合同，保留许可和归因，不导入整个应用 |
| Open edX ORA2 | 借 rubric 快照、分项与评价来源概念 | AGPL 代码不在本计划中直接复用 |
| LangGraph | 可选、独立的恢复试验 | 不在首版关键路径；图检查点不能替代业务事务与幂等 |
| PostgreSQL / Redis / 完整 Event Sourcing / LRS | 当前不引入 | 只有实际并发、容量或互操作需求证明必要时再单列迁移 |

各上游 commit、许可证与行为限制见第 2—6 批，不把“可复用”写成“已接入或已证明教育有效”。

## 2. 复习与错题：三个对象、两种测量目的

原稿正确指出：复习不是重发聊天记录，评分来自实际检索表现。但“完成学习→进入队列”需要拆开：

- **回顾候选**：可以来自讲解结束、自述困难、主动请求或形成性反馈；没有正式评分不影响提供回顾入口，但不产生掌握信用、FSRS 评分或遗忘结论。
- **可执行复习任务**：绑定当前可用题目、标准、来源、版本与学习范围；无合适题源时标为待配置，不伪造已审核题或擅自换源。
- **复习调度状态**：由合格的检索日志更新，含模型/参数/评分政策/卡片映射版本；候选创建、延期、取消、查看都不是一次成功或失败回忆。

已有 [review_followups.py](../../../integration/discrete-math-tutor/agents/review_followups.py) 从已发布进度卡生成只读回顾，校验课程与 memory_epoch，明确 formative_unverified、mastery_credit=False。已有 [原生 review.py](../../../integration/discrete-math-tutor/integrations/deeptutor/review.py) 和 [review_api.py](../../../integration/discrete-math-tutor/review_api.py) 提供正式队列与 start/defer/finish/return，继续沿用，避免再做第二个正式复习页面/调度入口。

当前原生 start 会复制原题内容并生成新的 interaction ID。这可以表示一次新的**检索发生**，却不表示题面是新题，也不证明新情境迁移。后续需保留 source question / item family / retrieval episode 身份：同题间隔复习可以服务记忆调度，正式掌握或迁移评价则另按测量政策判断。不能仅凭新 ID 增加“独立新题数”。

当前 repetition_states 主要按目标 ID 保存；原稿要求每个独立 Review Item 有记忆状态。若同一 KC 有定义、辨析、综合应用多种检索任务，必须明确卡片粒度及其到目标/KC 的映射，不能悄悄用一个状态覆盖全部，也不能无审查为每条聊天生成卡片。

错题记录保留原答、真实评分、帮助暴露、题/标准/映射版本、证据与修订引用；错误可以不伴随误解诊断，误解也可能尚无适合复习题。不得把 incorrect、misconception、needs_review、FSRS Again 四者强行合成同一个状态。

## 3. 三类状态应保留各自权威

| 状态维度 | 当前权威与建议 | 容易混淆的地方 |
| --- | --- | --- |
| 请求/任务生命周期 | LearningTaskRepository、request 收据、revision、epoch、状态与过期校验 | 回答轮 completed 不代表整节完成；awaiting_clarification 可能是待答，也可能是待补指代 |
| 教学活动与学习位置 | TeachingTurn、Q5 路径、原生 interaction/session；分解释、辅助练习、独立评价、复习等 | explained / understood / learner override 与 assessed mastery 分开 |
| 后续教学动作 | 第三层在约束下产生；第六层给带来源的建议 | 不由新的第六层状态机再做一次最终策略选择 |

原稿新枚举可以作为查询层归一化语义，但不应直接替换所有存储状态；应先列出两个模式的状态与转换映射，明确每个命令由哪个已有服务提交。状态转换应在写入边界验证，不能只靠模型返回一个 next_action。

现有任务 TTL 与过期冲突是实际政策。原稿“超时后继续等待”不能实现为忽略过期、复活旧 revision。较长等待可保存历史/恢复位置，用户重新进入时建立当前授权任务并重核来源；已过期题目、旧答案或删除前 epoch 不自动恢复。内存取消令牌负责同进程即时中止，持久状态控制最终提交；两者都需保留。

原稿交互示例的最后一步“补救讲解后答对→新的独立证据”需要修正：如果刚看到答案、提示或同一示范，先记辅助成功，后续另行安排满足独立测量条件的任务。闭环可以继续推进，不必通过虚报独立性来完成。

## 4. 事件、评价与投影：沿既有事实链补修订

| 原稿职责 | 可沿用的数据 | 需要补的内容 |
| --- | --- | --- |
| 原始学习事件 | LearningEventRow、对话 ID、来源键与归属 | 区分发生/接收/应用顺序，绑定原作答与机会；既有历史不补造缺失来源 |
| 学习证据 | EvidenceRow、EventEvidenceRow | 逐标准/逐 KC 评价、评分资格、算法工件、修订/撤销与父评价引用 |
| 学生能力状态 | KnowledgeStateRow、ExerciseSkillObservationRow、原生 LearningProgress | 稳定 KC 身份、投影算法/政策版本、输入摘要、重建游标与旧状态兼容 |
| 误解与画像版本 | MisconceptionObservationRow、MemoryRevisionRow、MemoryChangeRow | 具体测量机会与字段级资格；区别自动阈值确认、人工确认、用户偏好确认 |
| 任务与复习 | LearningTask/TaskRequest、Q5 状态、原生 LearningStore 日志/interaction | 统一只读视图；保留各自领域事务，不复制成一套平行状态机 |
| 后台处理 | MemoryJobRow 的租约、令牌、来源 hash 与重试 | 仅处理可重建产物；迟到执行者不能回写已经失效的来源/epoch |

[commit_learning_turn](../../../integration/discrete-math-tutor/memory/memory_manager.py#L297) 已在同轮事务中关联事件、对话、证据、状态、修订与后台任务；[session_scope](../../../integration/discrete-math-tutor/database/database.py) 通过 ContextVar 复用外层会话。应扩展这条单一工作单元，而不是让多个新 Service 各自 commit，造成一半状态成功。

事件 ID 去重只解决重复投递，**不能单独防止同一 ID 不同内容、同一答案不同新 ID、同一题重做或同一评价重算重复计数**。任务收据已有 payload hash 冲突检查；新增评价/复习命令应保留同等语义，并保存原 attempt / episode 身份。投影应消费每条作答当前有效评价，评价修订不是新作答。

### xAPI 的参考边界

固定读取 [adlnet/xAPI-Spec @ ca782a1129bc6ae848640ff4e8e262334bdd0ba5](https://github.com/adlnet/xAPI-Spec/tree/ca782a1129bc6ae848640ff4e8e262334bdd0ba5)。[README](https://github.com/adlnet/xAPI-Spec/blob/ca782a1129bc6ae848640ff4e8e262334bdd0ba5/README.md) 明确本仓库为旧版 1.0.3，指向 IEEE 的 2.0 文档；本次 IEEE 入口返回 418，未核验 2.0 正文，所以不宣称遵循最新 xAPI 标准。

所查 [Data 文档 §2.3](https://github.com/adlnet/xAPI-Spec/blob/ca782a1129bc6ae848640ff4e8e262334bdd0ba5/xAPI-Data.md#231-statement-immutability) 的 Actor/Verb/Object、来源与发生时刻、通过新记录作废旧断言的做法可作建模参考。它的不可变性规则有明确例外，不能简化为“数据库任何列都不能改”。本项目只是借思想，不实现 LRS，也不把该规范的保留/作废政策覆盖到现有用户删除机制。

当前 LearningEvent 的生命周期、状态和部分 payload 会被补充，不能写成“现有事件全都不可变”。后续应冻结原始作答与评价工件的内容，过程状态可在受控服务下更新；重新评价/撤销追加修订，不覆盖旧结论。memory_epoch、来源删除与旧任务拒绝机制必须贯穿重建，防止被撤回的数据从快照/缓存再次变成有效画像。

## 5. 迁移与恢复：已有工具可复用，但不等于可切生产

[database.py](../../../integration/discrete-math-tutor/database/database.py) 当前采用 SQLAlchemy、SQLite 课程独立库及显式 COURSE_DATABASE_URL 检查。[conversation_session_migration.py](../../../integration/discrete-math-tutor/database/conversation_session_migration.py) 追加可空会话列与索引；[session_plan_migration.py](../../../integration/discrete-math-tutor/database/session_plan_migration.py) 提供显式增量迁移，不在普通读取里暗改旧库。

[SQLAlchemy 官方文档](https://docs.sqlalchemy.org/en/20/core/metadata.html) 区分 create_all 与 schema migration；本批实际探针确认 create_all 不会给已有表增加新列。因此“改完 Pydantic/ORM 然后启动就完成迁移”不可接受。[Alembic batch 文档](https://alembic.sqlalchemy.org/en/latest/batch.html) 说明需要重建表的 SQLite 变更可用复制/替换流程，并需处理约束。是否采用 Alembic 应由实际变更与项目迁移机制决定，不为一两个可空增量字段先搬整套基础设施。

[learning_migration.py](../../../integration/discrete-math-tutor/integrations/deeptutor/learning_migration.py) 已有只读 Q5 快照→原生候选的路径：验证范围、精确保留 ID/位置/来源；understood 不迁成 assessed mastery；来源 available=False 待宿主核验；候选收据保存摘要、未映射项与 activated=False。已有候选导入收据可拒绝改变快照后的覆盖，但这不是在线入口已经支持双写或可以立即切换的证明。

该候选工具不能直接当第六层全量迁移器：教材导航仍属 Q2；旧命令收据、辅助待答题、会话安排、画像、来源运行时授权等有各自未映射边界。新增 KC 与评价迁移应借只读快照、摘要、隔离候选、幂等收据和核验流程，不把缺少来源的 mastery 数字逆向伪造成历史作答。

宿主业务库与原生 LearningStore 是不同事务边界。先明确每条命令的权威存储；如果必须跨库，用已有请求/命令身份与业务收据核对、重试和对账，不假设同进程调用就是分布式事务。相同数据库内的后台投影任务可以与事件同事务入队，继续借 [memory_jobs.py](../../../integration/discrete-math-tutor/database/memory_jobs.py) 的租约与来源 hash，避免模型调用占着写锁。

切换前需验证：只读快照可复现、源/候选数量与身份一致、旧记录未知仍未知、历史引用不失效、撤销与重放一致、读取切换可回退。回退首先切读路径并停止新引擎排期，不删除新事件来“恢复旧状态”。

## 6. 评测应按对象拆开

原稿的 AUC、Brier、F1、前后测方向可以保留，但有以下限制：

| 对象 | 工程验收 | 数据评价 |
| --- | --- | --- |
| 输入动作与测量资格 | 自述、插问、辅助、过期与未提交不误判成独立失败/成功 | 各类 Precision/Recall/F1、弃权覆盖与误更新率 |
| KC 与分项评分 | 目标与被测 KC 分开，标准不全保持未知 | 逐 KC/标准准确性、漏检/误检、标注一致性 |
| 潜变量/后续作答预测 | 时间前缀、同题组与学生分组无泄漏 | 在明确答对概率目标上计算 Brier/log loss、校准与 AUC；不拿 UI 分数直接代替概率 |
| 误解与修订 | 冲突、反证、恢复、撤销可追溯 | 候选诊断 precision/误报、分项支持数；阈值状态不当作人工真值 |
| 任务与恢复 | 重复、乱序、取消、删除、并发与故障窗口确定 | 错误恢复次数、丢失/重复业务写入，统计单位为任务而非 token |
| 复习与学习效果 | 延期/查看无伪评分，过期来源不记遗忘 | 真实检索保持与负担、独立前后测及延迟测；完成率不是学习增益 |

项目的 [psychology_evidence_gate.json](../../../integration/discrete-math-tutor/tests/data/answer_flow/psychology_evidence_gate.json) 明示 8 个 controlled cases 是人工标注的工程验收，**不是教师金标准**；psychology.json 仅有 6 条场景。本批没有发现可直接声称为已校准心理学学习序列的数据资产。以前发布的测试包绑定旧代码版本，只宜在重新核验后用于教材/状态兼容，不自动变成第六层训练或教育效果评价数据；本轮 GitHub connector 未取得该 release 元数据，未重新下载或检查其内容。

公开 CoMTA/MathDial、Eedi 和 KT 数据仅用于对应数学/对话任务的研究对照；不同许可、竞赛使用条款、标注对象和时间切片必须分别检查。本轮不下载新数据，也不把公开数据拼成中文心理学金标准。先建设小范围、盲标与仲裁的课程数据，再决定是否拟合/校准；没有真实标注时保持暂定反馈，不以数据不足阻塞其他已可完成的工程改造。

## 7. 最终缺口与实施次序

前六批累计应进入实施计划的优先项：

1. formal_mastery 与路径放行、learning_stage 与独立性、画像字段来源的语义修正。
2. 心理学稳定 KC、任务/题目/标准映射与课程范围，禁止文本别名自动合并状态。
3. 评价修订与资格合同，保留原始表现，逐字段决定是否更新。
4. 长期投影、误解/反证、错题与复习沿既有事务和读取边界接通。
5. BKT/FSRS 离线/影子适配，来源、时间、参数、评分政策和输入可重建。
6. 故障、迁移、双模式端到端与人工课程评价；必要时另做 LangGraph 试验，研究深度 KT。

详细文件级工作包、依赖、验收、回退与发布边界见 [实施计划](../../plans/2026-11-01-layer6-implementation-plan.md)。

## 8. 本批证据与未完成的实验

`.runtime/layer6-research/round07/`（不入库）保存固定 xAPI README / Data 两份文档与 blob 校验清单。`probe.py` 使用实际本地迁移函数、隔离加载的候选构建/关系校验、合成数据和临时内存/文件 SQLite，**11 项具名探针通过**：create_all 不是列迁移；会话迁移可重复且不补造归属；session_plan 迁移前置/可空/幂等；嵌套工作单元复用及回滚；候选身份/位置/输入保留；理解自述不补掌握；来源待复核；不合法路径/游标拒绝；源库只读与课程过滤；缺表不当空历史。

首次探针因 SQLite 临时连接未显式关闭导致 Windows 清理失败，已修正隔离脚本并重跑。没有修改业务代码、正式库、上游源文件或访问模型 API。未启动真实原生服务、未重跑完整浏览器/多进程故障测试、未演练生产迁移；这些已列入实施验收，不以纯函数探针替代。

至此分批调研完成；结果是可实施的工程建议与未验证事项清单，不是已完成改造或已证明教学收益。本轮未提交、合并或推送。
