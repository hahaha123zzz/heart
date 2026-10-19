# DeepTutor 对话工具与能力完整清单

日期：2026-10-19；源码：D:/deeptutor，提交 6cf793bd868ba5ecbe64722936d4be8fab5a01df。

本清单来自实际静态注册描述符及类定义：100 个内置工具、11 个顶层能力、14 个内置循环扩展。工具描述是用途概述；详细参数、返回值及实际写入语义以各行源码和 SOURCE_AUDIT.json 为准。注册存在、允许挂载、实际可用、已通过运行验收是四个不同状态。

## 100 个内置工具

### 用户可切换的增强工具

这 8 项由用户开关控制；模型、服务或凭据未配置时仍可能不可用。

| 工具 | 用途 | 源码 |
| --- | --- | --- |
| `brainstorm` | 拓展思路与候选方案 | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:33) |
| `web_search` | 搜索网络资料 | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:483) |
| `paper_search` | 搜索学术论文 | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:561) |
| `zotero_search` | 搜索 Zotero 文献库 | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:641) |
| `reason` | 调用专门推理模型 | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:523) |
| `geogebra_analysis` | 分析数学图像并生成 GeoGebra 指令 | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:764) |
| `imagegen` | 生成图片 | [media_gen_tool.py](D:/deeptutor/deeptutor/tools/media_gen_tool.py:135) |
| `videogen` | 生成视频 | [media_gen_tool.py](D:/deeptutor/deeptutor/tools/media_gen_tool.py:217) |

### 教材与附加来源

rag/kb_files/knowledge_frontier 要有可共存的传统 RAG 知识库；read_source 由材料预读流程使用，普通回答循环明确关闭其直接挂载。

| 工具 | 用途 | 源码 |
| --- | --- | --- |
| `rag` | 检索教材片段或核对原图/页面 | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:105) |
| `kb_files` | 枚举知识库文件和来源 | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:304) |
| `knowledge_frontier` | 查看知识库覆盖与探索入口 | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:400) |
| `read_source` | 按来源 ID 读取附加资料的具体内容 | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:898) |

### 记忆、学习日志、笔记与题库

read_memory 由已有 L3 内容触发；笔记工具由已有笔记本触发；题库通常要求已有题目，伙伴场景可允许记录首题；写偏好与学习日志属于普通循环默认内置项，可受白名单限制。

| 工具 | 用途 | 源码 |
| --- | --- | --- |
| `read_memory` | 读取已保存记忆与相关学习背景 | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:965) |
| `write_memory` | 新增或编辑明确偏好，并记录来源事件 | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:995) |
| `learning_status` | 读取学习目标、上次接续和学习记录 | [learning_journal_tools.py](D:/deeptutor/deeptutor/tools/learning_journal_tools.py:16) |
| `learning_update` | 更新学习目标、会话交接和确认的学习收获 | [learning_journal_tools.py](D:/deeptutor/deeptutor/tools/learning_journal_tools.py:47) |
| `list_notebook` | 列出可访问笔记本 | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:1164) |
| `write_note` | 把内容保存到笔记本 | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:1381) |
| `question_bank` | 查询、记录和管理保存的题目 | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:1214) |

### 科研上下文工具

由 scientific_context 条件挂载；具体数据源和工具运行条件须另外满足。

| 工具 | 用途 | 源码 |
| --- | --- | --- |
| `preprint` | 处理预印本文献资料 | [research_tools.py](D:/deeptutor/deeptutor/tools/research_tools.py:117) |
| `research_audit` | 开展研究审视与证据检查 | [research_tools.py](D:/deeptutor/deeptutor/tools/research_tools.py:219) |
| `research_lit` | 开展文献资料检索与整理 | [research_tools.py](D:/deeptutor/deeptutor/tools/research_tools.py:297) |

### 工作区、执行、交互与扩展

workspace_list/read/search/present 是基础工具；export 按注册情况追加；exec 受沙箱和身份约束；read_skill/load_tools 要有对应资源。ask_user 是可暂停交互，不能只渲染成一句文本。

| 工具 | 用途 | 源码 |
| --- | --- | --- |
| `workspace_list` | 列举当前内容工作区文件 | [workspace.py](D:/deeptutor/deeptutor/tools/workspace.py:25) |
| `workspace_read` | 读取工作区文件内容 | [workspace.py](D:/deeptutor/deeptutor/tools/workspace.py:73) |
| `workspace_search` | 搜索工作区内容 | [workspace.py](D:/deeptutor/deeptutor/tools/workspace.py:116) |
| `workspace_present` | 呈现工作区文件或产物 | [workspace.py](D:/deeptutor/deeptutor/tools/workspace.py:156) |
| `workspace_export` | 提出并处理工作区导出交互 | [workspace.py](D:/deeptutor/deeptutor/tools/workspace.py:219) |
| `exec` | 通过统一沙箱执行代码或脚本 | [exec_tool.py](D:/deeptutor/deeptutor/tools/exec_tool.py:36) |
| `ask_user` | 展示问题卡并暂停等待用户答复 | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:1570) |
| `cron` | 创建、查询或取消定时任务 | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:1866) |
| `read_skill` | 按需读取选定技能全文 | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:1714) |
| `load_tools` | 加载已授权 MCP/CLI 工具的完整 schema | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:1808) |
| `web_fetch` | 读取网页内容 | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:1100) |
| `github` | 访问 GitHub 资源与支持的仓库操作 | [__init__.py](D:/deeptutor/deeptutor/tools/builtin/__init__.py:1507) |

### 引导学习与掌握度

4 个导航工具在存在相关学习主题时挂载；15 个教学工具由 Mastery 扩展持有，并按学习/测试/复习模式进一步过滤。挂载不等于每轮调用。

| 工具 | 用途 | 源码 |
| --- | --- | --- |
| `mastery_topics` | 列出已有学习主题 | [mastery_nav.py](D:/deeptutor/deeptutor/tools/mastery_nav.py:206) |
| `mastery_sessions` | 列出主题下会话 | [mastery_nav.py](D:/deeptutor/deeptutor/tools/mastery_nav.py:255) |
| `mastery_open_session` | 提出打开已有学习会话的交接卡 | [mastery_nav.py](D:/deeptutor/deeptutor/tools/mastery_nav.py:306) |
| `mastery_new_session` | 提出新建学习会话的交接卡 | [mastery_nav.py](D:/deeptutor/deeptutor/tools/mastery_nav.py:405) |
| `mastery_status` | 读取本轮权威掌握状态 | [tools.py](D:/deeptutor/deeptutor/capabilities/mastery/tools.py:704) |
| `mastery_quiz` | 生成或提交题卡交互 | [tools.py](D:/deeptutor/deeptutor/capabilities/mastery/tools.py:885) |
| `mastery_note_explained` | 记录已解释内容 | [tools.py](D:/deeptutor/deeptutor/capabilities/mastery/tools.py:826) |
| `mastery_grade` | 评定学生作答并更新相关状态 | [tools.py](D:/deeptutor/deeptutor/capabilities/mastery/tools.py:1185) |
| `mastery_skip_question` | 跳过当前题卡 | [tools.py](D:/deeptutor/deeptutor/capabilities/mastery/tools.py:1528) |
| `mastery_repair_question` | 修复无效或有问题的题卡 | [tools.py](D:/deeptutor/deeptutor/capabilities/mastery/tools.py:1576) |
| `mastery_defer_objective` | 推迟当前学习目标 | [tools.py](D:/deeptutor/deeptutor/capabilities/mastery/tools.py:1693) |
| `mastery_assess` | 评估学习目标相关表现 | [tools.py](D:/deeptutor/deeptutor/capabilities/mastery/tools.py:1421) |
| `mastery_build` | 构建学习目标与路径 | [tools.py](D:/deeptutor/deeptutor/capabilities/mastery/tools.py:1761) |
| `mastery_mode` | 切换学习、测试、复习模式 | [tools.py](D:/deeptutor/deeptutor/capabilities/mastery/tools.py:1919) |
| `mastery_profile` | 读取或调整学习者画像 | [tools.py](D:/deeptutor/deeptutor/capabilities/mastery/tools.py:2013) |
| `mastery_revise` | 修订学习目标与路径 | [tools.py](D:/deeptutor/deeptutor/capabilities/mastery/tools.py:2147) |
| `mastery_paths` | 查看已有学习路径 | [tools.py](D:/deeptutor/deeptutor/capabilities/mastery/tools.py:2343) |
| `mastery_switch` | 切换当前学习路径 | [tools.py](D:/deeptutor/deeptutor/capabilities/mastery/tools.py:2384) |
| `mastery_leave` | 离开当前学习流程 | [tools.py](D:/deeptutor/deeptutor/capabilities/mastery/tools.py:2447) |

### 分步解题

deep_solve 激活 solve 扩展；计划和重规划预算由引擎状态约束，不能仅由模型文字声称完成。

| 工具 | 用途 | 源码 |
| --- | --- | --- |
| `solve_plan` | 建立解题计划 | [tools.py](D:/deeptutor/deeptutor/capabilities/solve/tools.py:77) |
| `solve_finish_step` | 核对并完成计划中的一步 | [tools.py](D:/deeptutor/deeptutor/capabilities/solve/tools.py:139) |
| `solve_replan` | 按预算重新规划解题 | [tools.py](D:/deeptutor/deeptutor/capabilities/solve/tools.py:206) |

### Obsidian 知识能力

选中的 Obsidian vault 激活知识能力，拥有其来源；可与其他传统 RAG 知识库共存。包含实际写笔记工具。

| 工具 | 用途 | 源码 |
| --- | --- | --- |
| `obsidian_search` | 搜索 vault 笔记 | [tools.py](D:/deeptutor/deeptutor/capabilities/obsidian/tools.py:108) |
| `obsidian_read` | 读取笔记原文 | [tools.py](D:/deeptutor/deeptutor/capabilities/obsidian/tools.py:140) |
| `obsidian_list` | 列出笔记和目录 | [tools.py](D:/deeptutor/deeptutor/capabilities/obsidian/tools.py:167) |
| `obsidian_backlinks` | 查看反向链接 | [tools.py](D:/deeptutor/deeptutor/capabilities/obsidian/tools.py:200) |
| `obsidian_links` | 查看正向链接 | [tools.py](D:/deeptutor/deeptutor/capabilities/obsidian/tools.py:224) |
| `obsidian_tags` | 查看标签 | [tools.py](D:/deeptutor/deeptutor/capabilities/obsidian/tools.py:247) |
| `obsidian_create_note` | 创建笔记 | [tools.py](D:/deeptutor/deeptutor/capabilities/obsidian/tools.py:274) |
| `obsidian_append` | 追加笔记内容 | [tools.py](D:/deeptutor/deeptutor/capabilities/obsidian/tools.py:323) |
| `obsidian_set_property` | 设置笔记属性 | [tools.py](D:/deeptutor/deeptutor/capabilities/obsidian/tools.py:347) |

### MarginNote 知识能力

需要绑定可访问的 MarginNote 数据；由知识能力挂载，并受来源绑定约束。

| 工具 | 用途 | 源码 |
| --- | --- | --- |
| `marginnote_search` | 搜索同步资料 | [tools.py](D:/deeptutor/deeptutor/capabilities/marginnote4/tools.py:98) |
| `marginnote_read` | 读取内容 | [tools.py](D:/deeptutor/deeptutor/capabilities/marginnote4/tools.py:144) |
| `marginnote_list` | 列出条目 | [tools.py](D:/deeptutor/deeptutor/capabilities/marginnote4/tools.py:175) |
| `marginnote_documents` | 列出相关文档 | [tools.py](D:/deeptutor/deeptutor/capabilities/marginnote4/tools.py:217) |
| `marginnote_links` | 读取条目链接 | [tools.py](D:/deeptutor/deeptutor/capabilities/marginnote4/tools.py:236) |
| `marginnote_tags` | 读取标签 | [tools.py](D:/deeptutor/deeptutor/capabilities/marginnote4/tools.py:265) |
| `marginnote_cards` | 读取学习卡片 | [tools.py](D:/deeptutor/deeptutor/capabilities/marginnote4/tools.py:291) |

### 外部 Agent

选中已配置的 subagent 连接后激活；实现存在不代表本机已安装或登录对应外部运行器。

| 工具 | 用途 | 源码 |
| --- | --- | --- |
| `consult_subagent` | 向外部 Agent 或连接的讨论方咨询 | [tools.py](D:/deeptutor/deeptutor/capabilities/subagent/tools.py:43) |

### IMA 知识能力

需要 IMA 知识库绑定和有效服务配置；查询与笔记写入具有不同业务行为。

| 工具 | 用途 | 源码 |
| --- | --- | --- |
| `ima_list` | 列出 IMA 资料 | [tools.py](D:/deeptutor/deeptutor/capabilities/ima/tools.py:119) |
| `ima_read` | 读取 IMA 内容 | [tools.py](D:/deeptutor/deeptutor/capabilities/ima/tools.py:184) |
| `ima_note_search` | 搜索 IMA 笔记 | [tools.py](D:/deeptutor/deeptutor/capabilities/ima/tools.py:232) |
| `ima_add_url` | 添加 URL 资料 | [tools.py](D:/deeptutor/deeptutor/capabilities/ima/tools.py:298) |
| `ima_write_note` | 写入 IMA 笔记 | [tools.py](D:/deeptutor/deeptutor/capabilities/ima/tools.py:354) |

### 沉浸式阅读

打开材料、阅读工作区或选择阅读模式时激活；仅选择空模式也有防止虚构材料的规则。

| 工具 | 用途 | 源码 |
| --- | --- | --- |
| `reading_list_tabs` | 列出阅读标签页 | [tools.py](D:/deeptutor/deeptutor/capabilities/reading/tools.py:67) |
| `reading_switch_tab` | 切换阅读标签页 | [tools.py](D:/deeptutor/deeptutor/capabilities/reading/tools.py:120) |
| `material_outline` | 读取材料目录 | [tools.py](D:/deeptutor/deeptutor/capabilities/reading/tools.py:171) |
| `search_material` | 搜索当前材料 | [tools.py](D:/deeptutor/deeptutor/capabilities/reading/tools.py:199) |
| `read_material` | 读取材料指定单元 | [tools.py](D:/deeptutor/deeptutor/capabilities/reading/tools.py:311) |
| `view_figure` | 查看材料原图 | [figure_view.py](D:/deeptutor/deeptutor/capabilities/reading/figure_view.py:31) |
| `reader_goto` | 让阅读器定位到原文 | [tools.py](D:/deeptutor/deeptutor/capabilities/reading/tools.py:405) |
| `reader_annotate` | 创建阅读批注 | [tools.py](D:/deeptutor/deeptutor/capabilities/reading/tools.py:491) |

### 设置引导

显式设置流程激活；凭据采集和设置任务依赖对应 UI 与后端，不是普通聊天任意调用的工具。

| 工具 | 用途 | 源码 |
| --- | --- | --- |
| `inspect_setup` | 检查当前设置状态 | [tools.py](D:/deeptutor/deeptutor/capabilities/setup/tools.py:66) |
| `apply_setting` | 应用支持的设置变更 | [tools.py](D:/deeptutor/deeptutor/capabilities/setup/tools.py:161) |
| `request_credential` | 请求用户通过设置流程填写凭据 | [tools.py](D:/deeptutor/deeptutor/capabilities/setup/tools.py:213) |
| `run_setup_job` | 执行设置或准备任务 | [tools.py](D:/deeptutor/deeptutor/capabilities/setup/tools.py:273) |

### 伙伴创建与讨论

伙伴创建或伙伴小组上下文激活；不能据此把全部普通对话解释为多 Agent 系统。

| 工具 | 用途 | 源码 |
| --- | --- | --- |
| `propose_partner` | 提出可创建的伙伴配置 | [tools.py](D:/deeptutor/deeptutor/capabilities/partner_authoring/tools.py:14) |
| `invoke_other` | 调用伙伴讨论中的另一方 | [tools.py](D:/deeptutor/deeptutor/capabilities/partner_group/tools.py:14) |

### 课程编排

course_study 且存在课程绑定时激活，负责课程状态与学习入口交接；课程编排能力本身强调不代替实际教学面。

| 工具 | 用途 | 源码 |
| --- | --- | --- |
| `course_overview` | 读取课程与学习进展概况 | [tools.py](D:/deeptutor/deeptutor/capabilities/course_study/tools.py:560) |
| `course_material` | 读取课程材料信息 | [tools.py](D:/deeptutor/deeptutor/capabilities/course_study/tools.py:577) |
| `course_edit` | 修改支持的课程内容或设置 | [tools.py](D:/deeptutor/deeptutor/capabilities/course_study/tools.py:603) |
| `course_handoff` | 将学生交接到相应学习界面 | [tools.py](D:/deeptutor/deeptutor/capabilities/course_study/tools.py:716) |

### 伙伴专属记忆

伙伴回合强制挂载，同时抑制普通 read_memory/write_memory；区分伙伴自身可写内容与所有者只读背景。

| 工具 | 用途 | 源码 |
| --- | --- | --- |
| `partner_read` | 读取伙伴可访问的记忆内容 | [partner_memory.py](D:/deeptutor/deeptutor/tools/partner_memory.py:87) |
| `partner_memorize` | 保存伙伴自身记忆 | [partner_memory.py](D:/deeptutor/deeptutor/tools/partner_memory.py:127) |
| `partner_search` | 搜索伙伴可访问的历史与资料 | [partner_memory.py](D:/deeptutor/deeptutor/tools/partner_memory.py:222) |

### 可视化提交

由可视化生成扩展挂载；提交并通过相应结构检查后才形成画布产物。

| 工具 | 用途 | 源码 |
| --- | --- | --- |
| `submit_visualization` | 提交 SVG、Chart.js、Mermaid、HTML 等可视化载荷 | [tool.py](D:/deeptutor/deeptutor/visualizers/tool.py:22) |

## 11 个顶层回合能力

| 能力 | 实际职责 | 执行入口 |
| --- | --- | --- |
| `chat` | 普通自主对话；同一循环内调用工具与回答 | [ChatCapability](D:/deeptutor/deeptutor/agents/chat/capability.py:25) |
| `ask_questions` | 先发起问题卡，答复后继续完成原任务 | [AskQuestionsCapability](D:/deeptutor/deeptutor/capabilities/ask_questions/capability.py:33) |
| `deep_solve` | 分步解题，复用聊天循环与 solve 状态工具 | [DeepSolveCapability](D:/deeptutor/deeptutor/capabilities/solve/capability.py:74) |
| `deep_question` | 静态题组生成及题目追问，不等于逐轮互动测验 | [DeepQuestionCapability](D:/deeptutor/deeptutor/agents/question/capability.py:39) |
| `deep_research` | 改写/澄清、分解、分块研究、迭代报告；独立研究管线 | [DeepResearchCapability](D:/deeptutor/deeptutor/agents/research/capability.py:55) |
| `math_animator` | 概念设计、代码生成/重试和 Manim 渲染 | [MathAnimatorCapability](D:/deeptutor/deeptutor/agents/math_animator/capability.py:41) |
| `visualize` | 可视化生成与载荷提交；Manim 分支另走渲染流程 | [VisualizeCapability](D:/deeptutor/deeptutor/agents/visualize/capability.py:102) |
| `mastery_path` | 以专用教学提示协议运行掌握学习循环和题卡门槛 | [MasteryPathCapability](D:/deeptutor/deeptutor/capabilities/mastery/capability.py:69) |
| `immersive_reading` | 材料、视口、原图与阅读操作驱动的对话 | [ImmersiveReadingCapability](D:/deeptutor/deeptutor/capabilities/reading/mode.py:54) |
| `course_study` | 感知课程状态并推荐/交接到学习入口 | [CourseStudyCapability](D:/deeptutor/deeptutor/capabilities/course_study/mode.py:72) |
| `audio_overview` | 知识库取材、双人讲稿、语音生成及发布 | [AudioOverviewCapability](D:/deeptutor/deeptutor/capabilities/audio_overview/capability.py:38) |

## 14 个循环扩展

扩展通过 is_active、system_block、owned_tools、augment_kwargs、pre_loop、finish_instruction 等钩子参与循环；并非 14 个每轮依次执行的 Agent。

| 扩展 | 激活条件与作用 | 源码 |
| --- | --- | --- |
| `ask_questions` | ask_questions_mode；贡献问题策略 | [AskQuestionsLoopCapability](D:/deeptutor/deeptutor/capabilities/ask_questions/loop.py:18) |
| `mastery` | mastery_mode；模式工具、题卡、完成门槛、状态种子 | [MasteryLoopCapability](D:/deeptutor/deeptutor/capabilities/mastery/loop.py:214) |
| `solve` | solve_mode；计划与重规划 | [SolveLoopCapability](D:/deeptutor/deeptutor/capabilities/solve/loop.py:34) |
| `obsidian` | 本轮存在绑定的 vault；专属知识工具 | [ObsidianCapability](D:/deeptutor/deeptutor/capabilities/obsidian/capability.py:31) |
| `marginnote4` | 本轮存在 MarginNote 绑定 | [MarginNoteCapability](D:/deeptutor/deeptutor/capabilities/marginnote4/capability.py:34) |
| `subagent` | 本轮存在外部 Agent 连接 | [SubagentCapability](D:/deeptutor/deeptutor/capabilities/subagent/capability.py:38) |
| `ima` | 本轮存在 IMA 绑定 | [ImaCapability](D:/deeptutor/deeptutor/capabilities/ima/capability.py:41) |
| `immersive_reading` | 已打开材料/阅读工作区，或已选择阅读模式 | [ReadingCapability](D:/deeptutor/deeptutor/capabilities/reading/capability.py:118) |
| `course_study` | course_study 且课程 ID 可解析 | [CourseStudyLoopCapability](D:/deeptutor/deeptutor/capabilities/course_study/capability.py:386) |
| `explore_context` | source_index 非空；回答前只读调查资料 | [ExploreContextCapability](D:/deeptutor/deeptutor/capabilities/explore_context/capability.py:90) |
| `setup` | 被识别为设置引导上下文 | [SetupCapability](D:/deeptutor/deeptutor/capabilities/setup/capability.py:45) |
| `partner_authoring` | 被识别为伙伴创建上下文 | [PartnerAuthoringCapability](D:/deeptutor/deeptutor/capabilities/partner_authoring/capability.py:22) |
| `partner_group` | 存在 partner_group 字典上下文 | [PartnerGroupCapability](D:/deeptutor/deeptutor/capabilities/partner_group/capability.py:35) |
| `visualization_generation` | 已设置可视化生成模式标志 | [VisualizationLoopCapability](D:/deeptutor/deeptutor/visualizers/loop_capability.py:27) |

## 动态扩展与运行依赖

- MCP、CLI Apps 和插件可额外贡献工具、能力或循环扩展，不计入上述 100/11/14 静态内置数。先通过授权和资源范围筛选，再按需加载 schema。
- 工具别名不作为额外工具计数；view_figure 在 reading/tools.py 重导出，真实类位于 reading/figure_view.py，清单已跟踪该引用。
- web_search、paper_search、Zotero、媒体生成、外部 Agent、IMA 等仍需各自服务/数据/凭据；实际可用状态必须运行确认。
- exec 依赖沙箱隔离级别和用户授权；Manim 分支依赖本机渲染环境。
- 本轮对核心对话流程运行专项替身测试，未逐项调用全部 100 个工具。完整来源哈希、类名和行号见 SOURCE_AUDIT.json。
