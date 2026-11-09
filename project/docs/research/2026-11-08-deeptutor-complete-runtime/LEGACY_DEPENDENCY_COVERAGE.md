# 旧教学依赖能否由 DeepTutor 覆盖：源码核对

日期：2026-11-09。结论：**通用回答内核、上下文/历史、模型调用、长期记忆和教学/学习主体可以进一步统一到 DeepTutor；产品特有的教材证据、任务授权和正式测评校验没有同等的直接替代，宜保留为独立宿主边界，而不是继续依赖旧教学执行器。**

本次只做静态图谱、架构 HTML、D 盘源码与宿主调用核对，没有修改业务代码，没有执行新迁移或真实模型测试。

## 来源及现状

- D 盘 `.ua/knowledge-graph.json`：5924 个节点、12070 条边；图谱和当前 HEAD 都为 `6cf793bd868ba5ecbe64722936d4be8fab5a01df`。图谱有 `services/session`、`services/memory`、`services/llm` 等层及 imports/depends_on 关系。
- D 盘 `ARCHITECTURE.html` 的 Application、Services、Domain 三段描述了会话存储、运行时协调、LLM、学习和阅读主体。
- 当前 D 盘存在 `services/llm/factory.py` 本地修改，已单独核对：把 provider-runtime 配置转换为 LLM 服务配置；与当前 vendor 文件一致。
- 本轮抽查的 25 个相关上游文件全部已存在于 `project/vendor/DeepTutor`；24 个与 D 盘内容相同。唯一差异 `learning/policy.py` 是宿主已有的独立作答/受助排除增强，不是缺迁文件。完整路径和结果见同名 JSON。

所以问题主要是“主机是否仍调用旧服务，以及现有数据/API如何交接”，不是再拷贝一批已经存在的原生文件。

## 不能仅按架构图盒子的名称替换

D 盘 `services/session/context_builder.py:199` 的 ContextBuilder 处理历史压缩、预算与模型历史回放；完整 UnifiedContext 在 `services/session/turns/executor.py` 中组装，还依赖 request_preparer、source_inventory、model_history 和资源解析。

宿主 `native_executor.py` 已调用原生执行链，但启动入口仍无条件构造 TutorOrchestrator，初始化十余个旧路由/规划/生成/质检组件。宿主 TaskContextBuilder 还为资源快照创建旧 TaskContext/UnifiedContext。这两部分可继续拆除，不能把原生 ContextBuilder 当作相同签名的单文件替换件。

## 覆盖矩阵

| 现有依赖 | 原生覆盖 | 结论 |
| --- | --- | --- |
| TutorOrchestrator 与旧 agents 初始化 | DeepTutorApp/ApplicationContainer/TurnEngine | 主聊天已接管；练习接口及宿主服务注入迁完后可取消旧初始化 |
| TaskContextBuilder、旧历史/摘要 | request_preparer + executor + ContextBuilder + model_history/source_inventory | 通用部分可替换；课本选区、小题及交互对象校验转为资源适配 |
| llm/client.py | services/llm 的配置、provider_factory、complete_with_config | 可替换，继续通过隔离 worker/现有 bridge 调用，补齐旧 chat/chat_json/图像/工具调用契约 |
| 旧教学策略/教学计划 | 原生 prompt/persona/profile、mastery loop/policy | 可改用原生行为；不是原13策略算法的逐项等价实现。现有7维数值偏好需映射或调整界面 |
| MemoryManager 的对话/长期记忆/学习状态 | SessionStore、MemoryStore、LearningJournalStore、LearningService/Store | 原生覆盖分布在多个子系统，须拆分数据与API迁移，不能拿MemoryStore单独替换整个MemoryManager |
| 练习提示、讲解、AI批改 | solve/question、grading/assessment、LearningService | 需要真实接入小题、图像和评分依据；当前这条旧入口尚未迁完 |
| 任务幂等/恢复 | submission/turn/事件、coordinator租约及fencing | 运行时可统一；宿主memory_epoch、教材版本、任务修订、学生/会话归属没有相同契约，保留薄层 |
| 教材正式引用与发布 | reading.verify_quote、原文窗口、research CitationManager | 覆盖不足，现有版本/原文块/坐标/编号核验应独立保留 |
| 正式学习进度、掌握度、复习 | learning/service/storage/policy/grading/mastery/scheduler | 原生主体已接；宿主审核依据、独立作答及写入授权仍保留，不能覆盖掉既有policy增强 |
| reader_goto / ask_user | 原生阅读工具、ReadingStore、tools/ask_user | 工具主体已在用；只需宿主UI/文档版本/回执映射，不需要旧教学执行器 |

## 新发现的旧入口

`practice_api.py:171` 的 ai_parts 仍调用 `main.orchestrator.llm` 和 `main.orchestrator.quality_checker`。`help_question:385` 以及无规则答案时的 `run_submission:316` 都会使用它，路由在 main.py 中实际挂载。

因此，上次“主聊天默认不走旧链”的结论成立，但不能扩大为“产品所有回答/批改都已经脱离旧服务”。这条入口应列入下一步替换范围。

## 为什么保留的是校验能力，不是旧教学链

- `_publish_gate` 的 orchestrator 形参当前没有实际属性读取；没有理由为了这一个门禁继续初始化整个旧协调器。将其与引用格式/证据发布助手移到独立宿主模块即可解除旧 agents 文件依赖。
- D 盘 `reading/service.py:155` 核验选定原生材料中是否存在引句；其 `reader_goto` 在引句无法匹配时可以只跳页而不高亮。它不提供宿主的教材 document/version、正式原文块、PDF矩形及任务快照一致性这一整套契约。
- D 盘研究 CitationManager 管理引用ID、来源信息与引用存在性；不能把“编号存在”当成“本轮正式教材原文与坐标已核验”。
- D 盘 LearningService 有评分、学习证据、复习调度和硬掌握闸门。但当前 vendor policy 已多出 `_independent_evidence`，会排除受助/讲解后作答；直接用 D 盘原文件覆盖会丢失这一已实现约束。
- 宿主偏好采用7个0..1数值和用户确认来源，原生账户画像/路径画像主要是结构字段及文本；需要迁移映射，不能用方法名相近作为数据兼容证明。

## 建议的实施顺序

1. 先让原生模式不再无条件初始化 TutorOrchestrator，宿主只注入实际需要的账号、授权、证据和公开结果保存服务；先处理 practice_api 对旧对象的直接引用。
2. 用原生会话/上下文装配取代宿主旧上下文复制层，只保留课本/小题/对象的只读资源绑定；保留本轮完成的题卡历史修复。
3. 将练习提示/讲解接到原生能力，把通用模型调用统一到原生 provider；正式批改继续执行既有审核和证据边界。
4. 将通用教学策略与长期记忆切换到原生 persona/profile/memory/journal/learning，对现有偏好、历史接口和删除语义做明确迁移。
5. 引用发布、任务授权和正式测评校验拆成独立宿主模块后，清理旧执行器与重复算法。源码存在性不算完成，须复跑普通聊天、教材引用、练习帮助/提交、删除后失效、出题后翻页和历史恢复等真实链路。

本核对不承诺逐项无行为差异，也不宣称第二部分全部完成；每项接入状态和所需适配见同名JSON。没有运行迁移测试或改动正式学生数据。
