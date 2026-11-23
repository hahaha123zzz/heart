# LightRAG 统一教材检索与原生预探索优化实施计划

日期：2026-11-10
状态：经 grill-me 修订，采用分阶段验证；尚未执行实施任务。
设计依据：../specs/2026-11-10-lightrag-native-retrieval-optimization-design.md
授权范围：本轮编写文档；以下复选框记录未来实施，不因计划写完而勾选。

## 1. 目标与约束

目标：必须用已构建的LightRAG教材库替换新回答链路的两路本地教材检索；后续分别优化重复工作与上下文，每阶段单独验证，保留教材证据质量。速度不作为LightRAG迁移门槛。

- 所有课程事实问答必须依据教材；缺证据可追问，不自动回退旧引擎。
- 不重建/复制/删除教材索引，不修改project/vendor/DeepTutor固定副本，不新增Agent循环或意图分类模型。
- 既有rag、RAGService、LightRagBackend、原文核验、原生预探索和ask_user均复用。
- 原生顺序保持“材料预探索 → KB seed → 主回答”，不提前seed，不增加额外预探索。
- 优先复用原生压缩与按需补读，不新增固定字符硬门槛；内部上下文压力不能伪装成教材证据不足。
- 阶段一必须完成LightRAG迁移，速度只记录；后续可选优化无收益时保留LightRAG与原生行为。
- 原始payload、request_id收据、已交付历史与引用不改写；只对新执行投影做旧KB别名映射。
- 本轮不实现正文流转发、能力路由优化、逐事件授权查询优化，也不做全仓库重构。
- 所有现有未提交修改视为用户工作，实施前记录diff；不重置、不混合提交。
- 独立测试数据先验证；正式服务切换单列，不能因写计划而自动重启。
- 单独串行执行本计划；如未来需要委派，由用户明确授权，不因本文件默认启动子代理。

路径约定：下文P=project/integration/discrete-math-tutor，V=project/vendor/DeepTutor。命令从P运行，使用.venv-deeptutor/Scripts/python.exe；node使用本机既有安装。
环境约定：测试设置DEEPTUTOR_HOME与COURSE_DATABASE_URL指向独立目录；仅设置DEEPTUTOR_HOME不够隔离宿主数据。真实测试本机HTTP禁用代理。

## 2. 实施前必须理解的调用链

1. P/integrations/deeptutor/native_bridge.py:_bind → register_course_sources。
2. P/integrations/deeptutor/heart_rag.py → V/deeptutor/tools/rag_tool.py → V/deeptutor/services/rag/service.py → factory/provider_binding。
3. P/memory/background_worker.py:memory_lifespan → knowledge.fixed_book.start/stop；现有常驻图谱属于宿主。
4. P/knowledge/lightrag/retrieval.py:LightRagBackend.search → query_ownership → resident.query → map_chunks/rank_sources；仅输出检索原文和辅助关联。
5. V/deeptutor/agents/loop/agent_loop.py:run：pre_loop_briefings → kb_seed → 主循环。
6. P/integrations/deeptutor/native_grounding.py:prepare_retrieval → native_delivery.publication_sources → native_executor → _publish_gate。
7. V/deeptutor/tools/builtin/__init__.py:ReadSourceTool仅接受source_id；保留其原生契约，优先按需读取，不预先新增分页/子来源ID。上下文压缩须区分历史与当前工作集。
8. P/integrations/deeptutor/local_research.py另有provider白名单与KB授权，必须同步单库迁移。

## 3. 依赖顺序

| 阶段 | 执行顺序 | 阶段结论 |
|---|---|---|
| 一：必须迁移LightRAG | 任务0 → 任务1/2/3 → 任务6相应回归 → 任务7阶段一对照 → 任务8阶段一切换 | 来源/权限/功能/恢复通过后迁移，不以提速作条件；不等待任务4/5 |
| 二：减少重复工作 | 阶段一验证完成 → 任务4 → 任务6相应回归 → 任务7阶段二对照 | 保留原生顺序；只评估重复查询/补读修改 |
| 三：上下文优化 | 阶段二评估记录完成 → 任务5 → 任务6相应回归 → 任务7阶段三对照 | 依据实测复用原生能力，不增字符硬门槛 |

阶段二/三若无可复核收益，记录原因并保留上一阶段已验证实现；不撤销LightRAG迁移。阶段一可独立切换，不能把后两阶段当成前置条件。
每个任务必须先有对应失败断言，修改后执行相关测试；出现新失败先定位，不叠加无关修复。

### 任务0：冻结基线与来源契约

文件：读取现有代码、索引manifest和测试记录；新增P/tests/data/native_lightrag_latency_cases.json及P/scripts/check_native_lightrag_latency.py。
从阶段一开始复用同一测量脚本；脚本采用check_preservation_smoke.py的SSE读取思路及既有native_timing/LightRAG trace，不复制启动器。
新增P/tests/test_native_lightrag_latency.py，使用受控事件验证测量脚本。

- [ ] 记录git HEAD、dirty文件清单、模型/SDK/embedding身份、教材release及candidate签名；输出不含密钥。
- [ ] 只读核对LIGHTRAG_CANDIDATE_PATH现有input_manifest/progress/policy/index，确认教材11章及原文映射完整；不能用原生provider目录探测失败推导“需要重建”。
- [ ] 固定题集：定义、同概念追问、跨章比较、显式选区、指定原图、一道测验、一个子主题研究、无证据问题、同回合重复读取、长会话历史。图表题以实际有效asset_id固定。
- [ ] 对照实际题面和证据对象，记录每题必需来源/章节和允许追问的情形；不能仅以回答中有关键词判定通过。
- [ ] 确认最新基线及测试隔离，实际旧引擎查询仅存在于旧基线测量，不能在新链路中作失败兜底。
- [ ] 测量脚本先有受控事件自测：首事件/首正文/完整答案分别计时，失败与追问不计为answered，并行区间不重复相加。
- [ ] 保存可复用的旧基线记录；LightRAG阶段结束就重测，不推迟到三项全改完之后。

完成条件：基线、题集、来源断言和对照条件可复用；不能跳过正确性基线直接宣称性能改善。

### 任务1：让原生worker查询宿主现有LightRAG运行时

新增：P/integrations/deeptutor/course_search_api.py。
修改：P/integrations/deeptutor/{client.py,native_contract.py}、P/main.py。
测试：新增 P/tests/test_native_course_search.py。
复用：native_authorization、task_projection、fixed_book、lightrag/retrieval；不改SDK/图谱算法。

- [ ] 先写失败测试：未授权令牌/任务、非本课程、revision/epoch/版本不符、非法query/mode/limit、服务未就绪均拒绝；请求不允许注入路径。
- [ ] 定义CourseSearchRequest复用NativeTaskCheck；实现POST /internal/heart/native/course-search，查询前后核验，调用宿主active().backend.search()。
- [ ] 返回既有结构化原文/图表/graph_context/usage/trace；只裁投影字段，不丢document_id/version/原文范围/映射所需location。
- [ ] DeepTutorBackend新增对应方法，继续使用本机地址校验、无代理、无重定向；响应限额显式限制，超限失败，不能截断JSON后继续处理。
- [ ] 接通原生取消、断连和预算到宿主查询生命周期；不在worker第二次初始化ResidentGraph。测试取消后的下一请求能获得所有权。
- [ ] 校验host→worker→host回查不持有全局登记锁等待模型，避免循环等待。
- [ ] 执行test_native_course_search.py与test_lightrag_backend.py、test_lightrag_acceptance_instrumentation.py。

完成条件：受控真实任务可调用现有后端；失败不返回伪造来源；一次查询只进入一个宿主常驻图谱。

### 任务2：规范单一教材库，迁移旧选择

修改：P/integrations/deeptutor/{course_rag_provider.py,heart_rag.py,native_bridge.py,local_research.py}。
必要时修改同目录native_routing.py的执行选项规范化；保持原始请求收据。
测试：新增 P/tests/test_native_course_kb_migration.py、test_native_course_rag_provider.py。
更新：P/scripts/check_native_course_rag_browser.cjs及check_native_chat_chain.py、check_native_delivery_browser.py中与两引擎绑定的夹具。

- [ ] 写失败测试：默认只有experimental-psychology-3-lightrag；两个旧名、别名“课程教材/实验心理学”均归一；两旧名同时选择只保留一次；非课程KB不被重写。
- [ ] 课程适配provider采用heart-course-lightrag，在既有factory安装边界注册；通用原生lightrag处理不受影响。
- [ ] CoursePipeline.search改为任务作用域下调用任务1接口，不再调用psychology_retrieval；实际后端标记lightrag。通过learning_tool_adapter.current_learning_context()获取身份，缺上下文拒绝。
- [ ] 用as_textbook_chunk与prepare_retrieval转换原文；复用LightRagNavigator中已有的图表sha256/版本校验逻辑，不丢image_refs。
- [ ] 原生CourseService挂载规范KB并解除两个旧课程资源；不删除原注册项/索引。get_catalog/kb_files仍显示真实教材目录而不是候选内部文件。
- [ ] 新会话默认、旧会话preferences、本轮显式选择与研究范围都做规范化和授权；显式选择其他上传KB仍保留，不扩大到未选资源。
- [ ] 迁移幂等，原payload/start/digest不改；旧收据重放返回原结果；无法兼容的活跃回合提示用户按原协议取消后重新发起，不自动结束任务，也不能偷偷调用旧引擎完成。
- [ ] mock旧retrieve_hybrid、local_llamaindex.retrieve为“调用即失败”，证明新课程问答、图表和研究请求都不会进入它们。
- [ ] 更新浏览器脚本“两库数量等于2/逐引擎循环”断言为单库、旧选择归一、真实来源/刷新恢复；旧引擎独立模块测试保留。
- [ ] 执行两个新测试以及test_native_grounding.py、test_native_figure_tools.py。

完成条件：一个课程KB、一个实际LightRAG后端，默认重复查询消失，旧选择可兼容且未扩大权限。

### 任务3：无证据追问与课程事实发布门禁

修改：P/integrations/deeptutor/{native_executor.py,tool_policy.py,course_rag_provider.py}；仅在现有边界需要时修改native_delivery.py。
测试：扩充test_native_executor.py、test_native_grounding.py，新建test_native_course_evidence_policy.py。

- [ ] 写失败测试：普通概念问答、明确“不需要引文”的问答，无来源均不能发布事实答案；有核验来源可自然改述。
- [ ] 区分no_evidence、not_ready、权限/版本错误、超时；向原生工具结果提供明确状态，不把所有错误压成空列表。
- [ ] no_evidence经既有原生ask_user协议追问范围/选区，用户回答后按同一任务revision规则恢复；不自动换旧引擎。
- [ ] 事实性课程结果收紧allow_model_knowledge放行；澄清等待走原生pending分支，不能当成完成答案。Word等非事实性交付继续保持现有门禁。
- [ ] 验证模型忽略缺证据状态并直接作答时，最终门禁仍拒绝；已有来源也不能让无关问题借壳通过。
- [ ] 执行上述测试，加test_deeptutor_native_runtime.py中的问题卡/恢复相关用例。

完成条件：模型自主探索与追问仍由原生完成，宿主负责不可绕过的最终证据边界。

### 任务4：保留原生顺序，减少同回合重复查询与补读（阶段二）

修改：P/integrations/deeptutor/tool_policy.py、course_rag_provider.py；只有现有context.metadata无法清楚承载状态时才新增native_source_context.py，不预先新建抽象。
测试：新增test_native_source_context.py，扩充test_native_tool_policy.py。
读取：V/deeptutor/capabilities/explore_context/{capability.py,explorer.py}与agents/loop/{pipeline.py,agent_loop.py}。

- [ ] 阶段一功能/来源验证和独立计时已完成，保存阶段一结果作为本阶段基线。
- [ ] 写失败测试：事件顺序仍为pre_loop_briefings → kb_seed → 主循环；pre_loop前不能提前查询LightRAG，seed后也不能额外补一轮预探索。
- [ ] 保留原生材料激活条件、独占能力及skip_kb_seed约定；纯KB问答不能因后续seed生成source_index而增加预探索。
- [ ] cache限定同一回合，key含课程KB、版本、query、mode、limit、章/节；同参数并发可合并，不跨用户/分支/任务缓存，不把取消/异常缓存为成功。
- [ ] 按原文身份+版本+范围去重；相似文本但版本/范围不同不合并，引用ID及原始别名可追溯。
- [ ] 原生上下文已含文本时减少重复投影；已摘要/移除后仍允许再次read_source，不发无法恢复的“已读”指针，不新造读取协议。
- [ ] 所有tool_call仍有匹配tool_result，保留provider状态及复杂材料补读能力；不压缩问题本身或删除相关证据来刷指标。
- [ ] 执行test_native_source_context.py、test_native_tool_policy.py、test_native_question_history.py、test_native_reading_scope.py，再执行任务6对应回归及任务7阶段二对照。

完成条件：顺序不变、同回合重复工作减少且功能/证据不退化。若无可复核收益，保留阶段一LightRAG与原生行为，记录本阶段结论后再评估阶段三。

### 任务5：复用原生上下文能力，减少冗余文本（阶段三）

修改：按实测需要调整P/integrations/deeptutor/{course_rag_provider.py,tool_policy.py,native_grounding.py}中的课程投影；native_source_context.py仅在任务4确已新增时使用。
测试：新增P/tests/test_native_context_reuse.py；不预先建立固定字符预算模块。
读取：V/deeptutor/services/session/context_builder.py及agents/loop/{pipeline.py,context_budget.py,agent_loop.py}；不修改固定上游副本。

- [ ] 保存前两阶段的tokens、最大工具结果、原生压缩/摘要事件和长会话失败样本，明确本阶段要消除的具体冗余。
- [ ] 先验证原生上下文规划/压缩分别作用于历史还是当前工作集，不把历史摘要宣称为已支持的本轮压缩。
- [ ] 写失败测试：kb_files不向模型附页坐标/全文/embedding；同一原文不在content及模型可见metadata里重复堆叠。
- [ ] 优先复用原生摘要/压缩与按需read_source，完整来源及版本映射保留；资料充足时验证复杂任务继续完成。
- [ ] 不新增48000字符总门槛，不强制8000字符分段，不新增子来源ID或分页协议，也不因内部预算要求用户缩小问题。原生fallback与现有历史压缩保留原语义。
- [ ] 原生不支持压缩的当前工作集，先减少重复投影和按需提供材料，不擅自复制摘要Agent/循环或硬裁切。真实模型容量受限时如实报告系统限制，不能伪装为教材缺证据。
- [ ] 断言tool_calls/tool_call_id一一对应，Responses状态、reasoning/thinking blocks及原文否定/条件完整。
- [ ] 研究、测验、Word、exec继续原生能力处理，不能为了减少聊天tokens砍掉正式交付。
- [ ] 执行test_native_context_reuse.py、test_native_history_compaction.py及受影响provider-state测试，再执行任务6对应回归和任务7阶段三对照。

完成条件：针对实测冗余有明确结果，原生压缩与按需补读得到复用；没有用新增字符硬门槛打断任务或减少必要证据。能力缺口如实记录，LightRAG迁移结果保留。

### 任务6：每阶段功能与恢复回归（按已实施范围重复执行）

修改/更新：P/scripts/check_native_course_rag_browser.cjs；P/scripts/check_native_research_browser.cjs中的课程KB夹具；适当补充tests/test_native_delivery.py。
文档：更新project/docs/research/2026-11-08-deeptutor-complete-runtime中的迁移进度和已实现边界，按hunk隔离既有修改。

- [ ] 阶段一仅运行任务1～3及现有native回归；阶段二再增加任务4；阶段三再增加任务5。不依赖尚未实施的后续功能或测试。
- [ ] 验证原生“材料预探索（有材料时）→KB seed→主回答/按需补读→正式引用→PDF原文打开→刷新恢复”闭环；任何阶段都不调整原生顺序。
- [ ] 验证旧两库选择的会话发出新请求只调用LightRAG；原request_id重放不会执行新检索。
- [ ] 验证研究outline/continue的KB范围一致，测验/学习能力未被聊天hook破坏；上下文优化不裁掉Word纯格式交付。
- [ ] 覆盖跨账号拒绝、材料更新、删除记忆、取消/重试；并发两回合不串source_index、编号、缓存或模型配置。
- [ ] 测试实际使用独立worker/home/database；pytest路径使用唯一临时basetemp，避免与既有运行并发写同目录。

建议命令组，从P运行，basetemp每次使用未被占用的独立目录。阶段一：
.venv-deeptutor/Scripts/python.exe -B -m pytest tests/test_native_lightrag_latency.py tests/test_native_course_search.py tests/test_native_course_kb_migration.py tests/test_native_course_rag_provider.py tests/test_native_course_evidence_policy.py --basetemp=.runtime/pytest-native-lightrag-20261110
阶段二另跑test_native_source_context.py；阶段三另跑test_native_context_reuse.py。以下为每阶段受影响的原生回归：
.venv-deeptutor/Scripts/python.exe -B -m pytest tests/test_native_executor.py tests/test_native_grounding.py tests/test_native_figure_tools.py tests/test_native_delivery.py tests/test_native_tool_policy.py tests/test_native_question_history.py tests/test_native_reading_scope.py tests/test_native_history_compaction.py --basetemp=.runtime/pytest-native-lightrag-regression-20261110

完成条件：核心功能通过；未运行/跳过的测试及原因单列，不能用受控模型测试代替真实模型性能验收。

### 任务7：每阶段真实题集与分段对照（重复执行）

脚本：复用任务0已新增的P/scripts/check_native_lightrag_latency.py，不到本任务才首次开发测量工具。
输出：P/.runtime/native-lightrag-latency/<run-id>/<stage>/report.json及审阅摘要，stage区分baseline、lightrag-only、dedup、context；不含密钥。

- [ ] 阶段一：任务1～3与任务6相应回归完成后立即与旧基线对照，此时尚未执行任务4/5。
- [ ] 阶段二：仅加入任务4后与lightrag-only对照；阶段三：仅加入任务5后与实际保留的上一阶段版本对照。
- [ ] 相同题集/版本，冷启动与预热后分开；每类预热后至少3次。记录模型成本与样本数，不用少量样本宣称P95。
- [ ] 输出query_count、实际backend、source_count、重读次数、探索轮数、输入/输出tokens、最大工具文本、所有权等待、召回、重排、映射、模型和发布耗时。
- [ ] LightRAG内部keyword/query模型开销单列，不能只拿native usage_summary当全链路总耗时；并行区间不重复相加。
- [ ] 断言新链路不执行两旧引擎；阶段二才断言同参数重复检索合并，不能以阶段二功能要求阻挡阶段一独立迁移。
- [ ] 逐题对照已核验来源需求；追问/拒绝/失败单列，不能计为成功答案；确认复杂材料完成能力与引用质量不退化。
- [ ] 阶段一迁移不以耗时是否降低为条件；若慢则报告瓶颈，继续使用LightRAG修复。不得以“至少快30%”或“没提速”为理由否决迁移。
- [ ] 阶段二/三的优化各自说明收益、波动与风险；无收益或有功能回归的可选优化不合入，保留已完成的LightRAG迁移，不回到两旧引擎。

完成条件：每阶段都有独立功能结果和耗时记录，能区分迁移与后续优化的影响；阶段一必须迁移，速度仅是后续优化依据。

### 任务8：阶段一独立切换，后续优化分别交付与定向回滚

- [ ] 阶段一功能/来源/权限/恢复通过即整理独立迁移diff、测试结果、计时记录及回滚清单；即使没有提速也继续推进LightRAG迁移，不等任务4/5。
- [ ] 在正式数据变更前备份将修改的课程资源/会话偏好；使用幂等迁移，禁止批量清空用户会话。
- [ ] 将正式8000/18001的切换作为单独操作处理；本轮计划编写不执行重启。
- [ ] 切换后核验单库目录、真实LightRAG后端、原文入口、追问及刷新恢复。
- [ ] 若功能/数据回归，定向恢复受影响代码和绑定；阶段二/三的优化回滚以阶段一LightRAG为底，不回到旧两路。阶段一故障需修复，不能仅以速度不升回滚。禁止整库覆盖或删除索引/历史/新增数据。
- [ ] 更新进度文档，仅在任务完成后勾选，不把“已写计划”标为“已实现”。

## 4. 风险与处理

| 风险 | 处理与验证 |
|---|---|
| 原生LightRAG目录与现有candidate不兼容 | 用课程薄适配调用已有宿主LightRagBackend，不重建 |
| 同一索引被host/worker重复加载 | 宿主现有runtime唯一执行查询，worker只做受控调用 |
| 同进程查询锁不能代表跨进程互斥 | 不增加第二查询owner；并发/取消测试覆盖现有write/query所有权 |
| LightRAG内部模型、重排或排队仍慢 | 各自记录trace和usage供后续优化；不作为否决迁移的门槛 |
| 别名归一破坏幂等或权限 | 原始payload/hash保留，执行投影映射且重新授权 |
| 优化改变原生预探索顺序 | 事件顺序测试；不提前seed、不追加预探索 |
| 上下文压力被误判为教材缺证据 | 优先原生压缩/按需读取；不新增字符硬门槛，不借内部预算要求用户缩小问题 |
| graph_context被当教材事实 | 仅原文来源进入prepare_retrieval/publication_sources |
| 控制模型通过、真实服务仍慢 | 功能测试与真实计时分开报告，保留原始样本 |

## 5. 计划自审

- 用户确认的三个范围分阶段实施和验证；必须迁移LightRAG，不以速度改善作门槛；没有混入正文流/路由/授权性能改造。
- 每任务注明真实路径、依赖、失败断言、修改点和完成条件。
- 新增的宿主接口只是复用常驻LightRAG的进程边界，不是新检索引擎。
- 保留原生预探索顺序，撤销提前seed与新增固定字符预算；优先复用原生压缩/按需补读。没有自动回退、索引重建、历史收据改写或直接截断provider状态。
- 没有声称已经实施或测试；所有任务保持未完成。
