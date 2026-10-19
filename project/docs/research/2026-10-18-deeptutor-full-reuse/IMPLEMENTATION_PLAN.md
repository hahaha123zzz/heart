# DeepTutor 整体复用实施计划

日期：2026-10-18。依据：本目录 REPORT.md、REUSE_MATRIX.md、SOURCE_AUDIT.json。
授权：保留现有页面，大块接入全部相关后端与组件；用户已要求制定计划并开始执行。

## 目标与约束

复用单位是完整服务、运行资源和配套组件。保留当前页面入口、心理学教材和已验证的课程证据规则。以固定源码副本、独立后端进程、现有 API/SSE 兼容层和前端组件挂载实现接入。

当前可运行宿主：project/integration/discrete-math-tutor。project/server 是原平台 Agent 抽取区，不能当成完整班级管理平台。原有未提交修改、教材迁移及数据库保持原状。

## A. 源码与运行基础（首先执行）

1. 固定上游提交 6cf793bd868ba5ecbe64722936d4be8fab5a01df，将 Git 已跟踪源码整体迁入 project/vendor/DeepTutor。包含后端、CLI、前端源码、提示词/模板、测试、依赖声明、构建与部署文件。
2. 记录所有迁入文件的提交/文件哈希。单独保留并注明本地 factory.py 的 ResolvedLLMConfig 兼容修复；不复制源项目 .git、虚拟环境、构建缓存、真实配置及运行数据。
3. 新增可重复的迁入/校验脚本；目标存在时拒绝覆盖。验证每个文件哈希和资源完整性。
4. 新增独立后端启动入口，默认 127.0.0.1:18001，运行数据放宿主 .runtime/deeptutor。源码引用只指向本仓库；Python 解释器可显式指定，日常默认项目独立环境。
5. 宿主新增只读状态和能力目录接口，不在宿主进程 import DeepTutor，不开放尚未完成身份/课程适配的通用写入代理。
6. 用真实上游后端验证启动、ready、能力注册和宿主只读桥接；关闭验证进程。未配置模型必须明确区分“后端可用”和“能够执行模型任务”。

变更范围：project/vendor/DeepTutor、project/scripts/vendor_deeptutor.py、宿主 integrations/deeptutor、scripts/start_deeptutor.py、main.py 路由接线、运行目录忽略项和对应测试。
验收：源码校验通过；危险归档路径/覆盖被拒绝；独立后端就绪；11 个顶层能力可发现；原页面和原 API 保持可访问。

## B. 对话、身份与教材证据

复用单元：runtime、session、chat、llm、config、courses、knowledge、rag、sources、identity、workspace、front_runtime、markdown。

1. 明确 student/course/session/turn 与 DeepTutor user/workspace/session/turn 的服务端映射，持久化映射关系；浏览器不能自行选择上游身份。
2. 把发布教材与来源版本接入知识库，保留 knowledge/grounded_citations.py、citation_index.py 的语义/几何核验。
3. 将现有 ChatRequest、PDFSelection、reader_location、任务 revision 转换为上游契约。明确待澄清任务、拒答、错误、取消和终态。
4. 接入持久化回合与事件游标，兼容当前 /api/chat/stream；重复请求不重复生成或写学习记录。
5. 原聊天区域接入完整富文本与消息传输组件，保留现有导航和来源点击。

验收：普通问答、圈选、资料外拒答、引用跳转、断线恢复、取消、幂等和学生隔离。使用现有心理学验收集，先比较再切换默认入口。

执行拆分（2026-10-19）：B1 先完成用户/课程/会话映射与原 API 接线，复用上游课程和会话存储；B2 接教材与任务 revision、持久化回合/事件/删除撤销；B3 接富文本和心理学全链路验收。B1 不等于 B 整批完成；B2/B3 的范围和验收要求保持上述约定。

本次 B2 已完成回合投影、教材来源/版本契约、终态事件游标及原页面断线恢复。原收据仍为正文权威来源，上游存协议指针。后续已接入正式教材 Obsidian 发布、原生知识库挂载、文本检索和上游隔离 Provider；B3 富文本已通过浏览器验收，9 类心理学真实模型代表性黄金集通过（见 GOLDEN_VALIDATION.md）。完整 AgenticChatLoop、向量索引、全教材扩展与默认部署切换仍待完成，B 整批尚未完成。

## C. 阅读与图文交互

复用单元：parsing、structure、reading、annotations、reading_extensions、visualize、visual_practice、files、notebook。

1. 接入 ParseService、缓存、索引准备状态与版本；确认当前教材的章节/页码映射。
2. 整体接入阅读目录、材料/revision、批注、笔记捕获、翻译/导读和随堂测验。
3. 将 Visualize 生成/工具提交/校验/修复及所有相关 Viewer 挂入现有图解区域。
4. 接原图资产、页面裁图和 identification/relationship/table_graph/comparison 练习。
5. 将上游证据比较替换为本项目符号保留与重复语句消歧策略，图解输出继续通过内容核验。

验收：教材圈选/跨页/重复句、PDF 坐标转换、图表回指、交互组件释放、失败保留文字、正式测验不泄露答案。

## D. 教学、测评、记忆与复习

复用单元：mastery、assessment、question、question_bank、practice、retention、memory、journal、persona。

1. 整体接入 Mastery 目标/题卡/模式，映射当前 LessonPlan、StudentState、提示级别和误解生命周期。
2. 出题结果接现有 question_agent 草稿与教师审核，正式发布沿用课程规则。
3. 统一 attempt/source 身份；不同学习面仅追加一次作答事实，避免两套掌握推导重复推进。
4. 接题库导入、错题、复习队列与两类调度；正式主观题接心理学 rubric，不用关键词覆盖作最终成绩。
5. 接 Memory 全层及治理 UI、Journal 跨会话接续、显式偏好与可纠错画像。

验收：有提示/独立作答区分、重复提交、双标签页版本冲突、错题复习、遗忘/误解重开、记忆撤销及学生隔离。

## E. 学习内容与管理功能

复用单元：book、dashboard、co_writer、solve_research、voice、video、tasks。

1. 整体接入 Book 的 13 类已注册生成器、来源、大纲、增量编译、阅读覆盖层和导出。
2. 交互块补齐教材来源绑定；额外六类枚举不当作已实现生成器。
3. 挂载实验报告编辑器、资料预览、模板与 DOCX 转换；实验数据和评分点由课程提供。
4. 接个人统计、课程资源导航、任务/提醒、语音/音频导读和实际支持的视频来源。
5. 教师统计补课程/班级范围和脱敏，不能把个人课程容器直接当作班级管理。

验收：章节学习闭环、真实实验数据报告、统计口径、报告/图解来源、录音/播放及未配置服务的明确状态。

## F. 扩展、部署与总体验收

复用单元：skills_plugins、mcp_exec、partners、subagents、evaluation；补齐所有批次的工程检查。

1. 接教学 Skill、插件、MCP、统计计算与产物管理，按课程任务授权。
2. 接需要的多角色讨论和外部 Agent；IM 外发不因带入源码自动启用。
3. 确认部署隔离后端、模型/工具配额、工作区导出恢复、许可证与本地修改记录。
4. 复用上游相关测试、协议/依赖边界检查，加入心理学黄金集与关键浏览器流程。

验收：课程/学生/教师隔离、任务限制、完整学习闭环、失败恢复、备份恢复和实际部署复现。

## 执行记录与退出条件

任务进度及本次真实检查写入 EXECUTION_LOG.md。每批只有在“功能接入 + 对应测试 + 可复现命令”完成后标记完成；源码已迁入不等于业务已接通。
用户要求每完成一个小阶段自动 commit 并 push；提交仅包含阶段代码、相关依赖和文档，不包含密钥、运行库或本机教材。
外部依赖安装、模型能力和真实教材验收分别记录，失败不伪装为成功；应用/索引/业务数据库不通过目录覆盖进行切换。

本轮优先完成 A 的可运行基础，再根据验证结果接续 B；后续批次保持在本计划内，不因复杂度删除复用范围。
