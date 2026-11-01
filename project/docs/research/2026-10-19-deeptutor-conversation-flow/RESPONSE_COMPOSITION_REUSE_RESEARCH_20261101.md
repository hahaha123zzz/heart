# 第五层：动态教学内容组合与回答生成源码调研

日期：2026-11-01。宿主基线：6122724，分支 codex/ta5-acceptance-20261029。

本次依据用户第五层讨论稿，核对本地宿主、DeepTutor、OpenTutor、OpenMAIC 源码，并查阅 ScaffoldLM、MRBench、PydanticAI、DSPy、AI SDK 官方材料。交付为静态源码调研及方案建议；未改业务代码、安装依赖、运行模型或测试、切换服务、改数据库或推送代码。源码身份和文件哈希见同目录 RESPONSE_COMPOSITION_SOURCE_AUDIT_20261101.json。

## 1. 结论

支持“教学策略驱动、语义内容分块、证据约束、类型化呈现”。第五层应在现有 TaskService → AgentLoop → 证据发布 → SSE/ChatMessageRenderer 内形成内容组合能力，保留原有目标、授权、取消、epoch、题卡和学习状态权威。

不建议照搬 BookCompiler，不建议默认每块单独调模型，不建议将 OpenMAIC 幻灯片 DSL 作为聊天回答协议。最有价值的复用是：DeepTutor 模块状态与可重试失败处理；本项目已存在的结构化展示与证据发布；OpenMAIC 类型/版本/校验分离及测试思路；OpenTutor 的按需 prompt 片段。ScaffoldLM、MRBench 分别提供教学连续性与评价依据，不是可直接替换当前运行时的成熟服务。

普通回答的默认生成路径不新增必经 Planner 模型调用；可在一次生成中得到多个语义块。长篇导学、独立图表等有明确依赖的复杂任务才启用多阶段生成，并共享活动预算。

## 2. 对讨论稿的核实与修正

| 讨论稿内容 | 核实结果与落地修正 |
|---|---|
| DeepTutor SectionArchitect 有 LLM 和静态回退 | 属实，但静态模板通常组合多个千字 SECTION、测验、图、代码等，不能原样用于短对话 |
| Section 是两阶段生成 | 属实：一次大纲 + 每个子节一次填充；填充 gather 的任一异常会使该 SECTION 整体失败，不等于子节级持久化、独立修复 |
| Compiler 支持并行、部分成功和重试 | 属实：块并发默认1，可调 semaphore；READY 块跳过；失败按 metadata 决定重试；页面可 PARTIAL。并发分支没有通用 depends_on DAG 调度，不能据此声称完整依赖图已可搬用 |
| 复用即可保证教材依据 | 不成立。optional_rag_lookup 明确把检索当可选项并吞掉检索失败；SourceAnchor 只有 kind/kb_name/ref/snippet；生成器 READY 也不表示语义、教材版本或引用已核验 |
| OpenMAIC 是“不让模型产生 HTML” | 不准确。其幻灯片文本元素 content 是 HTML 字符串，BaseTextElement 用 dangerouslySetInnerHTML，useInnerHtml 仅稳定对象身份。不能凭结构化 DSL 或这个组件断言安全，也不能推断整个产品没有其他清理层 |
| 当前 Python/FastAPI + React18，正在 LangGraph 改造 | Python/FastAPI 属实；React18 位于独立 reader 子项目，聊天主体是 vanilla JS。检索源码和依赖未见当前主回答入口运行 StateGraph；不能把拟议 LangGraph 子图当作既成条件 |
| 第三层已经给出 TeachingStrategyPlan | 当前有 TeachingPlan、TeachingTurn、策略库与条件 prompt，未检出同名统一类型。应对齐现有第三层建设，不由第五层另外重判策略 |
| 第四层已经统一给出 EvidenceBundle | 已有旧引用 EvidenceBundle，也新增 EvidencePackage/RequirementCoverage；二者不等价。后者的 execute_requirements 目前主要由测试调用，主回答仍走共享检索与 coverage_report；第五层需明确适配真实入口 |
| 程序能检查“证据是否支持一句话” | 程序可查身份、范围、版本和引用闭包；开放语义的充分支持不能仅凭 ID、字符串相似度或 schema 证明。继续调用受控语义核验/专用规则并保留人工抽查 |
| 每种模块各自 Generator 即各调一次 LLM | 不等价。语义模块、模型请求、渲染组件是三个维度；可批量生成后分别验证 |
| 16种模块分类完全分离内容与展示 | 列表仍混入 table 等表现形式。comparison 是语义内容，table 是可选视图；formula 应区分公式讲解任务与 LaTeX 视图 |

## 3. 本项目现状与改造入口

| 文件/符号 | 已有能力 | 第五层缺口/复用边界 |
|---|---|---|
| main.py::_execute_task_turn | 普通 Q3、文字选区、旧回答、练习和互动入口分流 | 不能只改旧 ResponseGenerator 就宣称普通聊天生效；需要共用组合契约及各入口适配 |
| agents/adaptive_tutoring.py::TeachingTurn、teaching_policy.py | 教法、待答、提示深度、困难支持、画像/偏好约束 | 组合层消费其结果，不再新增策略权威或把“懂了”改成掌握 |
| agents/prompt_blocks.py::PromptBlock/render_blocks、loop_prompts.py | 已有按名称组装 prompt 和语言约束 | 是 prompt 片段，不是学生可见语义块；可沿用，无须再复制同类工具 |
| agents/response_generator.py::ResponseGenerator.generate | 已结合计划、偏好、证据、追问与反馈生成 | 多数仍是整段文本与 prompt 约束，没有通用响应块计划 |
| agents/learning_cards.py | strict Pydantic 的 step_reveal/concept_comparison；presentation_text 程序生成正文 | 优先扩展已有正文/卡片同源模式；目前结构化回看主要由特定表达触发，还不是任意策略驱动组合 |
| agent_loop_service.py::final_gate/_publish_gate | 教学动作登记、引用编号、跨对象覆盖、来源发布与质量核验 | 主要面向整轮；没有通用块级必需项、依赖失效和定点修复收据 |
| 同文件固定教材分支 | 无上标时存在直接发布且无引用数组的快速路径 | 这是现有行为边界；第五层若要求所有事实块可追溯，不能将其直接当成已完成块级引用保证，须另定无引用块政策 |
| models/evidence_execution.py::EvidencePackage | 需求覆盖、版本/范围、真实来源、像素检查、检查点投影 | 首先完成与实际生成入口的接口绑定；ready_for_composition 是内部计算值，不接收客户端宣称 ready |
| knowledge/grounded_citations.py::EvidenceBundle | 引用、正文结论与来源重映射 | 保留现有出版器；逐块发布时必须补稳定编号策略，避免最终压缩编号使已显示上标错位 |
| llm/answer_events.py::AnswerEvents | answer/round/seq、草稿、撤回、最终权威替换 | 目前是轮级发布，新增块状态时要复用任务身份及重放，不能另建无校验的 SSE |
| frontend/chat-renderer.js、learning-cards.js | 稳定消息键、独立组件生命周期、安全 Markdown/已有卡片 | 可扩展 block_id 渲染；不必为聊天整体改成 React 或挂载幻灯片画布 |

当前有“第五层零件”，缺少的是：统一回答计划、块类型契约、生成批次与块的映射、声明级证据绑定、依赖与修复边界、块级稳定发布和评价集。

## 4. DeepTutor 可复用清单

固定提交：6cf793bd868ba5ecbe64722936d4be8fab5a01df，Apache-2.0；源码已在本机及 vendor 中。先查已迁入能力，避免重复复制。

| 源码 | 已核实行为 | 复用决定 |
|---|---|---|
| book/blocks/base.py::BlockGenerator.generate | GENERATING/READY/ERROR、payload/anchors/metadata、取消继续上抛 | 可抽取状态包装与契约骨架；增加本项目 guard/预算/证据检查。不能把 READY 当“已核验可发布” |
| 同文件 _classify_failure/_failure_metadata | 将故障转为 kind/retryable/source | 可适配分类与测试。使用字符串启发式，不照搬为全部业务判据；输出异常须先脱敏 |
| BlockGeneratorRegistry | 按类型注册、get/types、惰性默认注册 | 可迁入小型注册骨架，但已有类似能力时直接沿用；不能将其说成现成内容调度器 |
| BlockContext | 章节/页面/块/探索缓存上下文 | 只保留思想；本项目应使用只读、精简、带任务/策略/证据版本的上下文，不导入 Book/Page 持久模型 |
| SectionArchitect.plan_blocks_async | LLM候选校验、截断、类型过滤、静态回退 | 适配类型过滤、深度约束和回退测试；不复制千字/测验/代码模板 |
| compiler.py::_generate_with_retry | retryable 才重试，次数和退避有界 | 迁入控制结构，替换 sleep/事件/保存接口；全轮预算下限制总修复，取消/换版/删除不重试 |
| _finalize_page_status | READY/PARTIAL/ERROR 聚合 | 参考聚合；聊天必须区分必需块失败与可选块失败，不能“任意一块成功”就宣布完整完成 |
| compile_page | 并发、READY 跳过、块结束事件、逐块保存 | 只适配局部执行语义；替换 BookStorage、BookStream 和整页共享可变对象，补依赖检查及原任务收据 |
| SectionGenerator | 大纲+子节填充、选取探索片段 | 不作为默认聊天路径；仅长篇导学候选，需实测成本与小节修复粒度 |
| _rag_helpers.py / _llm_writer.py | 自行查 KB、全局模型配置/完成接口 | 不迁入：第四层负责检索，宿主 LLMClient 负责模型调用、连接池和活动预算 |
| models.py::SourceAnchor/Block | 宽松 payload 与轻量来源锚点 | 不直接作为正式协议。保留本项目 SourceRef 的版本、范围、原图和出版身份 |

测试可参考 tests/book/test_compile_scheduling.py、test_block_type_controls.py、test_source_partitioning.py、test_llm_writer.py 等；本轮仅核对源码/测试位置，未运行上游测试，不宣称其在本项目通过。

额外调用成本：一个 SECTION 有 n 个子节时，成功路径至少大纲1次+填充n次；另有章节规划和可能的块过渡语句生成。并行减少部分墙钟等待，不会减少调用数，也不能保证首段更快。

## 5. OpenTutor / OpenMAIC

### OpenTutor

固定提交 a890519f3632efa14cf24449b366b3b9d901eecf，MIT。

- apps/web/src/lib/block-system/types.ts、registry.ts：12种工作区块、来源/配置/可关闭、lazy组件注册属实。它们是工作区，不是回答内部语义模块。适配注册元数据和延迟加载思路，不搬整个课程面板。
- apps/api/services/agent/agents/tutor.py::build_system_prompt：按学习模式、任务、疲劳与已有元数据插入片段。沿用本项目 PromptBlock 消费已核实状态；不要为第五层重新靠关键词诊断疲劳/认知负荷。
- TutorAgent.profile 明确允许材料不足时 web_search，且要求底部 Sources。两项均不符合本项目固定教材、上标引用的约束，不复制完整提示或工具权限。

### OpenMAIC

固定提交 d128ef67c920571a86ce8a7c0430185689ab3d45，根及所查 @openmaic/dsl/renderer 为MIT；mathml2omml另查子包许可，不是第五层必需依赖。

- dsl/src/validate.ts：结构校验与跨语言 JSON Schema 分离，ValidationIssue 带路径。值得迁入错误路径、可判别类型与测试设计。它的结构校验是子集，不代表完整值检查，更不保证教学真实性。
- dsl/src/version.ts：数据版本与运行时版本分开、纯迁移与错误路由拒绝。适配原则；不原样复制几百行幻灯片迁移及其历史字段。
- generation/src/pipeline-types.ts::AICallFn：注入模型函数、生成包不自行读密钥，这点适合借鉴；所查签名仅 system/user/images→Promise<string>，没有原生携带宿主 deadline/取消/任务guard，不能称为即插即用。
- generation/src/generation-retry.ts：有 AbortSignal、取消退避、重试事件和状态分类。默认 maxRetries=5，且将409列为可重试；不能照搬到本项目 revision/epoch 冲突。Python核心保留宿主预算；TS可借用取消语义，模型与写操作重试分别处理。
- renderer是React的PPTist幻灯片画布，文本允许HTML、使用绝对坐标；不等于安全聊天Renderer。公式/表格纯工具可按需评估，但先复用已有Markdown、公式、卡片和教材原图。
- 可参考 dsl/test/{validate,schema,version}.test.ts、generation/test/generation-retry.test.ts，不把读取到测试等同于迁入验收。

## 6. 教育研究与其他工程资料

ScaffoldLM 的论文与仓库真实存在，数学多轮脚手架是其研究范围；所查 model_serving/structured_tutor.py 的 TutorSession 可用于理解步骤如何进入生成上下文，但代码会把 Express understanding 推进到下个步骤，且用英文答案标记结束会话。仅借鉴状态摘要，不搬推进、结束判据或同次隐藏答案；CC-BY-4.0按项目声明核对，实际迁入前仍需固定SHA。该远端本轮未能锁定提交，不列为可立即迁入来源。[论文](https://aclanthology.org/2026.acl-long.325/)；[所查源码](https://raw.githubusercontent.com/BNU-ERC-ITEA/ScaffoldLM/main/model_serving/structured_tutor.py)。

MRBench 的原论文八维、192对话/1596回答属实，是数学错误/困惑对话评价，不是心理学效果证明。当前README另有V2/V3，不能把V3新增样本当成完整八维标注；数据声明CC BY-SA 4.0。优先借鉴标注维度、自建教材样例，使用原数据须分别处理署名和衍生许可。[论文](https://aclanthology.org/2025.naacl-long.57/)；[版本及许可](https://github.com/kaushal0494/UnifyingAITutorEvaluation)。

AutoTutor提供教学对话研究依据，不是本次确认可搬用的现代Python组合库；不将论文学习增益外推到本项目。[论文信息](https://pubmed.ncbi.nlm.nih.gov/15354683/)。2025个性化反馈研究的35%结果属于特定代数ITS/GPT-4样本，支持保留质检，不是所有模型错误率。[原文](https://link.springer.com/article/10.1007/s40593-025-00505-6)。

PydanticAI官方说明结构化输出的流式部分验证与最终输出控制存在区别；部分JSON通过不等于最终完整，更不等于证据核验。借鉴验证反馈，保留已安装Pydantic，不增设第二Agent框架。[官方输出文档](https://ai.pydantic.dev/output/)。

DSPy只作离线优化候选：固定模型/数据划分，优化内容prompt，留独立测试集与人工抽查；不在线自动改prompt，不导入真实学生隐私。[官方优化器文档](https://dspy.ai/current/diving-deeper/choosing-an-optimizer/)。

AI SDK的自定义data part用稳定id更新同一块，进度可标transient不写入历史；可借鉴到现有Python SSE，不要求引入其React运行时，也不认为该协议自带教材校验。[官方说明](https://ai-sdk.dev/docs/ai-sdk-ui/streaming-data)。

讨论稿中AIME-Con评价一致性的具体论文未给出可唯一核实条目，本轮不拿它作为设计依据。EduAgent未纳入源码级候选，未凭star或少量提交判断成熟度。

## 7. 推荐的组合边界与协议

### 7.1 统一输入

- 任务身份、revision、学生/会话、epoch与活动deadline由TaskService提供。
- 第三层提供目标、允许动作、提示深度、禁止事项和待答状态；缺失字段先用适配器映射现有TeachingTurn/TeachingPlan，不复制分类器。
- 第四层提供受控SourceRef、逐项覆盖、像素是否实际进入模型、资料版本和执行收据。第五层只能上报缺口，由既有循环回到第四层，不从Generator自行检索。
- 只投影相关画像/偏好和当前步骤摘要；不复制全部历史、私有题目答案、模型思考或任意工具权限。

### 7.2 契约建议（非本轮已实现类型）

ResponsePlan保存strategy_version、target_id、required与optional目标、预算、交互政策及BlockSpec。BlockSpec包含稳定block_id、semantic_type、view_type、purpose、required、depends_on、evidence_requirements、expected_claims、生成批次。

ResponseBlock使用按semantic_type可判别的严格payload；同时带block_revision、输入依赖摘要、claim与source_id绑定、provenance_kind、生成/验证/发布状态。避免所有payload永久使用dict吞掉未知字段。编排元数据不让模型自行填写授权或publish状态。

LearningResponse保存schema_version、response_id、task identity、plan revision、blocks、服务端引用表、coverage_summary、complete/partial/insufficient/failed/cancelled。next_action只作受控建议，实际推进仍由Q2/Q5工具执行并回执，不能把模型JSON当导航指令。

### 7.3 全量能力映射

| 语义能力 | 优先已有资源/呈现方式 | 特殊约束 |
|---|---|---|
| direct_answer/definition/explanation | 单次正文生成+已有Markdown | 直接回应本轮对象，有原文/解释来源区分 |
| procedure | step_reveal或编号文字 | 当前步骤与完整流程区分 |
| comparison | concept_comparison或文字 | 每个比较对象有对应证据，不固定强制表格 |
| worked_example/analogy | 原文案例或标明生成的教学示例 | 概念依据与案例来源分别标记，不把新案例说成原书 |
| misconception/counterexample | 已核实学生原话和相关定义 | 无诊断证据不贴误区标签；不公开私有答案 |
| formula_explanation | 已有公式/Markdown/原图 | 符号、条件、原图是否可见分别检查 |
| visual_explanation | 已核验教材图、已有图解工具结果 | 原图缺失不伪造；概念示意与教材原图分开 |
| guided_question | 既有teaching_step和pending契约 | 问题放最后并停止，明确不出题时禁用，不新增正式分数 |
| teacher_item | 现有已审核题卡ID与版本 | 模型不生成答案键或伪造审核 |
| recap/next_step | 已完成内容投影、既有路径服务 | 不把一次回答当覆盖或掌握，不在第五层重排课程 |

table、latex、figure、interactive是视图/资产维度；不要求16种能力各自拥有一次模型调用和独立服务。

### 7.4 生成、失败及发布

1. 普通路径：规则编译ResponsePlan → 同次模型生成多个语义块 → 分块验证 → 程序组装，不新增必经Planner或最终整段重写。
2. 复杂路径：先校验依赖无环，允许无依赖任务有界并发。依赖输入固定到版本摘要；上游修复后所有受影响下游失效，不能只修上游还保留旧总结。
3. 全轮模型次数、token、工具与repair共用预算；不是每块各自可无限重试。永久身份/版本/epoch错误直接终止，临时模型错误有界修复。
4. 必需块失败不能宣布完整回答；可选独立块失败可省略并注明。比较题只查到一方须明确partial，不能硬凑另一方或假称完成。
5. 流式先发进度，闭合且验证完成的块才作为正式内容提交；候选若展示须与已保存内容区分。引用编号在已提交块中稳定，不在最终整段重新编号。已发布块不能被后到的旧revision覆盖。
6. idempotency包含task/plan/block/input revision，沿用现有仓储与回执。取消、删除、换版后拒绝迟到结果；刷新只恢复合法已保存块，不自动重新执行写工具。
7. JSON结构、来源真实、语义支持、教学策略、跨块一致性分层检查。独立模型评价可用于复杂疑难和离线抽样；没有证据前不规定每块都增加一次评审调用。

## 8. 三个用户场景与必要反例

- 自变量/因变量区别：直接区别+比较，可选同一案例；每个对象来源分开。只有一方证据时给缺口，不拼表凑答案。
- “还是不懂”：沿用目标，按第三层决定换解释/例子。若用户说“不出题”，不自动追加guided_question；若需要引导则登记后停止。已经用过的案例需可识别，避免原样重复。
- “这个实验没控制好”：先确定实验和学生质疑的环节。无明确第三层判断或证据时先澄清，不改写成已经确认的混淆变量，不入误区/掌握记录。

验收还需：正文与卡片语义相同、生成案例标签、页码与版本/原图SHA、部分图像不可读、闭合JSON前不发布、必需块失败、局部修复引起下游失效、引用跨块去重但已发布编号不漂移、流式断线/取消/重放、epoch删除、选区/普通/题卡入口一致、旧历史schema升级、预算耗尽仍诚实收尾。

## 9. 优先复用决策与下一步

优先沿用宿主已有卡片/证据/事件/预算；选择性迁入DeepTutor块状态和失败包装；适配OpenMAIC协议错误路径与版本测试；借鉴OpenTutor条件prompt。首版就定义完整能力边界与降级路径，但允许模型批量生成，避免模块数量成为调用数量。

进入实施计划前应先确定统一第三/四层输入适配、块级引用出版契约和发布状态机，再列源码迁入清单。LangGraph迁移、独立Node生成服务、BookStorage、全工作区React、在线DSPy优化都不是第五层的前置条件。

本轮只提供源码与文档证据；没有本项目延迟/质量提升实测，不能承诺直接达到任一上游产品效果。远端研究代码尚未固定SHA的条目只作参考，实际迁入时必须补锁定、文件哈希、依赖闭包、许可和本项目测试。
