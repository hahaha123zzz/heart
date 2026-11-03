# 回答教学感、内容形式与可视化：源码核查

日期：2026-11-03。范围：当前根工作区源码、选定配置与现有纯规划函数。当前存在其他窗口未提交修改，本轮只读业务文件；没有重启8000、修改开关、调用真实模型或读取新增学生对话。

## 结论

相关能力已经部分实现，但存在三个不同问题：自动图解配置关闭且普通AgentLoop入口未接生成；部分教学策略在兼容映射中失去区别；内容组合和前端展示只覆盖了策略库的一部分形式。不能仅靠改“像老师一样回答”的提示词或打开开关解决。

这是一份源码路径核查，不能直接证明用户某一条未提供task_id的回答实际经过哪些分支，也不把当前磁盘文件等同于正在运行的Python进程已加载代码。

## 一、已做的功能

- `knowledge/teaching_strategies.json`实际含13种策略：直接解释、苏格拉底提问、提示、支架、例题、概念比较、反例、自我解释、提取练习、引导修订、直接纠正、迁移、总结。
- `agents/teaching_strategy.py`有规则优先级、候选过滤、历史策略和困难反馈；`adaptive_tutoring.py::instructions`确实把策略及moves加入生成提示，不是只有一个未调用的策略JSON。
- `agents/course_prompts.py::SCOPE`已经要求亲切、通俗、按学生目标组织解释；允许改述、推演和类比，并未要求所有回答逐字复述教材。
- 第五层已有ResponsePlan/ResponseComposer，支持带来源的段落、例题、比较、步骤等。`learning_response`也可能只是已生成正文的host_snapshot，字段存在不等于执行了动态内容规划。
- 可视化已有四个心理学预制主题包：变量、被试设计、信号检测、空间线索；按需生成有实验流程、变量关系、设计矩阵三种心理学模板及experimental-design skill。
- 前端已经实现guided_visualization挂载、上一步/下一步、教材来源按钮；TaskService有文字先发布、图解随后生成并持久化的流程。

## 二、明确发现的可视化阻断

### A. 当前配置关闭自动图解

`project/integration/discrete-math-tutor/.env:12`为`VISUALIZATION_ON_DEMAND='0'`。`visualization/on_demand.py`的预制和按需入口均受这个开关影响。读取时只检索相关开关，没有输出密钥。

现有`.runtime/latest-8000-20261102/start-current.py`加载该.env，显式启用了AgentLoop和内容组合，但没有覆盖此可视化开关。其服务记录也未记录该项。因此可确认磁盘配置关闭，不能仅凭此文件断言当前未知启动方式的进程内值；如另一个启动器覆盖，应再核实运行配置。

### B. 普通聊天的主路径缺少自动图解接线

`main.py:220`：普通无选区、无习题目标的聊天，在LOCAL_AGENT_LOOP_ENABLED=1时直接进入run_agent_loop_turn。

`agents/agent_loop_service.py:806`：该函数内唯一build_guide调用被`selection_input is not None`包围，还要求回答完成、非恢复正文、没有待答检查题。用AST追踪实际父级条件已核实，不是仅看函数是否存在。

因此，即使打开开关，当前普通聊天AgentLoop也不会走到这处build_guide。main普通分支调用还未传visualization_jobs；单补参数仍不足以解决“根本没创建图解任务”。

旧`orchestrator.handle_turn`在orchestrator.py约779行确实调用build_guide，选区管线也有调用；但普通聊天启用AgentLoop后不再进入这个旧普通回答入口。表现符合“旧路径做过，主路径升级后没有同等接线”。这不意味着全部选区、练习或旧入口都无法绘图。

### C. 接通后还有覆盖和失败边界

psychology_presets.match_topic只覆盖上述四个主题，并要求问题经GENERAL词表剥离后无剩余字符、主题唯一、回答中含关键词且教材章节/版本匹配。自然表述、人物追问或自定义实验可能不命中；未命中会回退按需生成，不应误称整个系统立刻失败。

心理学按需CATALOG实际替换为三种模板，并没有沿用离散数学中的通用flow/tree/formula目录。对人物关系、发展时间线、方法选择、部分公式与统计解释尚无同等广度覆盖。可视化选择器允许返回空数组，不能保证每种困难概念都有图。

按需链路通常包括选择、生成、核验，总预算40秒，最多一次生成修订；缺引用位置或核验不通过会返回None。TaskService将其表示为unavailable，保留文字。部分调用方吞掉异常，因此要区分未启用、未排队、无模板和核验失败，不能统称“AI没选图”。

`visual_explanation`内容块是对视觉证据的文字说明，并要求模型确实看过图片；它不是自动绘图组件，不能通过计划中出现这个类型来替代guided_visualization。

## 三、回答形式单调的可定位原因

### A. 策略决策存在，但默认偏向直接解释

teaching_strategy._decide的普通默认候选为direct_explanation、worked_example、scaffolding，主策略取过滤后首项。只有明确比较、困难位置、复习、作答或练习等条件才改变优先级；减少重复主要在学生明确反馈困难后发生，不做无条件轮换。

这并不意味着应该为了花样随机轮换教学策略，但说明“有13种策略”不等于普通回答会主动评估并采用13种表达。

### B. 第三层到第五层的兼容映射丢失了策略区别

adaptive_tutoring将primary_strategy通过runtime_strategy投影为旧名称，response_composition_adapters.response_plan优先读取teaching.strategy再反向canonical_strategy；没有直接优先使用保留完整策略ID的teaching.plan.primary_strategy。

本轮在项目现有运行环境直接调用原runtime_strategy和response_plan，给定最小teaching对象、无学生数据和上下文，得到：

| 第三层策略 | 兼容值 | 内容规划结果 |
| --- | --- | --- |
| direct_explanation | explain | direct_answer |
| worked_example | worked_example | direct_answer + worked_example |
| conceptual_comparison | contrast | direct_answer + comparison |
| scaffolding | break_down | explanation + procedure |
| summary | explain | direct_answer |
| counterexample | worked_example | direct_answer + worked_example |
| self_explanation | guided_practice | direct_answer |
| transfer | transfer | direct_answer |

这是8项适配函数探查，不是8次真实学生问答。它证明部分策略信息在这条适配入口确实会坍缩；实际有TaskFrame时还会将普通direct_answer投影为explanation，并不会自动找回原summary/counterexample含义。待答题等路径也可能绕过composer，需逐场景判断。

### C. 内容协议的类型比实际规划器丰富

plan_response只对提示、比较、例题、支架、前置、recap/counterexample等有限情况编排，其他策略回退direct_answer。模型输出被约束为预先计划的pending块，不能自行追加尚未规划的模块。

主AgentLoop创建composer时仅传context和teaching；response_plan虽支持execution.learning_intents，却未在此调用接收execution。部分明确任务可经GroundedTurn映射，但不能假设execution中的所有教学信号都自动影响内容组合。

普通直接解释策略通常只有一个解释块，模型可在其中讲概念和加一个示例；这与用户观察相符，但不证明所有答案都由同一模板生成。当前没有逐条新日志证明其实际分布。

### D. 前端未利用内容类型做差异展示

frontend/chat-renderer.js:27的renderLearningResponse检查协议后，将每个块统一渲染为response-block section，再调用相同Markdown渲染器；没有按semantic_type选择比较卡、步骤区、关系结构或实验面板。

Markdown本身支持加粗、高亮、公式及表格，app.js也能挂载单独的guided组件，所以不能把问题归因于“前端完全没有富文本/图解能力”。现状是内容块语义和展示形式之间的连接薄弱。

## 四、教师感与证据约束需要分开处理

提示词已经允许自然解释，问题不宜简化成“再加一句像老师”。当前composer要求每条claim都有来源且限定在既定块中；有益的教学组织仍需规划器表达，例如先建立整体关系、对比易混点、逐步解释实验、指出条件和局限。

来源约束不等于只能抄书：现有协议支持paraphrase、derived_explanation、analogy和generated_example。但笼统要求模型多举例，可能继续放大当前“改述＋示例”的惯性。不能通过取消事实核验换取活泼语气，也不应把所有回答强行加图、加测验。

## 五、建议后续修改顺序

1. 补普通AgentLoop的自动图解任务接线，复用已完成回答、授权来源和现有execution上下文；接入既有延迟生成、取消、保存和前端展示。再在隔离验收后启用开关。
2. 第三层到第五层传递完整策略ID及moves；旧runtime别名只用于确有兼容需求的工具接口，避免summary/反例等被反向还原成另一策略。
3. 让规划器真正覆盖所选教学动作和内容需求，优先完善总结、反例、关系梳理、实验步骤与概念比较，不新增一套意图识别器，也不随机轮换模板。
4. 扩展心理学可视化覆盖，利用现有流程渲染能力支持方法判定与知识关系；人物/发展类再按真实高频需求决定是否增加时间线等模板。
5. 前端按已发布块类型做适度差异展示，保持简单操作与自动触发；验证普通问答、选区、连续学习和历史回放，而不只测试预制函数。

本轮未执行上述修复，也没有真实模型回放和浏览器验收。结论中“代码阻断/适配丢失”有源码与纯函数证据；“用户每次具体命中了哪个分支”仍需对应task_id的实际trace确认。
