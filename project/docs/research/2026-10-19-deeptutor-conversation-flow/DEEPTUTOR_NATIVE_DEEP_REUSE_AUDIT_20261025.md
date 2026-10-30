# DeepTutor 完整回答流程深度复用审计

日期：2026-10-25。用户目标：消息进入、原生Agent循环、工具/教材查询、流式生成与输出全链路复用，尽量不重写成熟实现。本轮仅研究、生成台账和隔离测试；未改业务代码、正式服务、教材、正式学习库。

## 1. 调研方法与证据范围

- D盘源码HEAD：`6cf793bd868ba5ecbe64722936d4be8fab5a01df`。但工作树**不是完全干净**：`deeptutor/services/llm/factory.py` 有本地配置类型适配补丁。
- 对49个执行、持久化、检索、学习关键文件记录SHA、声明位置、直接绝对导入、vendor对照。49个文件的内容在规范化换行后与本项目vendor一致，包括已登记的factory补丁。这不等于整个仓库逐行无修改。
- 静态绝对导入可达模块359个：包含可选分支，未完整解析相对/dynamic import，不是最小运行依赖数，也不是逐行读完359个模块。结论结合手动调用点/状态变更阅读和下述隔离测试。
- 文件、SHA及函数行号见 `DEEPTUTOR_NATIVE_REUSE_SOURCE_LEDGER_20261025.json`。最初台账脚本误用编码别名utf8-sig失败，修正为utf-8-sig后生成，未改源码。
- 重新执行宿主原生桥11项测试，全部通过，62.791秒；真实原生应用服务/SQLite/上下文与协调器，能力替换为受控对象，无真实模型/教材API调用。第一次模块名启动因tests命名空间冲突失败，改用unittest discover后通过。
- 上游StreamBus、暂停/重绑定工具调度、上下文预算、scoped registry共50项测试，首次48通过/2失败，原因隔离默认workspace目录不存在；初始化隔离workspace后50项全过，4.59秒，未patch上游代码。日志 `.runtime/native-reuse-audit-20261025/upstream-tests.log` 和 `upstream-tests-ready.log`。这些测试使用脚本客户端/受控工具，不证明模型回答质量。

## 2. 结论：直接使用原生包，适配宿主边界

推荐现有独立后端进程方案，直接从已固定vendor加载DeepTutor原生应用服务，不再把核心循环剪成若干函数在Q3里重写。359个静态可达模块说明，所谓“复制一个AgentLoop文件就能运行”不成立。

对用户输入的正式路径应是：

`页面/ChatRequest → 宿主身份与任务收据 → 已有原生桥 → DeepTutorApp/TurnApplicationService → TurnRuntimeManager各服务切片 → UnifiedContext → TurnEngine → ChatOrchestrator → chat/mastery能力 → AgenticLoopPipeline/AgentLoop → 原生工具调度与RAG → StreamBus → 原生事件日志/终态 → 宿主SSE与数据投影 → 页面`。

这里宿主任务记录负责权限、页面与结果索引，原生协调器拥有执行状态和事件顺序；不能让两边都决定重跑、暂停恢复、超时及保存终态。原生执行后不能再调用旧Q3把答案重新生成一遍。

## 3. A类：源码本体可直接复用，保留其原生依赖与生命周期

“直接复用”指在正确上游作用域内调用原包，**不表示可脱离依赖单文件复制**；下列能力并非全部完成宿主页面对接。

| 代码位置（D盘deeptutor目录下） | 实际职责/已核对行为 | 建议与条件 |
| --- | --- | --- |
| `app/facade.py::DeepTutorApp`、`app/service.py::TurnApplicationService` | SDK门面；start_turn收据去重、活跃冲突、订阅、取消、用户答复、无租约僵尸回合回收 | 直接使用，绕过这层只调AgentLoop会丢失持久化/重放；已有NativeTurnBridge已调用此入口 |
| `app/container.py::ApplicationContainer/RuntimeRegistry` | 每作用域的store/runtime，协调器和进程生命周期，关闭/drain | 直接使用；进程启动/退出接container，不能每次请求造一个互不知晓的协调器 |
| `runtime/turn_engine.py::TurnEngine` | 延迟构造标准ChatOrchestrator并执行统一上下文 | 直接使用；无需新的宿主turn engine副本 |
| `runtime/orchestrator.py::ChatOrchestrator` | 选择已登记能力、会话事件、usage、终态；消费者停止时取消能力子任务 | 直接使用；输出适配必须透传取消与终态，不能只取最后一段文本 |
| `agents/loop/pipeline.py::AgenticLoopPipeline` | 工作区、延迟工具、KB准备、schema、预取、提示块和loop构造 | 保持原生pipeline调用；已有agentic_bridge重写其多个钩子，不能视作默认原生行为 |
| `agents/loop/agent_loop.py::AgentLoop` | 模型/工具循环、有界收尾、输出协议缓冲/释放/丢弃、model_turn保存 | 直接使用；不要再套宿主探索/收尾循环；原生也不是所有草稿都实时发布 |
| `runtime/agentic/tool_dispatch.py` | 重绑定工具先执行并重新绑定参数、普通工具并发、暂停工具后置；超预算调用仍配齐tool消息；敏感参数从事件剔除 | 整体复用，比仅复制asyncio.gather完整；无需为现有工具逐个重写调度（实际挂载以契约为准） |
| `core/tool_protocol.py`、`runtime/registry/*` | 原生异步工具协议、schema、惰性目录、每回合overlay和provider执行期授权 | 直接作为原生内部协议；现有Q3同步工具需要边界转换，不能混用类实例 |
| `runtime/stream_bus.py::StreamBus`、`core/stream.py` | 回合事件、跨loop队列投递、历史/sequence、订阅关闭与用户输入 | 直接使用；不是完整的持久事件仓库，必须配session store与executor |
| `services/session/turn_runtime.py`及`turns/{request_preparer,context_assembler,executor,lifecycle}.py` | 准备/历史上下文/执行/命令与事件存储；fencing token拒绝过期owner写入、释放租约 | 作为一个运行时单元复用，不能只复制facade小文件，真正逻辑分散在切片中 |
| `services/session/sqlite_store.py`、`protocol.py`、`model_history.py` | 回合/消息/事件持久化、工具配对和模型历史，不只展示聊天文本 | 直接保留作为原生执行存储；不替换成宿主ConversationRow再手写所有协议 |
| `agents/loop/prompt_blocks.py`、`context_budget.py` | 结构化提示、动态快照重放；统计真实请求的消息/schema/工具上下文 | 原样使用并提供真实输入；不能只复制提示词内容却不传来源/技能/画像 |
| `runtime/agentic/client.py`及provider兼容层 | 有界loop-local客户端池、关闭、配置/模型请求兼容 | 原生后端采用原生客户端生命周期，避免同时套宿主SDK池造成两层重试/计量 |
| `runtime/coordination/*` | 回合租约、命令、故障恢复；memory/redis按部署配置选择 | 单进程可用内存协调器配持久store；不把它说成跨机器恢复完整方案，multiworker需相应协调配置 |

备注：上一表工具数不作为验收指标，具体挂载要由资源和授权决定；不能以“原生协议已复用”声称100个工具全部可用。

## 4. B类：原码可保留，但必须接资源/数据/协议

| 模块 | 为什么不能直接无配置启用 | 最少适配方式 |
| --- | --- | --- |
| `services/rag/service.py`、`factory.py`、`tools/rag_tool.py`、`builtin.RAGTool` | 依赖KB名称/目录、当前用户可访问资源和provider元数据；工具kb_name不是宿主course_id | 宿主课程到原生KB只读绑定；由服务端授权选择，不让模型传任意磁盘路径 |
| `services/rag/pipelines/lightrag/*` | 上游发布版本目录、embedding绑定和模型角色，与现有candidate/index及policy发布身份不同 | 保留上游引擎/worker/来源解析；做一次清晰的候选存储/配置适配，拒绝伪造ready或只改路径；不擅自重建全书 |
| `LightRag engine.query_with_sources` | 上游调用aquery_llm并返回答案+结构来源，当前宿主改成aquery_data | 若选择完整上游语义，应保留并计量其内层工具答案；外层由原生Agent回答，不再走宿主第二套生成。不能宣称完全原样又悄悄改为纯数据 |
| `roles.py`、模型目录和权限服务 | 上游按用户模型授权/selection运行，不读一份.env就等于配置齐备 | 沿用已有模型映射桥；query/keyword/VLM/embedding分别映射正确身份，凭据留安全配置；保留已知factory类型转换补丁及来源说明 |
| `_retrieve_kb_seed_block`与工具组合 | 空KB时不会挂RAG；knowledge_bases、source_index、manifest等是真实资源，不是提示词占位 | 从现有教材和宿主选择构造真实上下文；先确认每轮挂载schema再验收模型调用 |
| 原生`read_source/read_memory/read_skill` | source_index、memory store、skills runtime具有原生作用域，与宿主服务/技能目录不同 | 挂接真实资料索引、允许读取的记忆和技能manifest，或迁移这些资源；不把任意宿主绝对路径交给工具 |
| 上游完整`learning/service.py`、`storage.py`、mastery capability/tools | 上游mastery.sqlite3有目标、交互、证据、revision和租约；当前Q5六表/本次安排不是同schema | 如要完整上游教学，优先迁入原生LearningService/Store，逐项迁移/映射旧学习记录与来源，再由页面读取投影；不重写一套兼容LearningStore事务接口，也不双向无约束同步两套进度 |
| 上游画像/三层记忆 | 上游L1 trace、L2/L3文档和后台归并不同于本项目已确认偏好、删除epoch | 可使用原生记忆机制，但必须决定历史迁移/删除传播/可撤销偏好；未确认推断不能伪装已确认画像 |
| 上游WebSocket入口、事件与结果信封 | 当前页面为TaskService/SSE、上标引用、阅读器动作；上游使用命令ACK、seq、原生结果和workspace URL | 后端复用StreamBus与持久事件，宿主转换事件/回执/来源；不要求为复用后端重写整页或再造第三套流 |
| `book`、阅读/课程状态服务及视觉资料 | 原生book/source/path身份与现有document/version/section、图片审核、PDF拆分页不同 | 映射来源和实际阅读器回执；缺乏精确位置时保留降级，不自动升级审核或伪高亮 |

特别纠正：D盘此版LearningStore的主存储是**SQLite `mastery.sqlite3`**，旧JSON只属导入兼容。此前“避免复制JSON学习库”的旧判断不足以决定现在的复用方案。

## 5. C类：不宜直接替换，借鉴或保留现有业务边界

### 5.1 SmartRetriever不能代替精确覆盖证据

`services/rag/smart_retriever.py::retrieve`会生成多query、gather查询、再调用聚合模型，汇总sources只写query/provider。它没有把每条教材引句/版本范围完整保留下来，也没有本项目“比较双方均须证据”的门禁。可借鉴多查询并发和预算，但不能用它直接替掉现有CoverageNavigator后声称引用和双侧覆盖等价；也不应把它额外叠加到原生Agent循环上徒增生成。

### 5.2 权限默认值不能照搬成宿主授权

上游ScopedToolRegistry默认Allowlist.unrestricted，且其说明明确provider allowlist不替代built-in挂载规则；built-ins由tool_composition控制。宿主Q4工具白名单则具有自己的scope与根校验。必须复用上游组合+授权完整路径并传入实际权限，不能只复制scoped_registry一个文件替换宿主的默认拒绝实现。

### 5.3 业务发布约束不是上游通用答案格式

上游rag sources可能是文档/chunk/entity/relationship或只有KB级信息；其builtin `_rag_sources`在有答案但无原始来源时可形成KB级fallback。这不能自动标记本项目source_verified。来源恢复、原文版本/引句、图片身份、教师pending、ready=false要保留业务验证；但不再通过重跑旧Q3整链验证。

### 5.4 登录、现成前端与管理面不整套替换

上游登录/OAuth、workspace管理、WebSocket前端与现有账户/布局不相同。已有NativeTurnBridge创建的是内部映射身份，应明确其数据/权限生命周期；不要求学生使用第二套登录。前端状态管理/事件协议可借鉴，现有上标引用、阅读器和学习安排需接实际数据。无需为“全套回答引擎”同时迁入合作伙伴、媒体生成或管理员产品面。

### 5.5 自动路由不是万能意图识别器

`runtime/capability_routing.py::route_explicit_quiz_request`是窄范围规则路由，普通消息不必先额外调用一个意图分类LLM；workspace中还刻意禁止此类自动改路由。原生完整接入应保留上下文和能力选择，不能人为新增一个“每问先分类”服务后说这是上游原样流程。

## 6. 当前项目的五种接入不要混淆

| 已有代码 | 实际作用 | 能否当完整原生回答 |
| --- | --- | --- |
| `generation_bridge.py` | 用上游模型服务生成 | 否，没有完整原生回合与工具执行 |
| `agentic_bridge.py` | 定制TeachingPipeline/StrictLoop，只读宿主已选证据，重写提示/钩子并缓冲输出 | 否，是受限原生循环适配，不是默认原生聊天/检索 |
| `turn_bridge.py`、`task_projection.py` | 同步宿主已保存结果、教材指针并恢复 | 否，是事后投影，结果本来由宿主生成 |
| `knowledge_bridge.py` | 知识资源/发布边界 | 否，资源服务不等于会话引擎 |
| `native_bridge.py` | 实际创建原生user/workspace/course/session/turn并调用DeepTutorApp | 是正确起点，但接线与正式发布仍不完整 |

不新增第六种桥。原生迁入应基于native_bridge收敛前述职责，稳定后移除被替代的重复调用方。

### 原生桥尚未完成的具体位置

1. `worker.py:53—62`安装session/turn/generation/agentic/knowledge路由，**未安装install_native_bridge**。
2. `native_bridge.py:127`新workspace资源skills/mcp/knowledge_bases均为空；`start`约186—188行又指定tools=[]、knowledge_bases=[]、auto_route=False。因此不是“原生完整工具已经可用”。上游可能仍有按条件挂载的基线工具，不能反过来说所有工具被空列表禁用。
3. `NativeTurnStart`只允许chat/ask_questions，不接mastery等能力；没有选区、图片、书籍/阅读引用和本次安排的完整字段。
4. `NativeTurnReply`只有text，缺原生submit_user_reply支持的结构化answers数组，问题卡多题/选项需要适配。
5. start/status/events的publication_state固定pending_verification，无正式答案发布/宿主保存闭环。
6. memory_epoch/material_versions在桥中登记进SQLite，但此桥没有像task_projection.checked_task一样重新读取宿主事实核验；本身不等同删除后阻断或换版保护。
7. 宿主client、TaskService未发现调用native/start/events/reply的完整路径；worker启动也没有对应路由。启用环境变量不能自动补接线。
8. `native_bridge.account`会更新模型目录与grant；每次覆盖grant适合试验固定权限，不宜无审计地覆盖用户后续授权。模型配置会进入上游目录存储，须使用上游安全存储边界并核对落盘，不能因report没打印就认为没有凭据持久化。

这些是现有桥的缺口，不是需要重写上游AgentLoop的理由。

## 7. 最小新增工作应集中在哪里

按顺序只完善四类边界：

1. **入口/身份桥**：安装已有native路由、宿主请求到TurnRequest、真实课程/KB/学习上下文授权、工具边界；保留原生应用容器生命周期。
2. **资料与状态映射**：现有全书候选/图片/原文身份接原生服务；旧Q5路径和本次安排迁移策略；画像和删除epoch责任。不能只传一段泛化提示词。
3. **输出/数据投影**：StreamEvent→现有SSE/卡片/引用/reader动作，seq、cancel、reply和最终收据；原生存储是执行记录，宿主数据库保存用户可见索引/投影，避免两套执行状态互相重试。
4. **契约验收与清理**：同一稳定宿主的真实模型/全书/页面、故障与重启；与现网Q4/图片/提速成果对账。原生链稳定后才删除失去调用方的旧执行代码，保留可回滚发布及历史数据。

不新写Agent循环、工具调度器、模型客户端池、上下文压缩器、回合日志仓库或掌握度算法。业务映射必须有针对性测试，测试复用上游成熟集合而不把mock结果算正式教材成功。

## 8. 验收证据分层与仍未证明的内容

- 已证明：所列源码存在且已入vendor；本机能执行原生应用/回合持久化受控测试；50项上游事件/调度/预算/授权测试通过；上文桥缺口来自具体调用点。
- 未证明：完整原生真实模型与现有全书候选兼容、现有Q5无损迁移、真实页面完整回合、原生GPU推理和端到端提速。
- “成熟”由设计和回归覆盖支持，不能理解为零缺陷或任意环境不需初始化；本轮workspace失败即说明必须保留真实应用初始化顺序。
- D盘factory已修改，与vendor的既有LOCAL_PATCHES登记一致。迁入记录必须区分固定上游commit与补丁，不能宣称所有内容都是未经修改的原版。

相关原始资料：`DEEPTUTOR_NATIVE_REUSE_SOURCE_LEDGER_20261025.json`、上游测试两份日志、`DEEPTUTOR_NATIVE_END_TO_END_REUSE_SCOPE_20261025.md`、`ANSWER_LATENCY_CPU_GPU_AUDIT_20261025.md`。
