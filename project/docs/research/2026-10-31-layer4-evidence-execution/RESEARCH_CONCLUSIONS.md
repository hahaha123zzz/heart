# 第四层深度调研：教材证据与工具执行

日期：2026-10-31。状态：四批文本阅读与源码静态调研已完成；不是已批准的实施计划，也不是新组件运行验收。

## 调研方法与基线

- 用户输入：`C:/Users/free/.codex/attachments/73f704c2-f001-4133-a254-5fc29102d7ec/已粘贴的文本.txt`。将其中建议视为待核验假设，插图链接和推荐强度不作为技术证据。
- 代码基线：`94ba9ca`（第二层六维分类及第三层并行基线）；调研只读业务代码，不接入新依赖、不改变运行服务和数据库。
- 四批阅读：①架构、解析、多模态与目录导航（1—287行）；②检索路由与证据定位（288—563行）；③工具、LangGraph与论文（564—801行）；④复用矩阵、性能缓存和实施建议（802行至末尾）。行号按原文件实际行，不按去空行计数。
- 每个上游记录固定提交、实际源码入口、许可证、项目接口差异；代码静态可复用与本项目真实可运行分开判断。不把论文的公开数据集结果外推为本教材效果。
- GitHub连接器此次调用不可用，gh本地配置受限，已改为只读GitHub官方API及固定提交raw源码。公开仓库资料下载至`.runtime/layer4-research-20261031/`，不向外发送教材、学生记录或密钥。

## 第一批：架构、解析、多模态与目录导航

### 已核对的本项目事实

1. 现有`CourseSearch`已经提供精确读取、LlamaIndex混合检索/BGE重排快速路径及LightRAG复杂覆盖路径；新增“统一检索入口”应扩展已有入口，避免再建一套选择器。
2. 教材是《实验心理学（第3版）》DOCX来源，已有原文块、图片、表格、PDF与坐标映射。`manifest.json`仍为staging，运行检索ready不代表教师审核完成。
3. `read_memory`是明确确认的偏好/画像只读端口；完整`MemoryRetriever`是另一条相关学习记录取证链，不应合并为无差别文本。
4. 普通Q3聊天与DeepTutor原生测评仍有执行权边界；TA5/恢复记录明确NT3、NT8及部分人工/性能验收未完成。

### 对用户材料的初步纠正

- `zesks/deeptutor`页面明确是`HKUDS/DeepTutor`的fork。优先研究官方上游和本地固定vendor，不能将fork的功能描述默认当成官方成熟能力。
- 不接受“MinerU直接引入、Docling同时补充”的无条件结论。应先建立现有教材的缺陷样本，比较原生DOCX结构与PDF解析；优先保护现有来源ID、块索引和坐标。
- PageIndex应先核对是否能利用已有真实目录；目录树/模型摘要不等于精确原文证据，不能替换本项目坐标核验。

### 第一批源码结论（已核验）

| 对象 / 固定提交 | 核验入口 | 工程结论 |
| --- | --- | --- |
| Docling `764b5d4` / docling-core `2dc4c9f` | `docling/backend/msword_backend.py`、`docling/document_converter.py`；core `transforms/chunker/hybrid_chunker.py`、`types/doc/document.py` | MIT；可将原生DOCX后端作为离线对照器，复用DoclingDocument的结构/引用/页坐标思想；HybridChunker是真实结构+token预算切分，不是语义向量断点切分。需要DoclingDocument适配，不能直接塞入现有块数组。先对照后决定安装。 |
| MinerU `0ef2c20` | `mineru/parser/mineru_parser.py`、`LICENSE.md` | 当前解析器委托统一backend，支持范围需按本版本核对。许可证是Apache-2.0附加条款，GitHub标为NOASSERTION；不能沿用旧版本AGPL或笼统“宽松许可”判断。优先只作缺陷PDF页的离线修补候选，不是本轮必装。 |
| RAG-Anything `2cd2b33` | `raganything/modalprocessors.py`、`parser.py`、`processor.py`、`query.py` | MIT；确有ContextExtractor按页/块读取上下文及图片/表格/公式处理器。最有价值的是对象与邻文关联；描述和实体由模型生成，不能直接变成权威引文。处理器耦合自己的LightRAG存储/模型回调，不适合原样替换现有媒体链路。 |
| PageIndex `2e0f4dd` | `pageindex/page_index_classic.py`、`page_index_md.py`、`utils.py` | MIT；经典实现重点是LLM目录检测、页号核对及树构建。我们已有真实目录、块ID与read_target，先实现已有目录上的导航回退更小。完整PageIndex只作为离线对照实验，不加入所有问题的在线前置步骤。 |

许可证补充：MinerU本次快照要求基于其提供的在线服务作显著标识，且列出规模阈值下的商业许可条件；代码许可、模型权重许可和托管API条款应分别登记。Docling主包与core虽MIT，其模型/后端也需独立核查。本文记录许可文本事实，不把它等同于已完成商业法务审批。

本地额外风险：`knowledge/lightrag/block_policy.py`明确使用`mineru-legacy-content-list-v1`旧格式契约。用户材料建议直接接最新版解析器会遇到schema、页码和对象ID差异，必须建立版本适配，不能只换包名。

**第一批决策：保留原生DOCX与现有PDF坐标为权威；先补对象关系和解析质量样本，选择一个补充解析器开展离线对照。禁止同时重解析整书、重建图谱并更换定位索引。**

源码链接：

- [Docling DOCX后端](https://github.com/docling-project/docling/blob/764b5d4dc22b03ea87afd4c2207f510300b27a5b/docling/backend/msword_backend.py)
- [Docling HybridChunker](https://github.com/docling-project/docling-core/blob/2dc4c9f511269eb39be5aad84b838f7bb179142e/docling_core/transforms/chunker/hybrid_chunker.py)
- [MinerU许可](https://github.com/opendatalab/MinerU/blob/0ef2c20c4a56e68f81a66647f819d924ef2d89ce/LICENSE.md)
- [RAG-Anything模态处理器](https://github.com/HKUDS/RAG-Anything/blob/2cd2b3329c470ccb53923f8a6d320596b34e56c5/raganything/modalprocessors.py)
- [PageIndex经典目录构建](https://github.com/VectifyAI/PageIndex/blob/2e0f4dd35aa6a24c2dedfcf54678b0b0ad323ce8/pageindex/page_index_classic.py)

## 第二批：检索路由、多模态对象与证据定位（已完成）

### 不能重复建设的现有能力

`agents/course_search.py::CourseSearch`已整合直接目标读取、本地召回重排、复杂覆盖与证据选择；`knowledge/grounded_citations.py::EvidenceBundle`已组织sources/evidence/backgrounds及coverage_reason，并在publish时核对实际引用、去重原文范围、重新压紧显示编号和绑定claims。`figure_reading.py`已将指定原图与同小节邻文共同读取。第四层不是从只有content字符串的状态出发。

因此推荐：新增最薄的跨层请求/结果契约，包住现有服务；不新增一套RetrievalRouter、EvidenceBundle、对象索引和AgentLoop再把同一问题处理第二次。

### 已核验的上游实现

1. **LlamaIndex `619d746`（MIT）**：`fusion_retriever.py`有RRF融合，`recursive_retriever.py`支持由索引节点深入读取；可沿用本项目已装的相关接口。本项目已有真实目录及target读取，父节点导航->子块精读比同时新增PageIndex全栈更合适。不要将不同召回器的原始分数直接相加或解释为统一概率。
2. **LlamaIndex CitationQueryEngine**：`_create_citation_nodes`会再次切分节点并添加Source序号，主要服务回答合成；这不等于保证PDF坐标、原文字符范围和对象身份正确。本项目现有坐标/版本核验更贴近需求，不应替换为此组件。若采用其切片，必须保留父块和字符offset。
3. **RAGFlow `12d9a38`（Apache-2.0）**：本次默认分支相关实现位于Go目录，`citation_sources.go`包含来源token预算、合法ID过滤和跨流式delta的引用marker缓冲；对应测试覆盖空来源和来源格式。可移植有限状态过滤及测试思路，无法将Go文件直接导入Python；不要沿用历史文章的旧Python路径来声称源码已审查。过滤不存在的ID只保证格式/身份，不证明结论被支持。
4. **PaperQA `c692d0d`（Apache-2.0）**：`GatherEvidence`、`GenerateAnswer`分开，Context保存关联Text/Doc和score。适合借鉴“先积累证据、后作答；失败时再取证”的边界。生成的context/summary不是原文，其通用论文检索、外网搜索和默认多来源要求不能照搬成单教材门槛。
5. **STORM `fb951af`（MIT）**：`knowledge_curation.py`、`interface.py`区分信息收集和后续文章生成，可参考问题拆分与多角度资料收集。它是长文研究系统，不是经证明的学生测评系统；不能照搬多轮research流程作为每次短问答前置步骤。
6. **ColPali `97487f8`（MIT代码）**：`processing_utils.py::score_multi_vector`是真实多向量late interaction；可调用公开模型/processor做页面召回实验。它返回相关页面，不自动产生已核验的段落框或结论支持。权重及底座许可另查；本机GPU已承担BGE，不能未经峰值显存与中文教材评测就再常驻视觉大模型。

### 对EvidenceItem示意的必要修订

- 页码不改已有公共契约：`PDFRect.page>=1`，坐标在0—1；PyMuPDF内部才用`page-1`。若适配零起始库，只在边界转换一次。印刷页码另存page_label，缺失允许为空。
- 一个引文可能跨行/跨页，必须支持多rect和页范围，不压成一个bbox。图像原裁剪坐标、PDF坐标、浏览器CSS坐标分开。
- `object_id`必须挂document_id+version并落到真实块/素材；显示的[1]不是永久证据ID，重排和跨工具合并不改变身份。
- `source_verified: bool`不够：至少区分身份、原文一致性、坐标可定位、语义支持、人工审核这几种状态。重排分数高不等于以上检查全部通过。
- 模型解释、图谱摘要、OCR、VLM读图输出、教材原文、学生原话、掌握证据应分类型，派生项指向原始证据。图片只召回caption时，禁止声称已读取像素；图示箭头不直接证明因果。
- 表格保留表头、合并单元格和行列身份；多页表/续表关联作为候选，不能自动把实验数据与别的表头拼接。公式保留原文/OMML或LaTeX及符号邻文，不通过旧离散数学符号规则推断心理学统计结论。
- 保留现有reader_goto的requested/applied回执，任务/会话/版本失效时拒绝旧动作；“HTTP发出成功”不是“学生页面已跳转”。

### 第二批决策

优先级：①跨层薄契约及现有证据字段对齐；②补图片/表格/公式对象关系与缺失状态；③逐问题子目标覆盖；④离线比较目录导航回退和页面视觉召回。跨章不必一律图检索：少量明确章节可并行混合检索，只有关联需求、覆盖不足时才升级。用户例句“第三章信度”必须验证真实目录，不能把示例的章号当教材事实。

源码：

- [LlamaIndex引用节点](https://github.com/run-llama/llama_index/blob/619d74664e8404612038bc15a1a40c686037277c/llama-index-core/llama_index/core/query_engine/citation_query_engine.py)
- [递归检索](https://github.com/run-llama/llama_index/blob/619d74664e8404612038bc15a1a40c686037277c/llama-index-core/llama_index/core/retrievers/recursive_retriever.py)
- [RAGFlow流式引用过滤](https://github.com/infiniflow/ragflow/blob/12d9a38e24bf3fb8573b83bc41a2fe75dcd2c281/internal/agent/component/citation_sources.go)
- [PaperQA证据与生成工具](https://github.com/Future-House/paper-qa/blob/c692d0dfeac4a0296599f7fe21a253a58b7ac12a/src/paperqa/agents/tools.py)
- [STORM资料收集](https://github.com/stanford-oval/storm/blob/fb951af7744dab086e34962e9bc6fe878e145f83/knowledge_storm/storm_wiki/modules/knowledge_curation.py)
- [ColPali处理及评分](https://github.com/illuin-tech/colpali/blob/97487f8871ff4d5d2284411fe61bdcd2cfe99894/colpali_engine/utils/processing_utils.py)

## 第三批：工具执行、学习Agent、LangGraph与评估论文（已完成）

### DeepTutor：我们已经复用了，重点是补接线而非再迁移一套

官方`HKUDS/DeepTutor@1ea7df1`（Apache-2.0）的`capabilities/protocol.py`定义LoopExtension/KnowledgeCapability，后者支持收窄到本能力工具；`capabilities/reading/capability.py`封装阅读能力，`runtime/registry/scoped_registry.py`在执行时拒绝未授权工具。能力、工具与编排分层确有源码依据，但不能把prompt里的工具列表当授权。

本次对比本地vendor与此快照：`scoped_registry.py`、`learning/assessment.py`逐字节一致，`capabilities/protocol.py`不一致。因此“我们是否只能借鉴思路”的答案是：已有部分成熟上游代码正被直接复用；不能因此推断整个vendor等于当前上游、或直接覆盖不一致文件。

测评适配器把最新投影、不可变作答记录及可信知识点链接分开，未评分保持ungraded，先有真实绑定再消费证据。可继续复用现有原生路径。**教师审核HMAC、明确独立/辅助证据、宿主epoch和跨库授权是本项目的额外约束，不是引入上游即可自动获得。** 优先收敛TA5明确的NT3单入口、NT8删除传播；不另写第三套测评数据库，不让“LLM觉得答对”覆盖正式rubric。

### LangGraph：建议使用库，通过现有授权dispatcher适配

- `langgraph@e5c961d`为MIT，`ToolNode`支持同步/异步多工具调度和工具异常处理；`types.interrupt`及checkpoint base提供真实暂停与执行状态持久化。应固定经过验证的发行版，调研main快照不等于安装建议。
- 第三、四层共用一套宿主编排。第四层可提供子图/普通节点接口，不额外启动Agent Server，不在每个子图各自建持久化权威。
- 本项目ToolResult包括sources、pause_for_user、terminate_turn和只供模型使用的图像model_message，转换成ToolMessage时必须分别保留，不能只取content。
- **interrupt恢复会从节点开头重跑**。评分、学习记录和reader动作必须使用既有command_id/request_id、revision/epoch和回执；checkpoint不是跨库事务，也不保证外部工具只执行一次。
- graph state只保存可序列化ID、版本、结果摘要与执行状态；不保存SDK客户端、SQLite session、线程锁、权限服务、模型会话或学生密钥。恢复时重建授权并检查教材版本。
- 保留现有SSE正文轮次/撤回/正式保存语义。GraphInterrupt/GraphBubbleUp是控制流，不能被现有宽泛异常捕获吞成普通失败；取消/超时后晚到的工具不得登记来源或写成绩。
- 当证据不足时只做有预算、去重的补检索，并返回缺口。策略改变由第三层负责；第四层不能擅自强制出题、写掌握或改学习路径。

### MCP：需要外部提供方时使用官方SDK

`python-sdk@d7845c0`为MIT，`ClientSession`确有list_tools/call_tool和outputSchema结果校验。当前main也出现input-required等演进接口；应绑定实际稳定协议/SDK版本，不能将旧文档示例与当前main随意混用。

MCP解决外部服务连接，不证明其返回内容是教材证据。工具描述、annotations和外部返回均不是本平台授权；身份、scope、参数及输出校验继续由宿主负责。当前只有一本本地教材，没有具体外部服务需求，**不将所有本地函数改成MCP服务**。只读工具可按已有授权自动执行；正常作答提交沿用用户动作授权，不额外增加“允许AI执行”确认。

### 论文与源码的实际可迁入范围

| 论文 / 源码 | 已核验内容 | 对本项目的决策 |
| --- | --- | --- |
| [Self-RAG](https://arxiv.org/abs/2310.11511)，`AkariAsai/self-rag@1fcdc42`，MIT | 原生实现有reflection tokens、专门7B/13B模型和搜索/推理脚本，不是给任意API加一段反思prompt | 借鉴“按需检索、相关性与支持性分开检查”；不导入训练/推理栈，也不把DeepSeek自评宣称为Self-RAG算法。 |
| [CRAG](https://arxiv.org/abs/2401.15884)，`HuskyInSalt/CRAG@de7c296` | 训练检索评估器并按质量转向知识精炼/外网，README和train_evaluator均可查；该tree未找到LICENSE且API license为空 | 只借鉴分级纠错与有限补检索，不复制未明确授权代码、不搬未经中文教材验证的评价器，不自动外网覆盖教材。 |
| [RAGAS](https://arxiv.org/abs/2309.15217)，原地址跳转`vibrantlabsai/ragas@298b682`，Apache-2.0 | Faithfulness先分解陈述再做NLI判断；LLMContextRecall要求user_input、retrieved_contexts、reference | 直接复用离线评估库及固定数据格式，不作为每轮在线必经评委。Context Recall并非不需要参考答案；模型裁判要用人工抽查校准。 |
| [ColPali](https://arxiv.org/abs/2407.01449) | ICLR2025，页面图像多向量/late interaction；引入ViDoRe页级检索任务 | 只有图表版面导致文本检索漏召回时做离线小样本对照；页面召回与像素理解/坐标引用分开测量。 |
| [RAG-Anything](https://arxiv.org/abs/2510.12323) | 多模态对象及跨模态关联图 | 对象关联/邻文扩展可借鉴，模型生成描述明确标为派生资料。无证据证明整包替换能优于当前教材。 |
| [LightRAG](https://arxiv.org/abs/2410.05779) | 实体与关系检索、图与向量协同 | 保留现有已有索引及worker，对多对象覆盖做评测，不把论文总体结果当我们的跨章准确率。 |
| [ALCE](https://arxiv.org/abs/2305.14627) | 将回答正确性和引用质量分开评估 | 补结论级引用支持率/完整率，不能用“每条回答都有引用”代替评价。 |

### 第三批决策

直接复用现有DeepTutor测评/工具代码、LlamaIndex检索组件；新增LangGraph时使用依赖及薄适配；RAGAS仅离线。优先解决两个实际难点：①执行重放时不重复写学习证据；②教材证据、学生观察与AI推断的类型边界。保留文中Tool/Skill/MCP区分，但Skill不是可信代码权限，提示词不能授予额外工具或自动写入。

源码：

- [DeepTutor能力协议](https://github.com/HKUDS/DeepTutor/blob/1ea7df155447f4caf0e3abc86b3ff5395479cd4a/deeptutor/capabilities/protocol.py)
- [DeepTutor阅读能力](https://github.com/HKUDS/DeepTutor/blob/1ea7df155447f4caf0e3abc86b3ff5395479cd4a/deeptutor/capabilities/reading/capability.py)
- [DeepTutor测评记录](https://github.com/HKUDS/DeepTutor/blob/1ea7df155447f4caf0e3abc86b3ff5395479cd4a/deeptutor/learning/assessment.py)
- [LangGraph ToolNode](https://github.com/langchain-ai/langgraph/blob/e5c961d7fbe7ca6fdd4c94c84d90511372514d55/libs/prebuilt/langgraph/prebuilt/tool_node.py)
- [LangGraph interrupt源码](https://github.com/langchain-ai/langgraph/blob/e5c961d7fbe7ca6fdd4c94c84d90511372514d55/libs/langgraph/langgraph/types.py)
- [MCP结果校验](https://github.com/modelcontextprotocol/python-sdk/blob/d7845c073a2b9ba5ab2817ecf93d3e45ef24cd14/src/mcp/client/session.py)
- [RAGAS召回指标依赖](https://github.com/vibrantlabsai/ragas/blob/298b68274234c060deacab3cf5fb52aa3a20e885/src/ragas/metrics/_context_recall.py)
- [Self-RAG原始推理](https://github.com/AkariAsai/self-rag/blob/1fcdc420e48f50a7d7ab1ece5494221b93252e99/retrieval_lm/run_short_form.py)
- [CRAG训练脚本](https://github.com/HuskyInSalt/CRAG/blob/de7c2961ae624a1483a138c5798e1f6d0c4fb0e0/scripts/train_evaluator.py)

## 第四批：综合复用决策、性能与实施边界（已完成）

### 不采用原材料的整包P0列表

材料的总体方向合理：离线解析与在线执行分开、现有工具复用、证据可追溯。但“MinerU、LlamaIndex、LangGraph、RAGAS同时P0”不适合当前项目。它把已有能力、新依赖、离线评估和公共编排改造放在同一批，难以定位质量变化。完整目标保留，按风险独立验收。

| 复用层次 | 推荐对象 | 具体方式 |
| --- | --- | --- |
| 当前继续直接复用 | 已固定DeepTutor、LlamaIndex、LightRAG、FastEmbed/BGE、PyMuPDF、PDF阅读器 | 沿用现有依赖和来源适配，不整体升级到本次调研main快照。DeepTutor既有出处账本记录上游基线`6cf793b`；新旧快照不能混算。 |
| 下一步直接采用库的候选 | RAGAS离线评估；LangGraph执行子图 | 分别隔离评估环境/执行环境；兼容依赖、现有事件、幂等、暂停和删除后才接公共路径。不是复制完整源码。 |
| 选择性适配代码 | RAG-Anything邻文提取和模态处理；Docling原生结构/HybridChunker | 保留本项目对象、字符范围和坐标，先小样本对照；模型输出是派生证据。不要安装两套全书解析/图谱管线。 |
| 思路和测试用例移植优先 | RAGFlow流式引用ID检查、PaperQA证据/答案分离、STORM多角度资料收集、PageIndex目录导航 | 跨语言/异步/数据库耦合使直接复制成本高于已有服务适配；只迁移必要行为并保留来源声明。 |
| 有明确缺陷才做实验 | MinerU难页修补；ColPali页级视觉召回 | 要有实际漏检/解析错误样本，单独计时、显存、定位质量；结果有收益再上线。 |
| 本阶段只借鉴方法 | Self-RAG、CRAG | 特训模型不兼容现有DeepSeek API；CRAG许可未明确，不摘取代码。 |
| 有外部提供方再接 | MCP官方SDK | 本地读取保持原函数/工具，不为协议统一额外增加网络和鉴权复杂度。 |

### 心理学教材特有的结构缺口

`structured_index.build_records()`在心理学模式实际转到`scripts/build_psychology_sample_index.py::records`。该脚本按小节/标题及约760字符合并切分，表格另存行文本，图片通过asset_ids关联。虽然另有`semantic_chunks.refine`，不能据其存在就声称当前心理学全书索引全部使用语义切片。

优先保留“实验问题/假设—变量操作定义—被试与分组—程序/控制—结果—解释和限制”的实验单元。长单元可以子切片召回，再补父块和相邻对象；不能把结果段独立切出后丢掉组别与条件。表格复合表头、续表、统计公式与符号释义，应进入缺陷样本。Docling的HybridChunker只解决其中的结构/token分配，不能自行识别实验设计语义，也不能用关键词把时间先后标成因果关系。

### 最小完整的跨层接口（建议，不是当前已实现）

沿用第三层现有decision及TaskContext，经适配得到：

- 请求：决策/请求ID、教学目标、所需证据类型、必须/可选需求、章节/选区范围、只讲解/提示等约束、预算。学生与课程权限由服务端注入，禁止模型指定别的学生或扩大grant。
- 结果：既有EvidenceBundle的投影、分类型学习记录、工具结果、按需求的coverage/missing、可用资源、执行状态/trace及reader动作状态。
- 状态：区分成功、部分满足、需澄清、无依据、执行失败、取消；工具失败和任务失败分层。映射既有任务状态，不直接重命名数据库中的全部status值。
- `ready_for_composition`不能由“有一条命中”决定。必需证据缺失时禁止生成对应结论，可返回明确限制的部分讲解；缺少可选插图不应阻止已有定义讲解。
- 第四层返回可用候选、缺失原因及可行替代；是否缩小教学目标、改动作或提问由第三层决定。第五层逐结论绑定证据，保留生成后支持性核验。

建议目录只新增必要的跨层模型/适配，不照抄原材料的几十文件目录。映射优先入口：`agents/course_search.py`、`knowledge/grounded_citations.py`、`agents/tools/first_wave*`、`memory/retrieval.py`、`integrations/deeptutor/assessment*`、`visualization/on_demand.py`。

### 缓存与并发：保留已有收益，先测缺口

1. 固定教材运行时已有版本快照、常驻图谱、索引/模型缓存、原文和素材映射。不要为“五级缓存”再引Redis或重复存储相同数据。
2. 教材共享缓存键至少绑定release/document hash、index版本、模型/重排/检索配置、scope；图像缓存还要绑定原图hash、裁剪、处理/VLM版本。图像理解结果与原始像素、裁剪文件分别管理。
3. 学生记忆、成绩、个性化结果不得只按query做跨学生缓存；绑定student/session、epoch、相关记录版本并执行读取授权。删除后重读；不能把老缓存重新写成新记忆。
4. 请求收据与reader applied回执是业务状态，不是可任意淘汰的查询缓存。不可用/超时不长期负缓存；未知提交结果重试原command_id。
5. 只读独立取证可并行；评分写入、目标切换、依赖前一步来源的工具有顺序。当前常驻LightRAG原生查询有所有权锁，不能仅加asyncio.gather就认定图存储可并发。
6. 跟踪上下文读取、路由、查询embedding、召回、重排、证据映射、图片、VLM、生成、保存；首字记录区分处理记录、候选正文和最终保留正文。历史单次提速记录不足以承诺当前p95或认定生成永远不是瓶颈。

### 建议的验收实验

详细样本/指标见`EVALUATION_AND_PARALLEL_BOUNDARIES.md`。先构建60个分层黄金问题作诊断基线，再扩到150—200个冻结问题和真实盲评；不是宣称60例足以证明99%可靠性。不必在没有标注规范前一次堆300—500例。

- 同一教材快照比较：现有完整路径；混合召回不重排；混合+重排；目录父子扩展；图检索复杂覆盖；图表难例的视觉召回。一次只改变一个因素。
- 必须测按问题需求的全部证据覆盖，而不只算“至少命中一个正确块”。把空结果、缺某章节、错误图号、旧版本、拒答和模型幻觉纳入分母。
- 引用身份/原文/定位、结论支持、教学质量分开打分。来源正确≠支持结论；拒绝所有回答也不能得到高质量分。
- 训练/调参集与最终留出集隔离；同一实验/近重复问题分组划分，避免教材例句泄漏。RAGAS评委报告模型/版本、prompt、失败及人工一致性，不当作教师金标准。
- 工具关注授权阻断、错误状态、重放不重复评分、删除/换版后失效、真实reader applied及暂停恢复。单元测试通过不能代替页面动作完成。

### 与第三层并行实施的边界

可独立进行：第四层黄金集与取证改进、对象定位补齐、只读工具输出校验；第三层使用固定证据/失败样例验证策略。先冻结薄契约，随后各自稳定SHA交接。

公共文件`task_service.py`、`agent_loop_service.py`、`agent_loop.py`、`llm/answer_events.py`、公共前端事件、数据库迁移及LangGraph state/checkpointer由集成负责人单写入。第四层不顺带修改六维标签、教学动作优先级、掌握判断，也不复制第三层未提交代码。

推荐顺序：**统一契约和基线评估 → 补齐对象/覆盖/输出状态 → LangGraph只读子图试点及重放契约 → 测评单写入/删除接线 → 选择性解析或视觉实验 → 同版本联合验收**。LangGraph与NT3的执行权交接需合并设计，不能两边同时当任务主循环。

## 调研结论与未验证事项

1. 目标应是将现有取证与工具能力收敛为统一、可追溯的服务边界；我们已有核心检索/引用/工具运行，不需要重新搭建一整套知识平台。
2. 最先投入的不是更强的模型或更多框架，而是实验语义单元、多模态证据身份、按需求覆盖以及执行幂等/单写入。成熟上游能提供组件，不能替代本教材和本业务的验证。
3. 本轮完成四批原文阅读、18个仓库的身份/许可快照、选择性源码与论文核对。文件清单、固定SHA、下载文件hash和本地源码hash见`SOURCE_AUDIT.json`。已下载不等于逐行审阅，重点函数及调用边界已在正文列明。
4. **未安装新组件、未执行上游代码、未跑模型或性能实验、未改变数据库/教材/服务/开关，未将上游完整源码复制进业务目录。** 因此“建议可复用”属于静态工程判断，不是接入成功或性能提升承诺。
5. 仍需验证：实际解析缺陷集、图表/公式对象覆盖、教师批准题目与rubric、第三层最终契约、LangGraph稳定版依赖兼容、NT3/NT8、并发和GPU峰值、人工支持性标注。通过这些条件后再写正式实施计划。
