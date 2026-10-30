AI 教学 Agent 自主工具选择与多 Agent 协作优化调研
专题调研｜2026 年 10 月 12 日｜GitHub 开源项目、Agent 论文、教育场景技术设计
一、先明确这次优化真正要解决什么
你们现在已经完成记忆、意图识别和教材检索的优化。下一步要解决的，是让 AI 在理解学生需求之后，能够自主决定是否需要额外能力，以及应该选择哪一种能力来完成教学任务。
例如，同样是学习《实验心理学》，学生可能提出：
- “什么是实验效度？”——可能直接结合教材解释。
- “我不会区分内部效度和外部效度。”——可能加载概念对比教学 Skill。
- “帮我分析这个实验结果。”——可能调用统计计算 Tool。
- “带我一步一步设计一个实验。”——可能进入实验设计辅导工作流。
- “根据我最近的表现安排复习。”——可能调用已有学习状态服务和复习调度工具。
这五种情况不应该全部走相同的 Agent 执行流程。
1. Tool、Skill、MCP、子 Agent 到底有什么区别？
这是架构设计之前必须明确的概念。
类型	本质	在你们项目中的用途
Tool	执行某个明确操作的函数或 API	统计计算、图形生成、题目评分
Skill	可按需加载的一套任务知识、规则与工作流程	实验设计指导、分步教学、统计解释
MCP	向 Agent 标准化暴露工具、资源和提示的协议	连接外部统计服务、实验平台、校内系统
子 Agent	具有独立指令、上下文及可用工具的任务执行单元	专门诊断实验设计、评审统计分析
Workflow	对多个步骤进行显式编排的执行流程	测验→评分→更新学习状态→反馈
这里有两个容易混淆的地方：
MCP 不等于另一种 Tool。 它是能力接入协议，通过 MCP Server 暴露的函数仍然可以作为 Tool 供大模型调用。
Skill 不等于子 Agent。 Skill 主要告诉现有 Agent 应该怎样完成某类任务；子 Agent 则是把任务交给另一个独立执行单元。
Agent Skills 规范使用 SKILL.md 加载任务说明与资源；MCP Python SDK 则能够通过 Python 函数声明暴露工具及参数结构。

GitHub
+2



2. 我建议的目标：不是完全自由调用，而是受约束的自主决策
学生问题 + 已有意图理解 + 当前学习任务
确定本轮教学目标


Capability Router（能力选择层）
判断是否需要工具，以及有哪些候选能力


直接回答
不调用额外能力


加载 Skill
应用专门教学方法


调用 Tool / MCP
执行计算或查询


委派子 Agent
处理独立复杂任务




执行结果验证 + 教学回答生成
检查执行是否成功，以及结果是否有助于教学


这不是强制四选一。例如可以先加载“实验设计辅导 Skill”，然后调用统计 Tool，必要时再委派专门的评价子 Agent。
真正需要优化的是四个决策：
1. 需不需要调用能力？ 避免简单问题也触发大量工具。
2. 应该选择什么能力？ 避免工具误选、Skill 误触发。
3. 是否需要组合多个能力？ 解决复杂学习任务，而不是机械地每轮只调用一个工具。
4. 什么时候停止？ 防止重复调用、死循环和不必要的子 Agent 委派。
成熟的 Agent 框架普遍已经能够进行基本的模型驱动工具选择。但这并不代表它们自动知道哪种教学方式对学生最好。因此，我们既需要借鉴通用 Agent 的执行机制，也需要加入教育场景专用的决策条件。
二、GitHub 重点开源项目调研
我把项目分成四类：工具动态选择、Skill 管理、MCP 接入、子 Agent 协作。
1. LangChain：工具动态选择最值得先看的项目
重点：LLMToolSelectorMiddleware、ProviderToolSearchMiddleware
这是本轮调研最直接的工程发现之一。
LangChain 当前提供了专门的工具选择中间件：
LLMToolSelectorMiddleware
它在主模型执行任务前，使用模型从可用工具中预选与当前请求相关的工具。可以配置最大工具数量、始终保留的工具以及选择模型。
例如，你有 30 个工具，学生只是问“帮我计算这组数据的平均值”，无需向主模型暴露所有 30 个工具，可以先选择统计计算相关的几个工具。
ProviderToolSearchMiddleware
对于支持服务端工具搜索的模型，可以将部分工具延迟暴露，直到模型搜索并发现需要的能力。是否可用取决于具体模型提供商和版本。
已核实的源码与文档：
- tool_selection.py：LLM 工具选择实现。
- Middleware 官方文档：工具选择与按需搜索配置。
  
  GitHub
  +1
对你们的复用判断
可直接集成
前提是当前执行链采用兼容的 LangChain Agent 接口。


如果目前用的是自建 FastAPI + 自定义 LLM 调度器，则不必为一个预筛选功能重构系统，可以参照这个实现开发一个独立 Capability Selector。
不足： 它负责筛选相关工具，但不会自动理解“是否应该引导学生思考”“某个提示是否过早暴露答案”等教学规则。
2. Deep Agents：Tool、Skill、子 Agent 统一管理的重点参考
重点：SkillsMiddleware、SubAgentMiddleware、按需能力暴露
这个项目与你提出的问题匹配度非常高。
它并不是简单地将所有工具放进 Prompt，而是提供了多个中间件协调能力：
- SkillsMiddleware：按需查找与读取 Skill。
- SubAgentMiddleware：把复杂任务委派给具有专门职责的 Agent。
- FilesystemMiddleware：提供可控的文件读取与操作能力。
- 权限与中断机制：限制某些操作，必要时要求人工确认。
还发现了一个更有价值的细节：
Deep Agents 支持在 Skill 被加载时，才使相关工具对模型可见。
这意味着你们可以把“实验设计教学方法”和“实验设计所需工具”关联在一起。平时不暴露全部工具，只有当 Agent 进入实验设计任务时才提供该能力。
相关代码：
源文件	可以研究的机制
skills.py	Skill 发现、读取和相关工具暴露
subagents.py	子 Agent 注册、描述与委派
graph.py	Agent 与中间件组合
ARCHITECTURE.md	完整执行架构说明
这些机制均能在仓库中找到具体实现。

GitHub
+3



复用建议：高优先级。
如果你们将来希望支持几十个 Skill 和多个子 Agent，它值得做独立原型测试。但我不建议马上整体迁移到 Deep Agents，因为它还包含你们可能并不需要的文件系统、Shell 和长任务执行能力。
3. OpenAI Agents SDK：子 Agent 协作与权限管理
重点：Agent.as_tool()、handoffs、动态能力限制、Guardrails
这个项目把两种子 Agent 协作方式区分得很清楚。
Agent as Tool
主教学 Agent
统计分析子 Agent

主 Agent 保持对话控制权，专家执行子任务并返回结果。


Handoff
主教学 Agent
专项辅导 Agent

把当前会话控制权交给专业 Agent，由其继续处理。



对于你们的 AI 助教，我更推荐第一种。
例如学生希望设计一项心理学实验，主 Agent 可以调用“实验设计诊断 Agent”，得到变量控制、设计风险和改进意见后，仍由主 Agent 组织最终教学回答。
这样可以维持统一的教师角色，避免学生感觉自己在不同机器人之间反复切换。
项目还支持根据运行上下文动态启用或关闭工具、交接目标和 MCP 工具，以及工具输入输出检查。

GitHub
+2



可核对的代码入口：
- examples/agent_patterns/：Agent 编排实例。
- agents_as_tools.py：专家 Agent 作为工具。
- handoffs.md：控制权交接实现。
- guardrails.md：安全检查与执行限制。
需要注意：SDK 的 Tool Guardrails 并不会自动保护所有类型的内置工具或 Agent Handoff，应用端仍需要自行维护权限校验。

GitHub
+1



4. Google ADK：另一套值得研究的多 Agent 方案
重点：专业 Agent 描述路由、单轮委派、任务模式
Google ADK 的设计很有参考价值：父 Agent 可以依据子 Agent 的 description 选择转交对象。
其实现区分了不同的委派模式：
- chat：子 Agent 可以接管交互。
- single_turn：子 Agent 完成一次具体任务并返回。
- task：子 Agent 独立执行有明确完成条件的任务，并返回结构化结果。
相关实现：
agent_transfer.py、agent_tool.py。

GitHub
+2



可以借鉴的思想： 子 Agent 不只是不同 Prompt，还应该具有明确的任务边界、输入输出 Schema、允许使用的工具和终止条件。
但与 OpenAI Agents SDK、Deep Agents 解决的是同一类编排问题。不建议同时引入三套框架。
5. MCP 与 Skill 的专门实现
项目	代码入口	具体复用价值
MCP Python SDK	MCP Server、Client	将现有 Python 服务标准化为 MCP Tool
LangChain MCP Adapters	MultiServerMCPClient	在 LangChain 中接入多个 MCP Server
Agent Skills 规范	规范文档	用统一格式组织教学 Skill
Anthropic Skills	skill-creator/SKILL.md	参考 Skill 编写和触发测试方法
这些项目的作用不同，不需要全部部署。尤其对你们当前的 Python 后端，如果一个统计函数已经在同一个 FastAPI 服务中，直接注册普通 Tool 往往比先封装成 MCP Server 更简单。MCP 主要在跨服务、跨框架、独立部署或第三方接入时发挥优势。

GitHub
+3



一个需要避开的旧项目
LangGraph Supervisor
langgraph-supervisor-py 已于 2026 年 9 月 20 日归档，其 README 也建议大多数新场景直接使用基于工具的 Supervisor 模式。
它的旧代码仍有教学和研究价值，但不应作为新项目首选的核心依赖。

langchain-ai/langgraph-supervisor-py · GitHub



三、论文调研：有哪些值得真正借鉴的路由算法？
我把论文分为三个研究层次：
- Agent 如何学会调用工具。
- 工具数量很大时，如何准确发现、筛选和组合。
- 如何评价调用行为，而不只是看最终答案。
1. ReAct：推理与执行交替进行
ICLR 2023 · ReAct: Synergizing Reasoning and Acting in Language Models
ReAct 的基本思想是让模型在任务过程中交替进行决策、行动和观察，根据工具反馈调整下一步计划。

arxiv.org
+1



对你们的价值是：
假设学生说：“帮我判断这个实验设计有没有问题。”
Agent 可以先获得实验方案的结构化描述，再调用实验设计检查工具，观察发现的问题。如果已经获得足够证据就停止，而不是无限继续调用工具。
借鉴层级： Agent 执行循环思想，可以直接使用成熟框架实现。无需自行训练 ReAct 模型。
2. Toolformer：模型应该学习何时调用工具
NeurIPS 2023 · Toolformer: Language Models Can Teach Themselves to Use Tools
Toolformer 研究如何让模型学习工具调用的位置、工具种类、参数与结果利用方式，并通过自监督方式构造训练数据。

arxiv.org



对你们最有价值的思想是：
“不调用任何工具”也应该是一种可被正确选择的行为。
例如讲解一个已有教材证据支持的简单概念时，不需要额外调用计算工具或子 Agent。
反之，遇到需要精确数值验证的统计题，应该调用确定性计算工具，而不是让 LLM 自己口算。
当前不建议为此专门微调 Toolformer 类模型。先建立不调用工具、错误调用工具与正确调用工具的评测样例，可能更符合你们项目的开发成本。
3. Gorilla / ToolLLM：工具多了，需要专门的工具发现机制
Gorilla · ToolLLM
Gorilla 研究基于 API 文档生成可靠的函数调用；ToolLLM 则围绕大规模工具数据、调用训练和评测展开研究。

arxiv.org
+1



它们共同提示了一个问题：
即使模型本身会 Function Calling，工具描述不清楚、参数不匹配或工具太多时，也可能选错工具。
这对于你们后续增加大量教学工具非常重要。
建议建立统一的 Capability Registry（能力注册表），每个工具明确记录其用途、适用情况、输入输出、失败条件和权限要求。
4. RAG-MCP：用检索技术筛选工具
2025 · RAG-MCP: Mitigating Prompt Bloat in LLM Tool Selection via Retrieval-Augmented Generation
这篇论文与本次优化方向非常契合。
它不是使用 RAG 检索教材，而是使用检索方法查找适合当前任务的工具描述。
基本方法是：
当前教学任务


搜索能力目录
工具描述、功能类型、任务条件


筛选 Top-K 候选能力


LLM 选择与执行


作者在其基准实验中报告，相比直接暴露大型工具集合，RAG-MCP 降低了工具相关 Prompt 开销并改善工具选择准确率。但这些是论文实验结果，不代表在你们的中文教学数据上会达到相同增益。

arxiv.org



建议： 当项目工具扩展到几十个以后，研究这种工具检索架构。早期工具较少时，可以先使用 LangChain 的 LLMToolSelectorMiddleware。
5. MCP-Zero：先找服务，再找服务里的工具
2025 · MCP-Zero: Proactive Toolchain Construction for LLM Agents from Scratch
这是本轮非常值得深入研究的项目。
它提出分层工具发现思想：
首先选择相关 MCP Server，再从选中的 Server 中找到具体 Tool，并在任务需要时继续扩展工具链。
论文实验涉及数百个 MCP Server 和数千个工具。

arxiv.org



分层检索示意（针对实验心理学改造）
任务：分析实验数据


统计分析服务
候选


课程资源服务
候选


练习服务
候选




选择统计服务内的具体工具
t 检验 / 方差分析 / 描述性统计


更重要的是，我进一步确认了该项目已经公开研究代码，并非只有论文。
xfey/MCP-Zero
源码已核实

代码文件	用途
matcher.py	分层语义匹配，筛选 MCP 工具
test_matcher.py	Matcher 测试
prompt_guide/	工具发现提示设计
MCP-tools/	工具数据与构建方式

仓库采用 MIT 许可证，公开了 ToolMatcher 和实验脚本，但它的研究实现依赖特定 Embedding 与 Azure OpenAI 客户端，而且 README 说明仍有生产级服务动态部署等工作尚未完成。它适合移植工具匹配算法，不宜原样视为成熟的生产路由系统。

GitHub
+2



这是值得在第二阶段单独跑实验的方案。
6. BFCL：不要靠感觉评价 Tool Calling
ICML 2025 · Berkeley Function Calling Leaderboard
BFCL 是工具调用领域有代表性的评测体系，涉及函数选择、参数正确性、连续调用和多轮任务等。

proceedings.mlr.press
+1



相关 GitHub：
Berkeley Function Calling Leaderboard 代码与数据尤其值得参考：
- eval_runner.py：调用结果评价逻辑。
- TEST_CATEGORIES.md：测试类别。
- 数据说明：评测数据组织方式。
这套代码和测试设计可以作为你们 Agent 路由评测的重要参考，尤其是多步工具链和模型是否误调用工具。
四、教育理论怎样影响能力选择？
这里我建议参考 Google 2026 年 LearnLM 教学框架。
它总结了主动学习、认知负荷管理、学习动机、个性化适配和元认知等教育原则。

research.google



这些原则不直接告诉程序调用哪个 Tool，但可以提供一套教学决策约束。
例如：
当前教学情况	教学原则	推荐能力
学生刚接触复杂概念	降低无关认知负荷	分步讲解 Skill
学生把两个概念混淆	促进主动知识建构	对比教学 Skill
学生提交实验设计方案	提供具体反馈	实验设计诊断 Tool 或子 Agent
学生想完成一道练习题	适当保留思考机会	提示 Skill、步骤检查 Tool
学生反复答错同类题	形成性评价与适配	练习生成 Tool、学习状态服务
学生明确要求看完整答案	尊重当前学习目标	直接回答并提供后续练习选项
因此，我建议你们把工具路由与已经讨论过的教学策略引擎连接起来。
前者判断用什么能力完成任务，后者决定怎样完成教学目标。
这两个模块可以协同，但不应重复实施之前已经完成的意图识别和记忆功能。
五、结合你们平台，我最推荐的能力路由架构
综合这次调研，我建议采用：
Policy-First + Dynamic Tool Selection + Skill Loading + Bounded Agent Delegation
也就是：
先通过规则过滤不应该使用的能力，再由模型从合法候选中选择，最后进行受控执行。
1. 推荐整体架构
#chatgpt-mermaid-_r_amf_{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;fill:rgb(26, 28, 31);}@keyframes edge-animation-frame{from{stroke-dashoffset:0;}}@keyframes dash{to{stroke-dashoffset:0;}}#chatgpt-mermaid-_r_amf_ .edge-animation-slow{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 50s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_amf_ .edge-animation-fast{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 20s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_amf_ .error-icon{fill:rgba(255, 255, 255, 0.96);}#chatgpt-mermaid-_r_amf_ .error-text{fill:rgb(26, 28, 31);stroke:rgb(26, 28, 31);}#chatgpt-mermaid-_r_amf_ .edge-thickness-normal{stroke-width:1px;}#chatgpt-mermaid-_r_amf_ .edge-thickness-thick{stroke-width:3.5px;}#chatgpt-mermaid-_r_amf_ .edge-pattern-solid{stroke-dasharray:0;}#chatgpt-mermaid-_r_amf_ .edge-thickness-invisible{stroke-width:0;fill:none;}#chatgpt-mermaid-_r_amf_ .edge-pattern-dashed{stroke-dasharray:3;}#chatgpt-mermaid-_r_amf_ .edge-pattern-dotted{stroke-dasharray:2;}#chatgpt-mermaid-_r_amf_ .marker{fill:rgba(26, 28, 31, 0.494);stroke:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_amf_ .marker.cross{stroke:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_amf_ svg{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;}#chatgpt-mermaid-_r_amf_ p{margin:0;}#chatgpt-mermaid-_r_amf_ .label{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:rgb(26, 28, 31);}#chatgpt-mermaid-_r_amf_ .cluster-label text{fill:rgb(26, 28, 31);}#chatgpt-mermaid-_r_amf_ .cluster-label span{color:rgb(26, 28, 31);}#chatgpt-mermaid-_r_amf_ .cluster-label span p{background-color:transparent;}#chatgpt-mermaid-_r_amf_ .label text,#chatgpt-mermaid-_r_amf_ span{fill:rgb(26, 28, 31);color:rgb(26, 28, 31);}#chatgpt-mermaid-_r_amf_ .node rect,#chatgpt-mermaid-_r_amf_ .node circle,#chatgpt-mermaid-_r_amf_ .node ellipse,#chatgpt-mermaid-_r_amf_ .node polygon,#chatgpt-mermaid-_r_amf_ .node path{fill:rgb(224, 237, 254);stroke:rgb(83, 154, 248);stroke-width:1px;}#chatgpt-mermaid-_r_amf_ .rough-node .label text,#chatgpt-mermaid-_r_amf_ .node .label text,#chatgpt-mermaid-_r_amf_ .image-shape .label,#chatgpt-mermaid-_r_amf_ .icon-shape .label{text-anchor:middle;}#chatgpt-mermaid-_r_amf_ .node .katex path{fill:#000;stroke:#000;stroke-width:1px;}#chatgpt-mermaid-_r_amf_ .rough-node .label,#chatgpt-mermaid-_r_amf_ .node .label,#chatgpt-mermaid-_r_amf_ .image-shape .label,#chatgpt-mermaid-_r_amf_ .icon-shape .label{text-align:center;}#chatgpt-mermaid-_r_amf_ .node.clickable{cursor:pointer;}#chatgpt-mermaid-_r_amf_ .root .anchor path{fill:rgba(26, 28, 31, 0.494)!important;stroke-width:0;stroke:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_amf_ .arrowheadPath{fill:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_amf_ .edgePath .path{stroke:rgba(26, 28, 31, 0.494);stroke-width:1px;}#chatgpt-mermaid-_r_amf_ .flowchart-link{stroke:rgba(26, 28, 31, 0.494);fill:none;}#chatgpt-mermaid-_r_amf_ .edgeLabel{background-color:rgb(255, 255, 255);text-align:center;}#chatgpt-mermaid-_r_amf_ .edgeLabel p{background-color:rgb(255, 255, 255);}#chatgpt-mermaid-_r_amf_ .edgeLabel rect{opacity:0.5;background-color:rgb(255, 255, 255);fill:rgb(255, 255, 255);}#chatgpt-mermaid-_r_amf_ .labelBkg{background-color:rgba(255, 255, 255, 0.5);}#chatgpt-mermaid-_r_amf_ .cluster rect{fill:rgba(255, 255, 255, 0.96);stroke:rgba(26, 28, 31, 0.08);stroke-width:1px;}#chatgpt-mermaid-_r_amf_ .cluster text{fill:rgb(26, 28, 31);}#chatgpt-mermaid-_r_amf_ .cluster span{color:rgb(26, 28, 31);}#chatgpt-mermaid-_r_amf_ div.mermaidTooltip{position:absolute;text-align:center;max-width:200px;padding:2px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:12px;background:rgba(255, 255, 255, 0.96);border:1px solid rgba(26, 28, 31, 0.08);border-radius:2px;pointer-events:none;z-index:100;}#chatgpt-mermaid-_r_amf_ .flowchartTitleText{text-anchor:middle;font-size:18px;fill:rgb(26, 28, 31);}#chatgpt-mermaid-_r_amf_ rect.text{fill:none;stroke-width:0;}#chatgpt-mermaid-_r_amf_ .icon-shape,#chatgpt-mermaid-_r_amf_ .image-shape{background-color:rgb(255, 255, 255);text-align:center;}#chatgpt-mermaid-_r_amf_ .icon-shape p,#chatgpt-mermaid-_r_amf_ .image-shape p{background-color:rgb(255, 255, 255);padding:2px;}#chatgpt-mermaid-_r_amf_ .icon-shape .label rect,#chatgpt-mermaid-_r_amf_ .image-shape .label rect{opacity:0.5;background-color:rgb(255, 255, 255);fill:rgb(255, 255, 255);}#chatgpt-mermaid-_r_amf_ .label-icon{display:inline-block;height:1em;overflow:visible;vertical-align:-0.125em;}#chatgpt-mermaid-_r_amf_ .node .label-icon path{fill:currentColor;stroke:revert;stroke-width:revert;}#chatgpt-mermaid-_r_amf_ .node .neo-node{stroke:rgb(83, 154, 248);}#chatgpt-mermaid-_r_amf_ [data-look="neo"].node rect,#chatgpt-mermaid-_r_amf_ [data-look="neo"].cluster rect,#chatgpt-mermaid-_r_amf_ [data-look="neo"].node polygon{stroke:url(#chatgpt-mermaid-_r_amf_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_amf_ [data-look="neo"].swimlane.cluster rect{filter:none;}#chatgpt-mermaid-_r_amf_ [data-look="neo"].node path{stroke:url(#chatgpt-mermaid-_r_amf_-gradient);stroke-width:1px;}#chatgpt-mermaid-_r_amf_ [data-look="neo"].node .outer-path{filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_amf_ [data-look="neo"].node .neo-line path{stroke:rgb(83, 154, 248);filter:none;}#chatgpt-mermaid-_r_amf_ [data-look="neo"].node circle{stroke:url(#chatgpt-mermaid-_r_amf_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_amf_ [data-look="neo"].node circle .state-start{fill:#000000;}#chatgpt-mermaid-_r_amf_ [data-look="neo"].icon-shape .icon{fill:url(#chatgpt-mermaid-_r_amf_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_amf_ [data-look="neo"].icon-shape .icon-neo path{stroke:url(#chatgpt-mermaid-_r_amf_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_amf_ .node text{font-size:14px;font-weight:600;letter-spacing:normal;fill:rgb(0, 79, 153);}#chatgpt-mermaid-_r_amf_ .edgeLabels text{font-size:13px;font-weight:600;letter-spacing:-0.08px;fill:rgb(0, 79, 153);}#chatgpt-mermaid-_r_amf_ .node tspan[font-weight="normal"],#chatgpt-mermaid-_r_amf_ .edgeLabels tspan[font-weight="normal"]{font-weight:600;}#chatgpt-mermaid-_r_amf_ .edgeLabel .label rect{opacity:1;rx:13px;ry:13px;fill:rgb(245, 250, 255);stroke:rgb(206, 219, 229);stroke-width:1px;}#chatgpt-mermaid-_r_amf_ .node rect,#chatgpt-mermaid-_r_amf_ .node circle,#chatgpt-mermaid-_r_amf_ .node ellipse,#chatgpt-mermaid-_r_amf_ .node polygon,#chatgpt-mermaid-_r_amf_ .node path{fill:rgb(229, 243, 255);stroke:rgba(0, 0, 0, 0.1);stroke-width:1px;}#chatgpt-mermaid-_r_amf_ .node rect{rx:16px;ry:16px;}#chatgpt-mermaid-_r_amf_ .node.mermaid-decision .label-container{fill:rgb(245, 250, 255);stroke:rgb(206, 219, 229);stroke-dasharray:2,2;}#chatgpt-mermaid-_r_amf_ .edgePaths .flowchart-link{stroke:rgba(26, 28, 31, 0.494);stroke-width:1px;stroke-linecap:round;stroke-linejoin:round;}#chatgpt-mermaid-_r_amf_ .marker{fill:rgba(26, 28, 31, 0.494);stroke:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_amf_ :root{--mermaid-font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}学生输入已有意图识别与学习上下文教学决策模块Capability RouterCapability RegistryTool / Skill / MCP / Agent权限、教学阶段和环境过滤相关能力搜索与筛选模型选择执行方案不调用额外能力按需加载 SkillTool / MCP 调用子 Agent 委派结果验证是否满足教学目标生成教学回答安全降级 / 说明限制满足不足且预算允许预算耗尽或失败





这个架构里，Capability Registry 是我建议你们新增的核心组件。
它不是向量数据库的另一个教材知识库，而是统一管理系统当前有哪些能力，以及每种能力应在什么条件下被使用。
2. 统一能力注册表如何设计？
我建议每个能力至少记录以下属性。
属性	作用
id、type	唯一标识及 Tool/Skill/MCP/Agent 类型
description	让模型理解能力用途
use_when	适用任务与触发条件
avoid_when	不适用任务，避免误调用
input_schema	参数校验
output_schema	结果结构
permissions	权限与可操作数据范围
dependencies	所需数据或服务
cost_level	时间与计算成本等级
timeout	最长执行时间
side_effects	是否写入数据、改变状态
fallback	调用失败如何处理
例如一个用于实验心理学的统计工具可以这样注册：

id: statistics.ttest
type: tool
name: t_test
description: 对两组实验数据进行t检验并返回统计结果
use_when:
  - 学生需要计算t检验结果
  - 需要验证给定的统计量
avoid_when:
  - 学生只询问t检验的概念
  - 数据缺失或不满足所选检验的输入要求
permissions:
  roles: [student, teacher]
  side_effects: none
execution:
  provider: local_python
  function: statistics.ttest
  timeout_seconds: 10
  fallback: explain_without_calculation



这是一份建议中的注册配置，不是现有项目的真实配置文件。
还需要把输出 Schema、函数签名及统计假设检查补全，才能成为实际可执行的工具定义。
3. 路由不应该只靠一个 LLM Prompt
我建议使用三层选择机制：
L1

确定性过滤（Policy Gate）
根据学生或教师身份、学习任务、系统状态、权限、服务可用性，过滤不允许使用的能力。
例如学生不能调用教师端查询全班成绩的 Tool，这应由后端权限系统保证，不能让 LLM 自行决定。


L2

候选能力召回（Capability Retrieval）
在剩余合法工具中，通过关键词、标签、语义检索或轻量模型选择少量候选。
这一层可以参考 MCP-Zero；工具数量较少时，可以先使用 LangChain 的 LLMToolSelectorMiddleware。


L3

模型决策（Capability Planning）
根据当前教学目标、候选能力说明、执行成本和可用输入，选择直接回答、加载 Skill、调用工具、委派子 Agent 或组合执行。
模型生成的是执行计划，实际调用仍由后端验证。



4. Skill 采用渐进式加载
按照 Agent Skills 规范，首先只暴露 Skill 名称及描述，在确定需要时再读取完整 SKILL.md，更具体的参考资料或脚本可以再次按需加载。

GitHub
+1



例如你们可以建立如下目录：
skills/
├── concept-explanation/
│   └── SKILL.md
├── experimental-design/
│   ├── SKILL.md
│   └── references/
│       └── design-checklist.md
├── statistics-guidance/
│   ├── SKILL.md
│   └── references/
│       └── test-selection.md
├── misconception-correction/
│   └── SKILL.md
└── guided-practice/
    └── SKILL.md


这里的重点不是 Skill 越多越好，而是每个 Skill 要具有清晰的适用范围，避免多个 Skill 描述高度重叠。
Anthropic 的 Skill Creator 还提供了针对 Skill 描述生成正反触发测试、比较不同描述版本的方法。这一部分非常适合借鉴，因为 Skill 是否被正确激活，往往取决于 description 是否准确。

GitHub
+1




六、什么情况下才应该调用子 Agent？
这是我认为需要谨慎设计的地方。
假设学生要求：
请带我设计一项关于睡眠时间对注意力影响的心理学实验。

这个问题可能涉及实验假设、变量设置、混淆变量、实验流程、测量方法和数据分析。
它确实比较复杂，但复杂并不等于必须使用多 Agent。
我建议以以下标准判断是否委派。
情况	优先方案
单一、明确的计算或查询任务	Tool
有固定流程的教学指导任务	Skill
多步但执行顺序明确	Workflow
需要独立专业检查和结构化反馈	子 Agent
需要专家持续接管学生对话	Handoff，谨慎使用
针对你们的项目，第一阶段最多先研究两个专门子 Agent：
Experimental Design Reviewer：接收实验方案，检查假设、变量定义、混淆变量控制与设计合理性，输出结构化诊断，不直接决定最终教学方式。
Statistical Reasoning Reviewer：检查统计方法选择、前提假设、结果解释与因果推断是否适当，并利用确定性统计工具验证可计算部分。
不建议一开始就创建“教学 Agent、提问 Agent、思考 Agent、评分 Agent、总结 Agent、反思 Agent”等大量协作角色。
这种拆分看似专业，但如果每个角色都需要模型调用，容易增加延迟、成本和上下文传递错误。
Google ADK 和 OpenAI Agents SDK 都明确支持将专业 Agent 作为有边界的任务执行单元，因此这两个方案可以二选一用于试验。

GitHub
+1




七、针对《实验心理学》设计一组具体工具调用场景
下面这些是建议的路由测试案例，不代表目前系统已经具备全部相应能力。
选择一个学生提问，查看建议调用路径

什么是实验的内部效度？

我总是把随机抽样和随机分配弄混。

我有两组独立样本数据，帮我检查是否存在显著差异。

检查我设计的睡眠与注意力实验，看看有没有问题。

根据我之前做错的题，给我安排一轮复习。

给我演示一个 Stroop 实验。


直接回答

使用已有教材检索证据生成解释。无需加载统计分析工具，也不必创建子 Agent。
选择依据：低复杂度知识问答。


这些场景还有一个共同点：调用工具必须服务于当前教学目标，而不是仅仅因为系统有这个工具。
例如统计分析工具不仅要给出 p 值，还需要让学生理解它表示什么、不能表示什么，避免把工具正确执行误认为学生已经掌握统计推断。

八、工程上最重要的三个控制机制
1. 工具调用预算与停止条件
一个学习 Agent 不应该为了完成一轮普通答疑，连续调用多个并不必要的工具。
建议引入受控执行预算：
class ExecutionBudget(BaseModel):    max_tool_calls: int    max_agent_delegations: int    max_execution_seconds: float    max_retry_per_tool: int



具体数值应由真实测试确定，而不是现在直接写死。
停止条件包括：任务已经完成、结果可信度足够、学生需要补充信息、工具结果重复、调用失败或预算耗尽。
2. 权限和数据安全
学生、教师两类角色在平台中的可执行能力不同。
工具调用可能涉及成绩、学习行为与个人学习画像，因此至少需要：
- 后端进行资源级权限校验，不以模型传入的学生 ID 作为授权依据。
- 明确只读与写入操作，重要写入保留确认或审核机制。
- 不向外部 MCP Server 提供不必要的原始对话和学生数据。
- 记录工具参数、执行结果状态、使用的能力版本和错误信息。
- 将 MCP 返回内容视为外部数据，不能允许其修改系统指令或扩大权限。
OpenAI Agents SDK 的 MCP 文档也明确强调可信服务器、最小权限与敏感操作审批。

GitHub
+1



3. 失败回退和执行验证
假设学生提出 t 检验请求，但统计服务临时不可用。
系统应返回可理解的失败状态，必要时继续解释检验原理，而不是编造统计量与 p 值。
建议规定：计算结果来自工具，教材事实来自课程证据，教学表达来自教学策略。 三者的数据来源需要可区分。

九、这部分优化到底应该如何评测？
我建议参考 BFCL 的方法建立专属于你们项目的 Capability Routing Benchmark。
至少设置六组样例：
测试类型	测试目标
无工具问题	模型能否正确不调用工具
单工具问题	是否选中正确 Tool、参数是否正确
Skill 触发	是否加载合适教学 Skill
多步任务	是否按数据依赖正确排列工具
子 Agent 决策	是否在必要时委派，而不是过度委派
异常及权限	是否安全拒绝、回退或等待确认
第一轮可以人工标注约 200 条测试案例，其中加入语义相近但应调用不同能力的“困难负样本”。
例如：
“解释什么是 t 检验”和“根据这组数据计算 t 检验”，关键词相似，但正确执行路径不同。
建议监控如下指标：
指标	定义
Capability Selection Accuracy	所选能力是否符合标注的预期
Tool Recall@K	正确工具是否出现在前 K 个候选
No-Tool Accuracy	不需要工具时能否停止选择
Parameter Accuracy	Tool 输入是否符合 Schema 与任务要求
Execution Success Rate	工具链是否成功完成
Unnecessary Call Rate	不必要的调用占比
Cost / Latency	每个任务的成本与耗时
Pedagogical Appropriateness	调用决策是否适合当前教学目标
不能只依赖模型为自己的调用过程打分。计算和参数结果应该用程序验证；教学适切性则结合教师制定的评分规则与抽样人工复核。
建议进行一次三方案对照实验
A：全部工具直接暴露
作为最简单的基线，观察工具数量增多后的误选和 Token 开销。

B：LLMToolSelector 预筛选
验证简单工具预选是否足以满足当前项目需要。

C：权限过滤 + 能力检索 + 模型选择
验证分层路由能否进一步提高准确性、效率与安全性。


如果 B 与 C 的实际表现差距很小，就没有必要为了架构复杂度而引入分层检索。
如果工具目录扩展到几十甚至上百个，C 的研究价值才可能更加明显。

十、代码复用的最终优先级
功能	推荐项目	复用判断	优先级
工具预筛选	LangChain LLMToolSelectorMiddleware	SDK 兼容时直接使用	P0
工具选择安全过滤	OpenAI SDK 的 is_enabled / Guardrails	可复用机制，需应用权限规则	P0
Skill 格式与校验	Agent Skills 规范	直接采用标准	P0
动态 Skill 加载	Deep Agents SkillsMiddleware	可直接集成或移植思路	P1
Tool / Skill 关联	Deep Agents Skill Tool Resolver	依赖框架，需适配	P1
MCP 接入	MCP Python SDK	可直接安装	P1
多 MCP 服务管理	LangChain MCP Adapters	采用 LangChain 时可直接集成	P1
子 Agent 委派	OpenAI Agents SDK 或 Google ADK	二选一进行 PoC	P1
大规模工具检索	MCP-Zero matcher.py	研究代码，需改造	P2
工具调用评测	Gorilla / BFCL	可借鉴与复用部分评测代码	P0
大部分候选框架具备较宽松的开源授权：LangChain 与 OpenAI Agents SDK 为 MIT，Google ADK 为 Apache-2.0，MCP Python SDK 和 MCP-Zero 为 MIT。复用时仍需检查版本、依赖、许可证保留义务以及其他被引入组件的许可。

GitHub
+4



另外，这些复用建议是基于公开仓库和文档的代码级可行性判断，尚未在你们实际工程环境中安装、测试，不能等同于完成兼容性验证。
十一、下一阶段研发安排
我建议你们以四个阶段推进：

阶段 1：能力盘点与统一注册（P0）
把当前已存在的 Tool、Skill、外部服务、子 Agent 原型全部列出来，建立 Capability Registry，明确每项能力的用途、权限和输入输出。
交付：能力清单、注册 Schema、权限矩阵。



阶段 2：工具动态选择（P0）
比较全部工具暴露与 LLMToolSelector 预筛选两种方案，构建不调用、单工具、多工具及错误参数测试。
交付：基本路由服务、回退机制、评测报告。



阶段 3：Skill / MCP / 子 Agent 组合（P1）
将教学 Skill、专业统计工具和一个实验设计诊断子 Agent 组合成完整的实验心理学任务链。
交付：可完成真实教学任务的组合能力示例。



阶段 4：分层路由与持续优化（P2）
在工具数量增长、测试证明预筛选不足后，再引入 MCP-Zero 类语义检索与分层工具选择。比较延迟、Token 成本和正确率。
交付：A/B/C 对照结果与是否升级架构的决策报告。



十二、本轮调研结论
本轮已覆盖工具选择、Skill 按需加载、MCP 接入、子 Agent 委派、研究论文及调用评测，找到的关键源码入口包括 LangChain 的 tool_selection.py、Deep Agents 的 skills.py / subagents.py、OpenAI Agents SDK 的 Agent-as-Tool 示例，以及 MCP-Zero 的 matcher.py。
最值得直接开展原型实验的两个方向是：
第一，基于 LangChain Tool Selector 的轻量能力路由。 这有望以较小改造成本解决“什么时候调用哪一个工具”的核心问题。
第二，基于 Deep Agents 思路的 Skill 按需加载与工具关联。 这能让你们逐步构建课程专用教学能力，而不用把全部工具和教学规则都塞进一个庞大的 System Prompt。
对于 MCP 和子 Agent，我建议先作为上述能力路由系统的执行对象，而不是现在就给它们单独建设一套平行的选择系统。
最终目标不是让 AI 调用更多的工具，而是：
让 AI 能够用最合适、最少且可靠的能力调用，完成当前真正需要的教学任务。
这比简单增加工具数量、更换 Agent 框架，或者创建大量专业子 Agent，更值得作为你们现阶段的优化方向。









     






再调研教学类agent一般用哪些skill  哪些tool，哪些agent，需要哪些过程，还是按照同样的方式调研





 






思考了 4m 48s






教学类 AI Agent 的 Skill、Tool、子 Agent 与教学流程调研
专题调研｜2026 年 10 月 12 日｜GitHub 开源实现 + 学术论文 +《实验心理学》课程智能体适配方案
一、这轮调研要解决的核心问题
与上一轮不同，这次不只是研究 AI 如何自主选择能力，而是进一步研究：
一个真正能够教学的 AI Agent，内部应该具备哪些教学能力、调用哪些工具、需要多少个子 Agent，以及如何将它们组织成完整的教学过程。
目前调研到的开源实现，主要呈现三种技术路线：
技术路线	代表项目	主要特点
智能辅导系统（ITS）	OATutor	题目、步骤、提示、评分、掌握度驱动教学
LLM 教学 Agent	EduChat、SocraticMath、OpenTutor	自然语言引导、苏格拉底教学、动态反馈
模块化教学 Skill	Education Agent Skills、Edu Agent Skills	将教学方法拆成可按需调用的独立教学流程
这些路线并不互相排斥。
对你们的《实验心理学》智能体来说，比较合理的是：使用 ITS 的教学闭环作为整体结构、LLM 负责灵活教学决策、Skill 负责具体教学方法、Tool 负责可验证的操作、少量子 Agent 负责复杂专业任务。
需要说明，以下并非对所有教学 Agent 的统计普查。“常见能力”是从代表项目和相关教学理论中归纳出的设计模式；“推荐配置”则是结合甲方需求提出的架构建议。
二、已经找到的代表性教学项目

1. OATutor
研究型智能辅导系统 · React · Bayesian Knowledge Tracing
采用题目步骤、分层提示、脚手架任务、自适应选题和学生知识状态估计。它不是以多 Agent 为核心，而是围绕学习步骤设计确定性的教学工作流。
借鉴价值： 学生作答 → 检查答案 → 提供帮助 → 更新知识状态 → 选择后续题目。

GitHub
+1







2. SocraticMath
华东师范大学相关研究 · CIKM 2024
将苏格拉底式数学教学组织为四阶段：回顾、启发、纠正和总结；公开了约 6,846 段多轮教学对话的数据集。
借鉴价值： 将“AI 像老师一样教学”落实为可识别的教学阶段，而不是只要求模型多提问。

GitHub







3. EduChat
教育领域大模型 · 教学模式与提示设计
公开实现包括开放问答、启发式教学、写作批改等能力，并提供不同教学任务的提示模板。
借鉴价值： 让同一个教学模型采用不同的任务模式，不必每种教学行为都创建子 Agent。

GitHub
+1







4. OpenTutor（LEARNableLabs）
开源教学 Skill 与课程工作流
将教学组织为诊断、旧知识回顾、交错练习和知识应用。课程生成还引入独立 Critic Agent 进行评审，并支持固定工作流与 Agent 动态编排两种方式。
借鉴价值： 主教学 Agent 不必承担所有工作，课程生成或审核可以在独立流程中进行。项目功能来自仓库说明，实际教学效果仍需要单独验证。

Compounding Deliberate Curiosity · GitHub







5. Education Agent Skills Library
165 个教育 Skill · 20 个分类 · 标准化 SKILL.md
其中 13 个学生端 Skill 专门用于实时教学，包括逐级提示、错误诊断、学生复述、独立测验和学习支架撤除等。
借鉴价值： 目前发现的最值得研究的教学 Skill 分类和组织方式之一。但它是社区 Skill 库，作者标注的证据等级不等于所有 Skill 均经过独立效果验证。

GitHub
+1







6. PedagogicalRL
EMNLP 2025 Oral · 教师—学生—评审多角色研究
包含多轮教学交互、模拟学生、教学质量评价及强化学习训练代码。
借鉴价值： 适合参考离线教学评测、模拟学生与策略优化。现阶段不建议直接采用其大型模型强化学习训练方案。

GitHub
+1






初步发现
这些项目有一个共同启发：教学能力不能只按照工具名称划分，还应该按照学习任务和教学阶段组织。
尤其是 OATutor，它的核心并不是让模型自由调用十几个 Agent，而是让每个教学步骤都有明确的输入、反馈、帮助机制及后续动作。
因此，我建议你们接下来研究的重点是教学能力的职责边界、启动条件、运行过程与效果验证，而不只是扩展一个越来越长的 Skill 清单。
三、教学 Agent 具体需要哪些 Skill？
这一部分找到了一套可以直接参考的教学 Skill 分类体系。
我重点核对了 Education Agent Skills Library 的学生端能力。其 13 个 Skill 都有实际的 SKILL.md，并记录了功能描述、适用输入、教学步骤和学习证据字段。

GitHub
+1



1. 开源项目实际提供的 13 个学生端 Skill
Skill	教学功能	对你们的价值
retrieve-first-gate	在解释之前让学生尝试回忆	教前复习
explain-first-interrogator	让学生先提出自己的解释	检查初步理解
progressive-hint-ladder	逐级提供提示	分步辅导
confidence-calibration-check	对比学生自信程度与实际表现	识别过度自信和不确定性
stuck-and-error-diagnosis-coach	诊断卡住的位置和错误类型	错误纠正
ai-claim-checker	引导学生核查 AI 给出的观点	批判性思维
transfer-bridge	将知识迁移到不同情境	知识迁移
teach-back-evaluator	让学生用自己的话教回给 AI	理解检验
productive-failure-protocol	先尝试解决问题，再进行讲解	探索式学习
srl-session-wrapper	引导目标设定、学习过程监控和反思	自我调节学习
unassisted-evidence-checkpoint	检查学生在无 AI 帮助下的表现	独立掌握评价
weekly-agency-review	定期回顾学生的自主学习行为	学习复盘
fading-manager	随着学生能力提高逐步撤除帮助	自适应教学
这些名称是仓库中的真实 Skill 标识，不是我自行编造的模块名称。

GitHub
+2



其中最值得深入阅读的四份源码：
progressive-hint-ladder/SKILL.md
提供由抽象提示到具体操作帮助的阶梯式支持。适合建设你们的 HintPolicy。



stuck-and-error-diagnosis-coach/SKILL.md
区分概念、程序、策略和表征错误，并根据具体类型选择不同反馈。这份 Skill 的错误诊断步骤非常值得改造。

GitHub






teach-back-evaluator/SKILL.md
根据学生能否准确地用自己的话解释知识，判断其理解表现，但不能单凭复述就认定完全掌握。



unassisted-evidence-checkpoint/SKILL.md
将获得 AI 提示后的正确作答与无辅助独立作答区分开。非常适合甲方的学习画像和掌握度估计。



2. 我建议你们第一阶段实际建设的 Skill
不需要一下子接入上述全部 13 个。对于甲方提出的引导式辅导、分层教学、难点复习和学习画像，先整合成下面八个高内聚教学 Skill 更合理。
建议 Skill	职责	优先级
concept-explanation	概念解释、教材举例、分层讲解	P0
guided-questioning	启发式追问、激活先验知识	P0
progressive-hint	根据当前步骤提供逐级提示	P0
misconception-correction	识别并纠正知识误区	P0
worked-example	展示完整示范并逐步过渡到学生练习	P0
formative-assessment	生成小测验、检查理解、反馈	P0
teach-back	复述检验、反思、迁移	P1
retrieval-practice	主动回忆、关联复习与独立测验	P1
此外，为《实验心理学》增加两个专业 Skill：
experimental-design-coach：帮助学生提出假设、区分自变量与因变量、控制混淆变量、设计实验条件、检查效度。
statistics-interpretation：指导学生理解描述性统计、假设检验、效应量、置信区间及结果报告，不把统计计算与统计解释混为一谈。
这些名称是我提出的项目设计建议，并非上述仓库中原有的同名 Skill。
3. Skill 不应该只有一段 Prompt
从开源实现来看，较完整的教学 Skill 应包含：
推荐的 Skill 内部结构
触发条件
什么情况应加载


教学目标
本轮希望学生学会什么


教学流程
动作顺序和等待条件


相关工具
允许调用哪些 Tool


退出与降级
何时结束或切换方法


证据输出
如何记录学习表现




我特别认可 Education Agent Skills 的两个设计：通过元数据先发现 Skill，再按需加载完整内容；通过输入输出 Schema 描述 Skill 之间可以怎样衔接。
不过其文档也明确指出，更完整的 Context Engine 与 Orchestrator 仍处于开发规划阶段，所以应该复用已经公开的 Skill 文件与注册思路，而不能把完整的跨 Skill 智能编排视为现成产品。

GitHub
+1



还有一点需要修改：部分社区 Skill 强制学生在获得解释前回答问题，这并不适合所有学习场景。学生明确要求直接讲解时，系统应允许切换为讲解模式。教学 Skill 应提供灵活性，而不是制造固定的对话障碍。

四、教学 Agent 通常需要哪些 Tool？
Skill 决定“怎样教”，Tool 负责“实际做什么”。
对于你们的平台，我建议将 Tool 分成五个工具组。下表中的接口名称是拟议设计，不代表所有接口都已经在开源项目中存在。
1. 教材与课程资源工具
建议 Tool	主要作用	来源
get_textbook_evidence	获取已有教材检索证据	已有 RAG
get_chapter_outline	查询章节教学内容	课程管理
get_figure_by_reference	获取教材插图及对应位置	已有图文检索
get_prerequisites	查询知识点先修关系	课程知识点模型
这里不要重做教材检索。 Tool 只需要对已有服务提供受控、结构化的调用入口。
2. 练习与评价工具
建议 Tool	主要作用	推荐参考
get_question	获取指定知识点的题目	OATutor
check_objective_answer	客观题确定性评分	OATutor
grade_open_response	按评分标准评价论述题	自建，支持教师审核
analyze_student_attempt	分析学生本轮错误和尝试	OATutor、MathTutorBench
get_mastery_estimate	获取知识掌握估计	已有状态服务、pyBKT
get_review_due	获取待复习内容	Py-FSRS
OATutor 的 checkAnswer.js、HintSystem.js 和 BKT-brain.js 是三处非常具体的参考代码。

GitHub
+2



注意：OATutor 的原始题目评分主要面向代数、数值与字符串等类型。实验心理学中的实验设计论述题不能简单套用这类评分函数。
3. 实验心理学专用工具
这组工具更有机会形成课程特色。
建议 Tool	功能	可复用项目
run_behavioral_demo	运行 Stroop、简单反应时等课堂演示	jsPsych
analyze_experiment_data	t 检验、ANOVA、效应量等	Pingouin
plot_experiment_results	绘制数据分布、均值与误差线等	Matplotlib
check_experiment_design	检查变量定义、控制条件与效度风险	自建检查规则 + LLM
validate_statistical_assumptions	样本、设计结构和统计前提检查	SciPy、Pingouin
generate_experiment_report_outline	辅助组织实验报告结构	专用 Skill + 模板
jsPsych 的插件机制支持呈现刺激、采集按键与反应时间；Pingouin 直接支持多种 t 检验、ANOVA 和其他统计分析。它们属于可直接集成的执行组件。

GitHub
+3



需要强调，正式心理学实验的刺激时序、浏览器设备差异、数据保护及实验伦理要求，比教学演示严格得多。第一阶段更适合建设演示与学习工具，不要默认它已满足科研级实验规范。
4. 学习状态与复习工具
这些 Tool 主要负责消费和更新已有的学习数据。
建议 Tool	功能
get_learning_state	读取学生当前学习状态
get_recent_misconceptions	获取待确认的历史错误
record_assessment_evidence	写入经过校验的作答证据
schedule_revision	生成下次复习安排
get_learning_progress	获取章节与知识点进度
Py-FSRS 可以直接提供调度计算：Scheduler.review_card() 返回更新后的卡片状态和复习记录。

GitHub
+1



但要区分对话记忆与学习评价证据：学生说“我会了”，可以作为自我报告；只有经过适当任务验证的表现，才应成为强掌握证据。
5. 教师端工具
甲方需要教师查看资源使用、学习进度、成绩与常见错题，因此可以配置：
Tool	功能
get_class_progress	获取班级学习进度汇总
get_common_mistakes	查看常见错误与知识难点
get_assessment_summary	获取测验成绩及分布
prepare_teacher_feedback	生成面向教师的教学建议
教师端汇总应由数据库与统计程序生成；LLM 主要解释聚合结果，不应直接依靠未经核验的学生聊天记录推算成绩。
工具数量方面，我建议第一阶段只暴露当前任务需要的少量 Tool，不是把上面列出的全部函数每轮都传给模型。

五、教学 Agent 需要哪些子 Agent？
这轮有一个非常重要的发现：
真实开源项目中所谓的“多个 Agent”，有时并不是多个长期运行的智能体，而是拥有不同上下文和职责的独立模型调用。
例如 OpenTutor 的 架构文档 明确指出：Researcher、CurriculumBuilder、Critic、Teacher 等角色按任务触发，各角色只接收自己需要的上下文；其中 DeliberatePractitioner 甚至是一个不需要模型调用的纯函数。

GitHub
+1



这非常值得你们借鉴。
1. 从项目中归纳出的角色
Agent 角色	工作内容	是否必须是独立 Agent
Tutor / Teaching Agent	与学生对话，选择教学动作	是，作为主 Agent
Curriculum Planner	规划知识顺序和学习路径	不一定，可用 Workflow
Question Generator	生成或选择练习	通常不需要，Skill + Tool 即可
Assessment Agent	分析作答与评价	复杂主观题可独立
Misconception Diagnoser	定位学生的认知误区	可先作为 Tool / Skill
Experimental Design Reviewer	检查实验方案的结构性问题	值得作为专业子 Agent
Statistical Reasoning Reviewer	检查统计方法与结果解释	可作为专业子 Agent
Teaching Quality Critic	独立检查教学反馈质量	优先用于离线评测
Student Simulator	模拟不同学生与误解行为	优先用于离线测试
2. 我的推荐：一个主 Agent，两个按需调用的专业子 Agent
Main Teaching Agent
统一学生对话、教学决策和回答组织


实验设计审查 Agent
变量、对照、混淆因素、效度


统计推断审查 Agent
检验选择、前提、结果解释




离线辅助：教学评审 Agent + 模拟学生 Agent（不参与每轮在线答疑）

两个专业 Agent 都不应该自行决定对学生说什么，而是先返回结构化审查结果，由主教学 Agent 结合教材、学生状态和教学策略生成回复。
例如实验设计审查 Agent 的输出，可以包含：
{
  "design_type": "between_subjects",
  "identified_variables": [],
  "potential_confounders": [],
  "validity_risks": [],
  "recommended_revisions": [],
  "missing_information": []
}


这是建议的数据契约，不是某个仓库现成的返回值。
这样设计，既保留独立专业判断，又可以避免不同子 Agent 使用不一致的教学口吻和学生画像。
六、教学 Agent 一般需要哪些教学过程？
这是我认为比增加 Tool 或子 Agent 更重要的问题。
我建议将教学流程分成一个基础教学循环 + 四个专项工作流。这一设计综合借鉴 SocraticMath、OATutor、OpenTutor 及智能辅导系统研究，并针对你们的课程进行了调整。
1. 基础教学循环
#chatgpt-mermaid-_r_a6e_{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;fill:rgb(26, 28, 31);}@keyframes edge-animation-frame{from{stroke-dashoffset:0;}}@keyframes dash{to{stroke-dashoffset:0;}}#chatgpt-mermaid-_r_a6e_ .edge-animation-slow{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 50s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_a6e_ .edge-animation-fast{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 20s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_a6e_ .error-icon{fill:rgba(255, 255, 255, 0.96);}#chatgpt-mermaid-_r_a6e_ .error-text{fill:rgb(26, 28, 31);stroke:rgb(26, 28, 31);}#chatgpt-mermaid-_r_a6e_ .edge-thickness-normal{stroke-width:1px;}#chatgpt-mermaid-_r_a6e_ .edge-thickness-thick{stroke-width:3.5px;}#chatgpt-mermaid-_r_a6e_ .edge-pattern-solid{stroke-dasharray:0;}#chatgpt-mermaid-_r_a6e_ .edge-thickness-invisible{stroke-width:0;fill:none;}#chatgpt-mermaid-_r_a6e_ .edge-pattern-dashed{stroke-dasharray:3;}#chatgpt-mermaid-_r_a6e_ .edge-pattern-dotted{stroke-dasharray:2;}#chatgpt-mermaid-_r_a6e_ .marker{fill:rgba(26, 28, 31, 0.494);stroke:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_a6e_ .marker.cross{stroke:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_a6e_ svg{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;}#chatgpt-mermaid-_r_a6e_ p{margin:0;}#chatgpt-mermaid-_r_a6e_ .label{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:rgb(26, 28, 31);}#chatgpt-mermaid-_r_a6e_ .cluster-label text{fill:rgb(26, 28, 31);}#chatgpt-mermaid-_r_a6e_ .cluster-label span{color:rgb(26, 28, 31);}#chatgpt-mermaid-_r_a6e_ .cluster-label span p{background-color:transparent;}#chatgpt-mermaid-_r_a6e_ .label text,#chatgpt-mermaid-_r_a6e_ span{fill:rgb(26, 28, 31);color:rgb(26, 28, 31);}#chatgpt-mermaid-_r_a6e_ .node rect,#chatgpt-mermaid-_r_a6e_ .node circle,#chatgpt-mermaid-_r_a6e_ .node ellipse,#chatgpt-mermaid-_r_a6e_ .node polygon,#chatgpt-mermaid-_r_a6e_ .node path{fill:rgb(224, 237, 254);stroke:rgb(83, 154, 248);stroke-width:1px;}#chatgpt-mermaid-_r_a6e_ .rough-node .label text,#chatgpt-mermaid-_r_a6e_ .node .label text,#chatgpt-mermaid-_r_a6e_ .image-shape .label,#chatgpt-mermaid-_r_a6e_ .icon-shape .label{text-anchor:middle;}#chatgpt-mermaid-_r_a6e_ .node .katex path{fill:#000;stroke:#000;stroke-width:1px;}#chatgpt-mermaid-_r_a6e_ .rough-node .label,#chatgpt-mermaid-_r_a6e_ .node .label,#chatgpt-mermaid-_r_a6e_ .image-shape .label,#chatgpt-mermaid-_r_a6e_ .icon-shape .label{text-align:center;}#chatgpt-mermaid-_r_a6e_ .node.clickable{cursor:pointer;}#chatgpt-mermaid-_r_a6e_ .root .anchor path{fill:rgba(26, 28, 31, 0.494)!important;stroke-width:0;stroke:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_a6e_ .arrowheadPath{fill:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_a6e_ .edgePath .path{stroke:rgba(26, 28, 31, 0.494);stroke-width:1px;}#chatgpt-mermaid-_r_a6e_ .flowchart-link{stroke:rgba(26, 28, 31, 0.494);fill:none;}#chatgpt-mermaid-_r_a6e_ .edgeLabel{background-color:rgb(255, 255, 255);text-align:center;}#chatgpt-mermaid-_r_a6e_ .edgeLabel p{background-color:rgb(255, 255, 255);}#chatgpt-mermaid-_r_a6e_ .edgeLabel rect{opacity:0.5;background-color:rgb(255, 255, 255);fill:rgb(255, 255, 255);}#chatgpt-mermaid-_r_a6e_ .labelBkg{background-color:rgba(255, 255, 255, 0.5);}#chatgpt-mermaid-_r_a6e_ .cluster rect{fill:rgba(255, 255, 255, 0.96);stroke:rgba(26, 28, 31, 0.08);stroke-width:1px;}#chatgpt-mermaid-_r_a6e_ .cluster text{fill:rgb(26, 28, 31);}#chatgpt-mermaid-_r_a6e_ .cluster span{color:rgb(26, 28, 31);}#chatgpt-mermaid-_r_a6e_ div.mermaidTooltip{position:absolute;text-align:center;max-width:200px;padding:2px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:12px;background:rgba(255, 255, 255, 0.96);border:1px solid rgba(26, 28, 31, 0.08);border-radius:2px;pointer-events:none;z-index:100;}#chatgpt-mermaid-_r_a6e_ .flowchartTitleText{text-anchor:middle;font-size:18px;fill:rgb(26, 28, 31);}#chatgpt-mermaid-_r_a6e_ rect.text{fill:none;stroke-width:0;}#chatgpt-mermaid-_r_a6e_ .icon-shape,#chatgpt-mermaid-_r_a6e_ .image-shape{background-color:rgb(255, 255, 255);text-align:center;}#chatgpt-mermaid-_r_a6e_ .icon-shape p,#chatgpt-mermaid-_r_a6e_ .image-shape p{background-color:rgb(255, 255, 255);padding:2px;}#chatgpt-mermaid-_r_a6e_ .icon-shape .label rect,#chatgpt-mermaid-_r_a6e_ .image-shape .label rect{opacity:0.5;background-color:rgb(255, 255, 255);fill:rgb(255, 255, 255);}#chatgpt-mermaid-_r_a6e_ .label-icon{display:inline-block;height:1em;overflow:visible;vertical-align:-0.125em;}#chatgpt-mermaid-_r_a6e_ .node .label-icon path{fill:currentColor;stroke:revert;stroke-width:revert;}#chatgpt-mermaid-_r_a6e_ .node .neo-node{stroke:rgb(83, 154, 248);}#chatgpt-mermaid-_r_a6e_ [data-look="neo"].node rect,#chatgpt-mermaid-_r_a6e_ [data-look="neo"].cluster rect,#chatgpt-mermaid-_r_a6e_ [data-look="neo"].node polygon{stroke:url(#chatgpt-mermaid-_r_a6e_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_a6e_ [data-look="neo"].swimlane.cluster rect{filter:none;}#chatgpt-mermaid-_r_a6e_ [data-look="neo"].node path{stroke:url(#chatgpt-mermaid-_r_a6e_-gradient);stroke-width:1px;}#chatgpt-mermaid-_r_a6e_ [data-look="neo"].node .outer-path{filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_a6e_ [data-look="neo"].node .neo-line path{stroke:rgb(83, 154, 248);filter:none;}#chatgpt-mermaid-_r_a6e_ [data-look="neo"].node circle{stroke:url(#chatgpt-mermaid-_r_a6e_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_a6e_ [data-look="neo"].node circle .state-start{fill:#000000;}#chatgpt-mermaid-_r_a6e_ [data-look="neo"].icon-shape .icon{fill:url(#chatgpt-mermaid-_r_a6e_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_a6e_ [data-look="neo"].icon-shape .icon-neo path{stroke:url(#chatgpt-mermaid-_r_a6e_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_a6e_ .node text{font-size:14px;font-weight:600;letter-spacing:normal;fill:rgb(0, 79, 153);}#chatgpt-mermaid-_r_a6e_ .edgeLabels text{font-size:13px;font-weight:600;letter-spacing:-0.08px;fill:rgb(0, 79, 153);}#chatgpt-mermaid-_r_a6e_ .node tspan[font-weight="normal"],#chatgpt-mermaid-_r_a6e_ .edgeLabels tspan[font-weight="normal"]{font-weight:600;}#chatgpt-mermaid-_r_a6e_ .edgeLabel .label rect{opacity:1;rx:13px;ry:13px;fill:rgb(245, 250, 255);stroke:rgb(206, 219, 229);stroke-width:1px;}#chatgpt-mermaid-_r_a6e_ .node rect,#chatgpt-mermaid-_r_a6e_ .node circle,#chatgpt-mermaid-_r_a6e_ .node ellipse,#chatgpt-mermaid-_r_a6e_ .node polygon,#chatgpt-mermaid-_r_a6e_ .node path{fill:rgb(229, 243, 255);stroke:rgba(0, 0, 0, 0.1);stroke-width:1px;}#chatgpt-mermaid-_r_a6e_ .node rect{rx:16px;ry:16px;}#chatgpt-mermaid-_r_a6e_ .node.mermaid-decision .label-container{fill:rgb(245, 250, 255);stroke:rgb(206, 219, 229);stroke-dasharray:2,2;}#chatgpt-mermaid-_r_a6e_ .edgePaths .flowchart-link{stroke:rgba(26, 28, 31, 0.494);stroke-width:1px;stroke-linecap:round;stroke-linejoin:round;}#chatgpt-mermaid-_r_a6e_ .marker{fill:rgba(26, 28, 31, 0.494);stroke:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_a6e_ :root{--mermaid-font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}确认本轮学习目标获取已有学习状态和教材证据判断是否需要诊断性提问选择教学 Skill解释 / 举例 / 提示 / 追问学生尝试或作答评分与错误诊断达到本轮目标?调整难度与帮助等级独立检查 / 迁移应用记录学习证据总结并决定后续练习尚未达到达到





这里的循环不是要求每次普通问答都必须完成所有步骤，而是为进入“正式辅导模式”的学习任务提供一套流程。它需要允许跳过、暂停、直接讲解和提前结束。
智能辅导系统研究支持按照学生的具体解题步骤提供反馈，而不是只在最终答案层面判断正确性。VanLehn 的 2011 年综述正是按照答案级、步骤级和子步骤级区分教学系统。

数字对象标识符 (DOI)
+1



2. 四类专项工作流
Workflow A：新知识教学
对应甲方：教材问答、引导式教学、分层辅导
知识目标

先验知识

概念解释

示例

学生复述

小测验


使用：concept-explanation、worked-example、teach-back，以及已有教材证据 Tool。


Workflow B：学生错误纠正
对应甲方：引导式辅导、学习难点跟踪
接收尝试

定位错误

判断原因

定向提示

重新作答

反馈


使用：misconception-correction、progressive-hint 和题目评分 Tool。
关键是先区分概念性错误和操作性错误，避免学生只是算错了一个数，就被要求重新学习整章知识。


Workflow C：实验设计辅导
《实验心理学》特色增强方向
研究问题

假设与变量

实验条件

混淆因素

效度检查

设计修改


使用：experimental-design-coach，必要时调用实验设计审查 Agent。最终解释仍由主教学 Agent 完成。


Workflow D：测验与复习
对应甲方：课程测验、难点复习、学习画像
选择知识点

独立答题

客观评分

诊断薄弱点

学习证据

安排复习


使用：formative-assessment、retrieval-practice、评分 Tool、已有学习状态服务和 Py-FSRS。


3. 为什么不建议所有学生都按固定流程走？
这里有三个值得借鉴的学习科学依据。
论文	结论及启发
ICAP（2014）	鼓励学生生成解释、进行知识建构与有意义的交互，而非一味被动接收
Productive Failure（2014）	在适当条件下，先探索再讲解可以帮助形成概念理解与迁移能力
Testing Effect（2006）	主动提取知识有助于长期保持，测验不只是评价手段
上述证据来自特定实验和教学情境，不能推导为“所有学生都应该先失败”或“每轮都必须提问”。教学 Agent 应根据知识难度、学生尝试情况与当前目标决定具体方法。

数字对象标识符 (DOI)
+2



更重要的是，2025 年《PNAS》的一项随机实验指出，缺乏学习保护机制的生成式 AI 可能提高学生当下练习表现，却损害撤除 AI 后的独立表现。这支持把独立作答检验纳入教学工作流。

PNAS




七、综合起来，AI 应怎样自主选择 Skill、Tool 与 Agent？
我建议沿用上一轮的 Capability Router，但把其选择依据从“用户意图”进一步细化为教学任务 + 教学阶段 + 学生当前表现 + 可用证据。
实际路由示例
假设学生输入：
我知道实验要控制无关变量，但自己设计实验时总是不知道该怎么控制。

系统不应仅因为出现“实验”就调用全部相关工具。
建议执行过程
1. 识别当前教学困难
   已有意图模块判断学生需要学习帮助。教学决策模块进一步识别为“知道概念，但不会实际应用”。
2. 选择教学 Skill
   优先加载 worked-example 或 experimental-design-coach，用一个有明确变量和干扰因素的实验案例引导学生。
3. 判断是否需要 Tool
   若已有足够教材案例，直接展开教学；若需要获取特定实验图示，则调用对应图文 Tool。
4. 等待学生尝试
   让学生针对该案例提出一种控制方法，再用 misconception-correction 判断是否混淆了随机分配、匹配、恒定法等策略。
5. 决定是否委派子 Agent
   如果学生进一步提交了复杂完整的实验方案，再考虑调用 Experimental Design Reviewer，而不是在普通概念问题时就委派。
6. 验证与记录
   让学生将相同原则应用于不同实验情境。经过验证的独立表现交由现有学习状态模块记录。

这一流程既能保证自主选择，也能避免过度调用。
建议的教学决策状态结构
class TeachingAction(BaseModel):    learning_goal: str    difficulty_type: str | None    teaching_stage: str    selected_skill: str | None    selected_tools: list[str]    delegated_agent: str | None    hint_level: int    needs_student_response: bool    evidence_required: bool



这只是核心字段示例。实际执行还需要能力注册表、权限过滤、Schema 验证、调用次数预算及错误回退。
我建议特别增加 needs_student_response，因为教学 Agent 最大的特殊性之一，就是很多时候下一步不应该继续调用工具，而应该等待学生回答。

八、最终代码复用清单
以下是经过本轮资料核对后，建议优先分析的源码入口。
模块	公开代码	判断
Skill 注册与索引	generate-registry.py	可移植索引构建逻辑
教学 Skill	student-learning/	可借鉴或改造 SKILL.md
分级提示 UI	HintSystem.js	React 组件依赖现有前端适配
自适应题目选择	problem-select-heuristics/	可移植算法思想
题目组织	OATutor-Content	借鉴题目和知识点结构
启发式教学模式	educhat-r1_web_demo.py	可改造提示模板
多角色教学流程	OpenTutor architecture	借鉴上下文隔离与执行边界
统计工具	Pingouin	Python 可直接安装使用
浏览器实验	jsPsych	JavaScript 组件集成
复习调度	Py-FSRS	Python 可直接安装使用
教学评价	MathTutorBench	可改造为课程专用测试集
MathTutorBench 的公开实现覆盖苏格拉底式提问、学生解题正确性、错误定位、错误纠正和教学支架生成等评价任务，因此与本轮调研的 Skill 能力测试很契合。

GitHub
+1



还有两个值得注意的代码复用风险：
第一，不能把研究代码中的所有学生状态当成真实数据。 OATutor 的一份 Agent 状态说明明确记录了某版本 timeOnStep 使用随机生成值的情况。因此，如果借鉴其学习行为模型，必须逐字段核实数据采集方式，不能直接将模拟字段接入学生画像。

GitHub



第二，Skill 代码与数据的授权可能不同。 Education Agent Skills Library 采用 CC BY-SA 4.0，SocraticMath 的代码采用 MIT、数据集采用 CC BY-NC 4.0。尤其在甲方商业交付场景中，应在直接复制 Skill 文本或训练数据前核查授权义务。

GitHub
+1




九、建议给你们项目配置的第一版能力组合
基于甲方八项功能，以及现有的记忆、意图识别和教材检索，我建议按下面的规模启动。
8
核心 Skill
教学方法层


10–12
首批 Tool
资源、测验、统计


1+2
Agent
一个主 Agent，两个可选专业 Agent



这不是行业标准数量，而是适用于你们当前项目的建议起始规模。
分阶段实施顺序
阶段	主要工作	验收目标
P0：教学核心	先实现概念解释、启发提问、逐级提示、错误诊断、例题示范和形成性评价	能完整运行典型的教学与纠错流程
P1：教学工具	接入题目评分、学习状态、图文呈现、统计分析等工具	能在正确的教学阶段调用正确工具
P1：个性化学习	增加复述检验、主动回忆、独立测验和复习调度	能区分有提示表现与独立掌握
P2：专业 Agent	实验设计审查、统计推断审查	复杂任务的审查质量优于单 Agent 基线
P2：自动评测	模拟学生、教学评价集和教师复核	能量化比较不同教学策略的效果
十、本轮调研结论
本轮研究覆盖情况
完成方案级梳理

教学 Skill
核对 13 个开源学生端 Skill，筛选 8 个核心建设方向


教学 Tool
按教材、练习、课程实验、学习状态和教师统计分类


Agent 角色
区分在线主教师、专业审查与离线评测角色


教学过程
提出基础循环和四种专项教学工作流




这一轮最值得延续的研究结论有三点。
第一，Skill 应该围绕教学方法建立，而不是围绕知识点无限拆分。 例如“启发式追问”是通用 Skill，“实验效度”是课程知识内容。两者结合后完成具体教学任务。
第二，不要把本来可以由确定性程序完成的工作都做成子 Agent。 题目评分、知识状态查询、复习调度、统计计算等，通常更适合通过 Tool 实现；复杂专业判断才考虑委派。
第三，教学流程比 Agent 数量更重要。 OATutor 和 OpenTutor 都提供了很好的参考：关键是将学生尝试、提示、反馈、复习与独立评价串成稳定的过程。特别是 OpenTutor，已经将课程规划、教学、评审、复习规则分别隔离，并对动态编排设置执行上限。

GitHub
+1



我的优先建议是：下一轮直接深入研究教学 Skill 的内部设计和组合机制。 重点可以放在 progressive-hint、misconception-correction、worked-example 和 formative-assessment 这四个核心能力上，逐一分析开源实现的完整教学步骤、输入输出、触发条件、Tool 依赖以及在实际学生对话中的切换规则。
这样就可以把当前的项目调研进一步收敛成一份能够直接指导开发的 Teaching Skills & Tools Architecture，而不是停留在“应该有哪些能力”的清单层面。









     






我还想要调研一下对话中可视化的这个功能，针对我们现在的这个离散数学这本书，还有我们教学相关的一些可视化功能，就是让对话更好被学生理解，或者让对话更有趣





  






思考了 3m 21s

我会延续前几轮的调研方式，重点看三类方案：离散数学知识本身的交互可视化、教学对话中按需生成的图表与动画，以及让学生直接操作和验证的互动组件。会核对 GitHub 项目、相关学习科学论文和许可证，并区分哪些能直接接入你们的前端，哪些需要通过 Skill/Tool 动态生成。








已搜索 11 个网站













离散数学 AI 教学 Agent：对话可视化与交互式教学调研
第一轮综合调研｜2026 年 10 月 12 日｜GitHub 开源项目 · 学习科学论文 · 教学 Skill / Tool / Agent 设计
一、先给出本轮最重要的结论
我认为你们的对话可视化，不应该局限于让 AI 在回答中插入图片、流程图或数学公式。
更值得探索的是：把 AI 聊天窗口升级为能够边解释、边演示、边操作、边检查学生理解情况的交互式数学学习环境。
例如，学生问“关系的传递性怎么理解”，传统 Agent 可能输出定义、文字解释和几个例子。
优化后的 Agent 可以直接生成关系有向图，让学生点击两个节点、添加关系边，观察传递性是否被破坏，再根据学生操作给予针对性反馈。
这才是可视化与教学 Agent 真正结合的价值。
建议研究的五类可视化能力
AI 根据学生问题决定可视化类型
结合教材知识点、教学目标与当前交互状态


概念可视化
集合、关系、函数映射


步骤动画
逻辑推导、图算法、证明


可交互操作
拖动节点、选择元素、修改边


可视化练习
学生操作、自动验证、即时反馈



教材图文增强
已有教材插图 + AI 标注与聚焦解释


其中我最推荐优先研究的是：交互式关系图、集合运算演示、命题逻辑真值表、函数映射、图论算法动画、证明过程可视化。
它们与你们的离散数学教材高度相关，也较适合通过结构化数据实现，便于验证正确性。

二、GitHub 重点发现：已经有人把离散数学做成完整的交互实验室

Axiomara
重点研究

React / TypeScript · D3.js · KaTeX
这是本次找到的与离散数学教学最直接相关的项目之一。其 README 列出了 11 个交互式数学模块，涉及集合论、命题逻辑、布尔代数、组合数学、关系、函数、归纳法、鸽巢原理、容斥、递推和图算法。

GitHub





它已经包含哪些值得借鉴的功能？
离散数学知识	Axiomara 的实现方向	你们可借鉴的交互
集合论	D3 文氏图、集合编辑	动态观察并、交、差、补
命题逻辑	公式解析、语法树、真值表	修改命题，自动重算
布尔代数	卡诺图、逻辑电路	高亮合并项与简化过程
组合数学	杨辉三角、计数演示	动态改变参数
二元关系	关系矩阵、有向图	检查自反、对称、传递
函数	箭头映射图	判断单射、满射、双射
数学归纳法	多米诺骨牌动画	演示基础步骤与递推步骤
鸽巢原理	容器和元素模拟	改变物品数与容器数
递推关系	汉诺塔及序列演示	分步操作、观察递推规律
图算法	BFS、DFS、Dijkstra 等	逐步执行并显示内部状态
这些是项目声明支持的能力，并不意味着每个模块都已经达到生产级质量。需要进一步审查其实现、测试、依赖及许可证才能确定能否直接移植。
这一项目最值得学习的设计，是一个知识点可以对应一个可以操作的数学实验，而不只是对应一张静态图片。
我建议将它列为你们后续源码深入分析的第一梯队项目。
三、第二批重点项目：成熟的数学可视化与交互框架
Axiomara 最贴近你们的学科需求，但不能仅因为功能丰富，就认定它是最成熟的工程基础。
我建议把真正的技术底座重点放在以下项目上。









Cytoscape.js
图论可视化与图结构操作 · MIT · 约 11.2k GitHub Stars
适合：关系有向图、图论、连通性、路径、节点编辑、动态图结构。
复用判断：直接使用前端库。 这是我最推荐作为离散数学图论交互底座的候选之一。

GitHub
+1















JSXGraph
数学交互控件 · MIT / LGPL 双授权
适合：数学对象动态拖动、参数变化、函数及几何演示。
复用判断：直接使用。 特别适合需要拖动点、改变变量并实时重算的数学教学场景。

GitHub
+1















Mathigon Polypad 与 Mathigon Studio
交互式数学教材与操作画布
适合：拖拽式操作、数学探索活动、任务反馈和课程内嵌交互。
Mathigon 的教材仓库把 content.md、交互函数 functions.ts、样式与提示 hints.yaml 分开组织，非常值得借鉴其“内容 + 交互 + 教学提示”的结构。

GitHub
+1



复用判断：优先借鉴架构，谨慎复制课程代码。 其教材仓库的 package.json 标记为 UNLICENSED，不能因为源码可查看就认定可以自由复用。

GitHub















Mermaid + Viz.js
文本生成流程图与有向图布局 · MIT
适合：算法流程、知识关系图、证明步骤、状态转换图、逻辑推导结构。
复用判断：直接调用。 这两者适合低交互或静态布局场景，不需要为了每张流程图都调用图像生成模型。

GitHub
+1















React Flow
节点编辑器 · MIT
适合：命题推理树、知识依赖图、证明节点拖拽、教学流程搭建。
与 Cytoscape.js 不同，React Flow 更偏向可编辑节点界面；图算法分析并不是它的核心职责。

GitHub















tldraw
AI 可操作画布、形状编辑、图文协作
其文档已明确提供 AI 生成、读取和操作画布的集成方式，也支持将 Mermaid 转换为可编辑的原生画布对象。
复用判断：适合后期开放式 AI 白板。 需单独审查 SDK 授权与使用条款，不能直接把免费 Starter Kit 的 MIT 授权等同于整个 SDK 的无限制商业使用。

GitHub
+2






这几种库应该怎么选择？
需求	第一选择	原因
关系、图论、路径、遍历	Cytoscape.js	图结构操作成熟
集合、组合、数学自定义画布	D3.js	视觉表达自由度高
数学参数与动态对象	JSXGraph	数学交互能力
公式输入和编辑	MathLive	数学编辑体验成熟
快速生成流程图	Mermaid	文本到图表简单
可编辑推理树	React Flow	节点及连线操作方便
AI 自由白板	tldraw	适合开放式图文协作
这里特别推荐 MathLive。它支持数学公式输入、虚拟键盘、LaTeX 和 MathML 等格式，适合让学生在对话中输入离散数学公式，而不是只能通过纯文本写 forall x 一类表达式。

GitHub




四、从离散数学课程角度，建议重点建设哪些可视化组件？
下面是基于这批开源项目的能力，以及离散数学常见内容提出的建议。具体功能必须再与你们十章教材的实际章节核对，不能把通用离散数学目录当成已经确认的教材目录。









1. 集合运算交互板
可点击集合区域，切换并集、交集、差集和补集；输入元素后同步更新集合表达式。
推荐：D3.js + 确定性集合运算。
教学价值：从符号记忆转向区域与元素对应关系。












2. 命题逻辑实验台
学生切换 \(p\)、\(q\) 的真假，观察合取、析取、蕴含与等价命题的结果；还可以查看语法树和推导顺序。
推荐：Axiomara 的 Logic 模块 + MathLive。
教学价值：尤其适合解释“为什么前件为假时，材料蕴含为真”。












3. 二元关系图形实验室
学生添加、删除有向边，同步显示关系矩阵，实时检查自反性、对称性、反对称性和传递性。
推荐：Cytoscape.js + 关系性质验证函数。
教学价值：这是我最推荐的首批可视化功能之一。












4. 函数映射编辑器
在定义域与陪域之间拖动映射箭头，即时判定是否构成函数，以及是否满足单射、满射、双射条件。
推荐：D3.js 或 React Flow。
教学价值：直接展示多个原像、无原像元素与映射性质的关系。












5. 偏序集与哈斯图构造器
输入偏序关系，自动绘制哈斯图；可以操作覆盖关系、极大元、极小元、最大元与最小元。
推荐：Graphviz/Viz.js + 自建偏序算法。
教学价值：帮助学生区分关系有向图与哈斯图。












6. 图论算法动画
点击单步执行 BFS、DFS、最短路和最小生成树算法，突出当前节点、候选边与访问状态。
推荐：Cytoscape.js + NetworkX，或借鉴 Axiomara 的实现。
教学价值：让算法每次状态变化都与文字解释一一对应。



另外值得建设的扩展组件包括：逻辑表达式推导树、数学归纳法多米诺动画、鸽巢原理模拟、递推关系与汉诺塔、组合计数过程展示。
不建议第一阶段十几种组件同时开发。应该先在一个知识点上验证“可视化是否真的提升理解”，再逐步扩展。
五、来体验一下：对话里的交互式数学组件可以是什么样
下面使用命题逻辑中的蕴含式 \(p\rightarrow q\) 演示一个简单的交互方式。
传统 AI 解释这一知识点，可能输出四行真值表和一段文字。
交互式教学则允许学生亲自切换命题取值，观察结果。
命题逻辑实验台
修改 p 和 q，观察蕴含命题的真假

交互示例

p

真假



q

真假




真 → 假
结果：
假

前件为真而后件为假，这是蕴含命题唯一为假的情况。

完整真值表
p	q	p → q
真	真	真
真	假	假
当前
假	真	真
假	假	真

你们真正实现时，可以进一步加入“学生先预测结果，再点击显示正确答案”的教学模式。
这样组件就不只是动态真值表，还会产生可记录的学习证据：学生预测是否正确、在哪种命题取值上容易出错、经过提示后是否改善。
这一点能够直接接入你们已经建设的学生学习状态系统。

六、如何让 AI 自动选择可视化方式？
结合上一轮讨论的 Tool、Skill、MCP 与子 Agent，我建议新增一个能力类别：
Visualization Capability（教学可视化能力）
它可以登记在已有 Capability Registry 中，由教学 Agent 按需调用，无需建立一套完全独立的 Agent 框架。
推荐的执行流程
#chatgpt-mermaid-_r_b41_{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;fill:rgb(26, 28, 31);}@keyframes edge-animation-frame{from{stroke-dashoffset:0;}}@keyframes dash{to{stroke-dashoffset:0;}}#chatgpt-mermaid-_r_b41_ .edge-animation-slow{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 50s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_b41_ .edge-animation-fast{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 20s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_b41_ .error-icon{fill:rgba(255, 255, 255, 0.96);}#chatgpt-mermaid-_r_b41_ .error-text{fill:rgb(26, 28, 31);stroke:rgb(26, 28, 31);}#chatgpt-mermaid-_r_b41_ .edge-thickness-normal{stroke-width:1px;}#chatgpt-mermaid-_r_b41_ .edge-thickness-thick{stroke-width:3.5px;}#chatgpt-mermaid-_r_b41_ .edge-pattern-solid{stroke-dasharray:0;}#chatgpt-mermaid-_r_b41_ .edge-thickness-invisible{stroke-width:0;fill:none;}#chatgpt-mermaid-_r_b41_ .edge-pattern-dashed{stroke-dasharray:3;}#chatgpt-mermaid-_r_b41_ .edge-pattern-dotted{stroke-dasharray:2;}#chatgpt-mermaid-_r_b41_ .marker{fill:rgba(26, 28, 31, 0.494);stroke:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_b41_ .marker.cross{stroke:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_b41_ svg{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;}#chatgpt-mermaid-_r_b41_ p{margin:0;}#chatgpt-mermaid-_r_b41_ .label{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:rgb(26, 28, 31);}#chatgpt-mermaid-_r_b41_ .cluster-label text{fill:rgb(26, 28, 31);}#chatgpt-mermaid-_r_b41_ .cluster-label span{color:rgb(26, 28, 31);}#chatgpt-mermaid-_r_b41_ .cluster-label span p{background-color:transparent;}#chatgpt-mermaid-_r_b41_ .label text,#chatgpt-mermaid-_r_b41_ span{fill:rgb(26, 28, 31);color:rgb(26, 28, 31);}#chatgpt-mermaid-_r_b41_ .node rect,#chatgpt-mermaid-_r_b41_ .node circle,#chatgpt-mermaid-_r_b41_ .node ellipse,#chatgpt-mermaid-_r_b41_ .node polygon,#chatgpt-mermaid-_r_b41_ .node path{fill:rgb(224, 237, 254);stroke:rgb(83, 154, 248);stroke-width:1px;}#chatgpt-mermaid-_r_b41_ .rough-node .label text,#chatgpt-mermaid-_r_b41_ .node .label text,#chatgpt-mermaid-_r_b41_ .image-shape .label,#chatgpt-mermaid-_r_b41_ .icon-shape .label{text-anchor:middle;}#chatgpt-mermaid-_r_b41_ .node .katex path{fill:#000;stroke:#000;stroke-width:1px;}#chatgpt-mermaid-_r_b41_ .rough-node .label,#chatgpt-mermaid-_r_b41_ .node .label,#chatgpt-mermaid-_r_b41_ .image-shape .label,#chatgpt-mermaid-_r_b41_ .icon-shape .label{text-align:center;}#chatgpt-mermaid-_r_b41_ .node.clickable{cursor:pointer;}#chatgpt-mermaid-_r_b41_ .root .anchor path{fill:rgba(26, 28, 31, 0.494)!important;stroke-width:0;stroke:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_b41_ .arrowheadPath{fill:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_b41_ .edgePath .path{stroke:rgba(26, 28, 31, 0.494);stroke-width:1px;}#chatgpt-mermaid-_r_b41_ .flowchart-link{stroke:rgba(26, 28, 31, 0.494);fill:none;}#chatgpt-mermaid-_r_b41_ .edgeLabel{background-color:rgb(255, 255, 255);text-align:center;}#chatgpt-mermaid-_r_b41_ .edgeLabel p{background-color:rgb(255, 255, 255);}#chatgpt-mermaid-_r_b41_ .edgeLabel rect{opacity:0.5;background-color:rgb(255, 255, 255);fill:rgb(255, 255, 255);}#chatgpt-mermaid-_r_b41_ .labelBkg{background-color:rgba(255, 255, 255, 0.5);}#chatgpt-mermaid-_r_b41_ .cluster rect{fill:rgba(255, 255, 255, 0.96);stroke:rgba(26, 28, 31, 0.08);stroke-width:1px;}#chatgpt-mermaid-_r_b41_ .cluster text{fill:rgb(26, 28, 31);}#chatgpt-mermaid-_r_b41_ .cluster span{color:rgb(26, 28, 31);}#chatgpt-mermaid-_r_b41_ div.mermaidTooltip{position:absolute;text-align:center;max-width:200px;padding:2px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:12px;background:rgba(255, 255, 255, 0.96);border:1px solid rgba(26, 28, 31, 0.08);border-radius:2px;pointer-events:none;z-index:100;}#chatgpt-mermaid-_r_b41_ .flowchartTitleText{text-anchor:middle;font-size:18px;fill:rgb(26, 28, 31);}#chatgpt-mermaid-_r_b41_ rect.text{fill:none;stroke-width:0;}#chatgpt-mermaid-_r_b41_ .icon-shape,#chatgpt-mermaid-_r_b41_ .image-shape{background-color:rgb(255, 255, 255);text-align:center;}#chatgpt-mermaid-_r_b41_ .icon-shape p,#chatgpt-mermaid-_r_b41_ .image-shape p{background-color:rgb(255, 255, 255);padding:2px;}#chatgpt-mermaid-_r_b41_ .icon-shape .label rect,#chatgpt-mermaid-_r_b41_ .image-shape .label rect{opacity:0.5;background-color:rgb(255, 255, 255);fill:rgb(255, 255, 255);}#chatgpt-mermaid-_r_b41_ .label-icon{display:inline-block;height:1em;overflow:visible;vertical-align:-0.125em;}#chatgpt-mermaid-_r_b41_ .node .label-icon path{fill:currentColor;stroke:revert;stroke-width:revert;}#chatgpt-mermaid-_r_b41_ .node .neo-node{stroke:rgb(83, 154, 248);}#chatgpt-mermaid-_r_b41_ [data-look="neo"].node rect,#chatgpt-mermaid-_r_b41_ [data-look="neo"].cluster rect,#chatgpt-mermaid-_r_b41_ [data-look="neo"].node polygon{stroke:url(#chatgpt-mermaid-_r_b41_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_b41_ [data-look="neo"].swimlane.cluster rect{filter:none;}#chatgpt-mermaid-_r_b41_ [data-look="neo"].node path{stroke:url(#chatgpt-mermaid-_r_b41_-gradient);stroke-width:1px;}#chatgpt-mermaid-_r_b41_ [data-look="neo"].node .outer-path{filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_b41_ [data-look="neo"].node .neo-line path{stroke:rgb(83, 154, 248);filter:none;}#chatgpt-mermaid-_r_b41_ [data-look="neo"].node circle{stroke:url(#chatgpt-mermaid-_r_b41_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_b41_ [data-look="neo"].node circle .state-start{fill:#000000;}#chatgpt-mermaid-_r_b41_ [data-look="neo"].icon-shape .icon{fill:url(#chatgpt-mermaid-_r_b41_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_b41_ [data-look="neo"].icon-shape .icon-neo path{stroke:url(#chatgpt-mermaid-_r_b41_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_b41_ .node text{font-size:14px;font-weight:600;letter-spacing:normal;fill:rgb(0, 79, 153);}#chatgpt-mermaid-_r_b41_ .edgeLabels text{font-size:13px;font-weight:600;letter-spacing:-0.08px;fill:rgb(0, 79, 153);}#chatgpt-mermaid-_r_b41_ .node tspan[font-weight="normal"],#chatgpt-mermaid-_r_b41_ .edgeLabels tspan[font-weight="normal"]{font-weight:600;}#chatgpt-mermaid-_r_b41_ .edgeLabel .label rect{opacity:1;rx:13px;ry:13px;fill:rgb(245, 250, 255);stroke:rgb(206, 219, 229);stroke-width:1px;}#chatgpt-mermaid-_r_b41_ .node rect,#chatgpt-mermaid-_r_b41_ .node circle,#chatgpt-mermaid-_r_b41_ .node ellipse,#chatgpt-mermaid-_r_b41_ .node polygon,#chatgpt-mermaid-_r_b41_ .node path{fill:rgb(229, 243, 255);stroke:rgba(0, 0, 0, 0.1);stroke-width:1px;}#chatgpt-mermaid-_r_b41_ .node rect{rx:16px;ry:16px;}#chatgpt-mermaid-_r_b41_ .node.mermaid-decision .label-container{fill:rgb(245, 250, 255);stroke:rgb(206, 219, 229);stroke-dasharray:2,2;}#chatgpt-mermaid-_r_b41_ .edgePaths .flowchart-link{stroke:rgba(26, 28, 31, 0.494);stroke-width:1px;stroke-linecap:round;stroke-linejoin:round;}#chatgpt-mermaid-_r_b41_ .marker{fill:rgba(26, 28, 31, 0.494);stroke:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_b41_ :root{--mermaid-font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}学生提问已有意图、Memory、教材证据教学决策可视化是否有教学价值?文字 / 公式解释Visualization Router选择形式教材原图和标注结构化数学组件步骤动画交互式练习验证内容与数据聊天消息内嵌可视化学生操作与反馈更新学习证据不需要需要





1. 我建议先实现三个可视化 Skill
Skill	任务	触发条件
visual-explanation	选择适合的图形解释抽象概念	学生表示概念难理解，且图形能够帮助表达
step-by-step-animation	将算法或证明转换为步骤动画	需要理解状态如何逐步变化
interactive-visual-practice	让学生在画布上操作并接受即时反馈	教学目标涉及判断、构造或应用
这些是建议新增的 Skill，核心是教学方法，而不是图形绘制本身。
实际绘图与数据计算应由 Tool 完成。
2. 建议的首批可视化 Tool
Tool	输出内容
render_set_diagram	集合区域、元素和高亮
render_truth_table	公式对应的真值表
render_relation_graph	有向图、关系矩阵
render_function_mapping	集合之间的映射
render_hasse_diagram	偏序集的哈斯图
render_graph_algorithm	图算法逐步执行状态
render_proof_steps	分步推导或归纳法演示
validate_visual_interaction	学生操作结果的确定性验证
这一阶段不需要单独创建 Visualization Agent。
原因是大部分教学图形都可以通过结构化数据和确定性渲染器完成。只有以后需要将开放式自然语言自动生成复杂、全新的交互教学应用时，才值得考虑独立的可视化生成子 Agent。
3. AI 最好输出结构化组件协议，而不是任意 HTML/JS
例如，学生说：
“画个关系图，帮我理解对称性。”
模型可以产生：
{
  "type": "relation_graph",
  "version": 1,
  "data": {
    "elements": ["a", "b", "c"],
    "pairs": [
      ["a", "b"],
      ["b", "a"],
      ["b", "c"]
    ]
  },
  "interaction": {
    "allow_edit_edges": true,
    "show_matrix": true,
    "check_properties": ["symmetric", "transitive"]
  }
}


前端根据 type 选择对应 React 组件，后台或可信数学计算模块负责验证。
这种方式比让 LLM 每次生成一段可执行 JavaScript 更稳定，也更容易做自动测试、缓存、权限限制和跨会话恢复。
需要特别强调：模型负责选择组件和生成参数；数学性质由确定性算法计算；前端负责渲染。
这是我认为最值得采用的技术原则。
七、论文调研：可视化真的能够提高学习效果吗？
答案不是“只要增加图片，学习效果就一定更好”。
研究普遍提示，教学可视化必须考虑学生原有知识、交互复杂度、任务目标，以及文字与图形之间的关系。
1. 不同学生需要不同程度的交互
一项关于交互式计算机模拟的研究发现，在其研究情境中，先验知识较高的学生从高交互模拟中获益更多；低先验知识学生面对较低交互程度的模拟，认知负荷与学习效率表现更好。

ScienceDirect



对你们的启发： 同一个关系图组件，可以根据学生水平提供两种模式。
引导模式
预设关系、重点高亮、每次只呈现少量操作。


探索模式
允许自行添加节点和边，探索多种关系性质。



2. 图形太多也可能阻碍学习
2025 年一项关于代数 AI Tutor 的研究观察到，认为图示有用并且更频繁使用图示的学生，反而表现出更小的学习增益。它是关于相关性的研究，不能简单断言“图示造成学习下降”，但提示了图示使用频率不等于有效学习。

电子学术出版
+1



这意味着你们不应该设置成“AI 每次回答必须生成一张图”。
更合理的做法是让 AI 判断图形是否真的能解决当前学生的理解困难。
3. 可视化和 AI 教学支架可以结合
2025 年《Computers & Education》上的一项随机对照研究发现，在理解学习分析可视化的任务中，提供主动教学支架的生成式 AI Agent 可以改善学生对图表的理解。

ScienceDirect



它说明一种值得研究的交互方式：
不是只显示图，而是让 AI 指向图中的具体元素、解释其意义，并要求学生完成恰当的认知活动。
当然，这项研究对象是学习分析可视化，不是离散数学，因此需要在你们的课程中另行验证。
4. 自动生成交互课程，最好拆成多个步骤
2025 年论文 Automatic Large Language Models Creation of Interactive Learning Lessons 研究了使用大模型生成交互式教学内容。其结果显示，分任务生成的方案在人工评价中优于单次整体生成，但仍存在反馈泛化等问题。

arXiv



对你们的价值是：以后如果让 AI 自动设计新的可视化教学活动，建议拆成“选择教学目标 → 设计交互 → 生成结构化数据 → 验证数学正确性 → 渲染 → 评价”，而不是一次要求 LLM 生成完整网页代码。

八、最终推荐技术栈与代码复用判断
开源项目	可借鉴模块	复用程度	优先级
Axiomara	十余类离散数学交互模块	MIT；可研究并移植模块代码	P0
Cytoscape.js	图论、关系图、交互操作	MIT；可直接集成	P0
Mermaid	流程图、知识结构图	MIT；可直接集成	P0
MathLive	公式输入与编辑	MIT；可直接集成	P0
JSXGraph	动态数学对象	MIT/LGPL；可直接集成	P1
Viz.js	哈斯图与层次布局	MIT；可直接集成	P1
React Flow	推理树、可编辑知识图	MIT；可直接集成	P1
Mathigon Textbooks	教材、组件、提示三层组织	借鉴设计；内容授权需核查	P1
tldraw	AI 可编辑白板	需评估 SDK 许可与集成	P2
其中 Axiomara 虽然采用 MIT，且设计了 engine.ts（计算）、store.ts（状态）、theory.tsx（教学内容）、components/（交互视图）的模块结构，但目前公开仓库提交历史较少，不能仅凭功能表就认为全部实现已经经过充分验证。

GitHub



它特别适合作为功能原型和源码复用候选；而图形计算、状态管理和正确性验证，仍需要你们自己的测试集。
九、最推荐的实施次序

阶段 1：对话中支持标准数学组件
先实现公式、真值表、集合图、有向关系图和基础流程图的结构化输出。
验收：能够通过 Tool 输出直接渲染，正确性可复核，不需要每次运行新生成代码。




阶段 2：让组件真正可操作
增加边编辑、元素选择、命题切换、算法单步执行、学生预测和答案验证。
验收：学生的一次操作能够改变图形状态，并产生可解释的即时反馈。




阶段 3：与教学 Skill / Tool Router 联动
教学 Agent 根据知识点和学习目标选择图形；对基础薄弱学生优先使用引导模式，对具备先验知识的学生允许探索。
验收：能在可视化与纯文字之间做合适选择，避免无意义调用。




阶段 4：验证教学效果并扩展
比较纯文字、静态图和交互组件三种方式，在关系、逻辑、图论等知识点上使用独立测试题评估理解与迁移表现。
验收：根据学习效果和调用成本决定是否继续扩展更多组件。



十、本轮调研结论
我建议你们把这一优化方向正式命名为：
Interactive Visual Tutoring（交互式可视化教学）
它不应该只是一个“AI 图片生成工具”，而应成为教学 Agent 中一套与教材、Skill、Tool 和学习状态协同的能力。
本轮最值得深入研究的三个方向是：s
第一，Axiomara 的离散数学模块化实现。 优先拆解集合、逻辑、关系、函数和图算法五个模块，确认算法能否复用、React 组件如何封装，以及能否改造成聊天消息组件。
第二，Cytoscape.js + D3.js 的交互式数学组件体系。 通过统一协议，让 AI 输出结构化可视化描述，使学生能在对话中直接修改和验证数学对象。
第三，AI 选择可视化时机和教学形式的机制。 将它接入已有教学策略与 Capability Router，让 AI 决定什么时候用文字、教材图片、静态图、动画或交互实验，而不是简单地给每个回答添加图形。
最终的目标可以理解为：
学生不仅可以问 AI“为什么”，还可以让 AI“画给我看”，然后亲自修改这个图，观察会发生什么，并让 AI 根据自己的操作继续教学。
这会比单纯改善文字回答的排版，更有机会形成你们 AI 教学 Agent 的差异化能力。