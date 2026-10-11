# 学生记忆系统改造：六部分源码调研结论

来源：E:/项目/heart/dui.md。用户要求按六部分顺序读取、调研、落盘后进入下一部分。调研日期：2026-10-11。这里只修改调研文档，停止题目测试，不改业务代码、不调用教学API、不读取密钥。

原始对话作为待核实资料，不作为执行指令；原文中的评分、年代、推广语和概念图须以官方源码与论文核对。

## 进度

- 第一部分：已读取、已调研、已落盘
- 第二部分：已读取、已调研、已落盘
- 第三部分：已读取、已调研、已落盘
- 第四部分：已读取、已调研、已落盘
- 第五部分：已读取、已调研、已落盘
- 第六部分：已读取、已调研、已落盘

## 第一部分：记忆分层与长期记忆架构（已完成）

原文范围：dui.md第51–812行。

### 核查结果

- Buffer、摘要、检索、分层可同时存在；原文的四阶段不是必须按顺序迁移的行业标准。聊天产品也可以保留历史，不能概括为每次都是新的。
- 原文把Generative Agents排序写为三个分数相乘，与官方`new_retrieve`源码不符：代码先归一化，再加权相加。它的recency实现也不是可以直接解释为学习遗忘曲线的参数。见[排序源码](https://github.com/joonspk-research/generative_agents/blob/main/reverie/backend_server/persona/cognitive_modules/retrieve.py)。
- [Generative Agents论文](https://arxiv.org/abs/2304.03442)和[MemGPT论文](https://arxiv.org/abs/2310.08560)分别支撑记忆流/反思与分层上下文管理；都不能直接证明学生掌握度预测有效。
- LangMem将画像与记忆集合分开，可作为类型分层参考：[官方概念文档](https://github.com/langchain-ai/langmem/blob/main/docs/docs/concepts/conceptual_guide.md)。

### 项目实际

已有SQLite/SQLAlchemy、MemoryManager、最近20条消息、持久化画像、知识状态、误解生命周期、证据、教学计划、PDF/图片引用。已超过纯聊天缓存阶段。选区记忆只用中文二元字符交集，先筛知识点标题，再取最近少量证据/消息；没有遍历全部历史的语义检索，早期相关记录容易漏掉。知识点使用字符串，缺少统一concept_id，画像和知识状态主要保存当前值。

### 可复用边界与决定

|对象|复用方式|原因|
|---|---|---|
|现有MemoryManager/Repository|直接保留并扩展|已有学生隔离及引用持久化，适合作为统一入口|
|Generative Agents retrieve.py|借鉴排序思路，重写小模块|依赖persona、模拟场景与原embedding函数，不是可直接嵌入的教学组件；仓库Apache-2.0|
|MemGPT|借鉴核心上下文/历史检索分层|运行时整体替换成本高，不应让模型直接改学生掌握度|
|LangMem|后续核对核心抽取API，暂不引入框架|MIT；需适配现有LLMClient和持久化，不能因为分层概念就迁移整个Agent运行时|

第一阶段结论：采用“结构化当前状态直接读取＋可追溯学习事件检索＋有预算的上下文组装”。教材证据与学生记忆各自分区，记忆负责个性化，不作为数学定理依据。暂不新增图数据库、Redis或新模型。许可证见[Generative Agents LICENSE](https://github.com/joonspk-research/generative_agents/blob/main/LICENSE)、[LangMem LICENSE](https://github.com/langchain-ai/langmem/blob/main/LICENSE)。

## 第二部分：Student Model与Knowledge Tracing（已完成）

原文范围：第813–1754行。

### 必须修正的理解

Student Model是记忆系统中的状态估计层，不等于全部记忆。DKT预测答题表现；其输出不能无校准地解释为真实掌握度。DKVMN的key/value是学习的矩阵表示，不是“概念名称→一个概率”的SQL字典。用户说不会、问过问题、读完教材，与独立作答正确是不同证据。原文引用的2026年层级记忆论文页面本次无法读取，未核实其完整方法或源码，不把它作为实施依据。

### 实际源码与可复用性

- [pyBKT Model.py](https://github.com/CAHLR/pyBKT/blob/master/source-py/pyBKT/models/Model.py)提供fit/predict等API，输入需要学生、技能、正确性、顺序信息；区分correct_predictions与state_predictions。适合作为后续独立评估的BKT基线，可复用库；MIT，Windows依赖及编译路径仍需届时验证。
- [pyKT DKT源码](https://github.com/pykt-team/pykt-toolkit/blob/main/pykt/models/dkt.py)和[DKVMN源码](https://github.com/pykt-team/pykt-toolkit/blob/main/pykt/models/dkvmn.py)是PyTorch训练模型，MIT，可复用训练/离线比较代码；没有本教材的已校准权重，不能直接当学生记忆服务。论文：[DKT](https://arxiv.org/abs/1506.05908)、[DKVMN](https://arxiv.org/abs/1611.08108)。

### 项目差距（静态代码确认，未运行测试）

1. StudentState.blend_numeric使用EMA融合LLM评分，不是BKT/DKT；0.5是工程默认值，不能呈现为已测得的学生掌握概率。
2. Orchestrator先用EvidenceExtractor写证据/误解，后用StateUpdater再写一批；没有source_event_id或独立观测去重，存在同轮重复计数的风险。
3. Misconception._apply_thresholds允许单条confidence>=0.8直接confirmed，三条记录也可confirmed，未验证是否来自独立作答。resolved/dismissed又直接返回，后续错误复发不自动重开。
4. 普通提问会恢复总体mastery并阻止步骤推进，但steps_mastery、误解解决等更新并未统一按事件资格过滤。仅靠提示词不足以构成确定性证据规则。

### 改造决定

先实现EvidencePolicy：显式区分self_report、question、reading、hinted_answer、independent_answer、rule_verified、ai_provisional、teacher_reviewed。只有符合资格的独立证据可影响能力状态；同一作答一个事件，同一知识点/评分项一个幂等更新。保存source_id、原文片段、attempt_id、hint_level和判分来源。未知状态显式unknown。误解按支持证据与反证维护，可resolved→reopened。后续有足够本地序列数据再比较BKT与当前规则；不因电脑有GPU就立即训练DKT。

## 第三部分：Mem0、Letta、Graphiti接入判断（已完成）

原文范围：第1755–2868行。

### 原文需要更新

官方仓库应使用mem0ai/mem0、letta-ai/letta及其当前实现letta-ai/letta-code、getzep/graphiti。原文链接的Learn2Solve/memgpt、Memory-Agents/graphiti不作为官方实现依据。星级表和“最工程化”没有统一评估条件，不采纳为选型证据。“我理解了”只能记录自述，不能直接写mastered。

本次查阅main分支，未固定发行版；源码会变，正式接入前需锁定commit及依赖版本。

### 源码核查

|项目|已核查入口|可复用范围|本项目取舍|
|---|---|---|---|
|Mem0|[mem0/memory/main.py](https://github.com/mem0ai/mem0/blob/main/mem0/memory/main.py)：add、search、session过滤、批量写入/历史|可通过SDK适配画像事实抽取、受学生范围约束的记忆搜索；不是拷贝几个函数即可运行|暂不设为默认记忆后端，保留provider接口|
|Letta|[官方仓库README](https://github.com/letta-ai/letta)指向当前letta-code；[memory blocks文档](https://docs.letta.com/v1-sdk/memory/memory-blocks)|核心块＋按需历史检索思路；本次旧Python block路径读取失败，不声称已核查该文件|保留现有编排器，后续查当前代码，不整套替换|
|Graphiti|[graphiti_core/edges.py](https://github.com/getzep/graphiti/blob/main/graphiti_core/edges.py)：episodes、valid_at/invalid_at、created_at/expired_at、group_id|时间化事实和来源链设计；完整库需图存储和LLM适配|先在SQL实现有效区间与事件关系，暂不部署图服务|

[Mem0当前README](https://github.com/mem0ai/mem0)明确托管平台指标包含非开源优化，并描述ADD-only抽取；原文的“自动UPDATE替换旧记忆”不能当所有当前版本的事实。实际main.py也出现V3批量流程和ADD历史。因此须分开讨论原算法、当前SDK与托管服务，不能用托管分数承诺本地效果。[Graphiti官方依赖](https://github.com/getzep/graphiti#installation)包含图数据库与LLM，不是免费增加一张图表即可接入。三者仓库公开许可证均为Apache-2.0；仍应按实际复用版本保留声明。

### 项目决定

一个学生的历史事件可以追加保留，当前状态则有明确来源和有效期；“曾经不会”与“现在已纠正”不是应被语义去重吞掉的重复。教师回复与学生原始证据分别标注role，不能把AI说学生已经会了变成学生事实。画像、误解、知识状态仍由业务规则管理。统一MemoryManager入口比同时拼装三套记忆后端更适合当前FastAPI/SQLite架构。

## 第四部分：反思与教学策略记忆（已完成）

原文范围：第2869–3712行。

### 源码复用判断

- [Voyager SkillManager](https://github.com/MineDojo/Voyager/blob/main/voyager/agents/skill.py)保存可执行程序及描述，用Chroma召回技能；依赖Minecraft控制原语和旧LangChain调用。MIT。对本项目借鉴“描述检索＋经过验证的策略卡”，不直接执行其技能代码。[论文](https://arxiv.org/abs/2305.16291)不是教育效果研究。
- [Reflexion agents.py](https://github.com/noahshinn/reflexion/blob/main/hotpotqa_runs/agents.py)把失败试验反思带入后续尝试，示例有答案key和exact-match反馈。MIT。可借鉴评估→反思→下一次使用的流程；它不是通用学生长时记忆服务，也不能保证自我反思的结论正确。[论文](https://arxiv.org/abs/2303.11366)。
- [Generative Agents reflect.py](https://github.com/joonspk-research/generative_agents/blob/main/reverie/backend_server/persona/cognitive_modules/reflect.py)可参考反思触发与来源关系，不应从模拟人的经验直接推出学生认知根因。

### 项目实际与问题

已有teaching_policy.py、strategy_router.py和teaching_strategies.json；画像中的teaching_effectiveness已被策略选择消费，不必再新建一套完全重复的教师Agent。当前effectiveness为学生级策略EMA；Orchestrator将步骤推进或mastery增加0.08作为成功，其他情况记false。普通提问/直接讲解没有独立测量，却可能把策略当失败，混淆“尚未评估”和“教学无效”。它也缺知识点、难度、提示程度、样本数等条件。recent_moves只在进程内保存，重启后丢失。

### 改造决定

先新增StrategyObservation，记录student_id、concept_id、策略版本、event_id、before/after、outcome={success,failure,unknown}、反馈来源、hint_level。无独立验证时记unknown，不更新成败统计。成功次数/有效观察次数只能作为条件化观测，不宣称因果成功率；学生主观满意度单独记录。

反思结果保存为带supporting_event_ids和expires_at的假设/建议，模型不能把“问过三次”写成已确诊的能力缺陷。用户当前请求优先，历史偏好允许被覆盖。教学策略卡必须经审阅和版本管理后成为可选候选；保持现有规则预筛＋受限选择。跨学生共享只使用审核的通用教学模板或合规汇总，个人学习记录继续隔离。后台反思晚于可靠事件落库，不阻塞每个提问，也不自动改系统提示词。

## 第五部分：事件、事务、检索与遗忘设计（已完成）

原文范围：第3713–4964行。

### 取舍

“关系天然是图”并不意味着必须Neo4j；concept_relation邻接表即可表达前置关系。“你好”可以留在原始聊天记录，但不必抽成长期事实；原始事件与提炼记忆的保留策略应区分。向量索引是派生检索结构，不是真实状态的权威库。先保持单进程内的模块服务，不为MemoryManager新增HTTP微服务。

### 开源机制核查

[LangMem extraction.py](https://github.com/langchain-ai/langmem/blob/main/src/langmem/knowledge/extraction.py)使用Pydantic schema、trustcall提取/修订和受控步数；[reflection.py](https://github.com/langchain-ai/langmem/blob/main/src/langmem/reflection.py)提供后台处理实现。可借鉴受约束提取与后台合并；实际代码依赖LangChain消息/模型与LangGraph接口，现有LLMClient不能无适配直接传入。MIT；有SDK复用可能，第一版选择自建小型适配层，避免迁移整个教学运行时。

### 项目已确认的工程缺口

- Repository方法各自开启session_scope，不是一个教学回合共享事务。先写的证据/误解在后续质量拒绝或模型错误时已存在，缺乏明确有效性标记。
- MemoryManager快照只在内存里保存StudentState；rollback只写knowledge_states，不恢复证据、误解、计划、画像。当前Orchestrator回滚后又在结尾保存update.state，可能覆盖回滚值，不能当完整恢复保障。
- 误解解决接口在未指定type时解决该知识点全部误解；需要逐误解关联反证。选区检索只排除resolved，dismissed仍可能进入讲解。
- 练习已有submission/request_id幂等和规则/AI判分区分，且已写exercise_submission证据；并非完全未接入记忆。但提交完成与证据写入分两个事务，缺统一event_id、概念级状态投影和原子更新。证据文本12,000字符截断及检索再截350字符可能丢失评分项含义。

### 建议数据设计（草案，不是已实施）

|数据|核心字段/约束|
|---|---|
|concept与concept_alias|course_id、concept_id、名字、章节、教材版本；现有字符串映射不强行合并模糊同名项|
|learning_event|student_id、course_id、session_id、event_id、event_type、occurred_at、recorded_at、conversation_id/submission_id、selection_ref、request_id、schema_version；去重键含来源|
|event_concept|event_id、concept_id、part_id、rubric_id，多概念映射允许一题多个技能|
|learning_evidence|event_id、quote、evidence_type、source_role、verdict、verification_status、independent、hint_level、extractor_version；唯一键约束独立计数|
|state_revision|student_id、concept_id、before/after、source_event_ids、revision、policy_version、valid_from/valid_to；当前state是可重建投影|
|memory_item|类型、摘要、支持event_ids、status、valid_from/to、confidence_kind、expires_at、embedding_version|
|strategy_observation|学生/概念/策略版本、事件、outcome三态、评估来源、难度、提示级别|
|memory_job|job_id、event_id、状态、重试、幂等键；后台摘要/embedding失败可重放|

用户信心、模型置信分和判分可信度必须分别存，不能复用一个confidence字段。普通图片选区提问保留引用事件，不更新能力。

### 写入与读取流程

写入：可靠原始事件先落库→受schema约束抽取候选→EvidencePolicy校验来源/资格/去重→在事务内追加证据和状态版本→后台索引与反思。原始用户事件可保留，错误AI推断需标invalid，而不是删掉用户确实说过的话。LLM调用放事务之外；提交时核对revision，避免并发覆盖。SQLite采用串行短写事务；多用户规模达到实际瓶颈时再迁移PostgreSQL。

读取：学生及课程范围硬过滤→按concept_id/PDF选区/题号直接取当前状态→长期事件FTS5与dense并行召回→融合→按类型/有效性/来源/时间排序→去重及token预算→ContextBuilder分区输出。学生长期搜索必须查询归档记录，而不是先截最近20条。前置概念扩展用已审核关系，不能根据提问猜能力根因。现有BGE embedding及reranker可按负载复用，但是否启用记忆rerank由后续收益/延迟测量决定。

遗忘：分清“降低检索优先级”“摘要归档”“用户删除”“能力不确定性增长”。不同类型用不同规则，短期情绪可过期，明确偏好直到被更正，学习历史可按日期检索；不机械衰减所有掌握度。删除传播到源记录、引用、派生摘要、向量/FTS索引、缓存与后台任务，防止重建复活。

### 后续验收设计（本轮不执行）

借鉴[LongMemEval论文](https://arxiv.org/abs/2410.10813)及[作者代码](https://github.com/xiaowu0162/LongMemEval)的信息提取、跨会话、时间、更新和缺信息拒答维度，新增教学证据资格/独立计数/复发/回滚等项目专属项。通用聊天记忆分数不能替代本教材的教学正确性。

## 第六部分：源码复用清单与实施边界（已完成）

原文范围：第4965行至文件末尾。原文虽称源码级分析，主要给出伪代码和概念，缺少函数路径、依赖/版本、验证条件，不能直接据此集成。

### 当前源码的具体判断

|实现|已核查文件与机制|复用结论|需补的本项目逻辑|
|---|---|---|---|
|Mem0|memory/main.py的add/search；[memory/storage.py](https://github.com/mem0ai/mem0/blob/main/mem0/memory/storage.py)的SQLite历史、role和批量事务|SDK可适配；本轮不安装。抽取/检索逻辑不能脱离其LLM、embedding、vector provider直接复制运行|学生范围、原文来源、事件幂等、教学证据资格、状态事务；通用facts不作为掌握度权威|
|Letta当前实现|[memory-runtime.ts](https://github.com/letta-ai/letta-code/blob/main/src/agent/memory-runtime.ts)、[memory-format.ts](https://github.com/letta-ai/letta-code/blob/main/src/agent/memory-format.ts)、[memory-constraints.ts](https://github.com/letta-ai/letta-code/blob/main/src/agent/memory-constraints.ts)|当前为TypeScript/Node、MemFS文件/版本与上下文约束；借鉴预算、只读核心事实、版本化，不能当旧PythonMemoryBlock文件直接接入|本项目用SQL投影＋ContextBuilder实现核心块，不把所有学生数据改存Git|
|Graphiti|[graphiti.py](https://github.com/getzep/graphiti/blob/main/graphiti_core/graphiti.py)的add_episode与实体/边提取；[search/search.py](https://github.com/getzep/graphiti/blob/main/graphiti_core/search/search.py)的BM25/cosine/BFS及RRF/重排|完整SDK后期可选；当前借鉴episodes来源、时间边、检索组合|课程概念映射、学生隔离、已审核前置关系、事实有效性；group_ids为空会退为无范围，业务适配必须拒绝空学生范围|
|LangMem|knowledge/extraction.py核心manager；reflection.py后台执行|抽取SDK可做小型候选实验；暂不作为默认依赖|LLMClient适配、schema校验、持久任务/重试和候选审核|
|pyBKT / pyKT|Model.py与dkt.py/dkvmn.py|前者可做CPU离线KT基线，后者可复用训练与比较代码|题目技能映射、真实独立作答序列、参数校准、本课程评价|
|Voyager / Reflexion / Generative Agents|技能库、反思与排序模块，见第四/第一部分|主要复用思路，不复制模拟/游戏/问答运行时|审核教学策略卡、真实反馈、来源链和失败隔离|

[Mem0论文（2025）](https://arxiv.org/abs/2504.19413)与[Zep论文（2025）](https://arxiv.org/abs/2501.13956)可作为架构研究来源，不据其报告数字推算当前本机效果。2025论文、2026主分支和托管服务必须分开标注。Letta Code源码许可为Apache-2.0，品牌资产有额外排除条款，复用代码时不搬品牌素材。

## 六部分综合结论：建议的记忆系统改造路线

### 优先实施顺序

|优先级|工作|完成标准（计划，尚未执行）|
|---|---|---|
|P0|统一事件ID与EvidencePolicy|同一作答重试不重复计数；读教材/提问/听讲不提升能力；unknown不记失败|
|P0|修复回滚与状态事务|证据、误解、状态版本在一致事务内提交；无效推断可撤销并重建投影；不会被结尾保存覆盖|
|P1|concept_id及旧字符串映射|支持章节/选区/练习的多知识点映射，模糊映射保留unmapped|
|P1|统一检索与ContextBuilder|普通聊天、圈选提问、练习讲解调用相同MemoryContext；能检索超过20条以前的相关事件，隔离学生/课程|
|P1|偏好与误解的时间更新|明确偏好可更正；被纠正误解不再当当前事实；复发可重开且有独立来源|
|P2|后台摘要/反思与策略观察|结果有来源、时间、版本；任务可重放；没有测量的讲解不计教学失败|
|P2|用户记忆查看/更正/删除|源记录与派生索引同步处理；删除不被后台重建复活|
|后续|BKT、外部框架、图数据库对比|有本地数据与具体收益证据后才切换；不以模型更大作为升级依据|

### 建议模块边界

```text
FastAPI：聊天 / PDF选区 / 练习
  → MemoryManager（沿用统一入口）
      → EventRecorder → EvidencePolicy → StateProjector
      → MemoryRetriever → ContextBuilder
      → Consolidator / StrategyObservation（后台任务）
      → Repository（SQLite + SQLAlchemy）
          原始事件 / 证据 / 状态版本 / 画像 / 策略观察
          FTS5 + embedding派生索引 / concept_relation
```

教材RAG保持独立。当前提问与教材选区先确定讲解目标，MemoryContext只补充学习历史/偏好/已验证误解；不能让历史诊断抢占用户当前问题或覆盖数学证据。已有PDFSelection含document_id/version/rects，应作为学习事件定位，不反复存重复图片。

### 建议内部接口

```python
record_event(student_id, course_id, event_type, source_ref, request_id)
propose_evidence(event_id, observations)
apply_evidence(event_id, expected_revision)
retrieve_context(student_id, course_id, concept_ids, selection_ref, query, budget)
correct_memory(student_id, memory_id, replacement, source_event_id)
invalidate_derivation(student_id, derivation_id, reason)
```

返回的MemoryContext应包括profile、current_states、active_misconceptions、related_events、strategy_observations、provenance和coverage。只有实际取到来源时才说“你之前…”，没有记录时说明未知。profile显式用户设置优先于推断，短期情绪不当长期身份。现有state/confidence保留兼容，逐步引入unknown与可信来源，不给历史数据补造证据ID。

### 迁移方式

新增schema/migration和接口，先保留旧读取路径；历史对话与练习引用按现有ID回填来源，无法还原来源的旧证据标legacy_unverified。状态默认0.5不冒充历史测量。新投影先并行保存并与旧值可比，切换三种入口后再停旧写入；回退开关保留旧流程。迁移前快照备份，迁移不调用LLM重算全体学生状态。

### 后续验收与范围

本轮用户要求停止测试，故未运行题目/API/回归，不安装库，不改数据库或业务代码。静态发现的风险需实现阶段再构造可复现用例。验收重点：跨会话旧记录召回、同轮幂等、提示影响、自述与独立作答区分、误解纠正/复发、最新偏好覆盖、错误AI记忆撤销、并发版本控制、学生隔离、删除派生索引、选区定位版本，以及无记录时不编造历史。性能应记录检索/抽取/反思各段延迟及context token，阈值先建立本地基线，不能承诺框架宣传数字。

下一步具体工作：先写Memory v1事件与证据规则设计，随后实现P0事件去重和一致提交，再接统一记忆检索。


## 项目源码定位索引

以下为本轮静态核查位置；文档提出的是改造建议，业务实现尚未变更。

- [memory/memory_manager.py:22](E:/项目/heart/project/integration/discrete-math-tutor/memory/memory_manager.py:22)
- [memory/selection_memory.py:8](E:/项目/heart/project/integration/discrete-math-tutor/memory/selection_memory.py:8)
- [database/repository.py:313](E:/项目/heart/project/integration/discrete-math-tutor/database/repository.py:313)
- [models/misconception.py:70](E:/项目/heart/project/integration/discrete-math-tutor/models/misconception.py:70)
- [models/student_state.py:75](E:/项目/heart/project/integration/discrete-math-tutor/models/student_state.py:75)
- [orchestrator.py:254](E:/项目/heart/project/integration/discrete-math-tutor/orchestrator.py:254)
- [orchestrator.py:419](E:/项目/heart/project/integration/discrete-math-tutor/orchestrator.py:419)
- [practice_api.py:187](E:/项目/heart/project/integration/discrete-math-tutor/practice_api.py:187)
- [models/learner_profile.py:21](E:/项目/heart/project/integration/discrete-math-tutor/models/learner_profile.py:21)
- [agents/pdf_selection_tutor.py:19](E:/项目/heart/project/integration/discrete-math-tutor/agents/pdf_selection_tutor.py:19)
