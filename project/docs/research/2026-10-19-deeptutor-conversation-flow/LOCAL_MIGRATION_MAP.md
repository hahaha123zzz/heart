# 代码迁入地图与旧调用点处理

日期：2026-10-19。完整机器清单见 [LOCAL_MIGRATION_MAP.json](LOCAL_MIGRATION_MAP.json)。清单覆盖全部11个能力、14个扩展、100个工具，逐项登记固定源码、SHA-256、类入口、负责阶段、目标模块组和适配边界；均未冒充已迁入。

目标目录是计划落点，不表示已经创建。首批14个源文件记录了全部静态 import（包括函数内/条件导入）；这些是原始依赖线索，所需的本地依赖闭包在迁入时随实际裁剪逐批固定，不应把原包的全部传递依赖都装进项目。

## 旧调用点的逐项处置

| 当前调用点 | 行为 | 本轮处理 / 后续替换 |
| --- | --- | --- |
| main.py → _run_turn → TaskService / Orchestrator | 本项目现有主流程 | 保留入口；Q1/Q3按实际职责成组替换内部实现，禁止新增整轮应用转交分支 |
| worker.py → install_native_bridge | 注册完整DeepTutorApp回合接口 | Q0已撤下注册与import；实验文件/测试仅保留历史，不再由worker挂载 |
| .env.example → DEEPTUTOR_NATIVE_ENABLED | 启用原生应用实验的示例配置 | Q0已移除；不修改本机.env，不删除实验数据 |
| llm/client.py → DeepTutorBackend.generate | 旧模型/受限循环网关 | Q1迁入模型协议/生成模块，Q3接本地循环后替换对应分支；本轮保留既有兼容行为，尚未完成去网关 |
| orchestrator.py → knowledge_client.supplement | 旧教材文本检索补充 | Q2迁入完整检索实现后接knowledge接口，不把Obsidian文本命中冒充向量/重排 |
| main.py → sync_completed_session / sync_saved_turn | 旧独立会话映射与终态投影 | Q3迁入本项目协议/事件与恢复后替换；不能让它成为新本地模式的必要依赖 |
| recovery_router.py → task_projection.replay_events | 旧投影事件恢复 | Q3扩展本项目任务事件；区分旧投影与本地实际执行，不复用成另一轮生成 |
| integrations/deeptutor/router.py | 旧后端状态、目录、会话端点 | 迁入期间保留历史兼容，按调用点逐项退出新主链；当前目录注册数不当实际能力验收 |
| scripts/check_deeptutor_sessions.py / check_deeptutor_golden.py | 历史网关/worker模型验收 | 保留历史；Q1起增加本项目本地模块执行断言，未改造前不当新路线证明 |
| 已复用的Markdown/公式组件与reader构建 | 现有页面呈现 | 继续复用，Q3接问题卡，Q5/Q6接题卡、阅读操作和产物，不替换整个网页 |

撤下注册对下次worker启动生效；没有重启现有服务或删除已存储数据。本轮没有移除所有历史网关，也不宣称停掉旧后端后所有历史试点都已能运行。新路线的最终主对话不得依赖这些网关，逐批替换结果要写入记录。

## 首批文件按执行顺序分组

| 顺序 | 成组来源 | 原有依赖与本地处理 | 接入位置与验收 |
| --- | --- | --- | --- |
| Q1-A 上下文/历史 | core/context.py、session/model_history.py、ask_user_trace.py、provider_response_state.py | 先复用上下文数据与完整回合/澄清顺序处理；导入图中的Provider协议边界按实际需要迁入，不引入账户或会话数据库 | TaskContextBuilder、TaskContext及本项目会话记录；验证追问指代、澄清答复、完整工具配对及删除/版本过滤 |
| Q1-B 预算/提示词 | session/context_builder.py、llm/context_window.py、prompt/language.py、loop/prompt_blocks.py、capabilities/protocol.py、中文chat/agentic提示资源 | BaseAgent、SessionStoreProtocol、LLMConfig、StreamEvent、tool_dispatch等是需要替换的边界；模型与摘要用本项目客户端，存储/事件用本项目仓库 | ResponseGenerator、课程提示、上下文构建；保持明确请求、来源、偏好和历史分层，预算变化不切断整轮协议 |
| Q3 循环依赖组 | loop/agent_loop.py、loop/pipeline.py、runtime/agentic/tool_dispatch.py及实际使用的消息/流/工具模块 | 源码涉及较广的Provider、注册器、能力挂载与执行状态；按完整功能组迁入并替换本项目接口，不简单import原生应用容器 | 本地循环取代已接管场景的旧生成分支；同一请求只跑一个回答编排者，验证工具、澄清、取消、恢复和质量发布 |

首批不是整套范围上限，其余125项已经绑定目标模块组及阶段。详细字段来自固定源码实际文件和AST，许可沿用来源LICENSE及存在的NOTICE；迁入实现时逐文件保留来源与修改记录。

## 迁入前的关键差异

当前TaskContext历史上限为4条，TaskService常规会话只取最近2个完成任务，ResponseGenerator再截取历史。上游ContextBuilder采用预算化历史/摘要及完整模型回合；应成组替换历史选择和后续消费，不能只增加某一处切片长度。

上游LoopPromptAssembler的PromptBlock/运行时快照、用户材料与工具描述分层可直接复用。但中文循环提示含工具和skill指令，只有实际工具已经接通才可使用对应块；不能在普通单次生成中宣称能够调用未提供的工具。

Q1接入必须保留本项目已有教材引用编号失效处理、原图要求、提示限制、质量检查和显式请求优先级。预算、摘要和循环的原始成功测试不能替代这些业务验收。

## Q1 实际迁入与适配（2026-10-19）

| 来源 | 固定 SHA-256 | 本项目落点 | 实际处理与验证 |
| --- | --- | --- | --- |
| `services/llm/context_window.py` | `c1652a7760cd303f196522109b05267275d59a398ca1cd2960feaebee6324e9c` | `agents/context_window.py` | 原样迁入，纯函数，无上游启动依赖 |
| `services/prompt/language.py` | `8ade4d5f031ca6b79be6d69754ce768ca023d8e74e6260f8c4e66590efc4bac4` | `agents/prompt_language.py` | 原样迁入，作为提示词收尾的语言契约 |
| `services/session/context_builder.py` | `520b17920ea8e3319bc09770068c7cd5a72809d46de543fc1508b22eaa7688e9` | `agents/conversation_context.py` | 改为同步显示行；保留整轮分组、预算、最新一轮保留、滚动摘要；未引入 SessionStore/StreamBus/摘要模型 |
| `agents/loop/prompt_blocks.py` | `70c0cabeb6a230c58eff438beef1cbb352c96832a7c6708eb72cf45ccdd27ace` | `agents/prompt_blocks.py` | 保留 PromptBlock、空块省略、语言收尾；未迁入未挂载工具块 |
| `core/context.py` | `131c41f1f7eacd98acf02d2b95d7d28ab21aa720d14a8067aa06f3aafd90bcfd` | 仅接口参考 | 其统一上下文分层用于本地 TaskContext 设计；未整文件复制 |
| `services/session/model_history.py` | `335aaab5cfbf2aba6b50172e18d98eaf3d01cd27045bfdf96588dcd23473afbc` | 未迁入 | 完整 model_turn 工具协议与 provider 回放按 Q3 接入 |

本地另增 `agents/followup_context.py`（追问契约）和 `scripts/check_conversation_quality.py`（6 组连续对话样本、可离线自检、可真实模型运行）。Q1 的实际测试、通过/失败运行和未完成项见 [执行记录](EXECUTION_LOG.md)。
