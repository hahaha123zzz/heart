# 输入理解层 V1 执行计划

日期：2026-10-29。2026-10-30 更新：**首批规则理解、公共接线、复合回题及偏好确认已实现；整个 IU0—IU7 尚未完成，不具备全场景启用条件。**逐项证据及未通过项见 [执行记录](INPUT_UNDERSTANDING_EXECUTION_LOG.md)。

执行核对：原工作区实际为 `codex/ta5-acceptance-20261029 @ 816e78a`，包含 `7439ba5` 的后续修复；`main`/`origin/main` 均为 `3b212250`。本轮从实际工作版本建立 `codex/input-understanding-v1` 隔离工作树，未擅自把 TA5 分支称作 main，未合并或更新正式服务。此前计划中的“本地 main 7439ba5”表述已更正，详见 [基线](INPUT_UNDERSTANDING_BASELINE.md)。

依据：用户提供的《心理学教材学习 Agent：输入理解层 V1.0 完整技术方案》、[深度调研报告](INPUT_UNDERSTANDING_DEEP_AUDIT_20261029.md)、现有 TaskService/Q3/Q5/TA与原生授权契约。

## 1. 目标与范围

在现有回答链前形成一份可验证、可恢复的输入理解结果，让系统知道：

1. 学生原话是什么，文字、选区、按钮或题卡分别表达了什么。
2. 用户明确指向哪个教材、图、题目、示例或教学步骤；哪些还不能确定。
3. 本轮有几个任务，先后顺序是什么，哪些约束适用于本轮、本题、本次安排或长期。
4. 这一轮是在作答、插问、恢复、改变目标，还是提出偏好修改。
5. 下游还需要哪些分类标签；可靠规则已经确定的字段不重复分类。

本计划交付输入理解、分类接入协议、跨入口消费与相应页面交互。**多维分类器的正式维度/标签训练与校准另行确定；不把接口占位当分类器已上线。**

不新建 AgentLoop、通用工作流框架、教材索引或学习主库；不切换原生正式写入方，不重做评分/复习，不恢复昂贵的回答门禁或草稿撤回链。

## 2. 必须首先解决的真实问题

| 问题 | 已有证据 | 本计划要求 |
| --- | --- | --- |
| “先解释操作性定义，再回原题”只有旧题 | HTTP与同小节浏览器均命中resume_check，无模型调用 | 先完成解释，再展示同一待答题；不替学生作答 |
| 阅读位置覆盖教学位置 | 第一章reader_location导致第二章pending丢失，但模型仍能复述旧题 | 阅读位置默认仅作背景，不能静默结束活动题；显示与持久状态一致 |
| 自然语言长期偏好被丢掉 | 当轮比较完成，但没有长期修改确认动作 | 分离本题要求与长期偏好候选，后者需用户确认 |
| 多轮指代主要依赖历史文字 | 例子追问可回答，缺独立绑定；另会话只给文字询问 | 唯一对象可绑定，多对象结构化澄清；不猜ID |
| 多个入口分别理解 | 26轮宿主实际请求中ConversationRouter调用0次 | 公共入口产生统一结果，Q3/选区/Q5等消费它 |
| 局部选项解析可能忽略否定 | 纯函数将“我不选B”识别为可提交；真实链路模型兜底未误评分 | 在提交命令前确定性保护否定/问句/多选歧义，保留原文 |

`answered`、页面出现旧题、模型输出合法JSON，都不能单独作为以上问题解决的依据。

## 3. 运行边界与状态所有权

### 3.1 唯一写入方不变

| 对象 | 权威来源/写入方 | 理解层权限 |
| --- | --- | --- |
| 账户、记忆删除epoch | AccountManager/宿主仓储 | 只读，提交仍由原服务核查 |
| task、receipt、revision、取消/澄清 | TaskService/LearningTaskRepository | 保存理解快照及子任务状态，沿用原提交事务 |
| 教材来源、阅读游标、下一教材目标 | Q2导航与来源服务 | 引用/提出意图，不自行生成下一目录项 |
| 宿主辅助pending | 已发布任务的受控tutoring状态 | 绑定/暂停/恢复，通过既有宿主路径更新；不升级正式题 |
| Q5路径/本次安排 | Q5LearningService/SessionStudyService | 只读快照；动作仍调用原命令 |
| 原生题目、正式评估/复习 | 已授权启用的原生服务 | 只读公开投影及受控动作适配；不得启用第二写入方 |
| 独立练习提交/成绩 | practice_api | 保留原提交接口，聊天帮助不自动提交 |
| 持久偏好 | 现有偏好确认与Memory API | 只生成修改候选，用户确认后调用现有接口 |

原生开关关闭时，相应状态明确为unavailable，不伪造空题或临时原生路径。原生迁入窗口将来切换时，只更换受控适配，不重写输入协议。

### 3.2 有效任务与过期状态

- 当前 `LearningTaskRepository.expire()` 会清空payload/context/result；不能从已清空任务恢复未完成操作。
- V1保证有效期内的刷新、重启、插问和阅读位置变化不丢活动任务；到期后明确返回expired/missing，不擅自复活旧任务、原答案键或写入授权。
- 已有原生持久interaction/复习对象按其自身生命周期核验，不能套用聊天TTL将其销毁，也不能借持久题卡授权延长旧聊天生成任务。
- 教材块、已保存回答片段可在允许的历史来源中重新绑定；历史问答能阅读，不代表旧题可评分。
- 宿主辅助题跨聊天TTL的长期存续若要支持，必须单独交接权威存储及清理规则，不能在输入层偷偷复制一套持久pending。

## 4. 协议与模块边界

```text
ChatRequest / 显式动作
  → InputEnvelope：原话、输入来源、服务端作用域
  → ContextHeader：当前task/题目/计划/对象及各自revision
  → 按需展开已校验上下文
  → ReferenceResolver + 规则任务解析
  → 复杂输入按需一次结构化解析；分类插件补未确定语义
  → 本地校验 → GroundedTurn + 有限命令
  → 现有Q5/Q3/选区/练习/原生服务
  → 原有发布事务与收据保存理解、任务进度及结果
```

新增文件以职责为界，优先以下结构；不为每个函数拆一个模块：

```text
models/input_understanding.py          # 版本化协议与结构校验
agents/input_understanding/
  __init__.py                         # 有限公共导出
  service.py                          # 总入口、规则/模型升级、结果合并
  context.py                          # 摘要和按需上下文投影
  references.py                       # 候选和真实对象绑定
  rules.py                            # 安全规范化、确定性动作/否定/范围
  semantic.py                         # 复杂解析与分类插件边界
  adapters.py                         # 既有执行路径消费与旧协议投影
```

### 4.1 核心数据

| 数据 | 最小字段与限制 |
| --- | --- |
| InputEnvelope | schema_version、request_id、raw_text、normalized_text、input_kind、已验证显式引用；request_id沿用现有收据；raw_text按现有4000字符限制完整保留 |
| ContextHeader | student/course/session服务端作用域、task/revision/epoch、活动题及来源类型、Q5/path/session_plan/interaction各自版本、reader_location；不塞入全文历史和答案键 |
| ObjectReference | ref_id、mention及原话位置、kind、canonical_id或候选列表、status、provenance、资源版本；不得让模型自由指定权威ID |
| TaskFrame | 稳定task_frame_id、action、target_ref、query、depends_on、约束、状态；V1最多4个frame，超限进入澄清，不静默截断 |
| ScopedDirective | scope、目标身份、封闭key、严格类型value、原话依据、是否待确认；本轮/本题/本次安排/会话/长期分开 |
| SemanticAnnotations | classification_version/ontology_version、维度标签、rule/model来源、原话依据、unknown/abstain；维度未配置时为空，不补造标签 |
| GroundedTurn | 输入身份、上下文版本引用、已绑定对象、任务、约束、未知项、解析状态/来源；最终结果可序列化，不能包含DB session、回调或模型句柄 |
| ExecutionDecision | approved/read_only/clarify/reject、允许命令、原因；只能由服务端产生，不作为模型输出权限字段 |

解析过程的中间结构与最终GroundedTurn分开；不在Pydantic验证失败后用未经验证的model_copy更新绕过约束。

### 4.2 对象与动作

对象类型覆盖教材section/block/figure、概念检索目标、练习小题、formative/native question、教学步骤、示例/实验/回答片段。没有独立存储身份的“概念”可只作为query，不凭空注册实体。

V1有限动作采用可区分含义的名称：

- `explain_content`、`compare_content`、`provide_hint`、`discuss_claim`。
- `resume_pending_question`、`resume_learning_activity`。
- `propose_learning_plan`、`revise_learning_plan`、`confirm_learning_plan`。
- `submit_student_answer`、`request_practice`。
- `propose_preference_change`、`clarify_reference`、`switch_learning_target`。

避免含混的`answer`动作：给用户答案与提交学生答案必须区分。上述是执行动作契约，不是提前确定多维分类器标签。其他明确闲聊/结束学习等情况通过现有处理器映射，不制造教材缺失错误。

### 4.3 必须统一的语义

- 规则已核验的对象、否定和显式约束不得被模型低置信度结果覆盖；有冲突保留候选或澄清。
- 明确图号/选区动作可指向新对象；明确“我选B”优先绑定当前题；仅reader_location不切走当前题。优先级由动作及原话共同决定。
- `hint_only`、`no_full_answer`、`no_questions`等沿用已有名称；不同时接受no_question/no_questions等自由别名流入执行器。
- “以后详细”是persistent修改候选；“本题直接给答案”是question范围的呈现要求；没有可绑定题目时明确投影为本轮要求并记录依据，不能模型随意选scope。
- 区分resolved/missing/ambiguous/partial/stale/unauthorized；不把依赖不可用等同教材缺失或学生不会。
- 普通未知内容可只读讨论，不是每个unknown都必须ask_user；只有会影响对象选择、状态写入或任务方向的关键歧义才中断。

## 5. 分阶段执行

### IU0：冻结基线、失败样本与状态边界

任务：

1. 从最新稳定main建立 `codex/input-understanding-v1` 隔离worktree；不覆盖主工作区教材删除或其他窗口改动。
2. 记录代码SHA、实际导入路径、数据库位置、模型/检索模式、启用开关；密钥只读现有安全配置。
3. 将调研中的复合请求、阅读位置覆盖、偏好范围、否定作答、跨session指代转成独立学生/会话的可重复案例；测试输入与预期分开存储，预期不进入模型。
4. 为普通Q3、Q5计划、文本/区域选区、练习辅导、ask_user、题卡和复习动作列入口及唯一写入方；接线清单不允许只列ConversationRouter。
5. 在稳定基线上重新记录首Token/完成时间、理解/回答模型次数、状态前后快照；保留基线失败，不能事后改写。

交付：`INPUT_UNDERSTANDING_BASELINE.md`、初始标注集、入口/状态清单和隔离运行脚本。提交只含本阶段文件。

完成条件：两个真实缺陷在稳定基线HTTP与页面可复现；若已被其他提交修复，更新证据与剩余范围，不重复做相同补丁。

### IU1：协议、命令白名单与兼容投影

改动：新增 `models/input_understanding.py` 和最小包导出；扩展TaskContext的可选理解字段；补充旧TaskUnderstanding/TaskExecution的适配契约。

任务：

1. 实现第4节协议、枚举版本、长度/数量限制、严格类型与引用关联校验；保留raw_text，记录规范化位置映射。
2. 校验task_frame身份唯一、depends_on存在、依赖无环、目标引用有效；互斥约束不能“最后一项覆盖”后静默执行。
3. 同一输入结果兼容投影到旧路由字段；证明旧enum限制不会丢失复合任务。不能表达的旧路径由受控适配执行或澄清，不强制截成3个意图。
4. 为未来分类器定义 `annotate(draft, context_projection, missing_dimensions)` 边界：只补语义、不改对象与约束；未配置时不调用、不补标签。
5. 定义读写脱敏投影：理解模型只见公开题目，不见答案键；公开API不泄露内部身份、私有上下文或候选授权信息。

验证：`tests.test_input_understanding_contracts`，覆盖非法字段、未知版本、依赖环、伪造ID、answer动作歧义、scope冲突和旧记录缺字段。

完成条件：三份有效协议示例可用于实现：解释→恢复、否定选择、长期偏好+当轮解答。分类器标签尚未确定也可运行。

### IU2：上下文摘要、对象绑定与阅读位置分离

改动：新增context/references；接入TaskContextBuilder、TaskService._read_context、adaptive_tutoring.snapshot_from_recent；按需调整前端请求来源字段。

任务：

1. 先取轻量状态摘要；显式选区/题卡载荷沿用既有校验结果，不再解PDF或查全书第二次。按需读取历史/偏好，保持独立只读session的并发边界。
2. 将阅读背景、当前教学任务目标、用户显式新目标分别保存；前端默认section标题不得继续被当成用户明确learning_goal。旧客户端由服务端按保守规则兼容。
3. 读取有效pending和Q5目标时先核对owner/session/course/epoch/各自revision；保留当前题，再解释reader_location差异，不以不同章为由清空题目。
4. 显式切目标/选区插问只影响允许的本轮范围；保留可返回的原对象；明确“不要回原题”不能被resume正则当成恢复。
5. 对教材/图/题使用既有ID；示例、实验、assistant_claim先绑定已保存conversation及可定位片段。只有具有明确角色/片段的内容才注册对应kind，不把任意段落推断成实验。
6. 候选越界、删除、换版、多个合理对象时分别返回原因；缺失时允许用户重新圈选或提供引用，不让模型生成身份。
7. 回答发布成功后保存有限的对象引入记录与活动绑定；读取和构造候选不能推进学习位置或标记已理解。

验证：`tests.test_input_reference_binding`；真实页面“第二章出题→切到第一章/刷新→插问→回题”，核对同一question_id、pending、计划位置与会话身份。

完成条件：在有效生命周期内，阅读位置不再隐式销毁待答题；过期/取消/删除样本明确拒绝恢复；不能仅凭历史文字复述判通过。

### IU3：确定性输入解析与复合任务修复

改动：rules/service；消费TeachingTurn恢复快捷路径、teaching_policy、followup_context、course_search的重叠判断。

任务：

1. Unicode/空白处理保守执行，保留否定、数字、公式及原文；术语纠错只给候选，不覆盖学生作答。
2. 显式按钮、唯一有效题目下的明确作答、单一恢复、已绑定对象的简单追问走规则；明确“不选B”“为什么B”“B或C”不能提交。
3. 复用已迁入的pending解析函数，但在统一提交边界补否定/问句/歧义验证；不复制第三份选项解析器。不确定答案可澄清，不能判错。
4. “先解释X再回题”表示两个frame和解释→恢复依赖；普通“比较并举例”保持一个任务及回答结构。
5. `restore_reply()`只接受统一结果确认的单一恢复动作；不得继续按整句出现“回到”就提前结束。复合解释完成后最后展示服务端保存的原题，不能再生成一份相似题。
6. 统一hint/no_questions/完整解释等本轮要求；覆盖旧提示的规则只改变对应范围，不删除不相关限制。
7. 偏好解析输出原话依据和scope：本轮项立即用于呈现，长期项形成待确认候选；不把“详细一点”解释成画像或掌握证据。

验证：`tests.test_input_understanding_rules`、真实HTTP及页面合句/拆句对照；确认规则路径不新增理解模型调用。

完成条件：已复现的截断修好；否定选择不依赖模型兜底才能阻止提交；原题身份及辅助状态不变；规则结果不只是作为提示词附加后仍被旧逻辑覆盖。

### IU4：复杂解析与多维分类接口

改动：semantic/service；按实际兼容性扩展LLM客户端的可选结构化调用，不改变所有既有调用的默认行为。

任务：

1. 复杂度升级依据包括多对象、顺序/条件/否定冲突、未解关键指代；不能只靠句长决定，也不因所有短句都含糊就全部调用模型。
2. 一次调用接收有限原话、公开活动状态、真实候选、允许动作与待补语义维度；不得发送全量画像、完整所有历史、答案键或评测预期。
3. 提示词只让模型提出任务/约束/候选选择；权限、epoch、正式成绩、写入批准等不能成为可生成字段。
4. 复用现有JSON提取与Pydantic；若使用provider json_object，独立验证配置模型/网关，不能把合法JSON等同语义正确。V1不要求迁到beta/Responses或部署新模型。
5. 首次结构化结果失败允许最多一次有界格式修复；仍失败则保守澄清或安全只读回答。语义缺失不能由“格式修复”补造；超时受当前回合预算约束。
6. 正式分类器未配置时不加载BGE路由示例库、不强制embedding。若同时有复杂解析和已配置分类，合并同次调用或共用语义候选，禁止固定串行多次理解同一原话。
7. BGE只做可选候选实验：样例向量预计算、复用已有模型实例；缓存含ontology/model/上下文指纹。相似度不当概率，不能绕过对象/作答规则。
8. 自报困难只记录self_reported；具体误区必须来自后续独立诊断/证据，OpenTutor式失败默认conceptual不得迁入。

验证：`tests.test_input_understanding_semantic`；真实模型至少覆盖调研6类加否定/条件/省略/双对象变体。输出字段与scope按IU1固定，不靠事后别名猜测“差不多正确”。

完成条件：解析结果不能覆盖可信绑定；失败可解释且不写业务状态；模型调用数、耗时、升级原因可追踪。分类器端口测试通过不写成分类标签质量已验收。

### IU5：公共接线、子任务恢复和页面消费

改动：TaskService/main/Q3服务、Q5Runtime、selection_loop、TaskExecution/ConversationRouter适配；必要时扩展现有clarification与偏好确认页面。

任务：

1. 在请求重放/有效待澄清恢复后读取摘要，**在Q5和聊天分流前**形成统一理解；需要完整上下文时复用原_context对象，不再重复读取。
2. 同一request只解析一次；理解快照连同版本、对象依据、各frame状态随现有任务保存。幂等重放返回首次已保存结果；不能用新模型重解析已执行请求。
3. Q3普通聊天、文本/区域选区、旧Orchestrator和练习辅导均消费同一份结果；输入层启用后，停止旧路由对相同字段重复模型识别，保留兼容入口投影。
4. Q5生成/确认/修改计划按frame与显式动作路由；插问不推进current_item_id，不把插问讲解当原目标完成依据。允许合法记录导致revision变化，但每项写入原因必须明确。
5. 复合任务仍由现有任务/AgentLoop编排，不嵌套第二个loop。需要等待用户的步骤保存未完成frame与resume_ref；恢复后只做未完成项。
6. 同回合解释→回题可先生成解释，再确定性附回同一原题；本轮禁完整答案时解释也不能绕过限制。解释失败时不声称已完成再返回；取消/断线恢复不重复提交。
7. ask_user保存待解字段、候选、部分理解和原始frame；文本“第二个”与点击选项都恢复该对象，不当新概念检索。题目答案与澄清selected_option不得混用。
8. 长期偏好候选展示现有确认UI；学生可先读本轮答案，再确认/拒绝长期项。不因长期项待确认阻塞已明确的本轮讲解，也不覆盖已有未答题。
9. 题卡/复习/练习显式提交沿原强类型API，直接产生经验证动作，不额外用模型判分类；原生模式仍由现有开关决定。
10. 显式选区新问题和原任务共存时，在单一已授权session中记录临时focus/return_ref；不为V1新建全套父子侧栏UI。遇到现有独立子会话按真实服务端关系隔离，不能信任客户端自报parent_id。
11. 多个状态写入仍调用原命令并使用稳定子命令ID；跨库不假称原子事务。已成功项留收据，失败项保留partial，重试不重复执行；不支持的混合写入组合明确拆确认，不能整体重跑。

完成条件：入口覆盖表逐项可运行；只有显式用户动作和原有服务可改变学习状态；刷新后显示、pending/interaction ID、frame状态一致。

### IU6：联合验收、影子比较与性能检查

新增测试名以实施后的真实文件为准，本计划建议：

下列命令在 `E:\项目\heart\project\integration\discrete-math-tutor` 或对应隔离worktree的同级应用目录运行。

```powershell
& .\.venv-runtime\Scripts\python.exe -B -m unittest `
  tests.test_input_understanding_contracts tests.test_input_reference_binding `
  tests.test_input_understanding_rules tests.test_input_understanding_semantic `
  tests.test_input_understanding_integration -v

& .\.venv-runtime\Scripts\python.exe -B -m unittest `
  tests.test_task_api tests.test_task_execution tests.test_conversation_context `
  tests.test_q3_task_loop tests.test_teaching_modes tests.test_session_study_plan -v

& .\.venv-deeptutor\Scripts\python.exe -B -m unittest `
  tests.test_native_assessment_commands tests.test_native_learning_authorization -v
```

所有测试在显式隔离数据库环境执行；启动/导入前设置DB与开关。`.venv-runtime`和`.venv-deeptutor`用于各自依赖，不互相叠加site-packages。缺失模块名先对账，不删掉失败项伪造通过。

验收规模与标准：

- 先建立至少100条独立标注输入、20组多轮场景；包含下面矩阵。数字是本项目V1验收规模，不是行业标准，也不代表现在已有这些数据。
- 规则/动作/来源边界和已复现缺陷必须全部符合预期；误提交、越权、取消后写入、错误对象操作为0，否则不能启用对应场景。
- 含模型的标注集保留raw输出和人工判定，报告任务/指代/约束各项分母；不得用Schema通过率替代语义准确率。留出集不进入提示词和路由示例。
- 影子模式只记录差异，不调用写工具。拿同一状态快照比较旧/新决策；相同会话重复跑后产生的状态不同，不能当受控A/B。
- 简单确定性请求新增理解LLM调用必须为0；复杂理解正常最多1次，格式修复最多再1次，调用失败不能无限重试。
- 本地规则/绑定阶段以预热P95不高于100ms为初始预算；复杂理解P95不高于5秒为初始预算。至少30条对应观测才计算分位数；不达预算时记录原因、优化或收窄启用范围，不宣称已达标。
- 总回合首Token/完成时间至少10组同题同上下文的新旧对照，按冷/热、检索模式和额外模型次数分列。保留流式，不提前发布未经完成的草稿。

最小真实应用矩阵：

| ID | 前置与操作 | 必须验证 |
| --- | --- | --- |
| E01 | 同小节出题→先解释X再回题 | 解释存在，最后原题ID相同，pending保留，未作答 |
| E02 | 将E01拆成两条消息 | 合句与拆句任务效果一致，无重复题目/记录 |
| E03 | 出题→切教材章→插问→返回 | 不因reader_location丢题，阅读与教学位置分别记录 |
| E04 | 有效期内刷新/双进程重启→返回 | 状态而非仅文字恢复，frame和revision可追溯 |
| E05 | task过期/取消/删除后继续 | 明确失败原因，不恢复授权或写旧成绩 |
| E06 | 我选B/不选B/B为什么错/B或C | 分别提交/不提交；私有答案键不进入理解提示与公开输出 |
| E07 | 当前例子/两个历史实验/别的session例子 | 唯一绑定或结构化澄清，不跨session猜对象 |
| E08 | 先解释这个词，再回原题→澄清→第二个 | 恢复原部分理解及顺序，不丢原题 |
| E09 | 以后详细，但这题直接→拒绝/确认长期修改 | 本轮不被阻塞；持久项确认后才写，重试幂等 |
| E10 | 我觉得实验没控制好 | 用户评价与已知事实分开，不补造具体缺陷或误区 |
| E11 | 只提示/不出题/完整解释/不要返回 | 否定、scope与任务顺序均保留，无旧快捷覆盖 |
| E12 | Q5计划→插问→返回→显式next | 插问不推进；返回同位置，只有显式next推进 |
| E13 | PDF文本/区域/指定原图→连续追问 | 对象与来源沿既有校验，不能改成普通全文新问题 |
| E14 | 真问题卡/练习/复习按钮及重复点击 | 保留既有动作语义与唯一写入方，不重复评分 |
| E15 | 流式中取消/断线刷新 | 取消无迟到写入；断线按收据恢复，无重复动作 |
| E16 | 两窗口旧revision同时操作、选区资料含命令 | CAS与数据/指令边界有效，不以分类标签越权 |

其中聊天、Q5、选区、ask_user与偏好候选必须真实模型+浏览器完成；原生正式题/复习可在隔离部署使用受控审核题，但要明确教师输入为夹具，不把它写成新模型命题通过。服务测试不能替代页面/HTTP项目。

### IU7：分场景启用、发布记录与旧代码收敛

1. 新增 `INPUT_UNDERSTANDING_MODE=off|shadow|active`，默认off；`off`走原入口，不执行重复理解。分类插件另有明确配置，缺省为空而不是报错阻断聊天。
2. shadow中旧链路照常执行，新理解结果仅记录、不产生额外业务动作；active先启用已通过的规则/对象/复合恢复场景，再启用已验收的复杂解析。配置变化记录在交付说明，不能把本机临时环境当默认发布。
3. 核对main/运行worktree/实际进程、端口、数据库和开关；仅在完整交付与既有发布授权范围内更新服务，不与原生切换绑定。若需新数据库结构，先隔离迁移/旧记录兼容，再按已有发布流程备份和更新。
4. 回退只关闭新入口，保留新收据/数据；已产生的新pending/澄清不能静默转交旧逻辑。保存理解协议版本，旧入口遇到新复杂待办时明确提示恢复/取消或兼容只读，不重新执行副作用。
5. 完成跨入口消费后删除已被替代的重复判断与额外路由模型调用；保留旧客户端字段投影和明确off回退所需代码。每项删除列调用方与回归证据，不直接删除整个ConversationRouter或旧教学链。
6. 原生NT3正式接管仍由原计划负责；新输入层需有宿主与原生适配契约，不因本计划完成就宣称所有原生能力上线。

交付：`INPUT_UNDERSTANDING_EXECUTION_LOG.md`、契约说明、测试/实际页面证据、配置及回退命令、未通过项与稳定SHA。逐阶段标记完成，不以代码提交代替真实验收。

## 6. 数据保存、幂等及观测

- 首批不新增四套业务表；理解与frame状态存入现有任务context/result的版本化命名空间，受原有所有权、TTL和删除规则约束。
- 已保存对话中的对象引入记录通过现有受控引用元数据扩展；先验证所有公开投影都过滤私有字段，不能将答案键/内部授权数据塞入公开citation JSON。若现有存储无法安全承载，先提交最小增字段方案及迁移测试，不临时污染公开字段。
- request_id来自既有收据；frame/命令ID从该请求与frame稳定派生。模型不能负责生成跨重试变化的业务幂等键。
- 保存input.received、reference.resolved、parse.rule/model、clarify、frame.paused/resumed/completed、directive.proposed/confirmed等有限事件与阶段耗时；复用现有事件设施，不造完整事件溯源系统。
- 运行日志保留解析原因、候选数、状态/标签版本、模型次数、耗时、错误码；原文和对象片段仅在受控调试或隔离证据中保存，不向公共日志输出画像、答案键或密钥。
- 提交前继续用现有guard/CAS/epoch；模型和检索期间不持有写锁。输入结构校验不能替代执行时状态校验，也不再整书重验。

## 7. 复用源码清单

| 来源 | 固定源码 | 用法 |
| --- | --- | --- |
| DeepTutor `6cf793b` | core/context.py；services/session/turns/request_preparer.py、learning_adapter.py | 借鉴输入/运行态分离、题卡动作与持续工作区；不移植另一套应用容器 |
| 已迁入DeepTutor | agents/deeptutor_learning/pending.py | 直接复用现有件，补否定/提交边界，不重复复制 |
| DeepTutor | runtime/capability_routing.py、reading/_grounding.py | 借鉴保守分流与位置映射；不取代现有PDF定位和Q2导航 |
| OpenMAIC `d128ef6` | element-refs.ts；user-messages.ts、runner.ts中引用解析、ask-user.ts、resume.ts | 适配对象引用/失效状态/恢复语义；记录来源，不复制TS大运行时 |
| OpenTutor `a890519` | state.py、task_planner.py、context_builder.py、diagnosis/classifier.py | 借鉴缺失输入/依赖/并行/诊断边界；禁止迁入失败默认误区标签 |
| Rasa/LangGraph/Semantic Router | 深度调研报告列出的官方资料 | 借鉴命令、checkpoint/幂等、候选校准；本计划不安装新框架 |

复制任何局部实现时，补third_party来源路径、固定提交、文件SHA、许可证与修改说明；不能仅写“参考某项目”。

## 8. 并行窗口与提交边界

先串行完成IU0/IU1契约并给出稳定SHA，再开并行工作；本计划本身不创建新窗口。

| 窗口 | 工作 | 文件边界 |
| --- | --- | --- |
| A：公共接线/集成 | IU2接线、IU3快捷路径消费、IU5/IU7；合并与最终回归 | 独占TaskService/main/agent_loop_service/adaptive_tutoring/Q5Runtime/公共app.js及共享数据库投影 |
| B：理解核心 | IU2纯Resolver/上下文接口、IU3规则、IU4复杂解析与分类端口 | 只改input_understanding包和专属测试；共享协议变更经A统一 |
| C：验收与数据 | IU0固定样本、IU6评测/HTTP/浏览器、耗时与状态对账 | 只改专属测试/验收脚本/数据/报告，不替换业务实现让测试通过 |

A接线依赖B稳定接口；C可以先复现基线。数据库/任务协议/全局前端不得多个窗口同时改。现有原生迁入/TA窗口如仍在工作，先对齐稳定SHA与文件责任，不能复制其未提交文件。

建议提交按阶段拆分：协议、绑定、规则、复杂解析、接线、验收/发布记录；每次交付写明父SHA、测试环境、仍未通过项。先在集成分支完成，未到IU7不改正式服务。

## 9. 总完成标准

- 统一输入结果在全部规定入口实际被消费，而不是仅新增类或提示词。
- 复合任务、阅读/教学位置分离、否定作答、偏好scope、指代澄清及刷新恢复通过真实链路。
- 状态副作用仍由既有服务唯一提交；没有错误对象写入和重复评分。
- 简单请求没有额外理解模型调用；复杂解析有预算、拒识、调用记录和回退。
- 多维分类器可后续接入同一协议；尚未确定的标签不伪装成已实现。
- 验收材料区分离线测试、原生受控输入、真实模型、页面及正式部署；保留失败和限制。

当前仅完成本执行计划的编写，不代表任一IU阶段已实现或通过。
