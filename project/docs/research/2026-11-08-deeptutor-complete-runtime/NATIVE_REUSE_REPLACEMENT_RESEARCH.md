# 直接复用 DeepTutor：深入替换调研

日期：2026-11-09。以用户最新说明为准：**已复用的 DeepTutor 实现保留；独立自研的重叠业务由 DeepTutor 原生模块替换。目标不是优化旧实现，也不要求继续复现旧算法。** 本文修正上一轮把“完全保持自研语义”作为迁移前提的方向。

本轮没有修改业务代码。已读取 D 盘图谱、架构 HTML、相关后端与前端源码，并直接调用 D 盘原生函数做隔离验证；未调用真实模型或迁移正式数据。

## 1. 已有源码，不应再次做一套实现

当前 D 盘图谱为 19123 个节点、38026 条边，对应提交 `6cf793bd868ba5ecbe64722936d4be8fab5a01df`。本轮按整组目录和关联入口检查：

| 原生功能组 | 已有相关文件 | vendor缺失 |
| --- | ---: | ---: |
| app/runtime/session/AgentLoop | 95 | 0 |
| persona/mastery/learning | 64 | 0 |
| memory/learning_journal及API | 48 | 0 |
| practice/question/judge/assessment | 27 | 0 |
| KB/RAG/Reading及入口 | 140 | 0 |
| LLM/model_selection | 49 | 0 |

分组存在交叠，去重共 422 个相关文件；完整路径见同名JSON。这是选定主包和入口的存在性/内容检查，不是全部动态插件依赖的运行证明。除既有 `learning/policy.py` 补丁外，选定文件与 D 盘一致。

已在真实链路中使用的 DeepTutorApp、原生 TurnExecutor/ContextBuilder/AgentLoop、registry、原生能力和原生 memory/mastery 工具主体继续保留。接下来需要撤掉重复自研调用和覆盖，让这些已有模块直接承担业务。

## 2. 需要替换或恢复原生行为的位置

| 当前自研/覆盖层 | 直接使用的原生完整部分 | 接入后退出的旧依赖 |
| --- | --- | --- |
| TutorOrchestrator强制初始化及旧TaskContextBuilder | app + session/turns + context_builder/model_history/source_inventory | 旧路由、规划、生成、质检组件不再为原生回答初始化；不再装配第二个旧UnifiedContext |
| teaching_prompt_adapter注入自研strategy_plan | PersonaService + 原生learner_profile + mastery pipeline/prompts/tools + learning policy | 不再执行13策略选择、自研教案moves或旧TaskExecution决策 |
| mastery工厂/提交被宿主重定向 | 原生LearningService/LearningStore + mastery tools + 原生LearningTurnAdapter | 撤掉HostAssessmentService/HostAssessmentStore中的第二套评分事件改写、scheduler=None覆盖及AssessmentCommands接管；保留必要访问授权 |
| practice_api的ai_parts/提交/复习业务 | services/practice + practice API + question notebook + quiz_judge + learning/assessment | 自研练习判定、AI批改和复习业务退出，不只是换一个LLM客户端 |
| 宿主MemoryManager的回答依赖 | SessionStore + MemoryStore + LearningJournalStore + LearningStore | 不继续双维护旧对话摘要、长期偏好与学习状态决策 |
| 宿主llm/client.py实际调用 | services/llm + model_selection | 所有新入口通过已有隔离worker执行原生provider，不保留第二套模型循环 |
| HeartCourseRagTool/HeartCourseFilesTool覆盖内置工具 | 原生RAGTool/KbFilesTool + RAGService/provider + knowledge导入 + ReadingStore/source_visuals | 停止调用宿主独立检索和证据算法；恢复原生工具目录与KB绑定规则 |

这些覆盖中，有些类继承了原生类，但其方法仍修改原生业务判断，不能仅凭“继承/复用”就认定已经是原生主体。应保留原生类与已迁入源码，撤去重复决策覆盖。

例如原版 `mastery.tools._new_service()` 返回 `LearningService(LearningStore())`，当前却被替换为宿主服务/存储；宿主服务还会强制关闭原生scheduler。替换目标是恢复原生出题、评分和调度，身份授权可包在调用边界，不再另写评分算法。

## 3. 本轮新增的具体上游替代能力

### 原生练习是完整模块

图谱与源码链：`api/routers/practice.py → services/practice/{importing,answers,storage,scheduler,analytics}.py → 原生SQLiteSessionStore/题库`。

原生已实现导入预览与提交、题目内容去重、客观题判定、复习事件、版本冲突、请求幂等、复习队列和统计。`api/routers/quiz_judge.py` 提供学习者文字/图像作答的AI评判；`learning/assessment.py:record_assessment` 保存题目投影、不可变作答记录和可信学习关联。

因此可以用整套原生练习/题库/评判替换旧practice业务。注意原生 `check_answer` 对简答/定性题返回None，不凭字符串相同就发明客观分数；页面应按原生语义展示。不能继续把AI反馈套成旧“正式100分”契约，却又保留旧算法来补。

### 来源校验不止verify_quote

上一轮只拿阅读引句匹配对比旧证据包，覆盖看窄了。原生 `services/rag/source_visuals.py` 和 `visual_assets.py` 还有：

- 管理源码路径与目录边界，拒绝越界和符号链接路径；
- 源PDF内容hash与变更检查；
- 指定页与标准化region裁切、原文提取及像素证据；
- 读取前后hash核对，拒绝发生变化的来源；
- 原生rag接收source_path/page/region/source_hash，并按当前用户KB访问权限解析。

目标应为教材进入原生KB后，使用这整套来源能力和原生引用格式。它不与旧EvidenceBundle逐字段等价，但这不构成必须继续运行旧引用算法的理由；页面与数据契约随原生调整，并清楚说明实际校验层级。身份、资料归属和私有数据边界仍须校验。

### 目前原生请求入口被宿主截短

AST核对发现，NativeTurnOptions未包含这些实际功能入口：`mastery_answer`、`mastery_skip`、`question_notebook_references`、`parent_message_id`、`followup_question_context`、`selection_tutor_context` 等；native_bridge还固定传入 `auto_route=False`。

这些字段有原生代码不等于产品已能使用。应按原生TurnRequest接通作答/跳过、题库引用、编辑分支等，而不是继续在宿主新增一套独立意图和作答状态机。服务端拥有的user/workspace/course/session等身份不能直接信任浏览器，应继续做映射与授权。auto_route遵循原生配置和显式能力选择语义，不在桥接层永久强制覆盖。

特别注意：`selection_tutor_context`核对的是父聊天消息的选中文本，不等于PDF矩形选区。PDF使用 `ReadingReference(material_id, revision, locators)` 与 `ReadingViewport(locator, selection)`，必要图像用原生attachments/page inspection；不要误接。

## 4. 已复用的保留，真正的接口代码保留

保留既有原生核心、已运行的原生tools/capabilities，不重新迁一遍。31个不需要的工具继续隐藏。

保留账号/课程/会话ID映射、必要访问授权、隔离worker通信、公开结果字段裁剪、事件转发和阅读器回执。这些是接入宿主所需的接口工作，不应继续包含教学计划、评分、掌握度、复习、检索排序等第二套业务算法。

近期已验证的题卡历史交接修复先保留。它解决结构化结果进入后续上下文的接缝，不是第二套教学策略；若能用上游正式历史契约完全接管，再以回归证明替换。

`vendor/learning/policy.py`已存在独立证据补丁，按“既有复用保留”先不整包覆盖；必须单独记录其与D盘的差异。不能在迁入另一模块时顺手抹掉已有补丁，也不能因此继续保留整套宿主评分架构。

## 5. 已直接调用D盘源码的隔离验证

证据：宿主 `.runtime/native-reuse-probe/20261109-090058/report.json`，9项通过：

1. 原生客观题对错判定，定性题不发明客观判分。
2. 原生题目导入、提交重放与内容去重。
3. 原生复习持久化与请求幂等。
4. 拒绝过期复习版本。
5. 错误答案不能用good评级提交。
6. 从真实教材PDF副本读取第2页和区域文本、像素与hash。
7. 拒绝已变化来源引用。
8. 拒绝非法region。
9. 拒绝越界来源路径。

使用原版SQLiteSessionStore、PracticeStore、importing、answers、source_visuals；仅写隔离库与教材副本，无外网、无模型、未改正式数据。这证明对应原生函数在当前环境可运行，尚不等于主项目入口已经替换。

## 6. 直接复用的实施单元及验收

按完整业务链替换，每组都让原生代码真正被调用后，再移除旧主体：

1. 原生请求与会话绑定：补齐TurnRequest、接通作答/跳过等字段，明确原生身份与数据ID映射。旧TutorOrchestrator的最终移除应在练习等所有直接引用入口迁完后完成，不能第一步删除却让练习接口失效。
2. 教学主体：退出自研strategy_plan及相关monkey patch，接原生persona/profile/mastery；默认普通对话不强制套teacher persona，避免其苏格拉底式提示覆盖页面操作。
3. 记忆主体：旧偏好一次迁为原生preferences条目；对话、日志和学习记录进各自原生store，页面采用原生字段，不继续维护7维策略映射算法。
4. 练习主体：通过原生导入处理题目，练习、复习和评判直接使用原生services与API；多小题展开时保留共享条件，并保存旧ID→原生entry_id对应。旧成绩/进度不凭换算冒充原生独立掌握证据，必要时只读归档。
5. 教材主体：导入原生KB，恢复原生rag/kb_files及其挂载条件，读取/引用/原图/页码统一按原生数据流；旧SQLite索引不能直接改名冒充原生KB格式。
6. 验收：对普通聊天、选区、出题后翻页、题卡作答/跳过、练习导入/评判/复习、记忆跨会话读取、取消/重放/用户隔离逐条做真实链路测试。测试中将旧教学/LLM/评分入口设置为一旦调用就抛错，以证明新链路确实不再调用旧主体。

原生前端模块已有PracticePage、PracticeSession、PracticeImport、MemoryWorkbench等；它们依赖Next路由、i18n、workspace及API客户端，不能仅复制一个tsx就当接入完成。后端直接原生化与页面契约需一起验收。

本轮是进一步调研及原生函数验证，尚未实施以上替换。实施完成标准是“原生实现已在真实入口接管，旧业务不再被调用”，不是文件已存在或多包一层适配器。

## 后续修订说明（2026-11-09）

用户已确认保留现有legacy/local_llamaindex两种检索引擎并适配原生RAGService。本文第2节检索替换行、第6节第5项要求整体退出宿主检索并重建原生索引的方向已被替代，后续以[NATIVE_132_IMPLEMENTATION_PLAN.md](NATIVE_132_IMPLEMENTATION_PLAN.md)第八节为准。其余保留为调研记录，未在本次实施业务替换。
