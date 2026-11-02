# 第四批：FSRS、LangGraph 与现有复习／恢复机制

日期：2026-11-01。项目基线：`main @ e5b3c004e8eca02cd124539355ef5fe40866ee4b`。本批读取原稿 **403—536 行**，区分讨论建议、固定源码事实、隔离验证和工程推论。只交付调研，不实施迁移。

## 结论

**FSRS 可通过项目已有 RetentionScheduler 边界做候选适配，但不是字段替换；LangGraph 可用于持久化编排，但不能替代当前任务授权、版本检查、业务事务和事件去重。** 首版不必为接入这两者重写 TeachingTurn、AgentLoop 或再建立一套长期画像库。

当前最有价值的复用粒度是 FSRS 的卡片状态转移、序列化和基于评分日志的重算，以及 LangGraph 的检查点和等待外部输入机制。最容易误用的地方是：把概念掌握当记忆提取率、把辅助回答映射为一次独立记忆评分、把旧 stability 直接搬进 FSRS、以为恢复会从中断那一行无副作用地继续。

## 1. 上游版本与原稿核验

| 对象 | 固定版本 | 许可与本批范围 |
| --- | --- | --- |
| [py-fsrs](https://github.com/open-spaced-repetition/py-fsrs/tree/9446cb06605c597a063aeee49f7d188d42e34dc2) | `9446cb06605c597a063aeee49f7d188d42e34dc2`；pyproject 声明 6.3.2 | MIT；读 scheduler、card、review_log、rating、state、README、安装元数据与 LICENSE |
| [LangGraph](https://github.com/langchain-ai/langgraph/tree/e5c961d7fbe7ca6fdd4c94c84d90511372514d55) | `e5c961d7fbe7ca6fdd4c94c84d90511372514d55` | MIT；读 types、重试执行器、SQLite checkpointer、中断测试与根 LICENSE |

原稿列出的 FSRS 四级评分、目标保持率、卡片/调度器序列化，以及 LangGraph 的 Checkpointer / Store 区分，都有对应实现。原稿粘连的 Python 示例不是可直接执行代码。原稿的图像代理链接、搜索摘要和二手说明不作为本批算法依据。

[官方 Persistence 文档](https://docs.langchain.com/oss/python/langgraph/persistence) 区分线程状态检查点与跨线程 Store；内存 saver 不具备跨进程重启持久性。本次旧 durable-execution 文档路径重定向到 persistence，故节点重跑等具体行为继续用固定源码交叉确认，不依赖旧网址标题。

## 2. 本项目已经具备什么

### 2.1 两条复习路径已存在，不是从零搭建

宿主副本 [scheduler.py](../../../integration/discrete-math-tutor/agents/deeptutor_learning/scheduler.py#L65) 定义 `RetentionScheduler` Protocol，包括初始状态、复习更新、retrievability、风险、队列和 replay。默认 `SpacedRepetitionScheduler` 的注释明确写明是按知识类型给冷启动先验的指数遗忘基线，**不是经拟合校准的 FSRS**。

原生模式使用 [vendor scheduler.py](../../../vendor/DeepTutor/deeptutor/learning/scheduler.py)，由 [worker.py](../../../integration/discrete-math-tutor/integrations/deeptutor/worker.py#L28) 加载仓库内固定 DeepTutor 副本；[原生 review.py](../../../integration/discrete-math-tutor/integrations/deeptutor/review.py#L7) 导入的是 `deeptutor.learning.scheduler`，不是宿主 `agents.deeptutor_learning`。本批逐行比较两份 scheduler，差别只有模型导入路径，算法一致。这说明后续适配必须检查两条调用链，不能只改宿主文件就认为原生模式已切换。

已有能力及其边界：

- [RepetitionState / LearningEvidence](../../../integration/discrete-math-tutor/agents/deeptutor_learning/models.py#L166) 已保存稳定性、难度、到期时间、复习锚点、连续结果、lapse 和事件时间等；quality 是根据评价推导的 0—1 强度，**不是 FSRS 的四级回忆评分**。
- scheduler 支持注入时钟、按输入事件重放、从旧状态 hydrate、改变保持率时重算到期日；同一会话内成功重复练习不连续放大 stability，也不推迟既定到期日，但仍会增加 review_count。因此算法保护不等于事件幂等。
- `schedule_review` 将迟到事件的实际应用时刻限制为不早于 last_review_at；`replay` 沿输入列表顺序应用，不自行按时间排序或去重。不能把它与 FSRS 的按时间排序重算默认为同一种语义。
- 调度器本体不会核验独立性和 verification，`_resolved_quality` 主要处理质量、提示与尝试次数；数据资格必须由调用方保证，不能仅因事件类型叫 review 就直接应用。显式 quality 存在时，该函数也不会再自动扣除提示/重试惩罚。
- 受管 [sync_schedule](../../../integration/discrete-math-tutor/integrations/deeptutor/review.py#L24) 从 reviewed_key / reviewed_rubric 事件重建，并回查题目来源与失效状态；证据无法确认时保留原排期，不当作遗忘。正式受管 scheduler 强制使用天，屏蔽秒级 `LEARNING_DEBUG`。
- 原生复习已有队列、显式 start/defer/return/finish、题目来源与修订校验；延期只是队列操作，不能伪造一次 review。原生测试已有延期恢复、重复命令、新题复习、失效来源等用例，本批没有把它们重新实现。

### 2.2 回合恢复已经有业务约束

[LocalAgentLoop.state](../../../integration/discrete-math-tutor/agents/agent_loop.py#L84) 保存消息、执行轮次与工具步数、来源、待答题、pending tool call ID、目标等；[恢复消息路径](../../../integration/discrete-math-tutor/agents/agent_loop.py#L223) 以精确 pending call ID 替换答案，并用本次宿主提示重新核验策略与授权。它不是全节点检查点，但也不能描述为“暂停后只能重来”。

[LearningTaskRepository](../../../integration/discrete-math-tutor/database/learning_tasks.py#L141) 已有学生/会话归属、request_id 与 payload hash 收据、revision、epoch、任务状态和超时检查；claim 默认 TTL 为 1800 秒。恢复需是当前版本的 awaiting_clarification，取消、过期和记忆删除会阻止旧结果继续提交。LangGraph 的等待能力不能自动改变这些业务期限。

[task_cancellation.py](../../../integration/discrete-math-tutor/agents/task_cancellation.py) 的即时取消信号在进程内；数据库状态才是跨进程权威。[commit_learning_turn](../../../integration/discrete-math-tutor/memory/memory_manager.py#L297) 沿用同轮来源键去重和业务写入链。这里需要检查的是任意节点执行途中崩溃的恢复粒度，而不是再造一套任务身份或最终策略选择入口。

## 3. FSRS 源码审计：能借什么，哪里必须适配

### 3.1 三个状态量与旧字段不兼容

固定版本 [scheduler.py](https://github.com/open-spaced-repetition/py-fsrs/blob/9446cb06605c597a063aeee49f7d188d42e34dc2/fsrs/scheduler.py#L187) 使用参数控制的幂函数：`R(t) = (1 + FACTOR × t / S) ^ DECAY`，其中 FACTOR 根据 0.9 构造。因而在该曲线下 t=S 时 R=0.9。项目当前是 `exp(-t/S)`，t=S 时约为 0.3679。**同一个数值的 S 在两边含义完全不同。**

FSRS difficulty 约束在 1—10 的尺度；项目基线根据质量和意外程度更新，并限制在 0.05—0.95。即使做线性换算，也不能宣称得到经过数据验证的 FSRS 参数。迁移应从合格历史评分重新计算，或新建带模型版本的冷启动状态；不能将原数据库字段直接复制进去继续算。

[Card](https://github.com/open-spaced-repetition/py-fsrs/blob/9446cb06605c597a063aeee49f7d188d42e34dc2/fsrs/card.py#L62) 还有 Learning / Review / Relearning、step、last_review、due；本地 RepetitionState 没有同义的一组状态机字段。卡片 ID 默认按当前毫秒生成，不能把这种进程内生成方式当作多进程事件主键方案。项目应显式分配稳定卡片身份并关联课程、KC/检索任务与版本。

“卡片”建议对应稳定的检索任务或题型，而非任意聊天、整章知识点或一次动态生成路径目标。概念识别、例子分类、自由解释、实验设计的回忆难度和证据类型不同，聚成一张卡的适用性仍需验证。FSRS retrievability 是模型估计的卡片回忆率，不能输出成“已真正理解该概念的概率”；第三批对 BKT 的结论也同样只是模型估计。

### 3.2 评分来源必须先有合同

[Rating 定义](https://github.com/open-spaced-repetition/py-fsrs/blob/9446cb06605c597a063aeee49f7d188d42e34dc2/fsrs/rating.py) 是 Again / Hard / Good / Easy，值为 1/2/3/4。README 将 Hard 描述为仍记得但很困难，Again 为忘记。它不是四档正确率，也不是四档自信。

因此不能直接使用 `round(quality × 3) + 1`，也不能把“用了提示后答对”都记 Hard：辅助回答并不证明此前能独立提取。“我懂了”、跳过、取消、尚无作答、来源失效不能记 Again；否则系统会把缺少测量误写成遗忘。应保留原始作答、评价方法、帮助暴露、回忆评分及其来源，评分政策要有版本；首个候选基线只消费满足明确规则的检索事件。

后续可对独立错误使用 Again、明确的独立成功使用一个保守固定成功档作为试验政策，但须标明它是项目代理映射，并与真实四级回忆评分区分、验证。没有足够的困难程度/回忆流畅性信息时不要自动生成 Hard/Easy。正式掌握门禁仍由项目独立判断。

### 3.3 时间、短期练习和重放

[review_card](https://github.com/open-spaced-repetition/py-fsrs/blob/9446cb06605c597a063aeee49f7d188d42e34dc2/fsrs/scheduler.py#L236) 要求显式评分时刻是 UTC aware datetime；项目 epoch 秒应转换为 `datetime.fromtimestamp(value, timezone.utc)`，界面可再显示北京时间。应显式传事件时钟，不让恢复时的当前时间改写历史。

该版本 `get_card_retrievability` 使用 timedelta.days，即完整经过天数；不足 24 小时的回忆率计算与项目连续秒数指数曲线不同。Learning/Relearning 又可以按分钟安排。不能把项目秒级测试开关直接套到 FSRS 或用短期到期日解释长期遗忘。尚无 last_review/stability 的新卡该接口返回 0，不能因此宣称学生回忆能力为零。

默认 learning steps 为 1 分钟、10 分钟，relearning 为 10 分钟；项目已有同会话不推迟长期到期日的保护，FSRS 短期状态机会产生不同动作。是否保留短期步骤、怎样与既有修复练习和队列并存，要显式选择和测量，不能同时让两个引擎各自改 due。

[reschedule_card](https://github.com/open-spaced-repetition/py-fsrs/blob/9446cb06605c597a063aeee49f7d188d42e34dc2/fsrs/scheduler.py#L519) 可按日志时间排序后重新计算，并检查 card_id，但不按业务 evidence_id 去重。相同时间日志仍需稳定的原始序号决定顺序。直接 review_card 也不拒绝早于 last_review 的评分，探针确认它能把锚点移回过去。

所以乱序事件不能未经策略直接进入实时更新：需选择保留原始发生时刻、按已提交事件序列重建，或拒绝过时事件等待重算。本项目基线沿追加顺序并钳制时间，迁移时应明确这项行为变化。

### 3.4 随机性、序列化和依赖

FSRS 默认 `enable_fuzzing=True`，会给复习间隔加入随机扰动。合成条件相同，仅将随机数固定为两种值，到期日就不同。影子对照及可重放基线建议先关闭 fuzzing；若未来使用，必须保存调度结果或有可复现的随机方案，不能恢复时重新随机一次并悄悄改变已发布到期日。

Card、ReviewLog、Scheduler 的 JSON 往返已用实际源码验证。[ReviewLog](https://github.com/open-spaced-repetition/py-fsrs/blob/9446cb06605c597a063aeee49f7d188d42e34dc2/fsrs/review_log.py) 本身不含项目的独立性、原文、授权、撤销修订和唯一业务事件键；序列化能力不等于日志已持久化到项目数据库。工件还需外层绑定算法/库版本、参数、配置、评分政策、卡片映射与输入事件身份。

[pyproject.toml](https://github.com/open-spaced-repetition/py-fsrs/blob/9446cb06605c597a063aeee49f7d188d42e34dc2/pyproject.toml) 声明基础运行只依赖 typing-extensions、Python >=3.10；torch/numpy/pandas 等在可选 optimizer 里。构造器主要核验参数数组，项目仍应沿用自己的有限值和目标保持率范围校验，不能假设上游替我们完成全部配置验证。可先借调度器，不引入拟合训练栈。默认参数是冷启动候选，不是经本项目学生验证的个体记忆模型；自动优化保持率也不是本轮必须建设的功能。

## 4. LangGraph：等待与恢复能解决到哪一步

### 4.1 固定源码确认的恢复语义

[types.interrupt](https://github.com/langchain-ai/langgraph/blob/e5c961d7fbe7ca6fdd4c94c84d90511372514d55/libs/langgraph/langgraph/types.py#L903) 明确解释：第一次抛出 GraphInterrupt，恢复时从节点开头重新执行；同节点多个 interrupt 的答案按调用顺序匹配。函数使用 scratchpad 的计数器和 resume 列表，不能在恢复时随意插入/重排中断。候选模型重新生成题目后再调用 interrupt，可能让旧回答被应用到新问题。

固定版本还提供可选 response_schema，但这种形状验证不代替业务题目身份、来源版本和学生归属检查。Graph state 宜保存已持久化题目的 ID/版本、当前等待类型和待恢复任务引用，恢复时回查当前来源与权限；不要在等待节点每次重跑时再随机出一题。

[重试执行器](https://github.com/langchain-ai/langgraph/blob/e5c961d7fbe7ca6fdd4c94c84d90511372514d55/libs/langgraph/langgraph/pregel/_retry.py#L614) 在重试前清理 task.writes 后重新调用节点。这只涉及框架缓冲写入，不会回滚节点已经提交到项目数据库或外部 API 的副作用。[SQLite saver](https://github.com/langchain-ai/langgraph/blob/e5c961d7fbe7ca6fdd4c94c84d90511372514d55/libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/__init__.py#L187) 使用自己的连接、锁和提交生命周期，不能据此认为它与当前 SQLAlchemy 业务事务天然原子。

[官方 Interrupts 文档](https://docs.langchain.com/oss/python/langgraph/interrupts#side-effects-called-before-interrupt-must-be-idempotent) 同样说明中断前操作会重跑，且副作用即使放到中断后或单独节点，也可能在提交成功、节点完成前失败时重复。本批按固定实现做静态核对，没有安装 LangGraph 或运行完整图，因此不报告跨进程恢复成功率。

### 4.2 对本项目的最小接入边界

如果后续确实需要更细粒度的进程崩溃恢复，可以让图调度现有“准备教学动作 → 等待精确题目回答 → 评价 → 提交投影”的阶段。TeachingTurn 继续管理教学语义，统一策略入口继续选择策略，宿主事务继续写正式数据。此流程是候选边界，不是本批新增 Graph 设计承诺。

Checkpointer 保存执行游标、待答标识和已完成步骤引用；长期学习事实继续在现有事件/证据/修订表。Store 仅在跨线程访问有真实需求时按现有仓储接入，不复制一整份画像作为另一事实源。图 state 中的快照只能作恢复输入，不能越过当前 epoch 和授权把已删除记忆重新写回。

thread_id、checkpoint_ns 和 interrupt ID 都是定位机制，不是权限凭证。需要把它们与学生、课程、会话/任务映射并在服务端核验；保留现有 revision、过期、取消和删除检查。跨工作进程同时恢复同一任务时，依赖业务版本竞争与收据处理，不能靠一个 saver 实例的进程内锁宣布已防并发。

### 4.3 必须覆盖的故障窗口

| 故障位置 | 恢复时应得到的行为 | 可以直接复用的基础 |
| --- | --- | --- |
| 业务提交前崩溃 | 未生效的命令可重试；仍先校验身份与版本 | 既有任务 guard、事务与请求身份 |
| 业务提交后、图检查点前崩溃 | 重跑读取原收据，返回同一业务结果，不再记一次评分/复习 | source_key / request_id / 原生命令去重；逐入口确认覆盖范围 |
| 已存执行计划，但业务结果尚未提交 | 回查真实业务状态后执行，不能把计划视作完成 | 状态机、事件与事务查询 |
| 等待期间取消、题目失效、记忆删除或 TTL 到期 | 旧检查点不能恢复提交；按原业务状态返回冲突/失效 | ownership、revision、epoch、来源复核 |
| 流式答案已发送后执行重试 | 客户端与事件日志识别已发布内容，不能重复叠加或错误宣告已提交 | 现有发布/收据链；未来故障注入验证 |

算法调用本身即使是纯函数，重复调用得到相同输出，也不代表“相同事件应用到已更新状态上”是幂等。两者必须分开验收。模型请求还可能发生“供应商已处理但响应丢失”，图框架无法独自消除重复调用成本；需根据具体调用入口保留结果引用和重试策略。

## 5. 建议的验证与迁移次序

1. 先定义一份合格检索事件合同：稳定卡片/课程/KC/任务与版本、发生时刻、提交顺序、原始表现、帮助暴露、评分与政策版本、核验方法及业务去重身份。保留无资格事件与原因，不把它们编成失败评分。
2. 通过 RetentionScheduler 候选适配影子运行：显式 UTC、固定参数和关闭 fuzzing；原引擎继续负责已发布排期。比较长期 due、短期练习、lapse、回忆率及复习负担；先查行为差异，再评估留出数据上的预测校准，不预报学习增益。
3. 旧状态不原地换字段；有合格历史才重算，缺历史按新版本冷启动并保留已有到期安排的迁移政策。评分撤销、题目版本变化、延期、改目标保持率和同日事件均需覆盖。
4. 先确认图编排带来的具体新增恢复需求，再做最小 LangGraph 试验。用临时业务库和持久 saver 做进程终止/重启，分别注入上述故障窗口，核对事件、评分、修订与已发布题目是否只生效一次。
5. 同时验证宿主与原生 DeepTutor 两条模式；保留队列解释、来源失效保护与显式复习操作。不能因换引擎自动改学习模式、移动主路径或授予正式掌握。

## 6. 本批验证与剩余限制

缓存 `.runtime/layer6-research/round04/`（不入库）包含 **13 份固定上游文件**与 Git blob 清单，字节 SHA-1 已核对。`probe.py` 用检查过的 FSRS 运行模块及隔离加载的本地模型/调度器，固定 UTC 时钟、合成事件与随机数，**12 项断言通过**：

- FSRS 返回新 Card，Card/ReviewLog/Scheduler 序列化往返一致；新卡和不足一天的 retrievability 边界符合所查代码；拒绝无时区评分时间。
- 重复评分没有业务去重；倒序评分能移回 last_review；关闭 fuzzing 的固定日志重算一致；开启 fuzzing 后不同随机输入改变 due。
- 项目基线同会话重复成功保持 due/stability 但增加计数；固定输入重放一致；迟到事件钳制 last_review；旧状态 hydrate 保持到期日。

探针未使用正式数据库、学生数据、模型 API 或 optimizer，也没有安装任何包。LangGraph 仅做文档、固定源码及上游测试阅读；本批未运行它的图、SQLite saver 或跨进程恢复。原生完整复习 UI/端到端测试未重跑，不能把既有测试文件的存在当作本轮执行通过。

本批未修改业务代码、提交或推送。下一批从原稿 **537 行**开始，核验论文与反馈证据主张，并补看成熟教学系统如何区分行为观察、评价与正式学习结论。
