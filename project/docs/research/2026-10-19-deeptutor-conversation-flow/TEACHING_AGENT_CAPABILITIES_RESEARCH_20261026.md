# 教学 Agent 能力调研与源码复用对照

日期：2026-10-26。任务：核对用户附件中的引导教学、分层提示、学习证据、偏好、复习与交互卡片，并形成实施依据。本轮只调研和编写文档，不声明功能已经接入或测试通过。

## 1. 调研结论

这些能力不是“多加几个工具”就能完成：需要教学策略、明确的题目状态、可信学习证据和页面交互共同工作。当前项目已有相当一部分基础，主要缺口是统一接线、证据语义和完整回合验收。

优先复用 DeepTutor 的学习模型、题目状态、学习服务与复习调度；沿用本项目偏好、练习提示、教材来源和页面组件。不要另建 Teaching Agent、AgentLoop、画像数据库或复习算法。

架构以主计划第21节的原生完整链路迁入为准。本调研是 NT3 学习能力及相关页面的细化，不恢复此前“永久保留旧Q3核心”的架构方向。

## 2. 成熟产品与公开实现分别能提供什么

| 来源 | 核实到的内容 | 复用判断 |
| --- | --- | --- |
| ChatGPT Study Mode | 官方描述苏格拉底提问、分步解释、检查理解、个性化和模式切换；初期通过定制系统指令实现，也承认行为仍可能不一致 | 借鉴交互原则；没有取得可直接迁入的完整产品源码或完整官方提示词 |
| Khanmigo | 官方强调引导发现、学习支持和教师工作流 | 借鉴提示与参与方式；本轮未取得其完整教学核心开源实现 |
| DeepTutor | 本地可审计学习模型、服务、题目工具、调度器、模式和提示块 | 本项目首选源码来源，按固定提交和现有许可证记录迁入 |
| OATutor | 开源自适应练习；README列出提示、脚手架问题和解答路径及对应React组件 | 可参考提示路径和展开交互；尚未完成组件源码逐行审计，不标为可直接复制的已验证组件 |
| pyBKT / pyKT | 可复用的知识追踪实现或模型评测工具 | 后续有足够标注作答数据时做离线对照；不是首批教学 Agent 的必需依赖 |

来源：[Study Mode官方说明](https://openai.com/index/chatgpt-study-mode/)、[Khanmigo官方](https://khanmigo.ai/)、[OATutor仓库](https://github.com/CAHLR/OATutor)、[pyBKT仓库](https://github.com/CAHLR/pyBKT)、[pyKT仓库](https://github.com/pykt-team/pykt-toolkit)。OATutor的代码许可为MIT，题目内容另按CC BY 4.0及逐项归属处理，不能混为同一许可。

MIT学习科学资料支持检索练习、间隔安排、交错练习和逐步撤除示范等方向，但不能据此宣称某个固定日程适用于所有学生或保证提分。参见[研究总结](https://openlearning.mit.edu/mit-faculty/research-based-learning-findings)、[间隔与交错练习](https://openlearning.mit.edu/mit-faculty/research-based-learning-findings/spaced-and-interleaved-practice)。

## 3. 当前项目实际已有的能力与缺口

以下路径相对 `project/integration/discrete-math-tutor/`。

| 能力 | 已有源码 | 实际边界与缺口 |
| --- | --- | --- |
| 教学策略 | `agents/teaching_policy.py::select_policy`、`agents/teaching_planner.py` | 已有规则和策略库；旧策略默认提问并避免完整答案，与用户明确要求直接解释可能冲突；旧Planner会额外调用模型，不能每轮再叠加 |
| 辅助自适应教学 | `agents/adaptive_tutoring.py::analyze_teaching_turn`、`agents/agent_loop_service.py` | 已有困难识别、换策略、辅助检查、证据复用；受入口与开关约束，不等于完整正式评估/复习系统 |
| 提示 | `frontend/practice.js` | 练习已有1—3级提示，完整解释另有动作；应接成三级提示加完整解答，不另做冲突编号 |
| 偏好 | `models/interaction_preferences.py`、`frontend/interaction-style.js` | 已有长度、例子、节奏、提问频率、先讲/先问及next/session/long作用范围；优先复用并检查新链路是否实际消费 |
| 学习证据 | `memory/evidence_policy.py`、现有Q5学习模型 | 已区分独立证据与辅助证据；辅助检查为ai_provisional，不应直接当正式掌握评分 |
| 学生信心 | `models/student_state.py::confidence` | 表示学生自评信心，不是系统对掌握估计的可信度；意图识别confidence也不能混用 |
| 学习路径 | Q5首批服务、适配器及既有设计 | 已有计划、位置与恢复基础；讲解、理解、自报和正式掌握仍须严格区分 |
| 复习 | `web_api.py`学生review入口、既有待反馈数据 | 已有薄弱项/待处理列表，不等于完整间隔复习；后台记忆worker不等于复习调度器 |
| 交互输出 | Markdown、KaTeX、练习/问题卡、教材链接、关系图能力 | 已有渲染基础；尚未核实存在统一的分步展开/概念对比/学习进度卡片协议，不应声称全部已有 |

辅助教学中的固定 `hints_used=1` 不足以表示真实帮助强度，需要从实际提示/解答事件派生。学生提问、求例子、看图、要求换种解释，不应被判为答错。

## 4. DeepTutor 具体复用边界

审计来源：`D:/deeptutor/deeptutor/`，固定提交 `6cf793bd868ba5ecbe64722936d4be8fab5a01df`。现有vendor、来源台账与Apache-2.0登记继续沿用。上游工作区的LLM工厂本地补丁应与已登记补丁区分，不能当未修改原版。

| 源码 | 可以复用的职责 | 必须适配的部分 |
| --- | --- | --- |
| `learning/models.py` | LearningEvidence、待答题和交互模型 | 对接本项目学生/会话/任务、教材发布身份和来源；不能依靠模型忽略未知字段来保存新字段 |
| `learning/service.py`、`learning/storage.py` | 学习命令、记录作答、学习状态事务、revision及租约机制 | 原生学习库与现有Q5迁移/投影；只保留一个写入方，不能双方各推进一次 |
| `learning/policy.py` | 知识类型、证据与掌握规则分层 | 上游阈值是产品默认值；心理学概念与设计题需要rubric/教师校核，不能宣传为普适科学阈值 |
| `learning/scheduler.py` | RetentionScheduler、SpacedRepetitionScheduler、复习队列及原因 | 接现有学生身份、时间、证据和应用内待复习入口；生产环境禁用调试时间缩放 |
| `capabilities/mastery/tools.py` | 出题、作答评估、跳过、纠错、延后等状态动作 | Q2来源、可信答案键、视觉任务与页面题卡；先核对现有迁入模块，避免再次复制同一套 |
| `capabilities/mastery/mode.py`及pipeline/capability | outline/study/review生命周期与工具挂载 | 与直接讲解/引导/练习/备考的教学风格分开，不能用新枚举覆盖生命周期模式 |
| `agents/loop/prompt_blocks.py` | 画像、记忆、技能与上下文按需组装 | 注入现有偏好及可信证据，控制提示长度；不每轮加载完整画像/全部技能 |

原生存储包括SQLite学习库，不能笼统描述为“只需复制JSON”。迁移、备份和撤回策略沿用原生完整迁入计划。

## 5. 应补充到计划的核心内容

1. **教学决策统一**：当前显式要求优先；规则选择策略，模型执行讲解。简单查页/查目录不跑教学评估，不每轮增加一次规划模型调用。
2. **四种教学风格**：直接讲解、引导探索、分步练习、备考复习。备考重点要注明教材、考纲/教师标注或教学建议的依据，不能从图谱中心性推断考试分值。
3. **提示与证据关联**：记录实际获得的提示和完整解答；被辅助后答对不能直接视为独立掌握；不强制用户逐级点完才能看解释。
4. **可解释学习状态**：区分讲过、练过、独立答对、自报理解、待复习及正式掌握；误解记录先做可追溯假设，学生纠正后可撤销。
5. **分清三种confidence**：自评信心、模型判断把握、经过验证的掌握估计可信度。没有校准数据时显示证据不足/暂定，不生成貌似准确的概率。
6. **复习真正接到对话**：应用内队列与复习原因、延后和完成回执；不借此新增外发通知或要求记忆worker一直运行。
7. **有限交互卡片**：复用现有题卡，增量补分步展开、概念对比、进度卡；每个动作到达同一服务端状态机。

## 6. 本轮证据限度

已阅读附件、对照本地相关实现与DeepTutor源码，并核对上述官方资料与开源项目README。本轮没有部署、迁移数据库、训练知识追踪模型、运行真实教学回合或做教师效果实验。OATutor组件源码和pyBKT/pyKT完整依赖尚未做迁入审计；这些仅为后续候选，不计入可直接复制交付。

实施步骤见 [教学能力实施计划](TEACHING_AGENT_CAPABILITIES_IMPLEMENTATION_PLAN_20261026.md)。
