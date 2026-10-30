# LightRAG 交付缺口与 DeepTutor 源码深度对照

日期：2026-10-21。状态：源码与留存验收记录审查，未修改业务代码、索引、正式数据库或运行服务。

## 1. 核心结论

可以继续复用 DeepTutor，但目前缺口主要在检索外围的证据覆盖、工具循环和业务接线，不能靠再次复制 LightRAG 引擎或重建全书图谱一次解决。

- LightRAG 分支 `UPSTREAM.json` 已登记 18 项上游来源文件（包括 LICENSE），涵盖 engine、pipeline、parser、ingress、roles、storage、worker 等，已有迁入并非从零自研。
- 上游普通聊天没有“跨章问题一定覆盖全部章节”的程序保证。它有预检索与循环补查；BookEngine 另有多查询、限额并发、来源均衡及覆盖缺口报告，可组合复用。
- 旧检索此次跨章失败不是候选完全没有第一章：候选已有第一章片段，最终选择把它们全部排除。至少要修复选择/覆盖策略，不能仅提高图谱规模。
- 上游普通 LightRAG 调用会在内部生成答案；本候选改为 aquery_data 结构化检索，是为外层统一回答、来源核验及成本而作的明确适配，不能简单认定这项差异是错误。
- Q5 与聊天复用同一检索工具/服务、原图以临时模型消息注入、已发布版本与候选分离，这三组上游实现尤其值得继续采用。
- 旧验收宿主的 260 字失败要在最新稳定宿主复验；不能通过移除事实门禁冒充修复。

## 2. 版本与证据范围

- DeepTutor：`D:\deeptutor`，固定 HEAD `6cf793bd868ba5ecbe64722936d4be8fab5a01df`，Apache-2.0。
- 本项目：当前读取 main 为 `78fb20f`（UX2 文本预算和增量排版提交）；它不是旧验收使用的宿主。
- LightRAG 候选：`E:\项目\heart-worktrees\lightrag-integration`，交付报告/操作预案及 q3_adapter、retrieval、engine、UPSTREAM.json。
- 原有效对照宿主：`a2be38741c2c08162efd2335e7249db3353f9812`，不能将其失败直接当作最新运行代码的结果。
- 重点原始记录：旧检索跨章 `3cd84783-eb4e-4760-b596-3f1ba31e31d3`；LightRAG 跨章 `3c5afcfa-2ea7-4b1b-ad93-72dd1293b07c`。仅读取已有记录，未重新请求模型。

复核摘要保存在应用目录 `.runtime/lightrag-gap-audit-20261021/failure-analysis.json`；源码哈希和定位见同目录文档 `LIGHTRAG_GAP_DEEPTUTOR_SOURCES.json`。

## 3. DeepTutor 的实际普通对话检索链路

```text
用户消息 + 当前可访问知识库
  → AgenticLoopPipeline 组合工具及上下文
  → 可选预检索：rag(query=用户问题, kb_name, mode=hybrid)
  → RAGService 按知识库绑定的 provider 取 pipeline
  → LightRagPipeline 选择已发布、embedding 身份匹配的索引
  → worker 中 build_rag → initialize
  → engine.query_with_sources → SDK aquery_llm
  → 返回内部合成答案 + chunk/entity/relationship/reference/metadata
  → 外层循环读取工具结果，必要时进一步调用工具
  → 外层不带工具的回复结束本轮；能力协议可要求一次补做/撤回
```

### 3.1 预检索的作用和限度

`agents/loop/pipeline.py::_retrieve_kb_seed_block` 在循环前读取传统 RAG 知识库，最多 3 个，每个预置片段最多 4000 字符，独立知识库并行调用。需要重建、失败等结果不作为有效种子；某些能力可明确跳过。

它解决“模型忘记调工具，挂载教材却凭参数记忆作答”的问题。它仍使用整个用户问题作查询，没有按章节拆解，也没有强制每章原文覆盖。不要把最多 3 个知识库理解成最多查 3 个章节。

本项目已经要求教材问题先检索；若采用预检索，只能把同一证据结果复用到循环，避免预检索后模型再做一次相同查询。当前两个跨章失败都真实调用过工具，因此不是仅加预检索就能解决。

### 3.2 上游 LightRAG 的答案与本候选差异

`engine.query_with_sources` 使用 QueryParam(mode 默认 hybrid、stream=False、include_references=True)，调用 `aquery_llm`，同时保留完整来源。内部 QueryParam 的 stream=False 不代表外层聊天不能流式；这是两个不同模型调用。

候选 engine 使用 `aquery_data`，将内部 answer 留空，保留结构化 chunks/实体/关系等结果，然后由 Q2/外层生成和核验。这避免检索先生成一遍、外层再写一遍的重复合成。

建议保留当前结构化模式。要补的是外层能否消费带原文链接的关系上下文、是否补足跨章证据，而不是为了与上游相同切回双重生成。若比较两种模式，须同配置记录调用、来源和时长，不能凭流程更长推断更好。

## 4. 跨章漏检：真正可复用的上游模块

### 4.1 本次失败定位

用户问题：第一章的实验程序和第二章的自变量控制有哪些联系？

| 层次 | 旧检索 | LightRAG |
|---|---|---|
| 调用策略 | 一次混合查询，limit=8 | 一次混合查询，limit=8 |
| 候选/原始图谱 | 40 个候选中有 7 条第一章片段 | 留存 44 条 graph_context；完整原生阶段章节分布未在本次记录中确认 |
| 重排/选择后的旧检索片段 | 8 条全部来自第二章 | backend 调用记录计 8 条来源，随后 Q2 证据选择及工具返回只保留 3 条第二章原文 |
| 实际工具传给外层模型 | 第二章 8 条 | 第二章 3 条 |
| 缺口后动作 | 没有进一步补查 | 没有进一步补查 |

所以旧链已经证明候选之后的筛选会丢章。第一章候选是否真正涉及“实验程序”还需逐条核对；不能只因章节编号正确就把任意片段硬塞进答案。

LightRAG 还不能仅凭最后 3 条断定损失发生于原生召回、阈值、全局重排、limit 还是 Q2 choose_evidence。实施时须记录各层的块 ID/章节/得分与排除原因，逐层定位，不能虚构唯一根因。0.15 的重排阈值尚未校准，不可直接按概率解释。

### 4.2 上游可采用代码

**A. `services/rag/smart_retriever.py::SmartRetriever`**

- 生成多个查询，或接收 query_hints；并行搜索，再汇总。
- 由 RAGService.smart_retrieve 暴露，是可选辅助接口，不是所有普通聊天默认路径。
- 不能整段原样套用：当前实现 sources 只保留 query/provider 摘要，聚合还会额外生成；不满足本项目精确引用。应保留查询变体/调度思路，复用现有 SourceRef 合并、核验及单一回答生成。

**B. `book/agents/source_explorer.py`**

- 设计有限、多样查询；对查询×知识库做有界并发；查询优先交错，防止限额用完前后面的知识库没机会被检索。
- 原参数为并发 6、最多 48 次检索，这是写书工作流预算，不应照搬为普通一次问答的调用预算。
- `_balanced_slice` 在每个 source/kb_name 组内排序，再轮转取样，避免不同引擎得分量级造成某来源被全局 Top-K 挤掉。
- `_dedupe_and_clip`、覆盖统计、`book/engine.py::_source_quality_summary` 给出已覆盖和缺失来源，缺失时标 warning，不把少量检索冒充所有资料覆盖。

这些算法可迁入项目检索协调层，但 SourceChunk 的分组不是 chapter。当前 11 章在同一教材知识库，需要适配为“子问题/要求范围/章/来源版本”，不能只复制 `_balanced_slice` 后宣布跨章完成。

**C. `agents/research/pipeline.py::_decompose` 与动态 TopicBlock 队列**

上游 deep_research 真正按子主题检索并组织证据，适合研究/长报告，不属于普通聊天自动流程。可参考其子任务与缺口管理；本问题只有两个教材对象，不需要迁入完整研究队列、报告生成与额外账户状态。

### 4.3 本项目所需最小适配（新增，不能冒称上游已有）

1. 显式跨章问题先提取所需范围与对象：第一章/实验程序，第二章/自变量控制，以及两者关系；不重置 Q5 当前路径或游标。
2. 分别检索子问题，必要时通过 Q2 目录和精确原文读取补缺；同章片段按子问题相关性重排，再有界合并，保留每个必要对象的有效证据。
3. 检查要求范围、相关主题和有效原文是否覆盖，不只检查章节数量。缺失只补查缺口，使用有限查询/轮数预算，已有足够证据就停止。
4. 图谱关系可以辅助解释和发现候选；关系描述必须链接到可核验原文，不直接当成教材引文、先修或重点。
5. 仍缺证据时明确部分回答/缺口，不无界检索、不把任意第一章段落当成补齐。

## 5. 知识关系上下文没有完整进入候选工具输出

候选 retrieval.py 返回 graph_context；q3_adapter 保存到 last_result，但常规 search 返回值是 SourceRef 列表；当前 RetrieveCourseTool 主要将 SourceRef 原文组装成工具正文。该适配路径中未见 graph_context 进入外层模型的独立受控区块。验收记录存在关系数组，不等于回答模型已经利用关系。

上游 aquery_llm 在内部把实体/关系用于合成，再把内部答案交给外层，因此关系有一条明确的消费路径；这不等于上游关系结论自动可靠。

建议保留 aquery_data，在既有工具结果中补独立、有大小限制的“关联候选”区块，携带 relation/source IDs 和原文链接；只有当前有效证据能支持的关系进入解释。原文摘录编号仍由 Q2 分配。无原文链接的图谱描述只能提示补查，不能成为独立引用卡。

这是适配差距，不需要重建已有 7138 个实体/14741 条关系；重新建立图谱也不会自动修复工具结果丢字段。

## 6. 回答长度与发布：不能把上游 guard 当事实门禁

DeepTutor 的普通循环使用 token 预算，`respond_max_tokens` 默认 8000（可配置），不是所有问题一律 260 个汉字。它会识别 provider 截断和预算耗尽，做有界收尾；能力的 finish_instruction 可以要求一次补做，拒绝轮通过 answer_visible=False 撤回。

Mastery 的 finish_instruction 主要检查题卡是否真正投递、是否重复题卡、是否把测验写成纯文本。这是业务协议检查，不是本项目的教材逐事实/引用/视觉质检。不能因为上游普通聊天没有同样的严格门禁就删除本项目核验。

本地 `78fb20f` 的 Q3 门禁已经使用 max(600、Q3_REPLY_MAXIMUM 默认800、任务预算)，详细规划预算可达 2400；旧隔离脚本仍冻结在 a2be387 并明确使用 260 字。应在最新稳定宿主上复验原失败，不再以过期脚本的固定长度代表当前产品。

可继续复用上游：截断识别、有界修订、撤回与流式状态；保留本项目事实、来源、保存门禁。事实缺口与长度问题应分别报告。

## 7. Q3/Q5 为什么上游能用同一检索

`capabilities/mastery/pipeline.py::MasteryLoopPipeline` 继承 AgenticLoopPipeline，只改变提示词协议；将路径已选知识库并入本轮资源，使用同样的工具组合和 RAGService/provider 选择。`compose_enabled_tools` 给 Mastery 增加 owned tools，不悄悄换掉聊天已有检索工具。

本项目 run_agent_loop_turn 在 q5_binding 存在时创建 `Q5Navigator(..., search_fn=q5.search)`，所以仅传 LightRagNavigator 参数会被覆盖；这正是“构造了适配器但正式 Q5 没启用”的风险。

适配办法：保留 Q5 resolve/目标/学习状态，将检索后端选择放入 Q3 和 Q5 共用的 search 边界。精确教材目标仍走 Q2 read_target；跨章普通问答允许显式范围，不被当前一个小节的游标错误裁剪。actual_backend、索引身份和 fallback 必须进入日志和测试。

上游 factory/service 的统一 provider 路由可以参考，不能整套照搬上游账户、KnowledgeBaseManager 和 LearningStore；项目已有的课程与学生身份继续有效。

## 8. 原图：可以直接复用的完整消息方法

上游链路：RAGTool 精确图号/原页检索→VisualEvidence.model_message 或 _rag_visual_model_message→ToolResult.model_message→dispatch.model_messages→extend_transient_model_messages→with_transient_model_messages→模型请求。

`runtime/agentic/messages.py` 两个函数尤其适合迁入：

- with_transient_model_messages：将图片锚定到 tool_call_id，放在完整工具回复批次之后，不破坏 OpenAI 工具配对，也不把大块 base64 写进正式历史。
- extend_transient_model_messages：保留最新有界图片，上游默认最多 2 张；跨轮淘汰旧图，避免无限堆积。

source_visuals.py 提供 asset/source_hash/page/region 校验，向视觉模型发送真实像素；不支持视觉时只依据文字，不能声称看见。VLM 构图角色与聊天读图能力要分开：展示/读取原页不一定要重新用 VLM 构完整图谱。

本项目协议和调度已有 model_message/model_messages，但读取的当前 agent_loop 只追加 tool_messages，缺少临时消息消费；候选 q3_adapter 也明确 model_saw_pixels=False。因此应接 UX4 的完整消息链及质量检查，而不是再次核对一次原图 ID 后宣布多模态通过。

## 9. 索引加载、发布与部署

上游 LightRagPipeline.search 通过 storage.latest_published_root 只取已发布版本；require_compatible_embedding 不只比较维度，还比较 embedding 身份。构建/重建写独立候选，发布 metadata/binding 失败会撤掉新候选发布标记，保留旧版本和数据。

engine.workspace_for 优先使用 meta.json 固定 workspace，避免目录移动后按新路径哈希打开空库。这项函数候选已经迁入；不能只再复制它就声称整个候选可搬迁。输入清单 source_root、sidecar 和引用路径仍需完整迁移/验证。

上游每次 search 同样 build/initialize/query/finalize，不是一个可直接抄来的常驻缓存引擎。当前性能问题应测原生加载、源文件签名核验、关键词调用、embedding、重排和证据选择的分别耗时，不凭“缓存”二字承诺提速。

可复用版本就绪/发布、worker 生命周期、模型角色和兼容校验；本地独立环境借包、依赖锁、Windows/CUDA安装和异机路径验证仍需本项目完成。不能为了切换把 staging/ready=false 改成 true。

## 10. 建议后续工作与交付边界

| 优先 | 工作 | 主责/复用 |
|---|---|---|
| P1 | 在最新稳定宿主复验旧260字失败及跨章原题，记录召回→映射→重排→证据选择→工具输出每层覆盖 | 集成/回答窗口，继续 UX2/UX3 |
| P1 | 有界分题、按必要范围检索、组内排序/均衡合并、缺口补查 | 检索窗口；迁入 SourceExplorer 小算法，章节语义由项目适配 |
| P1 | 关系候选真正进入工具结果，原文与图谱分开，关系有来源链接 | LightRAG 接口与 Q3 工具协作 |
| P1 | Q3/Q5 共用后端选择，保留 Q2 精确目标 | 集成窗口，参考上游共享 RAGService |
| P2 | 临时图片消息、像素核验及正文展示/恢复 | UX4，复用 messages/source_visuals |
| P2 | 发布、干净安装/搬迁、并发/取消与回退 | LightRAG/集成，复用版本与worker，不放松门禁 |

不需把整套 deep_research、BookEngine 或 DeepTutorApp 再搬进一轮教材问答。可以先完成上面几个成熟模块的迁入/适配，再在当前项目真实页面验证。

本次审查不改实施状态；相关验证结果与限制以 `.runtime/lightrag-gap-audit-20261021/` 留存日志为准，不把源码分析当成本项目已验收。

## 11. 本轮验证与限制

- 读取 3 个仓库/工作树中的 38 个文件并登记哈希、函数定位；另复核上游提示词、测试和原始验收记录。未访问外部网站。
- 对上游原函数 AST 原样提取后隔离执行 8 项自检：小输入不裁剪、来源组均衡、组内排序、完整工具回复后再附图、不修改正式消息、累计图片有界、已发布 workspace 保持身份、未发布 workspace 路径签名稳定。结果见 `helper-selfchecks.json`。这是函数级验证，不是整体应用或真实检索验收。
- 原 pytest 组合先完成了 6 个用例，之后未及时结束而停止；缩小后的组合设置 45 秒上限，同样仅留下 6 个完成标记后超时，退出 124。保留 `upstream-tests.log` 和 `offline-checks.log`，不宣称全套通过，不据超时判定上游功能有缺陷。本轮未修改上游测试。
- 没有运行新的真实模型问答、浏览器、完整索引加载/搬迁或 Q3/Q5 页面联验；没有修改候选、发布状态或业务代码。来源覆盖策略和关系上下文适配仍待实施后验证。
