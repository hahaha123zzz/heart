# LightRAG 跨章覆盖与关系上下文交付报告

日期：2026-10-21。范围：独立后端与检索工具专项；正式答案、Q3/Q5完整回合、页面及正式切换未验收。

## 结论

原跨章问题已通过分对象检索→逐对象Q2选择→语义核查→均衡合并，真实工具最终同时返回第一章实验程序和第二章自变量控制的有效原文。仍缺的一方只做一次补查并明确partial；不硬塞同章片段。本轮没有重建、迁移或覆盖已封存候选，没有切换正式服务/数据库/索引，没有修改staging/ready=false。

本轮分支codex/lightrag-integration，worktree `E:\项目\heart-worktrees\lightrag-integration`；开始HEAD `d3d6a76b3677a6e7898dde8fb66cb6c2ecdd64e1`，本轮实现提交 `2b79ddc434824510a6d296d5f6201bc3858b3e81`。本轮开始主工作树观察到78fb20f，交付前观察到 `a3b653e3ba968242755c01781117d13203ca964c`；均只读，不将其当已经批准的集成基线。隔离宿主始终固定已提交 `a2be38741c2c08162efd2335e7249db3353f9812` 以保留原失败对照，未复制主工作区其余未提交改动。已读取用户指定5项文档；主工作区研究输入仅登记实际哈希在运行目录research-input-hashes.json，未整份复制。

候选仍为应用 `.runtime/lightrag-proxy-nothinking/0a6096dc43a8829d48776cbcd0c583b6dc779bd6b450614b4bd20bd1d7f0e5ce`，Q2冻结交付95b956a、325文件、11章。最终交付锁核验通过，锁SHA256仍 `9453b0d7c11d8447464f92f59052286de9e78a498e1a12f6b0aa0a473581aa89`，全书7138实体/14741关系/1239块及对应向量的封存文件未变。SDK固定1.5.7、模型/512维embedding/生成策略/许可证沿用交付锁和全书报告。

## 1. 原题证据丢失的实证

原用户问题：**第一章的实验程序和第二章的自变量控制有哪些联系？**

旧工具实际改写查询 `第一章 实验程序 第二章 自变量控制 联系` 已逐字保留并复现。以下使用这条相同工具查询，不能与直接以整句问题检索的轨迹混为一次。

|阶段|旧检索（第一章数/总数）|LightRAG（第一章数/总数）|
|---|---:|---:|
|原生候选/召回块|7/40|1/11|
|原文映射|limit前是原索引节点；limit后映射0/18|4/34|
|重排与0.15阈值之后|7/39|1/13|
|全局limit=8之后|0/8|0/8|
|Q2选择及工具输出|0/8，全为第二章|0/3，全为第二章|

旧检索7条第一章候选都超过阈值，分数约0.227～0.988；第一章不是被阈值全部排除，而是被全局Top-8挤掉。LightRAG原文映射有4条第一章，阈值保留1条（block77，约0.172），随后也在limit处被排除；其余3条分数约0.0018～0.0071。Q2拿到的8条已没有第一章，后续选择再缩减为3条第二章。原始ID/得分/排除原因见下方两个attempt。

尤其不能直接把LightRAG第一章block77保留下来算覆盖：它讨论的是教材结构优缺点，并没有给出实验程序的定义或步骤。已逐条查看相关原文；新方案真正取得的是实验程序的定义、步骤和实施内容，不能用章节配额代替语义。

- 旧检索精确重现：`01560729-ed08-4004-b14f-45117882d5b5`。
- LightRAG精确重现：`cf098ab8-170b-4381-875c-9d155b895ed6`。
- 另一次直接以完整用户句子查询，LightRAG原生12块没有第一章，31条映射原文→7条重排结果→Q2选2条第二章：`21700170-c50c-4cf1-90df-cfa10a6b9d5e`。这证明查询措辞/原生返回也会影响覆盖，不存在“所有失败唯一由Q2导致”的结论。

所有阶段现在记录块ID、SDK chunk ID、document/version、章、原文范围、子问题、分数、接受/排除原因。Q2不返回选择理由时仅标not_selected_by_q2/reason_not_returned，不替模型编造原因。初期失败路径未完整保存native Metrics的记录保持未知，后续已在异常上附可得审计，保留原异常类型。

## 2. 上游复用与本项目适配

固定上游D:/deeptutor SHA `6cf793bd868ba5ecbe64722936d4be8fab5a01df`，三个文件均与该提交逐字节核对一致；Apache-2.0，许可证保留在project/vendor/DeepTutor/LICENSE。

|上游|实际采用|
|---|---|
|book/agents/source_explorer.py|`_balanced_slice`函数原样摘取，AST完全一致；以子问题/章替代source/kb分组，组内使用子问题重排顺序，保留query-major公平调度思路。原48次/并发6未迁入。|
|services/rag/smart_retriever.py|采用显式query_hints/多查询调度的设计，保留精确SourceRef；不复制会丢来源的聚合输出，不额外生成内部答案。该文件是参考适配，不能冒称整类直接迁入。|
|book/engine.py::_source_quality_summary|适配required/covered/missing/warning覆盖报告；范围和语义由项目验证，不复制BookInputs/BookEngine或写书流程。|

实际文件与摘取文件哈希、许可和修改记录在knowledge/lightrag/UPSTREAM.json。SDK仍使用aquery_data；未引入BookEngine、deep_research、DeepTutorApp、第二套AgentLoop或引用协议。

## 3. 实现与边界

新增CoverageNavigator：显式跨章/比较拆必要对象，每对象首次1查，只有缺口最多补1查；最多3对象/6次后端调用，同候选并发1。每次按该对象查询及明确范围重排，再交现有Q2选择精确证据；独立语义核查允许空结果，检查的是实际引句是否直接支持对象，章节/提词不算覆盖。均衡合并后按document/version/原文范围去重，保留一个来源承担多个对象的关联。充分即停止，仍不足返回partial和具体缺口。单点不加规划/语义核查模型调用，只检索一次并沿用Q2选择。

为大候选量增加了失败回归：首次适配曾将总候选数传给上游limit，触发其“不需裁剪”分支而绕过均衡；已按真实输出预算调用，回归现通过。原失败日志保留，不将上游算法误归为故障。

新增ContextualRetrieveCourseTool继承现有RetrieveCourseTool，仅附独立上下文；原锁、授权、编号、去重、来源预算与失败处理保留。关系区块含entity/relation ID、端点ID、原始SDK块及当前Q2 source/document/version/release/range链接。有关联链接也仅为candidate_requires_claim_check，不等于关系描述已被逐句证明。无原文链接只能提示补查，不生成证据卡、先修、重点或掌握状态；原文编号继续用项目原协议。

默认最多12个关联、关联JSON最多6000字符，描述320字符、每项最多3个来源链接/12个SDK块，所有截断有计数/标志；覆盖报告与关联组成的工具附加上下文总限12000字符。优先有来源的关系，避免SDK先列实体而占完预算。aquery_data和原文SourceRef仍分开，未增加内部答案合成。接线契约详见LIGHTRAG_COVERAGE_INTERFACE.md。

resolve与Q2精确目标继续沿原导航。明确跨章插问只在检索时用临时子问题范围覆盖当前目标限制，不修改原target或数据库状态。真实Q5测试先用现有服务建立第五章目录导学路径，工具调用前后完整status相同；这是检索链路只读验收，**不是正式完整回合的Q5状态联调**。集成窗口不能因coverage=covered而调用record_explained/mark_understood。

没有修改main.py、TaskService、agent_loop、agent_loop_service、公共前端或回答预算。正式Q3/Q5共用入口与页面仍由集成窗口接线。

## 4. 验收结果与失败保留

49项独立专项通过（新增覆盖/上下文15、既有适配8、后端26）。另在已提交宿主a3b653e上完成15+8项纯接口兼容测试；首轮导入因宿主已有旧LightRAG包而被遮蔽，修正隔离包路径优先后23项通过，原失败日志保留。这不是最新宿主真实模型/页面验收。以下按具体能力列出真实请求结果；每项的旧失败仍在第5节全尝试表中，不将最终成功覆盖前次失败。

|能力|实际结果|调用/补查|工具总秒|返回tokens / 模型create|attempt|
|---|---|---:|---:|---|
|原跨章题：两对象均覆盖|通过（检索/工具专项）|2/0|145.422|3586 / 4|c53e45bd-abcc-43a2-abe0-ef1f9bbac1e5|
|单点：不增加检索|通过（检索/工具专项）|1/0|17.625|1232 / 1|a2ba000d-914e-4965-aaa5-b13f7f3ad740|
|单章：仅第一章|通过（检索/工具专项）|1/0|14.906|1866 / 2|d269ab81-65d1-4b9c-942c-6538e65e8834|
|比较：两种设计均有定义/特点|通过（检索/工具专项）|2/0|30.890|5453 / 6|fa291ee6-60f5-47c1-bfcd-e2a73357ee76|
|同章不同对象：自变量/因变量|通过（检索/工具专项）|2/0|44.532|5635 / 8|e731e784-ea34-4da1-911f-ad795dc59f90|
|某方无证据：partial，明确玄武岩缺口|通过（检索/工具专项）|3/1|94.468|3329 / 4|e578631b-a1aa-47f6-89ed-e398d4f21f26|
|真实Q5路径存在的跨章插问；状态相同|通过（检索/工具专项）|2/0|89.984|3584 / 4|65b34a22-10c8-46a0-89f1-3e101815aa95|
|语义相近对象；输出范围无重复|通过（检索/工具专项）|2/0|25.828|4784 / 5|ae2d800e-3e8a-4086-a86a-8fe7ce527804|
|真实重叠来源合并；同一引句承担双方|通过（检索/工具专项）|2/0|107.203|5184 / 6|78fb16b3-2738-44e6-812c-d2732dd6f116|
|取消：明确失败，无fallback|通过（检索/工具专项）|—/—|0.016|0 / 0|b835e179-1429-4109-8161-d273161d25a0|
|后端缺失：明确失败，无fallback|通过（检索/工具专项）|1/0|0.016|0 / 0|4662c6d6-fc7e-42e9-8a3a-7aef4c130b73|
|来源失效：Q2拒绝，无fallback|通过（检索/工具专项）|—/—|0.015|0 / 0|6676e7b5-29e0-4733-bb68-e86b78f0cbd9|

原题最终5条原文：第一章包括程序定义、步骤和实验实施内容，第二章包括自变量控制要点及水平数量；分别携带object-1/object-2，不混用来源。已人工查看这些原文主题，并独立复核本轮全部有效来源的冻结document/version/章节/块字符范围，74个来源出现项通过（不是74个唯一片段）。Q2选择阶段继续核验PDF原文。

最终原题关系区块实测有7条带原文链接的关系（早一版预算字段较少）；最终加入截断计数后的单点冒烟与真实重叠来源用例均通过。本轮检索不生成正式回答，不宣称因果关系解释或回答逐句支持已经通过。图像仍按既有Q2/source_visuals契约，pending状态与像素链路未改变。

真实重叠来源用例不仅检查输出没有重复，还检查merged_dedupe阶段实际排除了相同版本/范围的条目，合并后3条证据仍覆盖两个对象。取消包括真实HTTP预取消及单元级选择中途取消；本轮未再做长时SDK网络请求中途取消的真实注入。

矩阵运行：首轮13项5个执行判据通过（含2个旧链诊断、3个预期故障），8个新检索被连接错误中断；第二轮13项10个执行判据通过，3项连接失败；第三轮原题/缺失方/Q5三项3/3；最终版本单点/后端故障2/2；真实重叠来源1/1。诊断完成、故障处理与语义覆盖是不同统计，不能把“诊断调用成功”写成跨章质量通过。

连接失败cause链实测为TLS `[SSL: UNEXPECTED_EOF_WHILE_READING]`，并非余额402或检索未命中。单独传输探针中models GET成功，AsyncOpenAI与requests各一次极小completion成功、各返回8 tokens；这些不计覆盖验收。未改SDK版本、端点/模型身份或开启隐藏传输重试。失败时没有切换旧后端；aquery_data仍无内部回答。

本轮36次HTTP尝试，共观察到66次模型create、可得52,288tokens；另有上述两次传输completion共16tokens单列。早期native失败未附Metrics、8次网关调用无usage，故这些数字不是完整计费总量。最终补齐异常审计不回填旧记录。金额未返回，cost=null，不估算费用。关键词缓存会减少实际API调用，不能将检索次数当模型调用次数。耗时包含初始化、签名检查、Q2/语义模型、缓存与网络差异，不宣称速度提升，也不将本工具耗时冒称正式答案整轮时间。

资源：最后单时点服务PID79020 RSS1,725,673,472字节，CPU user73.1875/system45.671875秒；宿主GPU总占用3197/8151MiB、3%。非本进程GPU峰值，不把共享占用归因本窗口。模型检索按对象串行，未改其他窗口环境。

## 5. 全部尝试（不删失败）

|case|attempt|结果/实际后端|工具总秒|
|---|---|---|
|gap-original-diagnosis|3ce7c211-1d68-4a0f-abca-5c89662f26e2|LLMError；无记录/未执行|18.907|
|gap-original-diagnosis|21700170-c50c-4cf1-90df-cfa10a6b9d5e|完成检索；lightrag|19.516|
|gap-original-diagnosis-retry|26ea0470-804d-40b1-82a2-2636a8fe13af|完成检索；local_llamaindex|41.718|
|cross-coverage-first|89d67dd5-82c4-44b8-b5a7-2d53be11ae10|LLMError；无记录/未执行|88.219|
|coverage-legacy_baseline|01560729-ed08-4004-b14f-45117882d5b5|完成检索；local_llamaindex|90.344|
|coverage-legacy_lightrag|cf098ab8-170b-4381-875c-9d155b895ed6|完成检索；lightrag|67.046|
|coverage-cross_chapter|6ebea359-6907-4fd7-a270-2e376a262921|LLMError；lightrag|50.813|
|coverage-single|d4f6a08d-364b-4d9f-bfa1-e696cc0ced67|APIConnectionError；lightrag|13.969|
|coverage-single_chapter|1fa1d05b-0784-43ab-b04d-4c868579e0be|APIConnectionError；lightrag|18.000|
|coverage-comparison|03358bf1-c176-4ddd-9fc7-85648cec2564|APIConnectionError；lightrag|19.906|
|coverage-same_chapter|982ca059-99b0-491f-84a2-212f668f3f0e|APIConnectionError；lightrag|19.938|
|coverage-missing_object|522875db-3451-473c-9cbf-1f44837d8250|LLMError；lightrag|9.406|
|coverage-q5_interjection|f1b18824-0152-49ec-a7f2-b03dd2a31fae|LLMError；lightrag|17.563|
|coverage-duplicate_sources|53f1d92f-7ebe-4abc-a4d1-628c0dbfedf9|APIConnectionError；lightrag|29.578|
|coverage-cancel|8af06410-6cf9-4f24-807e-7971d5d25b92|CancelledError；无记录/未执行|0.031|
|coverage-backend_unavailable|71245cfc-97a0-41ad-90a9-f8117300e5d0|FileNotFoundError；lightrag|0.031|
|coverage-source_stale|43dcc9aa-146a-42fc-ac1e-ec25ae50f25c|ValueError；无记录/未执行|0.031|
|coverage-legacy_baseline|f05a2ef1-e6d9-4315-946f-bf74b6451e31|LLMError；local_llamaindex|9.234|
|coverage-legacy_lightrag|f9f72fe9-e0c0-4289-9f0a-9d7585a5c106|完成检索；lightrag|16.672|
|coverage-cross_chapter|c7f82bc3-53d7-4603-b038-3dc39ceb3bcd|完成检索；lightrag|31.016|
|coverage-single|1459a26f-df87-45f6-b818-ea9cd9da4ebe|完成检索；lightrag|18.203|
|coverage-single_chapter|d269ab81-65d1-4b9c-942c-6538e65e8834|完成检索；lightrag|14.906|
|coverage-comparison|fa291ee6-60f5-47c1-bfcd-e2a73357ee76|完成检索；lightrag|30.890|
|coverage-same_chapter|e731e784-ea34-4da1-911f-ad795dc59f90|完成检索；lightrag|44.532|
|coverage-missing_object|0ffad444-df28-430f-8759-a80738fe9645|LLMError；lightrag|5.390|
|coverage-q5_interjection|5c3f072c-4611-46e7-a03e-bfe6f536fcf3|LLMError；lightrag|5.109|
|coverage-duplicate_sources|ae2d800e-3e8a-4086-a86a-8fe7ce527804|完成检索；lightrag|25.828|
|coverage-cancel|b835e179-1429-4109-8161-d273161d25a0|CancelledError；无记录/未执行|0.016|
|coverage-backend_unavailable|a5f73a82-de70-4bce-9888-9f1c17cd6b9b|FileNotFoundError；lightrag|0.015|
|coverage-source_stale|6676e7b5-29e0-4733-bb68-e86b78f0cbd9|ValueError；无记录/未执行|0.015|
|coverage-cross_chapter|c53e45bd-abcc-43a2-abe0-ef1f9bbac1e5|完成检索；lightrag|145.422|
|coverage-missing_object|e578631b-a1aa-47f6-89ed-e398d4f21f26|完成检索；lightrag|94.468|
|coverage-q5_interjection|65b34a22-10c8-46a0-89f1-3e101815aa95|完成检索；lightrag|89.984|
|coverage-single|a2ba000d-914e-4965-aaa5-b13f7f3ad740|完成检索；lightrag|17.625|
|coverage-backend_unavailable|4662c6d6-fc7e-42e9-8a3a-7aef4c130b73|FileNotFoundError；lightrag|0.016|
|coverage-overlapping_sources|78fb16b3-2738-44e6-812c-d2732dd6f116|完成检索；lightrag|107.203|

## 6. 证据与操作

应用根目录：`E:\项目\heart-worktrees\lightrag-integration\project\integration\discrete-math-tutor`。

- `.runtime/lightrag-gap-coverage-20261021/matrix/`：各matrix运行ID及逐attempt完整返回，模型调用、阶段轨迹、来源、关系候选与Q5前后状态。
- `.runtime/lightrag-acceptance-01/attempts/<UUID>.json`、`attempts.jsonl`：本轮与旧轮全部原始服务记录，正式库无写入。
- `.runtime/lightrag-gap-coverage-20261021/summary.json`、`source-identity-check.json`、`health-final.json`、`resource-final.json`、`research-input-hashes.json`、`transport-probes.json`。
- `.runtime-lightrag-gap-matrix-01.log`、`-02.log`、`-03.log`、`.runtime-lightrag-gap-matrix-final-smoke.log`、`.runtime-lightrag-gap-overlap.log`：含所有非零退出与重试。
- `.runtime-lightrag-coverage-red*.log`、`-first.log`、`-limit-red.log`：原始失败/基础设施问题；最终 `.runtime-lightrag-coverage-final.log`、`.runtime-lightrag-adapter-gap-final.log`、`.runtime-lightrag-backend-gap-final.log`：15+8+26通过。
- `.runtime-lightrag-gap-seal-final.log`：封存输入与核心索引最终签名核验通过。

构建/加载命令沿用LIGHTRAG_SWITCH_RUNBOOK.md；本轮只运行检查/加载/查询，没有执行build_lightrag_book.py。新增复验与工具注册方法见LIGHTRAG_COVERAGE_INTERFACE.md。运行产物、密钥、教材、模型、学生库和索引不提交Git。

## 7. 集成与剩余阻碍

交付前观察到a3b653e已包含前批LightRAG后端包，默认检索/正式索引未切换；集成窗口先核对已采用内容，增量采用本轮实现2b79ddc434824510a6d296d5f6201bc3858b3e81、隔离加载兼容修正31adf968cfbc9a5490905867fc18eef194524d90，再采用本轮文档；不要重复套用旧批次，也不要自动合入main。让Q3与Q5共用既有search边界，使用CoverageNavigator与ContextualRetrieveCourseTool，按对象调用已有Q2证据选择/发布并保留SDK块链接；Q5 loop_binding覆盖navigator的风险仍须由集成窗口处理。正式图谱关联只作补查与解释背景，不能自动决定下一教学点。

旧260字失败应在集成窗口最新稳定宿主复验：同义问题 `f8696b37-7fd3-4b0d-b80a-1bab8cb04c18`、学习第一章 `87c5eea2-73fb-414a-9419-9da1185fd981`；原题仍用本文原句。旧记录源于a2be387，不能代表现已更新的回答预算。保持事实/来源门禁，本窗口没有放宽或删除。

**仍不满足正式切换条件**：尚无最新稳定宿主的正式回答/引用发布/Q3-Q5完整回合/浏览器联验；复杂指代需调用方传明确requirements；章节概述与所有跨章问法未穷举；TLS稳定性未解决；干净依赖安装/异机路径迁移未验收，179原图pending和公式逐式/像素链路仍属既有未完成项。发布授权、正式接线和切换由集成窗口另批处理。

隔离服务最终已核对命令行停止PID79020，候选、缓存、输入、测试库和全部证据保留。最新提交宿主的纯接口记录为.runtime-lightrag-latest-contract-coverage-final.log与.runtime-lightrag-latest-contract-adapter-final.log；初始遮蔽失败记录.runtime-lightrag-latest-contract-coverage.log保留。
