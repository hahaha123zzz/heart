《实验心理学》课程智能体平台：开源项目与学术论文调研
甲方需求驱动 · GitHub 开源项目 · 学习科学与教育心理学 · Agent 技术架构 · 代码复用分析
这次调研以甲方提供的《实验心理学》智能体教学平台功能文件为依据，不再单纯研究通用 AI 学习 Agent，而是围绕甲方要求实现什么、成熟项目如何实现、有哪些论文支撑、哪些代码能够复用展开。
你们已经优化完成的记忆、意图识别与教材检索模块，暂时视为现有基础能力。本轮重点研究这些能力怎样支持真正的教学功能，并寻找尚未覆盖的优化方向。
一、首先明确甲方的八项要求
甲方将平台定位为：提供课程资源、智能答疑和个性化学习支持，帮助学生理解和巩固知识，同时辅助教师了解学习情况。实验心理学课程智能体平台.docx

我将文件里的八项功能按原有阶段整理如下：
甲方功能	交付阶段	对历史交互数据的依赖
1. 课程资源与测验	基础	不需要
2. 学习数据统计	基础	需要
3. 课程知识问答（助教）	基础	不需要
4. 图文结合答疑	进阶（1）	不需要
5. 引导式与分层辅导	进阶（1）	分步引导不需要；历史分层需要
6. 学习难点跟踪与复习	进阶（2）	需要
7. 交互风格自定义	进阶（2）	需要
8. 学习画像与自动适配	进阶（3）	需要
依据甲方需求表整理。实验心理学课程智能体平台.docx

这八项功能背后的整体逻辑
基础阶段：学习资源与教学数据
课程内容 · 测验评分 · 教师统计 · 教材 RAG


进阶（1）：教学表达与引导
图文解释 · 认知负荷控制 · 分步辅导 · 追问


进阶（2）：跨会话个性化
难点跟踪 · 关联复习 · 交互偏好适配


进阶（3）：持续学习适配
学习画像 · 知识掌握估计 · 自动调整教学


一个值得注意的地方是：甲方并没有要求一个可以无限自主执行任务的通用 Agent。 它真正要求的是一个围绕指定课程、具有教学引导、学习评价和长期适配能力的智能教学系统。
因此，项目选型应该优先考虑教育场景的可靠性、可解释性和可评价性，而不是简单增加多个 Agent 角色。
还需要区分：
- 已经做过的底层能力：记忆、意图识别、教材检索。
- 甲方提出的应用功能：例如掌握度估计、难点复习、教师统计。它们可能调用已有底层能力，但不能因为底层模块完成，就认定应用功能已经交付。
- 本轮探索的增强能力：教学策略引擎、认知诊断、实验心理学专用交互工具、教学效果评测等。这些需要明确标记为研究建议，而不是甲方原文要求。
二、第一批重点开源项目：最值得研究的八个
这次我优先选择了有实际代码、明确技术能力或相关研究论文的项目。其中 OATutor 和 pyBKT 的优先级尤其高，因为它们直接关系到甲方要求的分层辅导、知识掌握估计和学习画像。

1. OATutor
重点

UC Berkeley 相关研究 · CHI 2023 · MIT
基于智能辅导系统（ITS）思想，具备分步提示、习题自适应选择、学生作答记录，以及基于贝叶斯知识追踪的掌握度估计。
对应甲方：1、2、5、6、8。
仓库已经包含教学提示、练习组织和学生状态更新代码，是这次调研中与甲方功能匹配度最高的参考项目之一。

GitHub
+1







2. pyBKT
重点

Bayesian Knowledge Tracing · Python · MIT
根据学生连续答题的正确与错误记录，估计其对特定知识技能的掌握概率。
对应甲方：6、8。
可以通过 pip install pyBKT 使用，公开了 Model.fit()、Model.predict()、Model.evaluate() 等接口，是最值得优先验证的 Python 组件之一。

GitHub
+1







3. EduStudio
合肥工业大学相关研究 · 认知诊断与知识追踪 · MIT
提供基于 PyTorch 的学生认知建模框架，覆盖 Cognitive Diagnosis 和 Knowledge Tracing。
对应甲方：2、8。
适合在有足够答题数据后比较不同模型，不建议一开始就使用复杂深度学习模型替代较简单、可解释的估计方式。

GitHub
+1







4. LearnHouse
开源课程平台 · FastAPI + Next.js · AGPL-3.0
包含课程管理、学习界面、后端 API、分析功能等，架构与你们 Python 后端有较好的参考关系。
对应甲方：1、2。
适合研究产品结构和接口设计，整体迁移成本较高，且 AGPL 许可证需要单独评估。

GitHub







5. jsPsych
实验心理学研究工具 · JavaScript · MIT
在浏览器内运行行为实验，支持刺激呈现、反应采集和实验流程控制。
对应甲方：可增强 1、4、5。
这不是甲方明确要求的在线实验系统，但它为实验心理学课程提供了非常有价值的扩展方向，例如课堂中的 Stroop 实验或反应时任务。

GitHub
+1







6. lab.js
行为实验可视化构建工具
提供可视化实验设计与浏览器运行能力，适合借鉴实验流程编辑和实验页面设计。
对应甲方：可增强 4、5。
其核心库采用 Apache 许可证，但图形化 Builder 采用 AGPL，不能把整个项目当作同一种许可处理。

GitHub
+1







7. Py-FSRS
间隔复习调度 · Python · MIT
根据复习反馈估算后续复习安排，可用于把“学生某知识点薄弱”转化为明确的复习任务。
对应甲方：6、8。
复习调度代码可以直接使用，但它不是理解能力诊断模型。知识点、复习材料、作答评分和记忆系统对接需要你们自己实现。

GitHub
+1







8. Kolibri
Learning Equality · 开源学习平台 · MIT
提供课程内容、练习与学习进度管理等能力，特别适合参考教师和学生两侧的资源组织与学习流程。
对应甲方：1、2。
更适合作为功能和用户体验参考，不建议直接把其整套平台嵌入目前的 AI Agent。

GitHub
+1






这一批项目的判断
OATutor 与 LearnHouse 都是教育平台，但研究价值不同：前者突出学习者模型和自适应教学，后者更偏向完整课程平台工程。
pyBKT、EduStudio 和 Py-FSRS 则不是聊天 Agent，而是可作为你们 Agent 内部服务的算法组件。
jsPsych 与 lab.js 的优势来自《实验心理学》这一具体课程的特点，值得作为课程特色能力单独研究，但不应该抢占甲方明确要求的基础功能开发资源。
三、与甲方需求最相关的论文调研
这次需要区分两类论文：一类回答应该怎样教学生，另一类回答系统如何估计学生学得怎么样。
1. 教学方法与认知心理学
论文	主要研究思想	可以转化的功能
Sweller（1988）	认知负荷理论：学习者处理信息的认知资源有限	控制信息量、分步讲解、先示例后练习
Mayer & Moreno（2003）	多媒体学习中如何减少无关认知负荷	图片与解释对应、重点标记、分段呈现
Chi & Wylie（2014）	ICAP：区分被动、主动、建构与交互式学习	引导预测、解释、比较、纠错
Karpicke & Roediger（2008）	主动提取知识能够促进学习保持	教后测验、主动回忆、独立作答
Dunlosky 等（2013）	系统比较十种学习方法的效果	分散练习、复习调度、测验反馈
这些是具有成熟研究基础的学习科学成果，而不是仅凭直觉得出的 Prompt 技巧。

Wiley Online Library
+4



2. 知识追踪与学习画像
An Introduction to Bayesian Knowledge Tracing with pyBKT（2023）
Bulut 等 · Psych
论文说明如何使用 pyBKT 对学生的答题序列进行知识追踪。对甲方第 8 项“学习画像与自动适配”尤其直接。它提供的是一种统计估计方法，不是对学生认知能力的绝对判定。

MDPI
+1



Deep Knowledge Tracing（2015）
Piech 等
使用循环神经网络建模连续学习行为。对复杂学习轨迹具有研究价值，但依赖训练数据，不适合作为缺少历史数据时的默认方案。

arXiv



OATutor（CHI 2023）
Pardos 等
将技能模型、分步提示、学生作答、自适应选题整合到同一个智能辅导系统。对甲方的价值不仅是某个算法，而是一条能够实际运行的教学闭环。

GitHub




3. LLM 教学可靠性
一篇发表于 2024 年《PLOS ONE》的研究使用 OATutor 作为实验平台，对 274 名在线参与者进行数学辅导实验。
研究发现，在该实验中，ChatGPT 生成的提示与人工教师提示之间没有观察到统计显著的学习增益差异，但原始 LLM 提示仍存在较明显的质量问题，研究通过额外的一致性检查降低了错误比例。

PMC
+1



对我们有一个直接启发：
自动生成教学提示并不代表可以省略质量检查。
特别是实验心理学涉及研究设计、统计结果解释、实验效度与因果推断。AI 即使能流畅解释知识，也可能给出错误的实验结论。
建议进一步参考 MathTutorBench 建设自己的教学评价集。它公开了教学能力任务、数据加载器和自动评测框架，但现有任务侧重数学辅导，需要改造成实验心理学场景。

GitHub




四、逐项分析甲方的八个功能：怎么实现、借鉴什么、代码能否复用
这是本轮调研中最重要的部分。
功能 1：课程资源与测验
甲方要求按教材章节组织教材、课件与测验题目，支持查阅、在线作答和自动评分。实验心理学课程智能体平台.docx

推荐参考 OATutor + LearnHouse。
建议把课程资源、测验管理与 RAG 知识库区分开。虽然都使用教材内容，但教材检索负责回答证据，课程模块负责学习单元、题目、答案和学生作答。
可以直接研究 OATutor 的以下代码：
- checkAnswer.js：已有的答案判断逻辑。
- Problem.js：习题交互和作答流程。
- OATutor-Content：题目、知识技能和提示的组织格式。
OATutor 现有评分逻辑支持代数、数值和字符串等类型，实验心理学的论述题、实验设计题不能直接依赖这些逻辑评分，需要教师制定评分规则，并为主观评分保留审核或申诉机制。

GitHub
+2



验收目标： 学生能够按章节完成题目；客观题准确评分；教师能查询成绩与错题；论述题有明确评分依据。
功能 2：学习数据统计
甲方要求展示资源使用、学习进度、测验成绩和常见错题。实验心理学课程智能体平台.docx

推荐参考 Kolibri + OATutor + 学习分析领域的 xAPI 思想。
这里最容易出现的架构误区是：将学习行为全部保存为聊天记录，等需要生成教师统计时再让 LLM 总结。
我建议建立独立的、结构化的学习事件记录：
{
  "student_id": "student_001",
  "event_type": "question_answered",
  "course_id": "experimental_psychology",
  "chapter_id": "chapter_03",
  "knowledge_point_id": "variable_control",
  "question_id": "q_001",
  "is_correct": false,
  "hint_count": 2,
  "occurred_at": "2026-10-12T10:00:00+08:00"
}


这是建议的数据格式，而不是甲方文档中已经定义的字段。
教师统计应优先基于数据库查询和聚合生成，而不是将班级学生原始对话直接交给大模型分析。
xAPI 可以作为学习事件标准化的参考。Learning Locker 是公开的 Learning Record Store 实现，但对当前规模的课程平台，未必需要立即部署完整 LRS。

GitHub
+1



验收目标： 每个关键学习行为均可追踪；教师看到的统计可以从原始学习事件复算；数据按学生、章节和知识点聚合。
功能 3：课程知识问答
甲方要求使用课程教材和资料进行 RAG 问答，并标注资料出处。实验心理学课程智能体平台.docx

你们已经完成教材检索优化，这部分不建议重新引入整套 RAG 框架。
本轮只建议验证三个集成条件：
1. 最终回答能否准确关联教材段落、章节或页码。
2. 教学决策、练习生成是否能够正确消费教材证据。
3. 当检索结果不足时，是否能避免编造课程知识或错误引用。
这些是对已有模块的集成验收，不是新的 RAG 重构任务。
功能 4：图文结合答疑
甲方希望解析教材插图、关联知识点，并在问答时按需展示配图，帮助理解实验装置、流程与结果。实验心理学课程智能体平台.docx

这项功能可以和实验心理学学科特点深度结合。
例如，学生问“经典 Stroop 实验是如何操作的？”时，AI 不应该只输出长篇文字，而可以：
- 展示对应的教材实验流程图。
- 说明刺激呈现、被试任务与因变量。
- 指出一致条件与不一致条件之间的差别。
- 用图示帮助学生理解为什么需要控制无关变量。
建议的功能演示示意，并非甲方教材原图：
Stroop 实验：课堂交互示例
任务：判断文字的显示颜色，而不是读取文字含义
蓝

一致条件


蓝

不一致条件



实际产品中可进一步记录反应时与准确率，但这些不是甲方图文答疑的必选交付项。

技术建议： 继续利用已有教材图片定位能力，增加图文呈现与教学解释层。图片来源仍需指向权威教材，不应让图像生成模型替代教材原图。
jsPsych 则作为独立的实验互动增强工具，用于以后真正运行课堂行为实验，而不是替代教材图片检索。
功能 5：引导式与分层辅导
这是我认为最值得重点研究的 Agent 核心功能。
甲方明确提到认知负荷、分层教学、分步讲解、举例与追问，并根据历史表现调整解释深度。实验心理学课程智能体平台.docx

建议建立一个教学动作决策层，至少支持以下操作：
教学动作	适用情况
直接解释	学生需要概念或知识事实
分步示范	学生难以完成复杂任务
提示与追问	学生已经具备部分知识
对比举例	学生混淆相似概念
错误诊断	学生给出错误实验设计或结论
形成性测验	需要检查是否理解
这里可借鉴 OATutor 的 HintSystem 和 ICAP、认知负荷理论。
更重要的是，不要把“分层”简单理解为给所有学生贴上初级、中级、高级三个固定标签。应该按具体知识点、当前任务、可用证据动态决定教学难度。
功能 6：学习难点跟踪与复习
甲方要求跨会话识别学习困难、疑似误区，并在后续新会话中检查与关联复习。实验心理学课程智能体平台.docx

你们的 Memory 已经完成优化，这项功能应重点研究记忆如何触发实际教学行为。
例如：
学生在第一天反复混淆“随机抽样”和“随机分配”，系统记录一个待确认的误区。
第三天学生学习实验设计时，Agent 可以在适当时机提出区分性问题，确认学生是否真正理解，而非仅因为曾经出错就一直认定学生不会。
建议以 Py-FSRS 处理复习时间安排，以已有 Memory 保存学习事实，以教学策略引擎决定何时进行适当复测。
关键是把“疑似误区”与“经过测验确认的知识缺口”区分开。
功能 7：交互风格自定义
甲方要求识别回答长短、讲解详略和举例偏好，同时支持学生主动修改设置。实验心理学课程智能体平台.docx

建议使用：
学生显式设置 > 当前提问要求 > 历史推断偏好 > 系统默认设置。
例如学生设置“简洁回答”，但本轮明确要求“详细解释实验设计”，应优先满足当前要求。
另外，文献并不支持把学生固定划分为所谓视觉型、听觉型等学习风格，再据此宣称能够提高学习成绩。Pashler 等人对相关证据进行了系统评议。

数字对象标识符 (DOI)



所以这里应做的是交互表达偏好适配，而不是缺少证据支持的“学习风格测量”。
功能 8：学习画像与自动适配
甲方将这项功能放在进阶（3），要求结合学习、测验和问答记录进行综合建模与知识掌握估计。实验心理学课程智能体平台.docx

建议从简单而可解释的三层结构开始：
第一层：真实学习证据
测验成绩、具体错误、提示次数、独立作答、复测结果


第二层：知识掌握估计
初期：规则与简单统计；有足够数据：BKT；较大数据规模：比较认知诊断与深度知识追踪模型


第三层：教学动作适配
调整例题难度、提示等级、练习顺序与复习内容


我不建议在项目初期仅凭几段聊天就生成一个看似精确的“知识掌握度 87%”。
初期数据不足时，应报告“证据不足”，通过短测验主动收集信息；等积累了标准化的作答序列，再利用 pyBKT 拟合和验证参数。
五、哪些代码可以直接复用？具体到 GitHub 文件
这里把“直接调用库”“改造开源实现”“只借鉴设计思想”严格分开。
来源	已核实的代码位置	复用方式
OATutor	BKT-brain.js	可以移植简单的 BKT 更新公式
OATutor	HintSystem.js	改造提示面板与提示等级交互
OATutor	checkAnswer.js	参考客观题评分逻辑
OATutor	problem-select-heuristics/	参考自适应选题策略
pyBKT	pyBKT.models.Model	直接安装并接入 Python 服务
EduStudio	edustudio/、examples/	离线训练、认知诊断模型对比
Py-FSRS	fsrs/scheduler.py	直接调用复习调度算法
jsPsych	jsPsych 框架	前端集成行为实验模块
Pingouin	parametric.py	可直接调用 t 检验、ANOVA 等统计函数
MathTutorBench	tasks/、dataloaders/、main.py	改造成专用教学评测框架
OATutor 的 BKT 更新函数、答案检查入口、提示组件等已在公开仓库核实；pyBKT 和 Py-FSRS 的 API 与代码入口也有对应文档。

GitHub
+5



这里还发现一个值得加入后续研究的工具：
Pingouin 支持方差分析、相关分析、效应量和置信区间等统计方法，非常适合以后实现“实验结果分析辅助”功能。它是实验心理学课程的特色扩展方向，而非甲方八项功能中的独立必选项。

GitHub
+1



开源许可证也会影响复用策略
项目	公开许可	工程建议
OATutor	MIT	可以优先评估局部代码复用
pyBKT、EduStudio	MIT	可以作为 Python 依赖接入
jsPsych、Py-FSRS	MIT	可以作为独立组件
LearnHouse	AGPL-3.0	优先借鉴设计，直接复制代码前审查
lab.js	核心 Apache；Builder AGPL	分别核查所用组件
Kolibri	MIT	可参考或集成适当能力
OATutor 的平台代码与 OATutor-Content 的课程素材不能视为同一许可证：内容仓库包含 CC BY 4.0 授权与来源归属信息。

GitHub
+4



六、建议最终形成的技术架构
我建议不改变你们已经完成的基础架构，而是在它上面构建学习应用层和教学策略层。
#chatgpt-mermaid-_r_6kj_{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;fill:rgb(26, 28, 31);}@keyframes edge-animation-frame{from{stroke-dashoffset:0;}}@keyframes dash{to{stroke-dashoffset:0;}}#chatgpt-mermaid-_r_6kj_ .edge-animation-slow{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 50s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_6kj_ .edge-animation-fast{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 20s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_6kj_ .error-icon{fill:rgba(255, 255, 255, 0.96);}#chatgpt-mermaid-_r_6kj_ .error-text{fill:rgb(26, 28, 31);stroke:rgb(26, 28, 31);}#chatgpt-mermaid-_r_6kj_ .edge-thickness-normal{stroke-width:1px;}#chatgpt-mermaid-_r_6kj_ .edge-thickness-thick{stroke-width:3.5px;}#chatgpt-mermaid-_r_6kj_ .edge-pattern-solid{stroke-dasharray:0;}#chatgpt-mermaid-_r_6kj_ .edge-thickness-invisible{stroke-width:0;fill:none;}#chatgpt-mermaid-_r_6kj_ .edge-pattern-dashed{stroke-dasharray:3;}#chatgpt-mermaid-_r_6kj_ .edge-pattern-dotted{stroke-dasharray:2;}#chatgpt-mermaid-_r_6kj_ .marker{fill:rgba(26, 28, 31, 0.494);stroke:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_6kj_ .marker.cross{stroke:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_6kj_ svg{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;}#chatgpt-mermaid-_r_6kj_ p{margin:0;}#chatgpt-mermaid-_r_6kj_ .label{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:rgb(26, 28, 31);}#chatgpt-mermaid-_r_6kj_ .cluster-label text{fill:rgb(26, 28, 31);}#chatgpt-mermaid-_r_6kj_ .cluster-label span{color:rgb(26, 28, 31);}#chatgpt-mermaid-_r_6kj_ .cluster-label span p{background-color:transparent;}#chatgpt-mermaid-_r_6kj_ .label text,#chatgpt-mermaid-_r_6kj_ span{fill:rgb(26, 28, 31);color:rgb(26, 28, 31);}#chatgpt-mermaid-_r_6kj_ .node rect,#chatgpt-mermaid-_r_6kj_ .node circle,#chatgpt-mermaid-_r_6kj_ .node ellipse,#chatgpt-mermaid-_r_6kj_ .node polygon,#chatgpt-mermaid-_r_6kj_ .node path{fill:rgb(224, 237, 254);stroke:rgb(83, 154, 248);stroke-width:1px;}#chatgpt-mermaid-_r_6kj_ .rough-node .label text,#chatgpt-mermaid-_r_6kj_ .node .label text,#chatgpt-mermaid-_r_6kj_ .image-shape .label,#chatgpt-mermaid-_r_6kj_ .icon-shape .label{text-anchor:middle;}#chatgpt-mermaid-_r_6kj_ .node .katex path{fill:#000;stroke:#000;stroke-width:1px;}#chatgpt-mermaid-_r_6kj_ .rough-node .label,#chatgpt-mermaid-_r_6kj_ .node .label,#chatgpt-mermaid-_r_6kj_ .image-shape .label,#chatgpt-mermaid-_r_6kj_ .icon-shape .label{text-align:center;}#chatgpt-mermaid-_r_6kj_ .node.clickable{cursor:pointer;}#chatgpt-mermaid-_r_6kj_ .root .anchor path{fill:rgba(26, 28, 31, 0.494)!important;stroke-width:0;stroke:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_6kj_ .arrowheadPath{fill:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_6kj_ .edgePath .path{stroke:rgba(26, 28, 31, 0.494);stroke-width:1px;}#chatgpt-mermaid-_r_6kj_ .flowchart-link{stroke:rgba(26, 28, 31, 0.494);fill:none;}#chatgpt-mermaid-_r_6kj_ .edgeLabel{background-color:rgb(255, 255, 255);text-align:center;}#chatgpt-mermaid-_r_6kj_ .edgeLabel p{background-color:rgb(255, 255, 255);}#chatgpt-mermaid-_r_6kj_ .edgeLabel rect{opacity:0.5;background-color:rgb(255, 255, 255);fill:rgb(255, 255, 255);}#chatgpt-mermaid-_r_6kj_ .labelBkg{background-color:rgba(255, 255, 255, 0.5);}#chatgpt-mermaid-_r_6kj_ .cluster rect{fill:rgba(255, 255, 255, 0.96);stroke:rgba(26, 28, 31, 0.08);stroke-width:1px;}#chatgpt-mermaid-_r_6kj_ .cluster text{fill:rgb(26, 28, 31);}#chatgpt-mermaid-_r_6kj_ .cluster span{color:rgb(26, 28, 31);}#chatgpt-mermaid-_r_6kj_ div.mermaidTooltip{position:absolute;text-align:center;max-width:200px;padding:2px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:12px;background:rgba(255, 255, 255, 0.96);border:1px solid rgba(26, 28, 31, 0.08);border-radius:2px;pointer-events:none;z-index:100;}#chatgpt-mermaid-_r_6kj_ .flowchartTitleText{text-anchor:middle;font-size:18px;fill:rgb(26, 28, 31);}#chatgpt-mermaid-_r_6kj_ rect.text{fill:none;stroke-width:0;}#chatgpt-mermaid-_r_6kj_ .icon-shape,#chatgpt-mermaid-_r_6kj_ .image-shape{background-color:rgb(255, 255, 255);text-align:center;}#chatgpt-mermaid-_r_6kj_ .icon-shape p,#chatgpt-mermaid-_r_6kj_ .image-shape p{background-color:rgb(255, 255, 255);padding:2px;}#chatgpt-mermaid-_r_6kj_ .icon-shape .label rect,#chatgpt-mermaid-_r_6kj_ .image-shape .label rect{opacity:0.5;background-color:rgb(255, 255, 255);fill:rgb(255, 255, 255);}#chatgpt-mermaid-_r_6kj_ .label-icon{display:inline-block;height:1em;overflow:visible;vertical-align:-0.125em;}#chatgpt-mermaid-_r_6kj_ .node .label-icon path{fill:currentColor;stroke:revert;stroke-width:revert;}#chatgpt-mermaid-_r_6kj_ .node .neo-node{stroke:rgb(83, 154, 248);}#chatgpt-mermaid-_r_6kj_ [data-look="neo"].node rect,#chatgpt-mermaid-_r_6kj_ [data-look="neo"].cluster rect,#chatgpt-mermaid-_r_6kj_ [data-look="neo"].node polygon{stroke:url(#chatgpt-mermaid-_r_6kj_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_6kj_ [data-look="neo"].swimlane.cluster rect{filter:none;}#chatgpt-mermaid-_r_6kj_ [data-look="neo"].node path{stroke:url(#chatgpt-mermaid-_r_6kj_-gradient);stroke-width:1px;}#chatgpt-mermaid-_r_6kj_ [data-look="neo"].node .outer-path{filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_6kj_ [data-look="neo"].node .neo-line path{stroke:rgb(83, 154, 248);filter:none;}#chatgpt-mermaid-_r_6kj_ [data-look="neo"].node circle{stroke:url(#chatgpt-mermaid-_r_6kj_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_6kj_ [data-look="neo"].node circle .state-start{fill:#000000;}#chatgpt-mermaid-_r_6kj_ [data-look="neo"].icon-shape .icon{fill:url(#chatgpt-mermaid-_r_6kj_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_6kj_ [data-look="neo"].icon-shape .icon-neo path{stroke:url(#chatgpt-mermaid-_r_6kj_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_6kj_ .node text{font-size:14px;font-weight:600;letter-spacing:normal;fill:rgb(0, 79, 153);}#chatgpt-mermaid-_r_6kj_ .edgeLabels text{font-size:13px;font-weight:600;letter-spacing:-0.08px;fill:rgb(0, 79, 153);}#chatgpt-mermaid-_r_6kj_ .node tspan[font-weight="normal"],#chatgpt-mermaid-_r_6kj_ .edgeLabels tspan[font-weight="normal"]{font-weight:600;}#chatgpt-mermaid-_r_6kj_ .edgeLabel .label rect{opacity:1;rx:13px;ry:13px;fill:rgb(245, 250, 255);stroke:rgb(206, 219, 229);stroke-width:1px;}#chatgpt-mermaid-_r_6kj_ .node rect,#chatgpt-mermaid-_r_6kj_ .node circle,#chatgpt-mermaid-_r_6kj_ .node ellipse,#chatgpt-mermaid-_r_6kj_ .node polygon,#chatgpt-mermaid-_r_6kj_ .node path{fill:rgb(229, 243, 255);stroke:rgba(0, 0, 0, 0.1);stroke-width:1px;}#chatgpt-mermaid-_r_6kj_ .node rect{rx:16px;ry:16px;}#chatgpt-mermaid-_r_6kj_ .node.mermaid-decision .label-container{fill:rgb(245, 250, 255);stroke:rgb(206, 219, 229);stroke-dasharray:2,2;}#chatgpt-mermaid-_r_6kj_ .edgePaths .flowchart-link{stroke:rgba(26, 28, 31, 0.494);stroke-width:1px;stroke-linecap:round;stroke-linejoin:round;}#chatgpt-mermaid-_r_6kj_ .marker{fill:rgba(26, 28, 31, 0.494);stroke:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_6kj_ :root{--mermaid-font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}课程资源 / 教材 RAG课程教学服务已有 Memory已有意图识别教学策略决策课程与测验服务图文教学服务提示 / 举例 / 追问 / 纠错评分与学习事件学习状态与知识掌握估计复习与自适应练习教师学习统计教学质量评测





建议保持三个重要的数据边界：
教材事实由权威教材与课程资料提供；学生知识状态由测验、作答及其他可验证学习证据支持；交互偏好由学生设置与历史行为提供。这三类数据可以共同影响教学决策，但不能互相替代。
尤其要避免将“学生曾经问过某个问题”直接转换为“学生已经掌握某个知识点”。
一、先给出核心判断
你们已经完成了三个重要的基础模块：
- Memory：管理学生历史、学习状态和相关长期信息。
- Intent Understanding：理解学生想做什么，以及不完整、模糊的输入。
- Textbook RAG：依据指定教材获取知识证据，支持有依据的回答。
接下来，最值得研究的问题不再是“AI 能不能理解学生、找到知识”，而是：
AI 能不能依据学生当前的掌握情况，选择合适的教学方法，并通过交互真正帮助学生学会知识？
这也是教育 Agent 与普通问答 Agent 的关键区别。
建议的下一阶段能力架构
已有基础能力
意图理解 + 学生记忆 + 教材检索


01
教学决策引擎
选择教什么、怎么教


02
教学工具系统
调用计算、图示、练习工具


03
学习诊断评价
发现具体错误与误解


04
交互式教学
提示、追问、反馈、复盘




教学效果评测与持续优化
不仅评价回答质量，还评价学生是否掌握知识


为什么建议这样做？
一篇发表于 2025 年《PNAS》的随机实验研究发现：普通 GPT 工具能够提高学生在练习时的表现，但在失去 AI 帮助后的独立测验中，部分学生表现反而下降；增加教学保护机制的 GPT Tutor 大幅缓解了这种负面影响，但并未证明能显著提高独立测验成绩。
这说明 回答正确、练习完成得快，不等于学生真正学会了。

PNAS
+2



因此，我建议将下一阶段的优化目标从单纯的 Answer Quality，扩展为：
Pedagogical Decision Quality（教学决策质量）+ Learning Outcome（学习结果）+ Agent Reliability（系统可靠性）。
二、GitHub 教育类 Agent 项目调研
这一批项目中，我认为最有价值的不是功能最多的学习平台，而是有明确教学机制、相关论文支持、代码或评测数据公开的项目。
1. 值得重点研究的教育 Agent









Verify-then-Generate
优先研究

ETH Zürich 相关研究 · EMNLP 2024
核心思想：先检查学生推理的每一个步骤，定位错误，再生成有针对性的教学反馈，而不是直接让大模型猜测学生哪里不懂。
最适合你们： 数学证明、集合运算、关系性质、离散数学解题过程的逐步纠错。












MathDial
EMNLP 2023 · 教师—学生教学对话数据集
提供约 2,861 段教学对话，包含学生错误、教师提示与教学引导。其研究指出，模型擅长解题并不意味着擅长教学。
最适合你们： 构建启发式教学动作库、多轮教学示例与模拟学生测试。

GitHub
+1















Book2Dial
ACL 2024 Findings · 基于教材生成教学对话
将结构化教材内容转换成模拟的师生交互，能够生成不同学生背景下的问题与回答。
最适合你们： 利用现有十章教材，自动建立具有教材来源的教学测试集，而不是继续改造检索链路。

GitHub















PedagogicalRL
EMNLP 2025 Oral · 多轮教学强化学习
通过教师模型、模拟学生、评审模型组成训练交互，以教学质量而不仅是解题正确率作为优化目标。
最适合你们： 借鉴教学奖励函数、模拟学生和策略评测；现阶段不建议直接运行大型强化学习训练。

GitHub
+1















LearnHouse
开源学习平台 · Next.js + FastAPI
包括课程、内容管理、学习界面、AI 和分析功能，与现有技术栈有一定重合。
最适合你们： 借鉴课程展示、学习体验与教师端交互。不建议整体替换你们已有系统；项目采用 AGPL-3.0，代码复用需要特别核查许可证义务。

GitHub






另外还有两个值得作为补充参考的项目。
EduChat：华东师范大学相关教育对话模型项目，覆盖启发式教学、自动出题、作业批改和课程辅导。更适合借鉴教育场景的指令设计、任务划分与训练数据建设，不适合直接把整个大模型当成你们的教学引擎。

DrJZhou/EduChat · GitHub
+1



Tutor CoPilot：研究让 AI 实时给人类教师提供教学建议。公开仓库主要是演示 Notebook，而非完整生产系统，但它关于教师策略辅助的研究，对教师端功能很有价值。

GitHub



2. 最有价值的代码在哪里？
以下路径均依据仓库公开文件结构或 README 核对。这里的“复用”指能找到明确的实现入口，不代表可以不修改就接入你们的项目。
项目	已核实的代码入口	建议用途
Verify-then-Generate	verification/error_verification.py	学生步骤验证
Verify-then-Generate	verification_based_response/main.py	根据错误诊断生成反馈
MathDial	interactivetutoring/evaluate.py	模拟交互评价
Book2Dial	Persona_models/Persona_high_info_final.py	基于教材生成对话
PedagogicalRL	src/classroom.py	教师—学生—评审交互机制
PedagogicalRL	prompt_templates/	教学规则与评审提示
MathTutorBench	tasks/、dataloaders/、main.py	自动化教学能力测试
特别提醒：Book2Dial、MathDial、Verify-then-Generate 和 MathTutorBench 的公开资源涉及 CC BY-SA 4.0 条款；数据、研究脚本与衍生代码的许可边界需要分别核实，不能简单当作 MIT 项目自由复制进产品。

GitHub
+5



三、最值得借鉴的教学理论与论文
只借鉴 Agent 技术还不够。你们需要一套能够解释“为什么这样教学生”的理论依据，否则教学策略容易退化成不同的 Prompt 模板。
我筛选了六个值得重点研究的方向。
1. Google LearnLM 教学框架（2026）
论文：Google's Pedagogical Framework for Generative AI to Support Human Learning
Google 总结了五项教育 AI 原则：主动学习、认知负荷管理、激发好奇心与动机、适应学习者、深化元认知。
对你们最直接的启发是：教学引擎要决定知识拆分粒度、解释深度、练习时机和反思方式，而不是仅调整回答长短。
研究论文与官方介绍 

research.google





2. ICAP 学习参与框架（2014）
Chi & Wylie · The ICAP Framework
从被动接收信息（Passive），到主动处理（Active）、自己构建解释（Constructive）、与他人交互构建知识（Interactive）。
对应到 Agent，可以从只给解释，升级为让学生预测、推导、举反例、纠正自己的推理。该框架关注认知参与，不代表每次交互越多就一定越好。
原始论文 

数字对象标识符 (DOI)





3. GuideEval：适应性教学引导（2025）
Discerning minds or generic tutors?
将教学引导分成三个阶段：Perception（识别学生状态）→ Orchestration（选择教学策略）→ Elicitation（激发学生思考）。
与你们已经实现的意图识别不同，这里要识别的是学生在当前知识点上的认知困难。例如学生知道定义，却不能判断一个关系是否具有传递性。
GuideEval 论文 

arXiv





4. 检索练习与分散学习
Roediger & Karpicke（2006）；Dunlosky et al.（2013）
学生反复阅读解释，与学生主动回忆并不等价。研究支持将练习测验和分散练习用于促进长期保持。
对你们的意义是：Agent 不能只记录“某知识点已经解释过”，还需要安排学生独立回答、延迟复测，并根据真实结果更新已有学习状态。
学习方法综述 · 检索练习研究 

APS
+2





5. MRBench 与 MathTutorBench（2025）
NAACL 2025；EMNLP 2025 Oral
这两项工作把教学能力拆成可测试维度，包括错误定位、避免过早泄露答案、提示有效性、教学连贯性等。
可以直接帮助你们建立 Teaching Quality Evaluator，避免只有模型主观评价“这段回答不错”。
MRBench 仓库 · MathTutorBench 仓库 

GitHub
+2





6. Rethinking Scaffolding in LLM Tutors（2026）
真实部署中教学支架与学生响应不匹配的问题
研究分析了多个教学数据集中的 9,490 次对话，指出真实学生经常不遵循 AI 预设的启发式对话路径。
这对产品设计非常重要：不要把苏格拉底式提问设计成必须完成的固定流程。 学生想快速查定义时应该能获得定义；正在做探索练习时才适合多轮提示；学生连续受挫时应允许切换为讲解或示范。
2026 年论文 

arXiv





四、其他类型的成熟 Agent，有哪些代码值得复用？
教育项目提供教学方法，通用 Agent 框架则提供更成熟的执行、工具、观测和优化能力。
开源项目	可以直接利用的能力	对你们的建议
LangGraph	状态图、暂停与恢复、人工介入	若现有编排缺少可靠恢复机制，可选用；不为它重写整个系统
OpenAI Agents SDK	工具定义、Guardrails、Trace、运行控制	参考工具安全边界，也可采用其 SDK
Pydantic Evals	测试集、输出评价、工具轨迹评价	很适合直接接入 Python 教学评测
Langfuse	LLM 调用追踪、Prompt 版本、评测、实验对比	可作为调试与教学质量观测平台
DSPy	依据评价指标优化 Prompt 和示例	有稳定的教学评测集后再引入
SymPy	符号计算、等式求解与验证	离散数学中适合工具化的符号题型
NetworkX	图算法、图性质检查	用于图论教学和具体反例验证
LangGraph 的检查点支持中断恢复与状态持久化；OpenAI Agents SDK 提供函数工具、输入输出约束与运行追踪；Pydantic Evals 则可以测试最终答案和工具调用路径。它们处理的是不同职责，不需要同时引入两个完整的 Agent 运行框架。

Docs by LangChain
+3



Langfuse 核心功能采用 MIT 许可证，企业功能另有授权；DSPy 本身也是 MIT。SymPy 与 NetworkX 采用 BSD 类许可证，适合通过 Python 包直接集成。

Langfuse
+3



我建议怎么选？
对于现有 FastAPI 后端，第一轮只需要引入少量能力：
- Pydantic Evals：先建立可重复的教学质量评测。
- Langfuse：检查一次教学回答究竟经过哪些决策、工具与模型调用。
- SymPy + NetworkX：让教学引擎具备部分确定性的数学验证能力。
- DSPy：在收集足够的高质量评价样例后，再优化教学提示与模块调用。
LangGraph 和 OpenAI Agents SDK 更适合作为编排能力的备选方案，而不是必选的新架构。
尤其是你们原先已经讨论过 TeachingDecisionEngine、StrategyRouter、QuestionDesigner 和 QualityChecker 一类模块。如果这些仍保留在当前代码中，应先进行差距检查与能力增强，而非从头开发同名模块。
五、结合你们项目，我建议优先探索的六个优化方向
以下优先级综合考虑了教学价值、代码复用程度、实施难度，以及与现有模块的兼容性。它们是研发排序建议，不是已经验证的性能排名。

方向 A：自适应教学决策引擎
P0

让 Agent 每轮决定是解释、追问、举例、纠错、提示还是练习，并结合教学目标和学生反应动态调整。
借鉴： GuideEval、LearnLM、MathDial。
自行实现： 教学动作选择、策略切换和教学状态规则。现有教学决策原型可以作为起点。




方向 B：学生错误诊断与纠错
P0

从“判断答案对不对”，升级为“定位哪一步出错、错误属于什么类型、下一步应该提示什么”。
借鉴： Verify-then-Generate、MRBench。
复用： 步骤验证研究代码、SymPy 和 NetworkX；数学证明的语义正确性仍需要单独设计验证机制。




方向 C：教学质量评测体系
P0

分别测试知识正确性、教学策略、错误纠正、工具调用和学生独立完成任务的能力。
复用： MathTutorBench、MRBench、Pydantic Evals、Langfuse。
自行实现： 中文教材专用测试题、教师评分标准和对学生实际学习效果的评价。




方向 D：教学工具调用系统 — P1
把抽象教学动作变成可执行工具，如反例生成、集合运算、图性质检验、分步验证、知识点测验和图示。
复用： SymPy、NetworkX、Agent SDK 的工具定义与约束机制。
自行实现： 教学工具选择规则、结构化输入输出、结果校验以及失败降级。




方向 E：主动练习与掌握学习闭环 — P1
将一次知识解释转化为练习、反馈、迁移题和延迟测试。使用已有 Memory 记录的学习证据，而不是重新建设记忆系统。
借鉴： ICAP、检索练习理论、OpenTutor。
可复用： Py-FSRS 的复习调度能力。题目难度、掌握证据、练习编排仍需自建。

GitHub
+1







方向 F：模拟学生与自动改进 — P2
用模拟学生压力测试 Agent 能否面对不同水平、错误类型和学习行为，而不是只测试单轮问题。
借鉴： PedagogicalRL、Book2Dial。
先复用： 对话生成和多轮评价脚本。优先做离线回归测试，暂不采用成本较高的教学强化学习训练。



六、用一个具体例子说明这些模块如何协作
假设学生正在学习离散数学的“关系的传递性”，输入：
我觉得这个关系满足传递性，但我不会证明。

传统教材 RAG 可能直接给出传递性的定义和证明方法。
优化后的教学 Agent 可以这样处理：
1. 教学状态判断
   已有意图识别得知学生需要证明帮助；教学决策模块进一步判断，学生目前的困难可能是不会组织证明，而非完全不理解定义。
2. 选择教学动作
   先要求学生写出一个推理起点，或让学生说明传递性的判断条件。若其已经多次尝试，转为提供具体示范。
3. 使用数学工具
   对有限关系，可以用确定性算法检查是否传递，并寻找反例。例如存在 \((a,b)\in R\)、\((b,c)\in R\)，但 \((a,c)\notin R\)，就构成传递性的反例。
4. 定位推理问题
   如果学生把“对称性”和“传递性”混淆，诊断模块识别为概念误解，生成针对性的对比例子和反馈。
5. 验证真正掌握
   给出另一个关系，让学生独立判断并解释。将学生作答、提示使用情况和测验结果作为学习证据，交给已有记忆系统更新状态。

这与普通 Chatbot 的差别是：AI 不只是解释定义，而是通过诊断—教学—检验完成一个学习单元。
当然，如果学生明确要求直接查看完整证明，系统不应强制他回答一系列问题。更合理的是提供证明，并允许他选择进一步练习。
七、建议的下一阶段技术架构
我建议保留现有 FastAPI、教材检索、Intent 和 Memory，只增加教学决策及执行层。
#chatgpt-mermaid-_r_5pi_{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;fill:rgb(26, 28, 31);}@keyframes edge-animation-frame{from{stroke-dashoffset:0;}}@keyframes dash{to{stroke-dashoffset:0;}}#chatgpt-mermaid-_r_5pi_ .edge-animation-slow{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 50s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_5pi_ .edge-animation-fast{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 20s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_5pi_ .error-icon{fill:rgba(255, 255, 255, 0.96);}#chatgpt-mermaid-_r_5pi_ .error-text{fill:rgb(26, 28, 31);stroke:rgb(26, 28, 31);}#chatgpt-mermaid-_r_5pi_ .edge-thickness-normal{stroke-width:1px;}#chatgpt-mermaid-_r_5pi_ .edge-thickness-thick{stroke-width:3.5px;}#chatgpt-mermaid-_r_5pi_ .edge-pattern-solid{stroke-dasharray:0;}#chatgpt-mermaid-_r_5pi_ .edge-thickness-invisible{stroke-width:0;fill:none;}#chatgpt-mermaid-_r_5pi_ .edge-pattern-dashed{stroke-dasharray:3;}#chatgpt-mermaid-_r_5pi_ .edge-pattern-dotted{stroke-dasharray:2;}#chatgpt-mermaid-_r_5pi_ .marker{fill:rgba(26, 28, 31, 0.494);stroke:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_5pi_ .marker.cross{stroke:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_5pi_ svg{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;}#chatgpt-mermaid-_r_5pi_ p{margin:0;}#chatgpt-mermaid-_r_5pi_ .label{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:rgb(26, 28, 31);}#chatgpt-mermaid-_r_5pi_ .cluster-label text{fill:rgb(26, 28, 31);}#chatgpt-mermaid-_r_5pi_ .cluster-label span{color:rgb(26, 28, 31);}#chatgpt-mermaid-_r_5pi_ .cluster-label span p{background-color:transparent;}#chatgpt-mermaid-_r_5pi_ .label text,#chatgpt-mermaid-_r_5pi_ span{fill:rgb(26, 28, 31);color:rgb(26, 28, 31);}#chatgpt-mermaid-_r_5pi_ .node rect,#chatgpt-mermaid-_r_5pi_ .node circle,#chatgpt-mermaid-_r_5pi_ .node ellipse,#chatgpt-mermaid-_r_5pi_ .node polygon,#chatgpt-mermaid-_r_5pi_ .node path{fill:rgb(224, 237, 254);stroke:rgb(83, 154, 248);stroke-width:1px;}#chatgpt-mermaid-_r_5pi_ .rough-node .label text,#chatgpt-mermaid-_r_5pi_ .node .label text,#chatgpt-mermaid-_r_5pi_ .image-shape .label,#chatgpt-mermaid-_r_5pi_ .icon-shape .label{text-anchor:middle;}#chatgpt-mermaid-_r_5pi_ .node .katex path{fill:#000;stroke:#000;stroke-width:1px;}#chatgpt-mermaid-_r_5pi_ .rough-node .label,#chatgpt-mermaid-_r_5pi_ .node .label,#chatgpt-mermaid-_r_5pi_ .image-shape .label,#chatgpt-mermaid-_r_5pi_ .icon-shape .label{text-align:center;}#chatgpt-mermaid-_r_5pi_ .node.clickable{cursor:pointer;}#chatgpt-mermaid-_r_5pi_ .root .anchor path{fill:rgba(26, 28, 31, 0.494)!important;stroke-width:0;stroke:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_5pi_ .arrowheadPath{fill:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_5pi_ .edgePath .path{stroke:rgba(26, 28, 31, 0.494);stroke-width:1px;}#chatgpt-mermaid-_r_5pi_ .flowchart-link{stroke:rgba(26, 28, 31, 0.494);fill:none;}#chatgpt-mermaid-_r_5pi_ .edgeLabel{background-color:rgb(255, 255, 255);text-align:center;}#chatgpt-mermaid-_r_5pi_ .edgeLabel p{background-color:rgb(255, 255, 255);}#chatgpt-mermaid-_r_5pi_ .edgeLabel rect{opacity:0.5;background-color:rgb(255, 255, 255);fill:rgb(255, 255, 255);}#chatgpt-mermaid-_r_5pi_ .labelBkg{background-color:rgba(255, 255, 255, 0.5);}#chatgpt-mermaid-_r_5pi_ .cluster rect{fill:rgba(255, 255, 255, 0.96);stroke:rgba(26, 28, 31, 0.08);stroke-width:1px;}#chatgpt-mermaid-_r_5pi_ .cluster text{fill:rgb(26, 28, 31);}#chatgpt-mermaid-_r_5pi_ .cluster span{color:rgb(26, 28, 31);}#chatgpt-mermaid-_r_5pi_ div.mermaidTooltip{position:absolute;text-align:center;max-width:200px;padding:2px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:12px;background:rgba(255, 255, 255, 0.96);border:1px solid rgba(26, 28, 31, 0.08);border-radius:2px;pointer-events:none;z-index:100;}#chatgpt-mermaid-_r_5pi_ .flowchartTitleText{text-anchor:middle;font-size:18px;fill:rgb(26, 28, 31);}#chatgpt-mermaid-_r_5pi_ rect.text{fill:none;stroke-width:0;}#chatgpt-mermaid-_r_5pi_ .icon-shape,#chatgpt-mermaid-_r_5pi_ .image-shape{background-color:rgb(255, 255, 255);text-align:center;}#chatgpt-mermaid-_r_5pi_ .icon-shape p,#chatgpt-mermaid-_r_5pi_ .image-shape p{background-color:rgb(255, 255, 255);padding:2px;}#chatgpt-mermaid-_r_5pi_ .icon-shape .label rect,#chatgpt-mermaid-_r_5pi_ .image-shape .label rect{opacity:0.5;background-color:rgb(255, 255, 255);fill:rgb(255, 255, 255);}#chatgpt-mermaid-_r_5pi_ .label-icon{display:inline-block;height:1em;overflow:visible;vertical-align:-0.125em;}#chatgpt-mermaid-_r_5pi_ .node .label-icon path{fill:currentColor;stroke:revert;stroke-width:revert;}#chatgpt-mermaid-_r_5pi_ .node .neo-node{stroke:rgb(83, 154, 248);}#chatgpt-mermaid-_r_5pi_ [data-look="neo"].node rect,#chatgpt-mermaid-_r_5pi_ [data-look="neo"].cluster rect,#chatgpt-mermaid-_r_5pi_ [data-look="neo"].node polygon{stroke:url(#chatgpt-mermaid-_r_5pi_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_5pi_ [data-look="neo"].swimlane.cluster rect{filter:none;}#chatgpt-mermaid-_r_5pi_ [data-look="neo"].node path{stroke:url(#chatgpt-mermaid-_r_5pi_-gradient);stroke-width:1px;}#chatgpt-mermaid-_r_5pi_ [data-look="neo"].node .outer-path{filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_5pi_ [data-look="neo"].node .neo-line path{stroke:rgb(83, 154, 248);filter:none;}#chatgpt-mermaid-_r_5pi_ [data-look="neo"].node circle{stroke:url(#chatgpt-mermaid-_r_5pi_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_5pi_ [data-look="neo"].node circle .state-start{fill:#000000;}#chatgpt-mermaid-_r_5pi_ [data-look="neo"].icon-shape .icon{fill:url(#chatgpt-mermaid-_r_5pi_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_5pi_ [data-look="neo"].icon-shape .icon-neo path{stroke:url(#chatgpt-mermaid-_r_5pi_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_5pi_ .node text{font-size:14px;font-weight:600;letter-spacing:normal;fill:rgb(0, 79, 153);}#chatgpt-mermaid-_r_5pi_ .edgeLabels text{font-size:13px;font-weight:600;letter-spacing:-0.08px;fill:rgb(0, 79, 153);}#chatgpt-mermaid-_r_5pi_ .node tspan[font-weight="normal"],#chatgpt-mermaid-_r_5pi_ .edgeLabels tspan[font-weight="normal"]{font-weight:600;}#chatgpt-mermaid-_r_5pi_ .edgeLabel .label rect{opacity:1;rx:13px;ry:13px;fill:rgb(245, 250, 255);stroke:rgb(206, 219, 229);stroke-width:1px;}#chatgpt-mermaid-_r_5pi_ .node rect,#chatgpt-mermaid-_r_5pi_ .node circle,#chatgpt-mermaid-_r_5pi_ .node ellipse,#chatgpt-mermaid-_r_5pi_ .node polygon,#chatgpt-mermaid-_r_5pi_ .node path{fill:rgb(229, 243, 255);stroke:rgba(0, 0, 0, 0.1);stroke-width:1px;}#chatgpt-mermaid-_r_5pi_ .node rect{rx:16px;ry:16px;}#chatgpt-mermaid-_r_5pi_ .node.mermaid-decision .label-container{fill:rgb(245, 250, 255);stroke:rgb(206, 219, 229);stroke-dasharray:2,2;}#chatgpt-mermaid-_r_5pi_ .edgePaths .flowchart-link{stroke:rgba(26, 28, 31, 0.494);stroke-width:1px;stroke-linecap:round;stroke-linejoin:round;}#chatgpt-mermaid-_r_5pi_ .marker{fill:rgba(26, 28, 31, 0.494);stroke:rgba(26, 28, 31, 0.494);}#chatgpt-mermaid-_r_5pi_ :root{--mermaid-font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}学生输入已有 Intent Engine整合学习任务与学生状态已有 MemoryTeaching Decision Engine教学动作解释 / 提示 / 追问练习 / 纠错受控工具执行已有教材 RAG结构化教学回答学生作答或反馈学习证据与质量评价





教学决策可以采用统一的数据结构，而不是为每种策略创建一个独立 Agent。
例如：
class TeachingDecision(BaseModel):    teaching_goal: str    student_difficulty: str | None    teaching_action: str    hint_level: int    requires_tool: bool    requires_practice: bool    decision_reason: str



这是建议的新接口示例，不是某个开源仓库中可以原样复制的实现。
这样做还有三个好处：可以记录每次教学动作的原因，可以在离线评测中比较策略选择是否合理，也能避免学生尚未回答时 Agent 自己连续生成多轮“师生对话”。
八、最终代码复用矩阵
这是我建议你们用于技术选型的清单。
模块	项目	复用判断
教学策略库	MathDial、GuideEval	借鉴理论与数据，自建执行逻辑
教学决策工作流	LangGraph	可直接使用框架，也可保留已有编排
错误步骤验证	Verify-then-Generate	研究代码需要改造与适配
数学工具	SymPy、NetworkX	直接安装调用
多轮模拟学生	PedagogicalRL	借鉴交互状态机，训练代码暂不接入
教材生成测试对话	Book2Dial	可改造离线脚本
教学能力评测	MathTutorBench	可复用评测框架，替换领域数据
教学评价维度	MRBench	复用评分思想和许可允许的数据
LLM 工程评价	Pydantic Evals	直接集成
Agent 可观测性	Langfuse	直接集成或独立部署
教学 Prompt 优化	DSPy	建立基线后直接使用
复习调度	Py-FSRS	若现有系统未实现则直接集成
这里需要区分三种情况：“可直接安装”表示成熟的软件依赖，“改造研究代码”表示还需要依赖适配、测试及许可检查，“借鉴思想”则不能当作已有可运行产品模块。最终还要通过你们当前代码的接口、Python 版本和依赖检查才能确认实际复用范围。
九、下一步怎么推进最合理？
我建议按照下面的四个研发阶段推进，而不是同时开工所有功能。
01阶段 1：建立教学能力基线检查现有 TeachingDecisionEngine、QuestionDesigner、QualityChecker 等模块的实现程度。建立中文离散数学教学测试集，接入教学评价和运行追踪。验收目标：能够稳定复现一次教学对话，定位策略、工具与回答质量问题。
02阶段 2：优化教学决策与纠错
03阶段 3：扩展工具与练习闭环
04阶段 4：模拟学生与持续改进
评价优化效果时，应该重点看什么？
建议设置三个层级的指标：
层级	评价重点
回答层	教材事实正确性、引用准确性、内容清晰度
教学层	错误定位、提示有效性、策略选择、答案泄露与无效追问
学习层	无 AI 辅助的独立作答、迁移题表现、延迟复测结果
建议将现有版本作为对照组，使用同一批题目和学生状态，先比较教学策略与纠错版本，再通过真实学生的小规模交叉测试验证学习效果。不要仅靠模拟学生或 LLM 评审就宣称学习效果提升。