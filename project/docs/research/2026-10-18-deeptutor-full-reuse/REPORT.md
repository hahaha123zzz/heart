# DeepTutor 全量复用深度调研

调研日期：2026-10-18（Asia/Shanghai）
源项目：D:/deeptutor
固定提交：6cf793bd868ba5ecbe64722936d4be8fab5a01df（本地 v1.6.14）
目标项目：E:/项目/heart，主要可运行入口为 project/integration/discrete-math-tutor
用户已明确：保留现有页面；尽量整块复用 DeepTutor 后端与组件；复杂度不作为排除理由。
本轮交付为源码调研与接入设计，没有迁入业务源码或改变应用行为。

后续实施已于同日开始，实际改动与接通状态见 [实施计划](IMPLEMENTATION_PLAN.md) 和 [执行记录](EXECUTION_LOG.md)；以下内容保留为调研基线。

## 1. 结论

应将 DeepTutor 视为可整体引入的学习平台能力底座，复用边界扩大到完整后端包、运行资源、配套前端模块、相关测试和工程检查。再以我们已有的教材证据、教学规则、正式题目审核、课程成员与学习事实记录作为课程业务层。

不是只抽取几个工具函数，也不必把我们已有页面替换成它的整套网站。推荐同仓库固定源码版本，完整保留上游运行生命周期，通过后端兼容入口和前端组件挂载接入当前页面。

本轮整理出 **43 个相关复用单元**，详见 [REUSE_MATRIX.md](REUSE_MATRIX.md)。这些分类是复用与适配形态，不是按复杂度缩减范围。与核心课堂无直接关系的外部 IM、登录方式、特定模型/远程服务连接器也保留为候选，不因带入源码就自动启用。

## 2. 调研证据与可信范围

- 对本地后端包进行 Python AST 静态扫描，识别 **1,030 个非 tests 目录的 Python 模块**；扫描未发现 Python 语法错误。语法通过不表示模块导入、依赖安装或功能可运行。
- deeptutor 包去除 __pycache__ 后共 **1,245 个文件、12,051,439 字节（约 11.49 MiB）**。包中包含提示词、模板与资源。
- 前端按源码后缀扫描到 **1,289 个 TS/TSX/MJS/CJS 文件**，包含测试与构建脚本，不是 1,289 个可直接移植组件。
- tests/ 下发现 **756 个 test_*.py 文件**；不含 deeptutor/learning/tests 内的额外测试。本轮没有将它们全部运行或宣称全部通过。
- 阅读了原始《实验心理学课程智能体平台功能》、详细技术设计与双主线执行计划的 Word 文本，建立了八项原始需求到上游实现的对应关系。
- 核查了能力注册表、API 路由入口、服务实现、前端组件/状态/传输层、依赖与资源声明及相关测试。
- 运行 **19 项不写磁盘的源码级断言**，涉及掌握度、选择题判分、复习调度、引文匹配与可视化协议。包含刻画现有局限的反例，不能作为整个平台的功能验收。
- 未访问源项目的真实配置或密钥文件内容，未启动完整服务、调用模型、解析教材、重建索引、迁移数据库或启动外部 Agent。
- 源码依据、路径存在性、代表性符号行号、文件 SHA256 与本地改动信息见 [SOURCE_AUDIT.json](SOURCE_AUDIT.json)。

静态依赖分析包含函数内延迟导入、TYPE_CHECKING 和可识别的动态类路径，结果是可能依赖上界，不是启动时实际加载数量，也不是必须安装的全部依赖。它用于解释为什么完整能力应连同共享服务迁入，不用来估算工期或运行成本。

## 3. 我们的八项原始需求，哪些可以整体复用

| 原始需求 | 可整体复用的 DeepTutor 系统 | 仍需接到我们业务的部分 |
| --- | --- | --- |
| 课程资源与测验 | CourseService、syllabus、知识库、阅读材料库、题库、出题、Practice | 课程/班级成员、教师发布的章节与题目版本、正式评分 |
| 学习数据统计 | 统一 Assessment、作答日志、Practice analytics、学习活动/课程状态/个人仪表板 | 班级与课程口径、教师查询范围、聚合脱敏、数据解释 |
| 教材 RAG 问答 | Agent loop、工具注册、知识库管理、七类解析适配、多 RAG 管线、嵌入/重排、来源事件 | 教材优先级、发布版本、证据选择、回答语义支持、精确引用 |
| 图文结合答疑 | visual_assets、source_visuals、覆盖报告、页面/区域裁图、Reading 图像工具、Visualize、原图练习 | 我们的生成阅读版页码与原文映射、实验图表含义、来源审核 |
| 引导式与分层辅导 | Mastery Path 全链路、四类知识目标、题卡、讲解/测试/复习模式、AskQuestions、Solve | 提示层级、等待学生、当前题答案开放限制、认知负荷策略 |
| 学习难点跟踪与复习 | 三层 Memory、Learning Journal、统一学习证据、题库与目标两类复习调度、任务提醒 | 误解的确认/纠正/重开，独立作答资格、证据去重 |
| 交互风格自定义 | Persona、learner_profile、prompt blocks、设置与记忆治理组件 | 用户确认偏好、会话覆盖/长期设置优先级、课程规则优先 |
| 学习画像与自动适配 | Mastery 状态、定量/定性通过门槛、难点/题目来源、学习进度与统计 | 我们的证据政策、置信度与能力语义，教师/学生纠错机制 |

对应原始需求文件：[功能原稿](<E:/项目/heart/实验心理学课程智能体平台.docx>)、[详细设计](<E:/项目/heart/project/docs/实验心理学课程智能体平台详细技术设计方案-v2.docx>)。

## 4. 本轮新增确认的高价值复用系统

### 4.1 统一测评与题库复习：补上跨场景闭环

[learning/assessment.py](<D:/deeptutor/deeptutor/learning/assessment.py>) 已将 Mastery、Book 和 Reading 等场景的测评归一，使用 origin_type、origin_ref、turn_id、question_id 标识来源，写入共享作答日志，并能关联知识目标的保留状态。

[services/practice](<D:/deeptutor/deeptutor/services/practice>) 不只是练习页面：包括 CSV/TSV/XLSX/JSON 导入预览与提交、中文列名映射、输入大小/行列限制、错题入队、版本冲突、幂等复习、保留原始作答、到期队列和分时区统计。配套测试明确覆盖“重复请求不重复推进”“两个标签页冲突”“复习不覆盖原始作答”。

这套系统应连同 question_notebook 的存储、API、前端筛选与题卡整体迁入，接入我们现有练习与学习事件。它支持个人练习/错题管理，但没有因此自动形成我们的正式题审核发布流程。

### 4.2 Learning Journal：跨会话目标与教学接续

[services/learning_journal](<D:/deeptutor/deeptutor/services/learning_journal>) 保存 mission、last_session、records，并提供原子写入、去重、模型可读取/更新的工具以及有限的上下文注入。

可直接承担“本次学什么、上次停在哪里、下次先做什么”的接续层，与当前 MemoryManager 衔接。源码明确把它定义为 soft teaching state，而不是另一套掌握度计算。课程画像与能力结论仍以作答证据为依据。

### 4.3 三层记忆与治理：不只是长期摘要

[services/memory](<D:/deeptutor/deeptutor/services/memory>) 提供 L1 原始事件/工作区快照、L2 分场景文档、L3 汇总槽位、脚注引用、来源范围校验、update/audit/dedup/merge、行级修改、备份与撤销、运行过程事件和治理 UI。

这比只复制“记忆搜索函数”完整得多。应该整套复用，并将当前项目已经核验的学生事件作为输入。注意 consolidator 的运行管理器保存在内存，进程重启后运行记录会消失；文档与元数据逐步原子落盘，不能称为所有执行过程都可跨重启恢复。

### 4.4 Book Engine：章节学习内容的完整生成系统

[book/engine.py](<D:/deeptutor/deeptutor/book/engine.py>)、[compiler.py](<D:/deeptutor/deeptutor/book/compiler.py>) 已实现来源探索、主题/章节大纲、页面规划、逐块生成、增量落盘、失败处理、进度、共享内容的个人阅读覆盖层与 Markdown 导出。

默认生成器注册 **13 类实际实现**：text、callout、quiz、user_note、figure、interactive、animation、code、timeline、flash_cards、deep_dive、section、concept_graph。可用于心理学章节导学、概念比较、实验步骤、复习卡、流程图、测验和交互演示。

BlockType 还声明 diagnostic、pretest、retrieval_practice、error_diagnosis、module_test、progress_dashboard 六个名称，但未在默认生成器中注册，不能把枚举项算成现成生成能力。另外 InteractiveGenerator 当前返回空 source_anchors；生成成功/格式校验通过不证明它已经绑定教材证据。迁入后必须加入我们的来源绑定和教学内容核验。

### 4.5 阅读、批注、笔记、学习路径之间已有接口

[reading/knowledge_capture.py](<D:/deeptutor/deeptutor/reading/knowledge_capture.py>) 可以整理阅读批注、发送到 Notebook，并形成 Mastery 来源。阅读引擎有 material/revision/locator、目录、全文搜索、批注、导出、原页查看、阅读动作与随堂测验。

前端有 TextQuoteSelector + TextPositionSelector、前后文消歧重锚定、PDF/EPUB、批注列表/弹层、阅读动作卡和笔记捕获。这些适合整套搬到现有阅读页面，而不是只迁一个 PDF 组件。

### 4.6 报告写作、音视频与实验图表练习

- [co_writer](<D:/deeptutor/deeptutor/co_writer>) 与配套编辑器已有选区编辑、流式修改、草稿/操作历史、资料上下文和 Markdown/DOCX 互转，可用于实验报告辅导。实验报告模板、评分点、真实数据和引用规则由本课程提供；它不是现成的心理学报告判分系统。
- [voice](<D:/deeptutor/deeptutor/services/voice>) 包括 STT/TTS、多供应商适配、数学口语化、录音与播放；audio_overview 能基于知识库生成双人导读音频和文本。
- [video_learning](<D:/deeptutor/deeptutor/video_learning>) 和 reading/ingestion 具备已有远程平台来源的字幕/时间戳、标记与笔记，可接实验示范材料。未将远程平台适配泛化为“任意本地录像都能直接学习”。
- [learning/visual_practice.py](<D:/deeptutor/deeptutor/learning/visual_practice.py>) 支持 identification、relationship、table_graph、comparison 四种任务，带原图绑定、来源哈希、提示记录与答案隐藏。适合实验装置、变量关系、数据曲线和设计对比。

### 4.7 课程编排、任务与多角色讨论

Course Study 可读取课程资源状态并交接至阅读、学习路径、题库、笔记和聊天。Task Board 能关联会话、持久化任务状态；cron 提供 at/every/cron 调度与后台 leader 执行，可承接复习提醒，但提醒投递不应重新计算第二套复习队列。

Partner Groups 提供 panel_parallel、sequential、debate 三种讨论模式，可用于教师配置的不同助教角色/实验设计讨论。外部 IM 通道与 Agent 连接器可保留源码候选，实际启用按课堂需求决定；本轮没有进行消息外发。

## 5. 后端和前端要一起迁入的范围

### 后端

建议保留 deeptutor/ 整包，连同 pyproject.toml、requirements/、许可证、第三方声明及测试。其共享服务和延迟导入关系密集，完整保留可避免重建一套缩水运行时。

同时迁入 YAML/JSON 提示词与配置模板、Markdown Skill、Jinja 模板及相关脚本。pyproject.toml 的 package-data 已明确声明这些资源，缺失它们会导致能力到首次实际运行时才失败。

11 个已注册顶层能力包括 chat、ask_questions、deep_solve、deep_question、deep_research、math_animator、visualize、mastery_path、immersive_reading、course_study、audio_overview。Book 和 Co-Writer 是另外的领域系统，不应因为不在这 11 项里就漏掉。

### 前端

保留当前页面外壳、导航、教材与聊天布局，迁入完整功能组件及其配套 Provider、context、hooks、lib、协议类型、错误/空态、样式与资源。相关目录：

| 现有区域 | 可迁入前端范围 |
| --- | --- |
| 对话区域 | web/features/chat、components/chat、components/common、components/activity、contracts、传输/恢复/草稿模块 |
| 教材阅读 | components/reading、reading-* lib、批注/选区/引用/阅读动作、笔记捕获 |
| 图解区域 | components/visualize、iframe-html、visualize-types、Mermaid/Chart.js/GeoGebra/Manim 展示 |
| 练习和复习 | components/space/question-bank、components/learning/practice、Mastery 题卡和评估事件 |
| 学习进度 | components/learning、components/space/learning、courses、学习日志与统计数据契约 |
| 记忆/偏好 | components/memory、Persona/learner profile、相应设置与治理接口 |
| 报告/资料 | features/co-writer、components/notebook、文件库/附件/预览 |
| 管理区域 | 知识库/解析/模型/工具/权限/运行状态的设置组件 |

源前端使用 Next.js 16 / React 19；当前阅读器是 Vite / React 18。推荐将完整功能按独立 React 根节点构建、通过挂载接口连接当前原生页面。上游 next/navigation、next/link、next/dynamic、i18n、CSS tokens 和路由依赖需要显式适配。不同 React 实例不跨根共享组件实例或 context；是否统一升级 React 应由阅读器兼容测试决定，而不是直接覆盖当前 package.json。

## 6. 推荐接入结构：保留页面，完整运行上游生命周期

进一步读取源码后，默认建议为 **同仓库源码副本 + 独立 DeepTutor 后端进程 + 当前应用兼容入口**。这仍然是直接复用源码，不依赖 D 盘路径，也不是把我们换成它的网站。

理由是 deeptutor/api/main.py 在模块导入时会创建/导出运行设置、配置日志，并在 lifespan 中启动容器、迁移、进度端口与后台服务。直接 import 后挂到当前 FastAPI，可能把进程配置、单例与生命周期混在一起。完整后端单独运行更容易保留上游行为。SDK 嵌入仍是候选，但必须明确处理其配置与生命周期。

建议结构（为接入设计，尚未创建）：

    project/
      vendor/DeepTutor/                 # 固定源码、资源、测试与声明
      integration/discrete-math-tutor/
        main.py                        # 当前页面和 API 入口保留
        integrations/deeptutor/         # 身份/课程/协议/测评适配
        frontend/deeptutor/             # 功能组件构建产物
      docs/research/2026-10-18-deeptutor-full-reuse/

请求链路：

    当前页面与组件
        → 当前 API / SSE 兼容入口
        → 服务端解析身份、课程、任务与证据约束
        → DeepTutor 回合运行时及完整能力
        → 本项目发布教材、正式题目、教学规则
        → 统一测评事件和当前页面结果

DEEPTUTOR_HOME 指向新接入版本的独立运行目录。源码可以完整迁入，data/、.env、真实 API Key、聊天记录、数据库与已有索引不能当代码资源直接覆盖到我们项目中。上游工作区迁移工具是其自身格式的迁移，不是我们 SQLAlchemy 表的自动迁移器。

## 7. 六个必须明确的兼容接口

1. **身份与资源范围**：服务端绑定 student_id / 用户 / 课程 / 工作区；不把浏览器传来的任意 student_id 当上游权限依据。上游 user context、grants、PathService 与现有课程成员体系映射一次。
2. **请求与流式事件**：当前 ChatRequest/PDFSelection/reader_location/task revision 转换为 TurnRequest/ReadingViewport 等契约；保留 turn_id、seq、终态、取消与重放。现有 SSE 可以继续使用，但要有明确协议映射。
3. **教材与证据**：当前 TextbookChunk、课程发布版本、阅读版 PDF 字符/矩形和证据 ID 对接知识库/reading material。页级定位不伪装成精确高亮，外部资料单独标注。
4. **教学与测评**：正式答案、hint_only、练习辅助状态、评分点和误解更新仍有服务端门槛。统一 attempt/source identity，避免同一作答在两套状态引擎重复推进。
5. **存储与迁移**：既有数据库保留；逐类导入并有映射记录。先做会话、课程、教材、作答来源映射，再决定各领域的事实来源，避免静默双写两个主库。
6. **前端与资源**：功能组件、路由/翻译/样式、构建资源、生命周期一起适配；保持现有页面入口、布局、来源跳转和练习答题行为。

现有关键入口已核实：main.py、agents/task_service.py、orchestrator.py、memory/memory_manager.py、memory/evidence_policy.py、knowledge/grounded_citations.py、knowledge/citation_index.py、knowledge/psychology_retrieval.py、visualization/on_demand.py、practice_api.py。

## 8. 源码实证：哪些默认规则需要课程化

### 8.1 引文比较不是精确证据核验

reading/_grounding.py 的 evidence_key 删除数字独占行、空白及连字符。实际断言确认 x-1 和 x1 的比较键相同；selection_range 对重复原文只返回首次匹配。

我们现有 [grounding_text.py](<E:/项目/heart/project/integration/discrete-math-tutor/knowledge/grounding_text.py>) 已在同一提交基础上保留所有候选并保留负号等差异。整体迁入 DeepTutor 时应保留这层课程证据适配，继续使用文档版本、重复语句消歧和几何定位。

### 8.2 默认开放题评分不是心理学正式评分器

learning/grading.py 的 open 分支按关键词覆盖比例判分。实际断言确认：期望答案“随机分配”时，“不采用随机分配”也被返回 True。

这不妨碍复用题卡、作答日志、练习 UI 与复习系统；正式判分应接我们已有 rubric、教材依据及必要的人工审核。services/practice/answers.py 对 short_answer/essay 等返回 None，明确保留未判定状态，这种边界应一起保留。

### 8.3 掌握度、复习与自述状态必须分清

compute_mastery 最近正确率加权并限制少量作答：一次全对上限 0.5，两次 0.8，三次全对可为 1.0。它是确定性规则分数，不能标成心理测量意义上的已校准掌握概率。

Mastery 对概念/设计类型有定性通过门槛，也允许显式 learner mastery override 影响路线推进，并暴露 learner/system 来源。课程正式进度需决定是否接受自述推进，不能把 learner override 写成考试成绩。Course 的 syllabus covered 也由学习者明确标记，不是自动推断的能力结果。

Practice scheduler 是 SM-2-style 冷启动规则；Mastery scheduler 是带类型先验的指数遗忘基线，源码明确不是拟合的 FSRS。两者可完整使用，但效果需要真实学习数据评估。

### 8.4 注册名称、角色名称与上线能力不是同一件事

Book 中额外六类 Guided Learning 枚举不等于有生成器；textbook_struct 的辅助算法有实现和测试，本轮未发现它已进入主要生产导入调用链。

multi_user/models.py 有 admin、teacher、student、user 四种角色，但源码说明只有 admin 自动提升权限。课程 registry 是按用户保存的个人资源容器。现成 teacher 字段和 guardian 授权都不能直接替代学校的班级、任课教师、发布审批与正式考试权限。

### 8.5 生成与执行能力需要保留真实边界

Visualize 有 SVG、Mermaid、mindmap、Chart.js、HTML 以及可选 Manim/GeoGebra 类型。格式/schema 校验不证明图表正确或教学有效。Book 的交互生成路径与通用 Visualize 的工具提交路径也有差异，不能把一种路径的修复保证套到另一种。

沙箱有 Runner Sidecar、Linux bwrap 和受限 subprocess 等后端；后者是应用层限制，不是 OS 隔离。统计计算、文件生成和外部工具可以整体复用，生产课堂需选择与真实部署相符的执行权限和隔离方式。

## 9. 复用时一并带走的验证体系

优先复用上游相关测试与 fixtures，覆盖：

- 回合开始、等待输入、取消、失败、事件重放、多 worker。
- 阅读 revision、批注/原文、PDF 页图、跨用户隔离。
- 可视化 payload/schema、包路径、工具提交与前端 iframe。
- 不同学习场景写入测评、原始作答保留、复习请求幂等、双标签页冲突。
- 记忆来源引用、原子修改、去重与撤销。
- 解析签名、失败恢复、索引版本和检索评测。
- TypeScript 契约生成、导入边界、组件测试和关键浏览器流程。

再追加本项目原有教材样例与规则：心理学概念正反例、实验设计、图表判读、选区与跨页引用、资料外拒答、提示不泄露答案、正式题目发布与学生隔离。

RAG Eval 可以复用 Recall@k、MRR、nDCG、黄金证据集和生产检索调用路径。匹配允许包含/词重叠，衡量的是检索相关性，不是语义支持。运行器将无法评分的失败用例排除出聚合，必须同时展示成功/失败数量，不能只报平均分。

本轮 19 项源码级检查见 [PROBE_RESULTS.json](PROBE_RESULTS.json)。本报告没有以源码数量、测试文件数量或这些断言替代模型/浏览器/课堂验收。

## 10. 接入批次与每批可审查结果

这些是实施顺序，不是范围删减；43 个单元都在候选范围。

| 批次 | 迁入完整单元 | 本项目可见结果 |
| --- | --- | --- |
| A 共同底座 | 固定上游源码/资源/依赖声明/测试，运行目录、身份、课程与会话映射 | 当前页面能访问独立运行的完整能力服务，健康检查/错误可见 |
| B 对话与证据 | Agent loop、回合恢复、模型网关、知识库/解析/检索、来源适配、富文本 | 现有聊天和教材提问贯通，可取消/恢复，引用可靠 |
| C 阅读与视觉 | Reading、批注/笔记捕获、Visualize、原图证据与图表练习 | 原页面可读、可圈选、可追问、可看交互图并返回教材 |
| D 教学与复习 | Mastery、出题、题库、Practice、Assessment、双调度、Journal/Memory | 学习—作答—错题—复习—跨会话接续贯通 |
| E 学习内容与管理 | Book、Co-Writer、统计、任务、语音/视频、课程/资源管理 | 导学内容、报告、进度与管理入口可用 |
| F 扩展与运营 | Skill/插件、MCP/计算、伙伴/外部 Agent、迁移导出、评测与运维 | 需要的扩展和部署能力有真实配置与权限验收 |

每批通过当前页面的端到端流程后再切换默认入口；已有教材与学习数据库不通过整目录覆盖来“迁移”。

## 11. 来源、许可证与本地差异

源仓库 LICENSE 和 pyproject.toml 声明 Apache-2.0；THIRD_PARTY_NOTICES.md 有额外来源说明。迁入时保留声明、记录修改，逐项核对第三方依赖与资产；这些代码声明不提供心理学教材的再分发授权。

源仓库存在未提交的 deeptutor/services/llm/factory.py 修改以及 providers.json、setup.json 等本机文件。SOURCE_AUDIT.json 记录所核查源码的文件哈希和差异状态，不读取凭据内容。迁移时应保留/审阅 factory 的本地改动，不能把“基于某提交”误写成“所有文件与该提交一致”。

当前仓库有大量已有业务改动，本轮只新增本调研目录，不清理、覆盖或提交这些改动。

## 12. 尚未由 DeepTutor 直接提供的课程专属部分

下列是需要由我们的业务模型与上游模块连接的内容，不是因复杂度拒绝复用：

1. 班级、选课、任课教师范围、正式资料/题目审批发布、考试答案开放时间。
2. 心理学实验设计与主观题的正式 rubric、教师终审及成绩解释。
3. 生成阅读版 PDF 与教材原文/版本的精确映射与当前高亮契约。
4. 独立作答资格、辅助使用标记、误解生命周期、学生/教师纠错与申诉。
5. 班级统计、教学审计口径与经过真实学生数据验证的个性化模型。

其余相关能力，优先直接迁入上游完整实现及配套组件；在连接这些课程规则时修改，而不是先重写同类功能。
