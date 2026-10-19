# DeepTutor 全量相关能力复用矩阵

日期：2026-10-18。源仓库：D:/deeptutor，提交 6cf793bd868ba5ecbe64722936d4be8fab5a01df；factory.py 存在本地修改，详见 SOURCE_AUDIT.json。目标：保留现有页面，大块复用后端和配套组件。

本表 43 项均为复用候选，分类说明接入方式，不按复杂度排除功能。源码目录中的候选不意味着当前服务已启用、外部依赖已配置或心理学业务验收已通过。

## 01. 统一回合运行时

- 复用形态：统一底座和身份接入。
- 当前项目接入点：接管对话任务执行；现有 API/SSE 作兼容入口。
- 关键入口：deeptutor/app/facade.py: DeepTutorApp.start_turn / stream_turn / cancel_turn。
- 完整复用边界：完整回合应用服务、运行时容器、能力注册与输出契约。与当前 main.py / TaskService 之间建立唯一执行入口。
- 上游测试/验证入口（本轮未执行整套测试）：tests/app/test_turn_application_service.py。
- 源码范围：
  - [deeptutor/app/facade.py](<D:/deeptutor/deeptutor/app/facade.py>)
  - [deeptutor/app/service.py](<D:/deeptutor/deeptutor/app/service.py>)
  - [deeptutor/app/container.py](<D:/deeptutor/deeptutor/app/container.py>)
  - [deeptutor/runtime/turn_engine.py](<D:/deeptutor/deeptutor/runtime/turn_engine.py>)
  - [deeptutor/runtime/orchestrator.py](<D:/deeptutor/deeptutor/runtime/orchestrator.py>)

## 02. 会话持久化与断线恢复

- 复用形态：整套服务/组件复用。
- 当前项目接入点：保留聊天布局，接事件游标、恢复、取消及幂等。
- 关键入口：deeptutor/services/session/sqlite_store.py; deeptutor/runtime/coordination/journal.py。
- 完整复用边界：复用持久化回合、事件序号、重放、取消、等待输入与进程协调。当前 SSE 名称可保留，但不能丢失 turn_id/seq/终态。
- 上游测试/验证入口（本轮未执行整套测试）：tests/services/session/test_turn_event_flush.py; tests/app/test_multiworker_turn_application.py。
- 源码范围：
  - [deeptutor/services/session/sqlite_store.py](<D:/deeptutor/deeptutor/services/session/sqlite_store.py>)
  - [deeptutor/services/session/turns](<D:/deeptutor/deeptutor/services/session/turns>)
  - [deeptutor/runtime/coordination](<D:/deeptutor/deeptutor/runtime/coordination>)
  - [web/features/chat/transport](<D:/deeptutor/web/features/chat/transport>)

## 03. Agent 对话及工具循环

- 复用形态：整套服务/组件复用。
- 当前项目接入点：替换通用生成执行链；教学动作受本项目规则约束。
- 关键入口：deeptutor/agents/chat/capability.py: ChatCapability; deeptutor/agents/loop/pipeline.py。
- 完整复用边界：完整 Agent loop、提示词组装、上下文预算、工具参数验证、流式工具调用与并行调度。课程提示级别在工具调用前由服务端限制。
- 上游测试/验证入口（本轮未执行整套测试）：tests/agents/chat; tests/core/agentic。
- 源码范围：
  - [deeptutor/agents/chat](<D:/deeptutor/deeptutor/agents/chat>)
  - [deeptutor/agents/loop](<D:/deeptutor/deeptutor/agents/loop>)
  - [deeptutor/runtime/agentic](<D:/deeptutor/deeptutor/runtime/agentic>)
  - [deeptutor/capabilities/ask_questions](<D:/deeptutor/deeptutor/capabilities/ask_questions>)

## 04. 模型网关与多模态

- 复用形态：整套服务/组件复用。
- 当前项目接入点：替换单一 OpenAI-compatible 客户端，映射当前配置。
- 关键入口：deeptutor/services/llm/factory.py; config.py; provider_core/。
- 完整复用边界：模型选择、原生 tools、结构化输出修复、视觉输入、重试/退避、限流、错误映射、Token 计量一起复用。当前单一客户端配置通过适配迁入。
- 上游测试/验证入口（本轮未执行整套测试）：tests/services/llm。
- 源码范围：
  - [deeptutor/services/llm](<D:/deeptutor/deeptutor/services/llm>)
  - [deeptutor/services/model_selection](<D:/deeptutor/deeptutor/services/model_selection>)
  - [deeptutor/services/provider_registry.py](<D:/deeptutor/deeptutor/services/provider_registry.py>)
  - [deeptutor/services/keypool.py](<D:/deeptutor/deeptutor/services/keypool.py>)

## 05. 模型设置与就绪检测

- 复用形态：整套服务/组件复用。
- 当前项目接入点：接入管理员配置区域，运行时配置归一。
- 关键入口：deeptutor/services/config/runtime_settings.py; model_catalog.py; readiness.py。
- 完整复用边界：配置目录、模型目录、草稿、就绪检查、能力参数与设置界面一起复用；不复制本机真实凭据。
- 上游测试/验证入口（本轮未执行整套测试）：tests/services/config。
- 源码范围：
  - [deeptutor/services/config](<D:/deeptutor/deeptutor/services/config>)
  - [deeptutor/services/settings](<D:/deeptutor/deeptutor/services/settings>)
  - [web/features/settings](<D:/deeptutor/web/features/settings>)
  - [web/features/runtime-status](<D:/deeptutor/web/features/runtime-status>)

## 06. 课程资源与学习导航

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：绑定现有课程/章节；个人容器扩展为课程成员资源视图。
- 关键入口：deeptutor/services/courses.py: StudyCourse / CourseService; courses_state.py: build_course_state。
- 完整复用边界：资源关联、课程约定、syllabus、归档、状态聚合、学习动作导航完整复用。课程是个人容器，不能直接充当班级成员/教师发布模型。
- 上游测试/验证入口（本轮未执行整套测试）：tests/services/test_courses.py; tests/capabilities/test_course_study.py。
- 源码范围：
  - [deeptutor/services/courses.py](<D:/deeptutor/deeptutor/services/courses.py>)
  - [deeptutor/services/courses_state.py](<D:/deeptutor/deeptutor/services/courses_state.py>)
  - [deeptutor/capabilities/course_study](<D:/deeptutor/deeptutor/capabilities/course_study>)
  - [web/components/courses](<D:/deeptutor/web/components/courses>)

## 07. 多引擎解析与缓存

- 复用形态：整套服务/组件复用。
- 当前项目接入点：接教材导入、解析状态与失败恢复。
- 关键入口：deeptutor/services/parsing/service.py: ParseService; engines/factory.py。
- 完整复用边界：七类解析适配器、统一 ParsedDocument、内容哈希缓存、签名、准备检查、模型安装与 MinerU 切片检查点一起复用。引擎可选依赖需实际安装配置。
- 上游测试/验证入口（本轮未执行整套测试）：tests/services/parsing/test_parse_service.py。
- 源码范围：
  - [deeptutor/services/parsing](<D:/deeptutor/deeptutor/services/parsing>)
  - [web/features/settings/sections/DocumentParsingSettingsSection.tsx](<D:/deeptutor/web/features/settings/sections/DocumentParsingSettingsSection.tsx>)

## 08. 教材章节结构重建

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：接教材章节目次抽取；保留人工确认。
- 关键入口：deeptutor/textbook_struct/chapter_rebuild.py; page_headers.py。
- 完整复用边界：复用 MinerU 版面到章节树的重建及页范围算法；本地调用检索主要发现库自身和测试，未证明其已接入当前生产导入主链。
- 上游测试/验证入口（本轮未执行整套测试）：tests/textbook_struct/test_page_headers.py。
- 源码范围：
  - [deeptutor/textbook_struct](<D:/deeptutor/deeptutor/textbook_struct>)
  - [tests/textbook_struct](<D:/deeptutor/tests/textbook_struct>)

## 09. 知识库与索引任务

- 复用形态：整套服务/组件复用。
- 当前项目接入点：替换导入与重建索引生命周期，保留课程发布约束。
- 关键入口：deeptutor/knowledge/indexing_run.py: IndexingRun; manager.py。
- 完整复用边界：导入、增量加文档、任务所有权、取消/恢复、索引状态、失败时保留上个发布版本与库存清单完整复用。课程内容审核层继续控制可见版本。
- 上游测试/验证入口（本轮未执行整套测试）：tests/knowledge/test_indexing_run.py; tests/knowledge/test_manifest.py。
- 源码范围：
  - [deeptutor/knowledge](<D:/deeptutor/deeptutor/knowledge>)
  - [deeptutor/services/rag/index_versioning.py](<D:/deeptutor/deeptutor/services/rag/index_versioning.py>)
  - [web/components/knowledge](<D:/deeptutor/web/components/knowledge>)

## 10. 多管线检索与重排

- 复用形态：整套服务/组件复用。
- 当前项目接入点：提供统一检索服务，连接现有证据包和中文评测。
- 关键入口：deeptutor/services/rag/factory.py; pipelines/; embedding/。
- 完整复用边界：LlamaIndex、PageIndex、GraphRAG、LightRAG、LightRAG Server、IMA、WeKnora、Kiwix 适配及嵌入服务纳入。完整带入代码不等于所有外部引擎已部署。
- 上游测试/验证入口（本轮未执行整套测试）：tests/services/rag; deeptutor/services/rag/eval。
- 源码范围：
  - [deeptutor/services/rag](<D:/deeptutor/deeptutor/services/rag>)
  - [deeptutor/services/embedding](<D:/deeptutor/deeptutor/services/embedding>)
  - [deeptutor/tools/rag_tool.py](<D:/deeptutor/deeptutor/tools/rag_tool.py>)

## 11. 原图表与页面取证

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：接图文答疑、表格裁图和文档版本核验。
- 关键入口：deeptutor/services/rag/source_visuals.py: source_file / source_state / page_image。
- 完整复用边界：原图/表格资产、源文档哈希、页码和区域核验、图像像素与提取覆盖报告一起复用。回答事实仍走语义支持和精确引用核验。
- 上游测试/验证入口（本轮未执行整套测试）：tests/services/rag/test_source_visual_grounding.py; tests/services/rag/test_visual_assets.py。
- 源码范围：
  - [deeptutor/services/rag/source_visuals.py](<D:/deeptutor/deeptutor/services/rag/source_visuals.py>)
  - [deeptutor/services/rag/visual_assets.py](<D:/deeptutor/deeptutor/services/rag/visual_assets.py>)
  - [deeptutor/services/rag/visual_coverage.py](<D:/deeptutor/deeptutor/services/rag/visual_coverage.py>)

## 12. 教材阅读引擎

- 复用形态：整套服务/组件复用。
- 当前项目接入点：保留阅读页面位置，接材料目录、批注、引用及阅读动作。
- 关键入口：deeptutor/reading/service.py; store.py; catalog_store.py; capabilities/reading/。
- 完整复用边界：材料库、文档单元、revision、阅读位置、目录、搜索、批注、引用、导出及阅读工具整套复用；现有 PDF 展示和跳转入口通过位置转换接入。
- 上游测试/验证入口（本轮未执行整套测试）：tests/reading; tests/api/routers/test_reading_progress.py。
- 源码范围：
  - [deeptutor/reading](<D:/deeptutor/deeptutor/reading>)
  - [deeptutor/capabilities/reading](<D:/deeptutor/deeptutor/capabilities/reading>)
  - [web/components/reading](<D:/deeptutor/web/components/reading>)

## 13. 批注与引用前端契约

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：适配现有 PDFSelection 与字符/矩形坐标。
- 关键入口：web/lib/reading-w3c-annotations.ts: resolveTextSelectors; deeptutor/reading/models.py。
- 完整复用边界：复用 TextQuoteSelector、TextPositionSelector、前后文重锚定、标注数据与列表组件；转换本项目 PDF 矩形、选区和版本标识。
- 上游测试/验证入口（本轮未执行整套测试）：web/tests/reading-selection.test.ts; tests/reading/test_references.py。
- 源码范围：
  - [web/lib/reading-w3c-annotations.ts](<D:/deeptutor/web/lib/reading-w3c-annotations.ts>)
  - [web/lib/reading-selection.ts](<D:/deeptutor/web/lib/reading-selection.ts>)
  - [web/lib/reading-citations.ts](<D:/deeptutor/web/lib/reading-citations.ts>)
  - [web/lib/reading-quote-locator.ts](<D:/deeptutor/web/lib/reading-quote-locator.ts>)
  - [deeptutor/reading/models.py](<D:/deeptutor/deeptutor/reading/models.py>)

## 14. 阅读测验、翻译和导读

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：接现有圈选菜单；替换引文比较并服务端保管答案。
- 关键入口：deeptutor/reading/extensions.py: ReadingContext / ReadingExtensionRegistry。
- 完整复用边界：复用运行协议、结果 schema、导读/翻译/词汇/随堂测验与工具条。替换不适合数学/心理学引文的 evidence_key 比较，不用模型自报引用作为确证。
- 上游测试/验证入口（本轮未执行整套测试）：tests/reading/test_quiz.py; tests/reading/test_translation.py。
- 源码范围：
  - [deeptutor/reading/extensions.py](<D:/deeptutor/deeptutor/reading/extensions.py>)
  - [deeptutor/reading/quiz.py](<D:/deeptutor/deeptutor/reading/quiz.py>)
  - [deeptutor/reading/translation.py](<D:/deeptutor/deeptutor/reading/translation.py>)
  - [deeptutor/reading/study_guidance.py](<D:/deeptutor/deeptutor/reading/study_guidance.py>)
  - [deeptutor/reading/vocabulary.py](<D:/deeptutor/deeptutor/reading/vocabulary.py>)

## 15. 通用可视化完整链路

- 复用形态：整套服务/组件复用。
- 当前项目接入点：扩展现有聊天图解区域，保留教材一致性审核。
- 关键入口：deeptutor/agents/visualize/capability.py; visualizers/loop_capability.py; tool.py。
- 完整复用边界：类型选择、payload 生成、submit_visualization 提交、schema 校验、修复循环、画布结果及 Viewers 全套复用。通用画布校验后再接本项目教学内容审核。
- 上游测试/验证入口（本轮未执行整套测试）：tests/visualizers/test_registry_and_tool.py; tests/visualizers/test_ggb_validator.py。
- 源码范围：
  - [deeptutor/agents/visualize](<D:/deeptutor/deeptutor/agents/visualize>)
  - [deeptutor/visualizers](<D:/deeptutor/deeptutor/visualizers>)
  - [web/components/visualize](<D:/deeptutor/web/components/visualize>)
  - [web/lib/iframe-html.ts](<D:/deeptutor/web/lib/iframe-html.ts>)
  - [web/lib/visualize-types.ts](<D:/deeptutor/web/lib/visualize-types.ts>)

## 16. 自适应讲义与交互页面

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：嵌入章节学习区域；实际注册 13 类块，配来源与进度。
- 关键入口：deeptutor/book/engine.py: BookEngine; compiler.py: BookCompiler; blocks/base.py。
- 完整复用边界：复用来源探索、大纲、页面规划、13 类已注册内容块、增量保存、失败恢复、进度和 Markdown 导出。BookType 内额外 6 类 Guided Learning 名称未在默认生成器注册，不能算已交付。 InteractiveGenerator 当前返回空 source_anchors，因此接入后需显式绑定教材证据，不能把格式校验当来源核验。
- 上游测试/验证入口（本轮未执行整套测试）：tests/book; tests/api/test_book_ws_stream.py。
- 源码范围：
  - [deeptutor/book](<D:/deeptutor/deeptutor/book>)
  - [deeptutor/api/routers/book.py](<D:/deeptutor/deeptutor/api/routers/book.py>)
  - [web/app/(workspace)/learning/books](<D:/deeptutor/web/app/(workspace)/learning/books>)
  - [web/lib/book-api.ts](<D:/deeptutor/web/lib/book-api.ts>)

## 17. 引导式教学与学习路径

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：映射 StudentState、LessonPlan 与提示策略，单一证据事件更新。
- 关键入口：deeptutor/capabilities/mastery/pipeline.py; tools.py; deeptutor/learning/service.py。
- 完整复用边界：完整学习目标生成、四知识类型、讲解/测验/复习模式、题卡、作答、定性评估、进阶与路径导航。映射现有 StudentState/误解/教学计划，保留独立作答与提示规则。
- 上游测试/验证入口（本轮未执行整套测试）：deeptutor/learning/tests; tests/capabilities/test_mastery_capability.py。
- 源码范围：
  - [deeptutor/learning](<D:/deeptutor/deeptutor/learning>)
  - [deeptutor/capabilities/mastery](<D:/deeptutor/deeptutor/capabilities/mastery>)
  - [web/components/space/learning](<D:/deeptutor/web/components/space/learning>)

## 18. 跨场景统一测评

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：贯通教材测验、练习、可视化与学习路径的作答身份。
- 关键入口：deeptutor/learning/assessment.py: record_assessment; core/assessment.py。
- 完整复用边界：读书、阅读、Mastery 等场景写入统一测评记录和不可变作答日志。以 origin_type/origin_ref/turn_id/question_id 和本项目 attempt_id 关联，防重复计入。
- 上游测试/验证入口（本轮未执行整套测试）：tests/api/test_book_quiz_attempt_notebook.py; tests/api/test_reading_quiz_answers.py。
- 源码范围：
  - [deeptutor/core/assessment.py](<D:/deeptutor/deeptutor/core/assessment.py>)
  - [deeptutor/learning/assessment.py](<D:/deeptutor/deeptutor/learning/assessment.py>)
  - [deeptutor/services/session/sqlite_store.py](<D:/deeptutor/deeptutor/services/session/sqlite_store.py>)
  - [deeptutor/learning/question_card.py](<D:/deeptutor/deeptutor/learning/question_card.py>)

## 19. 原图表练习

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：支持实验装置识别、变量关系、表格/曲线判读与对比。
- 关键入口：deeptutor/learning/visual_practice.py: prepare_visual / public_visual。
- 完整复用边界：复用 identification、relationship、table_graph、comparison 四类原图练习与来源绑定、提示标记、答案隐藏。题目正确性需心理学评分规则和老师确认。
- 上游测试/验证入口（本轮未执行整套测试）：deeptutor/learning/tests/test_visual_learning_workflow.py。
- 源码范围：
  - [deeptutor/learning/visual_practice.py](<D:/deeptutor/deeptutor/learning/visual_practice.py>)
  - [deeptutor/services/rag/source_visuals.py](<D:/deeptutor/deeptutor/services/rag/source_visuals.py>)

## 20. 出题与仿题

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：接现有 question_agent 草稿和审核链，生成结果不能直接正式发布。
- 关键入口：deeptutor/agents/question/pipeline.py: QuestionPipeline; mimic_source.py。
- 完整复用边界：基于主题/教材/试卷的模板规划、出题循环、历史、题型结构、结果存储与追问整套复用。coordinator.py 是兼容壳，不作为新实现主入口。
- 上游测试/验证入口（本轮未执行整套测试）：tests/agents/question; tests/api/test_practice.py。
- 源码范围：
  - [deeptutor/agents/question](<D:/deeptutor/deeptutor/agents/question>)
  - [deeptutor/tools/question](<D:/deeptutor/deeptutor/tools/question>)
  - [deeptutor/api/routers/question.py](<D:/deeptutor/deeptutor/api/routers/question.py>)

## 21. 题库与错题笔记

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：接正式题库/个人错题区域，保持答案开放规则。
- 关键入口：deeptutor/api/routers/question_notebook.py; web/components/space/question-bank/。
- 完整复用边界：来源场景、题目归类、错题状态、作答、图片答案、笔记与筛选一起迁入。个人题库不能代替正式题审核/发布时间/试卷版本。
- 上游测试/验证入口（本轮未执行整套测试）：tests/api/test_practice.py; tests/api/test_book_quiz_attempt_notebook.py。
- 源码范围：
  - [deeptutor/api/routers/question_notebook.py](<D:/deeptutor/deeptutor/api/routers/question_notebook.py>)
  - [deeptutor/tools/question_bank.py](<D:/deeptutor/deeptutor/tools/question_bank.py>)
  - [web/components/space/question-bank](<D:/deeptutor/web/components/space/question-bank>)

## 22. 题库导入与复习练习

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：接现有练习页；导入预览、幂等提交、到期队列和分析。
- 关键入口：deeptutor/services/practice/importing.py / storage.py / answers.py。
- 完整复用边界：导入预览/提交、5 MB/500 题等输入限制、中文列名、错题触发、提交幂等、版本冲突、复习事件与 UI 整套复用。主观题返回未判定，正式评分需现有 rubric。
- 上游测试/验证入口（本轮未执行整套测试）：tests/api/test_practice.py。
- 源码范围：
  - [deeptutor/services/practice](<D:/deeptutor/deeptutor/services/practice>)
  - [deeptutor/api/routers/practice.py](<D:/deeptutor/deeptutor/api/routers/practice.py>)
  - [web/components/learning/practice](<D:/deeptutor/web/components/learning/practice>)

## 23. 两类间隔复习调度

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：题目复习和知识点复习分别接入，避免重复派发。
- 关键入口：deeptutor/services/practice/scheduler.py; deeptutor/learning/scheduler.py。
- 完整复用边界：题库 SM-2-style 调度与知识目标的指数遗忘基线都带入；题目与目标各有队列，共享作答证据并由统一任务展示合并。不是已拟合 FSRS。
- 上游测试/验证入口（本轮未执行整套测试）：deeptutor/learning/tests/test_scheduler.py; tests/api/test_practice.py。
- 源码范围：
  - [deeptutor/learning/scheduler.py](<D:/deeptutor/deeptutor/learning/scheduler.py>)
  - [deeptutor/services/practice/scheduler.py](<D:/deeptutor/deeptutor/services/practice/scheduler.py>)
  - [web/components/space/learning/ReviewTrail.tsx](<D:/deeptutor/web/components/space/learning/ReviewTrail.tsx>)

## 24. 可追溯分层记忆与治理

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：接 MemoryManager、来源引用、编辑、撤销、审计与偏好。
- 关键入口：deeptutor/services/memory/store.py: MemoryStore; consolidator/; snapshot/。
- 完整复用边界：原始事件/快照、分场景记忆、汇总文档、来源脚注、update/audit/dedup/merge、行级修改、备份/撤销与治理 UI 全带入。学生能力事实由现有证据规则批准。
- 上游测试/验证入口（本轮未执行整套测试）：tests/services/memory。
- 源码范围：
  - [deeptutor/services/memory](<D:/deeptutor/deeptutor/services/memory>)
  - [deeptutor/api/routers/memory.py](<D:/deeptutor/deeptutor/api/routers/memory.py>)
  - [web/components/memory](<D:/deeptutor/web/components/memory>)

## 25. 跨会话学习日志

- 复用形态：整套服务/组件复用。
- 当前项目接入点：接学习目标、上次卡点和下次计划；不替代掌握证据。
- 关键入口：deeptutor/services/learning_journal/store.py: LearningJournalStore。
- 完整复用边界：复用 mission、last_session、records、去重、原子持久化、提示词注入与对话读写工具。它是软状态，不是又一套掌握度评分器。
- 上游测试/验证入口（本轮未执行整套测试）：tests/api/test_learning_journal.py; tests/tools/test_learning_journal_tools.py。
- 源码范围：
  - [deeptutor/services/learning_journal](<D:/deeptutor/deeptutor/services/learning_journal>)
  - [deeptutor/tools/learning_journal_tools.py](<D:/deeptutor/deeptutor/tools/learning_journal_tools.py>)
  - [deeptutor/api/routers/learning_journal.py](<D:/deeptutor/deeptutor/api/routers/learning_journal.py>)

## 26. 表达偏好与角色

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：对接 interaction_preferences；显式偏好和教师规则优先。
- 关键入口：deeptutor/services/persona/service.py; multi_user/learner_profile.py。
- 完整复用边界：角色描述、年龄/年级/阅读水平/讲解风格、选择与 prompt block 整体复用。接入本项目显式偏好确认规则，课程/测验约束优先。
- 上游测试/验证入口（本轮未执行整套测试）：tests/multi_user; tests/services/persona/test_persona_service.py。
- 源码范围：
  - [deeptutor/services/persona](<D:/deeptutor/deeptutor/services/persona>)
  - [deeptutor/multi_user/learner_profile.py](<D:/deeptutor/deeptutor/multi_user/learner_profile.py>)
  - [deeptutor/agents/loop/prompt_blocks.py](<D:/deeptutor/deeptutor/agents/loop/prompt_blocks.py>)

## 27. 学习笔记和资料回收

- 复用形态：整套服务/组件复用。
- 当前项目接入点：保存圈选、问答、图解、学习结论，并作为复习来源。
- 关键入口：deeptutor/services/notebook/service.py: NotebookManager; reading/knowledge_capture.py。
- 完整复用边界：问答、阅读、解题、研究、报告等记录库及选择/编辑/保存组件整体复用。支持批注整理到笔记，再作为学习路径材料。
- 上游测试/验证入口（本轮未执行整套测试）：tests/reading/test_knowledge_capture.py; tests/services/test_notebook_service.py。
- 源码范围：
  - [deeptutor/services/notebook](<D:/deeptutor/deeptutor/services/notebook>)
  - [deeptutor/reading/knowledge_capture.py](<D:/deeptutor/deeptutor/reading/knowledge_capture.py>)
  - [web/components/notebook](<D:/deeptutor/web/components/notebook>)

## 28. 学习统计与资源总览

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：接个人学习概览；班级聚合及教师权限另接现有业务。
- 关键入口：deeptutor/services/practice/analytics.py; courses_state.py; api/routers/dashboard.py。
- 完整复用边界：按时区的 7/30/90 日作答/错题/复习统计、课程状态和跨学习面活动聚合、个人仪表板组件一起复用。教师班级统计需课程成员范围聚合与脱敏。
- 上游测试/验证入口（本轮未执行整套测试）：web/tests/learning-dashboard.test.ts; tests/api/test_practice.py。
- 源码范围：
  - [deeptutor/api/routers/dashboard.py](<D:/deeptutor/deeptutor/api/routers/dashboard.py>)
  - [deeptutor/services/practice/analytics.py](<D:/deeptutor/deeptutor/services/practice/analytics.py>)
  - [deeptutor/services/courses_state.py](<D:/deeptutor/deeptutor/services/courses_state.py>)
  - [web/components/learning/LearningDashboard.tsx](<D:/deeptutor/web/components/learning/LearningDashboard.tsx>)
  - [web/lib/learning-dashboard.ts](<D:/deeptutor/web/lib/learning-dashboard.ts>)

## 29. 实验报告协作写作

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：在现有页面嵌入报告编辑区；模板、评分规则由课程提供。
- 关键入口：deeptutor/co_writer/edit_agent.py; storage.py; docx_converter.py。
- 完整复用边界：选区改写、流式编辑、资料检索、操作历史、草稿持久化、Markdown/DOCX 转换及编辑器 UI 一起复用。实验报告模板、真实实验数据和评分点由本课程补入。
- 上游测试/验证入口（本轮未执行整套测试）：tests/api/test_co_writer.py; tests/api/routers/test_co_writer_contract.py。
- 源码范围：
  - [deeptutor/co_writer](<D:/deeptutor/deeptutor/co_writer>)
  - [deeptutor/api/routers/co_writer.py](<D:/deeptutor/deeptutor/api/routers/co_writer.py>)
  - [web/features/co-writer](<D:/deeptutor/web/features/co-writer>)

## 30. 深度解题与专题研究

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：用于实验设计分析、文献与专题学习，教材/外部证据分流。
- 关键入口：deeptutor/capabilities/solve/; agents/research/; services/research/primitives.py。
- 完整复用边界：解题计划、步骤完成/重规划、研究主题队列、引用管理及一手文献/仓库静态读取一起纳入。外部资料与教材事实分开标注，不能把源码审查当实验复现。
- 上游测试/验证入口（本轮未执行整套测试）：tests/capabilities; tests/agents/research。
- 源码范围：
  - [deeptutor/capabilities/solve](<D:/deeptutor/deeptutor/capabilities/solve>)
  - [deeptutor/agents/research](<D:/deeptutor/deeptutor/agents/research>)
  - [deeptutor/services/research](<D:/deeptutor/deeptutor/services/research>)
  - [web/components/research](<D:/deeptutor/web/components/research>)

## 31. 语音输入、朗读与音频导读

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：接输入框、教材朗读和章节导读；依赖实际语音服务。
- 关键入口：deeptutor/services/voice/; capabilities/audio_overview/。
- 完整复用边界：STT、TTS、供应商适配、数学口语化、浏览器录音/自动播放和知识库双人音频导读一起纳入。不是所有模型都带音频能力，需配置和真实试听。
- 上游测试/验证入口（本轮未执行整套测试）：tests/services/test_voice.py; tests/api/test_voice_routes.py。
- 源码范围：
  - [deeptutor/services/voice](<D:/deeptutor/deeptutor/services/voice>)
  - [deeptutor/capabilities/audio_overview](<D:/deeptutor/deeptutor/capabilities/audio_overview>)
  - [web/hooks/useVoiceRecorder.ts](<D:/deeptutor/web/hooks/useVoiceRecorder.ts>)
  - [web/hooks/useVoiceAutoplay.ts](<D:/deeptutor/web/hooks/useVoiceAutoplay.ts>)
  - [web/components/whisper](<D:/deeptutor/web/components/whisper>)

## 32. 实验视频和时间戳笔记

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：接实验示范材料；本地视频要另核实，不把远程平台支持等同通用本地视频。
- 关键入口：deeptutor/reading/ingestion.py; video_learning/service.py; marks.py; notes.py。
- 完整复用边界：已实现远程来源的字幕/定位、时间段标记、播放器和笔记一起复用。确认源码有 Bilibili/YouTube 读取路径，不泛化为任意实验录像完整支持。
- 上游测试/验证入口（本轮未执行整套测试）：tests/reading/test_ingestion.py; tests/video_learning。
- 源码范围：
  - [deeptutor/video_learning](<D:/deeptutor/deeptutor/video_learning>)
  - [deeptutor/reading/ingestion.py](<D:/deeptutor/deeptutor/reading/ingestion.py>)
  - [web/components/reading/workspace/MediaReadingStage.tsx](<D:/deeptutor/web/components/reading/workspace/MediaReadingStage.tsx>)

## 33. 文件库、附件和 Office 预览

- 复用形态：整套服务/组件复用。
- 当前项目接入点：接教材资料和实验报告附件，保留文件访问控制。
- 关键入口：deeptutor/services/storage/file_library.py; attachment_store.py; services/office_preview.py。
- 完整复用边界：附件持久化、跨会话文件库、原始文件获取、Office 预览、复用选择与文件卡片整体接入；文件资源归属继承本项目账号课程授权。
- 上游测试/验证入口（本轮未执行整套测试）：tests/services/session/test_attachment_parsing.py; web/tests/file-previewer.test.ts。
- 源码范围：
  - [deeptutor/services/storage](<D:/deeptutor/deeptutor/services/storage>)
  - [deeptutor/services/office_preview.py](<D:/deeptutor/deeptutor/services/office_preview.py>)
  - [deeptutor/api/routers/file_preview.py](<D:/deeptutor/deeptutor/api/routers/file_preview.py>)
  - [web/components/chat/preview](<D:/deeptutor/web/components/chat/preview>)

## 34. 学习任务板与提醒

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：接学习任务、会话关联与复习提醒；与已计算复习队列协作。
- 关键入口：deeptutor/services/task_board.py: TaskBoardStore; services/cron/service.py。
- 完整复用边界：任务 todo/doing/done、会话关联、SQLite revision、提醒调度、后台 leader 执行和任务 UI 全部可迁入。复习 due 队列与提醒投递分工。
- 上游测试/验证入口（本轮未执行整套测试）：tests/multi_user/test_task_board.py。
- 源码范围：
  - [deeptutor/services/task_board.py](<D:/deeptutor/deeptutor/services/task_board.py>)
  - [deeptutor/services/cron](<D:/deeptutor/deeptutor/services/cron>)
  - [web/components/tasks](<D:/deeptutor/web/components/tasks>)

## 35. 身份、资源隔离与授权

- 复用形态：统一底座和身份接入。
- 当前项目接入点：对接现有角色和课程成员，不并行使用互不关联的身份体系。
- 关键入口：deeptutor/multi_user/models.py; context.py; grants.py; knowledge_access.py; learning_access.py。
- 完整复用边界：复用身份上下文、资源授权、模型/工具白名单、个人目录、监护授权和审计。teacher/student 字段存在，只有 admin 自动提权；班级/教师管理要接课程业务。
- 上游测试/验证入口（本轮未执行整套测试）：tests/multi_user/test_learning_records_isolation.py; tests/multi_user。
- 源码范围：
  - [deeptutor/multi_user](<D:/deeptutor/deeptutor/multi_user>)
  - [deeptutor/services/auth.py](<D:/deeptutor/deeptutor/services/auth.py>)
  - [web/features/multi-user](<D:/deeptutor/web/features/multi-user>)
  - [web/components/access](<D:/deeptutor/web/components/access>)

## 36. 资源工作区和迁移导出

- 复用形态：整套服务/组件复用。
- 当前项目接入点：映射课程、学生、会话与物理数据目录，支持备份/迁移。
- 关键入口：deeptutor/services/workspace/service.py; resources.py; data_migration.py。
- 完整复用边界：资源范围、文件访问、工作区绑定、导出、迁移预览/恢复、知识库移动及资源选择 UI 一起复用。不会自动迁移我们的 SQLAlchemy 业务表。
- 上游测试/验证入口（本轮未执行整套测试）：tests/services/workspace。
- 源码范围：
  - [deeptutor/services/workspace](<D:/deeptutor/deeptutor/services/workspace>)
  - [deeptutor/services/path_service.py](<D:/deeptutor/deeptutor/services/path_service.py>)
  - [web/components/workspaces](<D:/deeptutor/web/components/workspaces>)
  - [web/lib/workspace-scope.ts](<D:/deeptutor/web/lib/workspace-scope.ts>)

## 37. 教学 Skill 与插件机制

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：承载课程技能/教学工具；教师审核是本项目附加发布规则。
- 关键入口：deeptutor/services/skill/service.py / runtime.py; plugins/lifecycle.py。
- 完整复用边界：按需读取教学技能、作用域、包导入、插件声明/权限/安装/回滚/前端资源一起复用。builtin 文档技能可支持教学文件；课程 Skill 自动生成审核要另接发布链。
- 上游测试/验证入口（本轮未执行整套测试）：tests/plugins; tests/services/skill/test_skill_service_v2.py。
- 源码范围：
  - [deeptutor/services/skill](<D:/deeptutor/deeptutor/services/skill>)
  - [deeptutor/plugins](<D:/deeptutor/deeptutor/plugins>)
  - [deeptutor/skills/builtin](<D:/deeptutor/deeptutor/skills/builtin>)
  - [web/components/agents](<D:/deeptutor/web/components/agents>)
  - [web/lib/skills-api.ts](<D:/deeptutor/web/lib/skills-api.ts>)

## 38. MCP、统计计算与文件生成

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：接统计计算/图表/报告生成等扩展能力，按课程和任务授权工具。
- 关键入口：deeptutor/services/mcp/; services/sandbox/; tools/exec_tool.py。
- 完整复用边界：工具发现、延迟加载、参数校验、连接恢复、凭据隔离、执行配额和产物展示整体复用，可接实验统计计算与文件生成。Windows 降级 subprocess 不是 OS 沙箱。
- 上游测试/验证入口（本轮未执行整套测试）：tests/tools; tests/services/mcp; tests/services/sandbox。
- 源码范围：
  - [deeptutor/services/mcp](<D:/deeptutor/deeptutor/services/mcp>)
  - [deeptutor/services/cli_apps](<D:/deeptutor/deeptutor/services/cli_apps>)
  - [deeptutor/services/sandbox](<D:/deeptutor/deeptutor/services/sandbox>)
  - [deeptutor/tools/exec_tool.py](<D:/deeptutor/deeptutor/tools/exec_tool.py>)

## 39. 多角色学习伙伴与群组

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：可用于教师定义的不同助教角色或讨论；IM 外发另行启用。
- 关键入口：deeptutor/services/partners/; services/partner_groups/modes.py。
- 完整复用边界：多角色伙伴、群组共享上下文和并行/顺序/辩论模式可用于教学讨论。外部 IM 通道也有源码，但与当前核心功能无直接关系，候选保留且默认不启用外发。
- 上游测试/验证入口（本轮未执行整套测试）：tests/partners; tests/services/partners。
- 源码范围：
  - [deeptutor/partners](<D:/deeptutor/deeptutor/partners>)
  - [deeptutor/services/partners](<D:/deeptutor/deeptutor/services/partners>)
  - [deeptutor/services/partner_groups](<D:/deeptutor/deeptutor/services/partner_groups>)
  - [web/components/partners](<D:/deeptutor/web/components/partners>)

## 40. 外部 Agent 后端

- 复用形态：整套复用并接课程规则。
- 当前项目接入点：用于实验代码/分析任务等扩展，保持用户和工作目录范围。
- 关键入口：deeptutor/services/subagent/registry.py; sessions.py; process.py。
- 完整复用边界：完整连接器和会话连续性可用于代码/分析辅助。该项是项目可复用功能调研，本轮未调用/启动任何这些 Agent。
- 上游测试/验证入口（本轮未执行整套测试）：tests/services/test_subagent_backends.py; tests/capabilities/test_subagent_capability.py。
- 源码范围：
  - [deeptutor/services/subagent](<D:/deeptutor/deeptutor/services/subagent>)
  - [deeptutor/capabilities/subagent](<D:/deeptutor/deeptutor/capabilities/subagent>)

## 41. 富文本、数学公式与图表显示

- 复用形态：整套服务/组件复用。
- 当前项目接入点：替换当前有限 Markdown 输出，保留页面结构与来源卡。
- 关键入口：web/components/common/RichMarkdownRenderer.tsx; web/lib/latex.ts。
- 完整复用边界：Markdown、表格、公式、代码块、Mermaid、链接和文件卡完整渲染能力可替换当前 chat-renderer.js 的有限语法。保留来源点击和页面滚动语义。
- 上游测试/验证入口（本轮未执行整套测试）：web/tests/rich-code-block.spec.tsx; web/tests/reading-citation-capture.test.ts。
- 源码范围：
  - [web/components/common](<D:/deeptutor/web/components/common>)
  - [web/lib/latex.ts](<D:/deeptutor/web/lib/latex.ts>)
  - [web/lib/markdown-display.ts](<D:/deeptutor/web/lib/markdown-display.ts>)
  - [web/components/Mermaid.tsx](<D:/deeptutor/web/components/Mermaid.tsx>)
  - [web/components/Geogebra.tsx](<D:/deeptutor/web/components/Geogebra.tsx>)

## 42. 前端传输、缓存、草稿与类型

- 复用形态：整套服务/组件复用。
- 当前项目接入点：复用消息状态机、恢复和输入行为，适配当前 API。
- 关键入口：web/features/chat/transport/TurnRuntimeClient.ts; web/contracts/; web/shared/。
- 完整复用边界：前端命令投递、重连、事件解析、状态对账、草稿/失败请求、平滑流式文本、IME 与组件通用层一起带入。完整 Providers/context/hooks 与样式资源不能漏。
- 上游测试/验证入口（本轮未执行整套测试）：web/tests; web/package.json: contracts:check / architecture:check / typecheck。
- 源码范围：
  - [web/features/chat](<D:/deeptutor/web/features/chat>)
  - [web/contracts](<D:/deeptutor/web/contracts>)
  - [web/shared](<D:/deeptutor/web/shared>)
  - [web/hooks](<D:/deeptutor/web/hooks>)
  - [web/lib/turn-reconcile.ts](<D:/deeptutor/web/lib/turn-reconcile.ts>)
  - [web/lib/failed-submissions.ts](<D:/deeptutor/web/lib/failed-submissions.ts>)

## 43. 评测、回归测试与工程检查

- 复用形态：整套服务/组件复用。
- 当前项目接入点：迁入相关测试与构建检查，加心理学教材/课堂规则样例。
- 关键入口：deeptutor/services/rag/eval/runner.py / metrics.py; .importlinter。
- 完整复用边界：复用检索 Recall/MRR/nDCG 等指标、黄金集结构、运行器、上游相关测试、导入/架构检查和浏览器测试框架。自动检索相关性不等于回答语义支持或真实教学效果。
- 上游测试/验证入口（本轮未执行整套测试）：tests/services/rag/eval; tests/architecture; web/tests/e2e。
- 源码范围：
  - [deeptutor/services/rag/eval](<D:/deeptutor/deeptutor/services/rag/eval>)
  - [tests](<D:/deeptutor/tests>)
  - [web/tests](<D:/deeptutor/web/tests>)
  - [.github/workflows/tests.yml](<D:/deeptutor/.github/workflows/tests.yml>)
  - [.importlinter](<D:/deeptutor/.importlinter>)
  - [web/.dependency-cruiser.cjs](<D:/deeptutor/web/.dependency-cruiser.cjs>)
