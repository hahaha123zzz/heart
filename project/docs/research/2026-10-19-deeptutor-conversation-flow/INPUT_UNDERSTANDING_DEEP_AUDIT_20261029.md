# 输入理解层深度调研：完整请求、真实对话与多项目对照

日期：2026-10-29。本文补充并优先于同日 `INPUT_UNDERSTANDING_CLASSIFIER_RESEARCH_20261029.md` 的初步判断。性质：研究结论与设计建议，未接入新的业务模块。

后续执行计划见 [INPUT_UNDERSTANDING_IMPLEMENTATION_PLAN_20261029.md](INPUT_UNDERSTANDING_IMPLEMENTATION_PLAN_20261029.md)，所有IU阶段初始为未执行，不将本报告的调研验证算作功能交付。

## 一、结论

需要补输入理解能力，但不应新建独立的执行框架。真正的缺口是：**统一原话与输入对象、区分阅读位置和活动教学任务、解析复合请求顺序、统一作用范围、使所有入口消费同一结果**。分类标签本身不能解决这些问题。

推荐将用户给出的“输入理解层 V1.0”作为目标设计基础，并修正三点：

1. GroundedTurn 分阶段构造：可信对象与任务骨架先形成，分类器只补语义字段，服务端再决定允许执行的命令。
2. 不增加第二套学习状态和写入方；TaskService、Q5、原生题目/测评/复习继续拥有各自状态。
3. 简单明确输入不新增 LLM；复杂理解与分类尽量共用一次受限结构化调用。BGE 仅用于候选，不负责判断答题提交或长期偏好写入。

这次最直接的证据不是纯函数结果：**真实浏览器已复现“先解释，再回原题”被快捷规则截断；阅读位置改变还会让待答状态消失，即使模型仍能复述旧题。**

## 二、研究范围与证据等级

### 2.1 实际核查与运行

| 范围 | 本轮做了什么 | 能证明什么 |
| --- | --- | --- |
| 附件 | 重新按章节核对整份《输入理解层 V1.0 完整技术方案》 | 下文逐项映射，不只沿用 DeepTutor 的结构 |
| 当前项目 | 跟踪页面载荷→ChatRequest→TaskService→Q5/Q3/旧路由→教学判断→模型/工具→持久化 | 找到会绕过旧路由的实际路径与状态变化位置 |
| 完整宿主应用 | 隔离 8147，实际 main.app、真实 DeepSeek、真实本地检索/已有 LightRAG 配置、独立 SQLite | 19 轮直接 HTTP/SSE、7 轮浏览器聊天，保留输入、输出、阶段调用与状态证据 |
| 浏览器 | 可见 Edge，实际教材阅读与聊天界面，两组各有刷新恢复 | 复合请求缺失在页面也发生；两组均无 pageerror，末轮历史刷新恢复 |
| 原生测评 | 10 项现有集成测试重跑，真实临时 SQLite、原生服务/受控命令 | 验证原生幂等、作答、帮助、评分等边界；模型、教师及部分授权输入为夹具，不计为真实模型或页面验收 |
| 理解原型 | 6 条真实模型受限结构化解析实验，只记录，不执行 | 验证一次解析可表达顺序/拒提交/歧义；也暴露词表不固定时字段不一致 |
| 外部项目 | DeepTutor、OpenMAIC、OpenTutor 本地源码；Rasa/LangGraph/Semantic Router/DeepSeek 官方资料 | 说明各机制如何工作、哪些能复用；没有宣称这些外部完整应用均真实启动通过 |

### 2.2 基线和环境

- 主项目本地 HEAD：`c701670`。被测进程直接加载当前工作树，包含其他窗口已有未提交的教学/复习/协议处理改动；不是“纯 c701670 提交树验收”。相关文件 SHA 留存在 `deep-summary.json`，本轮未改业务文件。
- 收尾时其他窗口已提交 TA5，main 推进到 `7439ba5`；再次核对本报告记录的21份源码/附件 SHA，全部未变。该提交收录了此前部分未提交代码，但本轮没有重跑一个独立的完整7439ba5部署验收。时间线与端口停止证明见 `closeout.json`。
- 之前部署工作树 `.worktrees/integration-main-20261025` HEAD 仍为 `3a0b0fb`。本次没有将其更新，也未把该历史部署信息当成当前主分支能力。本轮初始监听检查未发现 8000/8137 的监听；未对它们执行启动或停止。
- 8147 使用 `.runtime/fixed-book-speed-20261025/standalone-venv`，加载已有私有模型配置，但 DB 显式覆盖为本轮 `deep-legacy.sqlite3` / `deep-course.sqlite3`。
- `LOCAL_AGENT_LOOP_ENABLED=1`、`Q5_LEARNING_ENABLED=1`、`ADAPTIVE_TUTORING_ENABLED=1`；原生正式写入/同步关闭。模型非 mock，未替换检索返回或回答发布函数。
- 观测包装只记录边界调用和返回值，不修改原方法结果。19 轮直接 HTTP 和 7 轮页面请求中的 `ConversationRouter.route` 实际调用总数为 **0**。
- 本轮重用预建教材索引/候选，不重建图谱；所有新学生、题目和计划均在本轮隔离数据中。

外部源码版本：DeepTutor `6cf793bd868ba5ecbe64722936d4be8fab5a01df`；OpenMAIC `d128ef67c920571a86ce8a7c0430185689ab3d45`；OpenTutor `a890519f3632efa14cf24449b366b3b9d901eecf`。本地代码结论不外推到它们未核查的版本。

## 三、真实对话发现：完成状态不等于语义任务完成

### 3.1 已实证的复合任务截断

前置：在第二章第二节请求一道 A/B/C 题，系统登记真实辅助待答题。

输入：`先解释“操作性定义”这个词，再回到原来的题，不要替我作答。`

- HTTP：0.086 秒，`answered`；输出只有“原来的小检查是……”及旧题；没有解释操作性定义。
- 同小节浏览器：0.123 秒，`answered`；可见页面同样仅重显旧题。
- 两次调用轨迹都显示无理解 JSON 调用、无回答模型调用；`turn_move=resume_check`。
- 对照：拆成单独“请解释……”可得到解释（同小节页面 4.326 秒）；再单独“回到原题”可恢复（0.118 秒）。

根因链：

```text
TaskService 构建保留待答题的上下文
  → TeachingTurn.__init__ 检测 RESUME_CHECK.search(整句话)
  → 命中后直接 show_pending / resume_check，未表示“先解释”子任务
  → run_agent_loop_turn 调用 restore_reply()
  → 持久题干直接重放，跳过 AgentLoop 模型轮
```

因此，单纯增强大模型或多维分类准确率不会修好这一条：模型根本没收到执行机会。应在快捷动作前先判断请求是否为单一恢复动作；复合输入需要保留 explain→resume 的依赖关系。

源码：`agents/adaptive_tutoring.py::RESUME_CHECK / TeachingTurn.__init__ / restore_reply`；`agents/agent_loop_service.py::run_agent_loop_turn`。

### 3.2 阅读位置会替换教学上下文，历史文字掩盖了状态丢失

第一次浏览器复用 HTTP 的第二章题目会话，但页面刚打开时教材停在第一章。

- 页面自动发出 `reader_location={chapter_id:1,section_id:1}` 与第一章 `learning_goal`，尽管用户只要求解释后回到原题，没有说要切换教学目标。
- `snapshot_from_recent` 发现旧教学章与当前 reader_location 章不同，返回只含偏好与画像的缩减快照；原待答题不再进入 TeachingTurn。
- 同一句复合请求这时反而得到了模型解释及旧题复述，看起来成功；但返回 `teaching.pending_check=null`，内部当前教学目标是第一章。
- 这不是一次真正的“正确恢复题目”：历史文字仍在，题目状态已丢。
- 第二次在页面实际点击第二章第二节、先重新出题，再测试相同复合请求，便稳定复现上一节的截断。

根因不在会话 ID 串线。两次页面会话身份都已核对；差别在请求把“当前看到哪里”同时当成“当前在学什么”。

建议：阅读位置默认只作背景/检索偏好；有效待答任务仍拥有自己的目标。只有用户明确换题/换目标，或显式选区动作指向另一个对象时，才改变本轮任务对象。改变阅读页不能静默销毁待答题。

源码：`frontend/app.js` 的聊天 payload 构造；`TaskService._read_context`；`adaptive_tutoring.snapshot_from_recent`。

### 3.3 否定作答：完整链路没有复现纯函数推导的误评分

同一真实待答题下：

| 输入 | 完整链路实际行为 | 结论 |
| --- | --- | --- |
| 为什么 B 不对？我是在问选项，不是提交答案。 | 解释选项，保留同一 pending，辅助作答记录仍0 | 已有问句保护有效，但回答直接透露B正确，这是教学策略问题，不能混同提交评分 |
| 我不选 B。 | 进行一次辅助判断 JSON；判为 question，未增加作答，保留 pending | 本轮完整链路没有误提交；之前“可提交B”只是选项纯函数风险 |
| 我选 B。 | 实际得到正确反馈，`turn_move=answer`，`formal_mastery=false` | 辅助作答通路可用，不能因此说正式掌握评分已统一 |

需要统一输入协议的原因仍成立：同一个否定选择目前要依靠下游辅助判断模型兜底。不能让未来分类器只调用 `resolve_choice_submission` 后直接执行正式命令。

### 3.4 “刚才那个例子”能回答，但还不是可靠对象绑定

- 相同会话的例子追问 2.493 秒，模型正确沿用了背景音乐/背单词示例。
- 该轮没有独立 example 对象 ID；是模型读取历史文字完成的，不是 ReferenceResolver 已实现。
- 同一学生不同 session 询问“刚才那个例子”，没有泄露另一 session 的例子，返回文字询问具体对象。
- 但后者 `answer_status=answered`，没有 ask_user/pending_clarification 对象。不能等同于已验证结构化多轮消歧恢复。

新增对象引用应优先绑定持久化 conversation_id + 已保存片段/版本，不给每次重读的同一例子重新生成身份，也不把自由生成的 UUID 当作事实来源。

### 3.5 偏好范围没有形成可执行的两个独立请求

输入：`以后详细一点，但这一题直接给答案：自变量和因变量有什么区别？`

- 1.767 秒，完成了当轮比较。
- 没有生成“长期详细度修改”的待确认动作；隔离库该学生没有持久化 learner_profiles 偏好记录。
- 不应为此直接自动保存长期偏好；现有确认要求仍应保留。缺的是识别并展示“长期偏好候选 + 本题要求”两个不同作用范围。

### 3.6 Q5 插问没有移动位置，但不能声称完全没有状态变化

真实生成20分钟、零基础、变量主题、只讲不测的本次安排：生成4.934秒，确认1.906秒，插问信度3.233秒，返回2.585秒。

三次持久化快照的 `current_item_id` 相同；revision 依次是 **2→3→4**。因此证据支持“没有推进到下个活动”，不支持“插问完全不改状态/revision”。

这里的插问原句以“先解释一下信度，再继续……”开头；现有 `question_interjection` 主要匹配整句解释问法及显式章节/图号，难以稳定表示复合插问。统一解析应给下游明确的 interjection/resume 任务关系，而不是继续扩大多个分支的正则。

### 3.7 用户评价可能被过早认可

输入：`我觉得刚才那个背景音乐实验没控制好。`

回答开头是“你抓得很准。这个例子里确实有没管住的地方”，后文才用“如果还在不同房间、不同时间……”提出条件性可能。

这没有形成一条正式误区或评分证据，但与附件的要求存在差距：**先区分用户的评价、自报疑问、已给事实和待核实缺口，再讨论可能的问题。** 不能把后文假设升级成已确认缺陷。该样本不能证明模型每次都会犯同样错误，也不据此计算分类准确率。

## 四、DeepTutor 的完整入口怎么做

这次不只查看 context/pending 四个文件，而是追到 `services/session/turns/request_preparer.py`、`executor.py`、`learning_adapter.py`、`runtime/orchestrator.py` 和 mastery pipeline/loop。

### 4.1 从消息到执行

1. **准备请求与工作区**：读取会话偏好、课程、workspace_mode；先确定工作区承诺，再判断是否允许显式 quiz 路由。自动路由不应把持久偏好改成临时选择。
2. **验证输入与访问范围**：能力配置、模型授权、工具白名单、教材/阅读引用在准备阶段收敛；不能让后面的语义判断随意改变允许的动作。
3. **绑定父子选区会话**：`selection_tutor_context` 验证真实选区与父 session，禁止自己成为父节点；必要的父工作区信息经服务端继承。不是只加一个无校验的 branch_id。
4. **结构化题卡答案**：题卡携带 question_id/text 等专门载荷；有受管路径时先提交真实答案，再开始模型回合。executor 对可判定题卡调用同一个 MasteryGradeTool，结果作为上下文种子，后续重复工具调用读取已提交结果。
5. **组装上下文**：UnifiedContext 包含历史、来源清单、侧栏上下文、技能清单和显式引用；TurnRuntimeContext 保存模型历史和运行回调。用户原话与附加资料分别组织。
6. **能力与工具循环**：mastery 的模块按路径/模式挂载工具；工具执行与状态存储才是权威，不由一个粗意图标签直接写掌握。

### 4.2 值得直接借用的判断

- 题卡点击已经给了稳定对象和动作，应优先走确定性提交，而不是把“B”交给通用分类模型重猜。
- 工作区/待答题是一种持续承诺；临时查看别处或一次问答不自动离开它。
- 对模型可见的是当前公开待答题与来源清单；答案键和授权状态留在服务端。
- 原生 mastery 将资料清单与按需 read_source 分开，不为每一句都强制整套资料探索。这有利于保持新增理解层轻量。

### 4.3 不应夸大的地方

- 没发现附件描述的完整 GroundedTurn + 通用 ReferenceResolver + 多维教学分类器可整体复制的实现。DeepTutor 同样通过协议、路径状态、局部规则、工具和模型协作。
- `capability_routing.py` 只是一项保守的显式题集路由，不是通用中文输入理解器。
- 单独的 `pending.py` 已迁入本项目，不应再次复制。原生题卡通路与宿主辅助小检查也不是同一个东西，需要适配统一输入结果，不能混用成绩含义。
- 本轮未启动 D 盘完整 DeepTutor 并让它对同一套题实际作答；其比较结论来自完整相关源码追踪，而不是未经运行的速度或质量胜负声明。

## 五、其他项目与方案逐项对照

### 5.1 OpenMAIC：对象引用比自然语言改写更值得迁入

源码：`lib/workbench/element-refs.ts`、`lib/server/agent-runtime/{user-messages,runner,ask-user,resume}.ts`。

- 事件中的 elementRefs/courseRefs 和文字一起保存；投影遗漏引用时从权威事件恢复。
- `resolveElementRefsForContext` 不仅返回“找到/没找到”，还区分 resolved、stage-mismatch、scene-missing、element-missing、unverified。
- 对失效/跨课程对象明确提示不要猜测；附带的用户快照是 untrusted data，不能充当系统指令或真实当前对象。
- ask_user 结束本轮；恢复逻辑遇到已成功发出的问题，不自动继续替用户回答。无结果的工具调用可重发，因此副作用需要幂等。

适配方向：为教材块、插图、题目、示例/回答片段增加同样的稳定引用、失效状态与来源依据。**借鉴数据协议和局部校验，不复制庞大的 TS runner 及其 PostgreSQL/课程编辑依赖。** 本项目已有任务恢复，优先复用。

### 5.2 OpenTutor：分类、上下文、规划和错误诊断分工明确，但不能照搬

本地 `apps/api/services/agent/router.py` 实际采用四类粗路由：layout/plan/learn/general；规则命中后直接返回，未命中 GENERAL，无 LLM fallback。主要匹配英文。它不是适合直接替换本项目的中文多维分类器。

`orchestrator.py` 的实际流程包括：构建上下文→解析澄清输入；显式 GUIDED_SESSION 信封先走专门处理；普通请求再做路由、上下文加载和增强；复杂请求可生成/保存多步计划并发出 plan_step。

可参考的具体模块：

| 源码 | 有价值的机制 | 本项目适配与限制 |
| --- | --- | --- |
| agent/state.py | AgentContext / InputRequirement 结构化描述状态和缺失输入 | 可借鉴缺失信息的声明，不替换 TaskContext |
| agent/context_builder.py | 偏好、记忆、RAG可并发，各用独立 DB session | 本项目已部分并行；共享 AsyncSession 不能直接并发复用 |
| agent/task_planner.py | PlanStep 有步骤、输入和 depends_on，复杂目标持久化 | 借鉴“任务关系”；当前规划偏备考/活动编排，不等于短句指代理解 |
| agent/guided_session_handler.py | 显式 start/resume/pause 信封；阶段状态不靠自然语言反复猜 | 本项目可强化按钮/显式动作协议，但不接受用户自由伪造任务身份 |
| diagnosis/classifier.py | 已有题干、参考答案、学生答案和题目元数据后，生成错误类型+证据 | 这是作答后的诊断，不能移到所有用户消息的入口 |

不建议复制的部分：

- 错误诊断失败时默认 conceptual/confidence0.3；对本项目应为 unknown/unavailable，不能在失败时给学生贴概念错误标签。
- task_planner 的归一化/default 并不等于严格语义校验；本项目仍要校验动作、依赖环、对象和权限。
- 引导流程会替换 ctx.user_message 为阶段提示；本项目必须另外保留原始用户输入，不能拿阶段提示当学生作答证据。
- 不移植回答 verifier/reflection 等串行重生成机制，以免恢复用户已要求去掉的延迟与草稿撤回问题。

OpenMAIC 与 OpenTutor 本地 LICENSE 均为 MIT；DeepTutor 为 Apache-2.0。后续真正复制代码时需记录文件 SHA、许可和改动，不能把整个仓库许可证当成所有外部依赖都无额外限制。

### 5.3 Rasa CALM：借鉴“理解输出命令”，而不是先分一个大类

官方材料说明，CommandGenerator 结合会话状态、活动流程和槽位产生 StartFlow/SetSlot/CorrectSlot/Clarify 等受限命令；无效生成不会直接执行。这里最有价值的是把“说了什么”与“可以做什么”分开。[Rasa Dialogue Understanding](https://learning.rasa.com/rasa-pro/dialogue-understanding/)、[Rasa 官方命令生成模型说明](https://huggingface.co/rasa/cmd_gen_codellama_13b_calm_demo?library=transformers)。

本项目可用有限命令表达：解释指定对象、暂停/返回待答题、提出偏好修改、澄清目标；交给现有服务验证与执行。无需为此安装整个 Rasa Pro 或更换运行时，也不将其商业组件视为可直接复制的开源代码。

### 5.4 LangGraph：恢复时要保留执行边界，不能只保存自然语言总结

官方文档要求持久化 checkpoint 和稳定 thread_id；恢复时节点可能从头运行，中断之前的副作用须幂等。这支持附件的“关键事件+当前快照”，也解释了为什么仅将原题写入对话历史不算可靠恢复。[LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)。

本项目已有任务收据、loop_state、revision、原生 interaction；应扩展其存储部分理解与未完成子任务，而不是再引入一套 LangGraph 状态所有者。

### 5.5 Semantic Router：语义候选可以复用，置信度不能直接照搬

官方当前文档区分向量路由、决策模型、顺序回退 Chain 和融合 Merge；有阈值、校准与评测机制。未经校准的相似度不是正确概率；最新 v1 与0.x有接口差异，不能直接抄旧安装示例。[Semantic Router Routers](https://docs.aurelio.ai/docs/semantic-router/v1/user-guide/components/routers)、[版本与组件说明](https://docs.aurelio.ai/docs/semantic-router/v1/get-started/introduction)。

建议先复用已有中文 BGE 做候选对照；标签示例向量预计算，缓存绑定标签版本。规则先排除不能提交的动作，再比较语义；不让“我选B/我不选B”的高相似度决定评分。若未来引库，先证明它在本项目标注集上有收益，再固定版本。

### 5.6 DeepSeek 结构化输出：附件方向正确，当前 SDK 用法尚不相同

当前 `LLMClient.chat_json` 是普通 chat 后 extract_json/Pydantic，并不等于已经启用 provider 的 JSON Schema 强约束。官方 Chat Completions 提供 json_object；JSON 合法性仍不代表教材 ID、用户约束和业务状态正确。[DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)。

本轮6条原型实验用的是现有客户端，没有顺便更换正式模型接口。后续如采用 strict/Responses Schema，应独立验证所用模型、端点与网关，不凭“OpenAI兼容”推断支持。

## 六、回到附件：各部分采用、调整还是后移

| 附件内容 | 判断 | 结合当前项目的落点 |
| --- | --- | --- |
| 状态优先理解 | 采用，最高优先级 | 当前待答/澄清/计划绑定优先；阅读位置不是隐式切任务指令 |
| 安全规范化 | 采用 | 原话不可覆盖；保留否定、公式、数字和字符依据；OCR纠错先给候选 |
| ContextHeader + 按需展开 | 采用并改造 | 先读服务端状态摘要，必要时展开原 _context；不要再重复拉一份全量画像/历史 |
| ReferenceResolver | 必须补，但不是另造教材库 | 统一 Q2 SourceRef、TaskObject、游标、原生interaction；例子/回答片段补真实持久来源 |
| 多任务 TaskFrame / 依赖 | 采用，小规模开始 | 覆盖解释→返回、偏好候选+当轮解释、不同对象的顺序动作；普通“比较并举例”不拆成多Agent |
| GroundedTurn | 采用分阶段协议 | raw/envelope→bound references/tasks→semantic annotations→validated execution，不要求每个模块完整理解一次 |
| BGE候选 + DeepSeek升级 | 做可替换接口，先影子评测 | 明确任务0新增LLM；复杂理解+标签同次调用；低确定度允许unknown |
| 四张新表 | 不直接照建 | 优先借用现有任务快照/收据/原生记录；跨任务引用检索或独立分支确有需求时才建相应存储 |
| 关键事件与快照 | 采用最小实现 | 保留 reference.bound、clarification、task.paused/resumed、偏好确认等；不是重建完整事件溯源框架 |
| 主/侧分支隔离 | 需要设计真实父子关系和授权 | 当前tabSessionId不是完整分支模型；不能把图形侧栏误当独立对话 |
| Pydantic / 命令校验 | 保留并集中 | 字段校验+真实ID+约束+CAS；不是恢复昂贵回答门禁 |
| 500—800样本、50—100多轮 | 可作后续规模建议 | 先覆盖本轮已证实的边界；数字不是已验证行业标准，不宣称本轮达到此规模 |
| QReCC / MathDial | 后续评测参考 | 不作为现成输入层或必须安装的分类器；本轮未下载/实测其数据集 |

## 七、原型实验：一次模型解析可表达任务，但自由字段还不稳定

实验代码 `shadow_cases.py` 只存在 `.runtime`；不执行模型输出、不接正式业务。候选包括真实待答题及明确标注的受控实验对象；模型看不到 expected 字段。

| 样本 | 耗时 | 实际输出与限制 |
| --- | --- | --- |
| 解释后返回 | 2.485秒 | explain→resume，依赖保留，绑定真实题目ID，不提交答案 |
| 我不选B | 1.197秒 | 不提交，保留未给出有效选择 |
| 长期详细+本题直接 | 0.863秒 | 提取persistent与turn两类要求；预定校验期待question，作用范围粒度尚不一致 |
| 两个实验无唯一指代 | 1.161秒 | 请求澄清，不随意绑定一个对象 |
| 实验控制评价 | 1.539秒 | 保留具体问题未知，但有过度澄清倾向；不一定必须中断用户才能讨论 |
| 只提示不出题 | 1.211秒 | 表达hint与禁止出题，但输出no_question而非预定no_questions键 |

6条通过了结构、候选ID、依赖顺序和引文真实性检查；固定的6项机械预期中4项命中、2项未命中。两项差异部分来自原型协议没有锁定键名/作用范围语义，不能将4/6包装为通用分类准确率，也不能把语义近似等同于可执行契约。

另一个重要问题：原型 action=`answer` 同时可表示“给用户答案”和“提交学生答案”，但 commit_answer=false。这种歧义在真实写入前必须消除，改用不同动作命名；不能只相信一项布尔标志。

最初试验脚本意外把预期名称也放入模型输入，该运行已排除，保留为 `shadow-with-expectation-invalid.*`；上述数字全部来自修正后不发送预期的重新运行。不是把旧结果覆盖成通过。

结论：复杂句升级一次结构化理解有可行性，但不能所有消息都走它。以上延迟是小样本单次观察，不是P95、不含真实执行，也不证明接入后全回合一定更快。

## 八、建议的职责和接口

```text
用户文字 / 选区 / 显式按钮 / 题卡作答
  → 原始 InputEnvelope（保留raw，服务端身份）
  → 当前状态摘要 + 必要上下文展开
  → 真实对象绑定 + 规则/必要时模型任务解析
  → 多维分类只补未确定语义字段
  → 最终校验、产生有限执行命令
  → 已有计划 / Q3 / 练习 / 原生测评与复习服务
```

### 8.1 稳定核心

- 对象字段：mention、类型、真实ID/候选ID、绑定状态、来源、引入轮次、教材/题目版本、绑定理由。不把分类相似度写成绑定事实。
- 任务字段：明确动作、target_ref、新查询文字、约束、顺序/依赖、暂停/恢复对象。限制数量、检查环和冲突，不先引入通用工作流引擎。
- 作用范围：turn、question、session_plan、session、persistent，采用有版本的封闭核心词表。长期修改输出 proposed change，再走现有确认。
- 分类：ontology_version、各维度值、rule/model来源、原话依据、unknown/abstain；标签词表与实现解耦，但核心执行约束不能任意自由命名。
- 版本：保留task/path/interaction/session-plan各自的revision与epoch，不虚构一个能代替所有存储CAS的全局session_version。

### 8.2 分类维度还没定，不宜先写死标签

可先讨论“用户行为/任务意图、希望的认知活动、自报困难、教学呈现要求”四组。需要分清：

- 评价实验是请求行为/认知要求，不代表已发现确定的实验错误。
- “我不会”是自报困难线索，不是已经诊断出的误区或低掌握分。
- “我懂了”是自报理解，不是答题证据。
- 教材概念类型 memory/procedure/concept/design 来自目标定义，不由用户一句话随意改写。
- 教学策略和权限是下游决策，不能用分类标签直接授权写入。

### 8.3 接线位置

统一理解应位于请求重放/待澄清恢复之后、Q5与聊天分流之前，但需要先取得可信状态摘要。大上下文按需展开，复用已有解析过的对象。

Q3、选区、旧Orchestrator和专用练习通过适配消费同一协议；随后逐步停止各处重复猜同一字段。只加提示词、不改变旧快捷规则消费方式，无法修复本轮截断。

显式题卡/复习按钮继续走强类型动作接口，不额外调用分类器；把这些入口的身份、状态和事件映射到相同上下文投影即可。

## 九、实施前必须固定的验收

1. 同一小节、有真实待答题时“先解释X再回题”两项都完成；拆句与合句效果一致；模型没有替学生提交答案。
2. 只改变阅读位置不静默删除待答题；刷新后文字、interaction ID、pending和返回点一致，不能只核对显示内容。
3. 我选B/我不选B/B为什么错/B或C、同一题/过期题/跨会话题分别验证；题卡与自由文本都覆盖。
4. 真实选区/图号/待答题冲突时按明确输入及动作语义决定，不写一个永远固定的全局优先级。
5. 同时提出长期偏好与本题要求，保留两者；长期项必须确认；确认恢复不重复写。
6. 例子/实验有多个候选时不猜；没有真实对象注册时不得声称已确定某个ID。
7. 新分类器影子运行期间不写成绩、掌握、计划位置或偏好；同一结果经过不同执行入口语义一致。
8. 统计任务完整率、指代正确率、否定/约束保留、状态恢复正确率、误提交数、额外LLM次数与分阶段耗时。answer_status=answered不足以作为通过依据。

建议三批：先协议/状态优先与已复现缺口→再复杂任务解析及分类接口→最后标签校准、跨入口联合验收和逐场景启用。两部分一起设计、分步开发；分类器不另做一遍对象消歧。

## 十、证据、限制与本轮改动边界

证据目录：`E:\项目\heart\.runtime\input-understanding-audit-20261029`。

- `http-results.json`：16轮初始HTTP，每轮含前后SQLite任务/计划快照、真实SSE与结果。
- `extra-http-results.json`：3轮追加HTTP，含明确作答与评价讨论。追加否定返回样本发生在旧会话已被第一组浏览器换章之后，不作为“有待答题时否定恢复”的有效对照。
- `deep-trace.jsonl`：完整边界调用记录；`deep-summary.json`：26轮宿主请求汇总、源码SHA、模型调用及状态核对。
- `browser-results.json`：第一组3轮，记录阅读位置导致待答状态丢失；`browser-same-reader-results.json`：第二组4轮，同小节复现与拆句对照；对应PNG截图已检查。
- `native-commands-tests.log`：10项通过，60.705秒；真实隔离存储和服务，不是新真实模型验收。
- `shadow-results.json`：6条不执行的模型解析实验；错误试验独立保留。
- `serve_deep.py`、`http_cases.py`、`extra_http.py`、`summarize_deep.py`：本轮隔离与观测脚本；浏览器脚本位于系统Temp。
- `closeout.json`：收尾 HEAD、记录过的源码 SHA 未变化、8147端口已停止；服务日志显示全部存储正常finalize并完成shutdown。

联网资料读取：按 agent-reach 网页路由尝试 Jina；Windows curl 的 schannel 凭据错误使其失败，随后用现有网页工具读取上述官方一手资料。agent-reach CLI 不在PATH，未完成其版本检查；不影响已读取的官方资料。没有为研究安装新依赖。

本轮未修改业务代码、正式DB或私有模型配置，未合并/推送；8147仅为本轮临时隔离服务，收尾停止。未对外部三套完整应用做同题端到端模型对照，未进行大规模人工标注、多进程并发、完整父子侧栏或长期学习效果验收。新的输入层与分类器仍未实现，以上是有运行证据的设计依据。
