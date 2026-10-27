# TA0：基线与状态写入契约

日期：2026-10-27。状态：收尾验收中；本文件按原计划TA0四项范围执行，不将NT3正式迁移或TA1—TA5算作TA0完成条件。

## 1. 范围纠正

原计划TA0标题是“固定当前基线和写入契约”。它要求记录身份/入口/状态归属与基线，并明确：原生尚未稳定时可先完成协议设计、暂停公共入口接线。

此前进度表将原生正式单写入、完整删除及回退列成TA0的全部剩余完成条件，混入了NT3/NT8和后续教学阶段。本轮按原文收尾，不以此宣布原生迁入或正式评分已完成。已有隔离迁移/授权/工厂/路径交接候选保留，仅固定为后续可复核的代码检查点。

## 2. 基线、运行身份和依赖

- 进入TA0时HEAD、本地main、缓存origin/main均为 `3b212250f774d2f461fb1676fd4bf2acd23bc475`。
- 本轮通过既有本机代理执行 `git ls-remote --heads origin main`，远端main核实为同一SHA。第一次TLS探测失败，代理重试成功；没有把缓存ref当作实时远端结果。
- 8000和18001均未监听；当前没有可声明版本的正式运行进程。旧发布记录中的PID、健康或模型结果不能证明此刻服务在线。
- 当前工作区包含此前教学提示/原生隔离候选的未提交源码及大量其他教材删除、运行产物、worker/.env.example改动。检查点只收本会话候选与TA0文件，不提交教材、密钥、库、.runtime及其他窗口改动。
- 宿主使用 `.venv-runtime`；完整原生验证使用 `.venv-deeptutor`。宿主环境缺完整原生依赖是进程边界，不是允许回退到无授权写入的理由。
- 固定vendor提交 `6cf793bd868ba5ecbe64722936d4be8fab5a01df`；应用/循环/存储原码与本地适配必须分开。`agents/deeptutor_learning` 是已迁入的纯类型/策略/待答模型，不能因类名相同就宣称完整DeepTutor应用在执行。

## 3. 五类输入：当前事实与未来写入权

机器可检验清单见 [TA0_STATE_OWNERSHIP.json](TA0_STATE_OWNERSHIP.json)。其中current和after_cutover是两个互斥阶段，不允许同时启用；after_cutover是未来契约，不是现状。

| 输入 | 当前读取/执行 | 事件产生 | 当前唯一写入方 | 原生交接边界 |
| --- | --- | --- | --- | --- |
| 普通聊天 | main.chat/chat_stream → TaskService → Q3；读取Q2与已存教学上下文 | teaching_step/TeachingTurn、检索及发布结果 | 任务/待答归TaskRepository；对话与辅助观察归宿主Memory/Repository | 原生turn接管活动执行；宿主只保留授权/页面投影，不再调用Q3二次生成 |
| 学习路径/本次安排 | Q5Runtime、Q5LearningService、SessionStudyService；教材next仍由Q2 | 草稿、确认、讲解、自报理解、活动推进 | Q5服务写路径；SessionStudyService写session_plan | 原生学习服务成为目标路径唯一写入方后，Q5停写并只读兼容；本次安排尚需适配原生执行 |
| PDF文字/区域选区 | TaskContextBuilder校验来源；文字开关走selection_loop；区域/兼容分支走explain_selection | 选区讲解/帮助、原图和来源结果 | 宿主发布/记忆事务与任务收据各写所属对象 | 位置/版本仍由Q2校验，不能把原生完成态当作来源核验通过 |
| 练习与练习帮助 | practice_api独立草稿/提交；聊天帮助走explain_exercise | 独立练习作答/评分、提示及讲解 | practice_api写ExerciseSubmission；帮助记忆仍由宿主Repository写 | 原练习业务保留为原生工具；练习分不自动成为正式掌握证据 |
| ask_user恢复 | 读取同一TaskRepository的loop_state、版本与问题 | 学生答复替换原工具消息，继续同任务 | TaskService/TaskRepository保存暂停/恢复，不创建另一个待答库 | 原生继续同turn；text/多问题answers及旧revision交接仍属NT1，不在TA0伪造完成 |

现有宿主的对话保存、Q5讲解记录和任务结果保存并非一个跨对象原子事务。TA0只确认每种对象的唯一写入方，记录这个事实；不把它描述成原生事务已统一。

## 4. pending、evidence、review及旧数据

| 数据 | 当前语义/位置 | 原生契约及迁移限制 |
| --- | --- | --- |
| 小检查pending | TaskContext.tutoring中的纯PendingQuestion；公开输出走public_pending_question | host_formative，不直接迁成正式题；答案键/参考解释不进入公开卡片 |
| 帮助事件/观察 | 宿主任务与记忆记录，保留实际提示级别/解答已见 | ai_provisional和assisted不等于独立证据，不生成正式掌握分 |
| explained / understood | Q5持久进度；understood为自报 | 保留目标身份/来源/位置；不写learner_mastery_overrides或定量掌握 |
| 正式题目/评分/掌握 | 当前在线未启用 | 未来复用原生interaction、LearningEvidence及服务事务，须有可靠来源/答案或rubric；TA2验收 |
| 回顾建议 | 对话引用元数据的只读派生 | 不等于到期review_queue；未来由原生Scheduler/服务写正式复习状态，TA4验收 |
| 账户偏好/目标画像 | 全局偏好仍属宿主；原生路径LearnerProfile尚未全量接线 | 区分全局/会话/目标作用域；不能把同一对象在两库都当作可编辑权威 |

- TA0不增加业务表，不改正式库schema。旧字段缺省按未知/未评，不补造得分、掌握概率或复习到期时间。
- 身份映射：student/course/session/request/task/revision/epoch → native user/workspace/course/session/submission/turn/seq，全部来自服务端。重复请求复用收据，内容变化冲突；不接收客户端指定内部用户、根目录或任意工具授权。
- 当前epoch在宿主，是删除/取消/恢复授权事实；原生派生数据物理清除、跨库提交竞争、WAL断电一致性尚未解决。正式入口暂停，不将多项单测等同于完整删除传播。
- 将来交接必须按对象/路径固定单一写入方，旧Q5停写后才允许原生写；失败保持原方或只读。回退保留新原生记录，不能整库覆盖旧备份。

## 5. 固定样例与计时定义

可复现脚本：`scripts/check_ta0_baseline.py`。默认只盘点身份/源码/监听/依赖，`--live`用新的.runtime/ta0目录和独立SQLite执行当前宿主链路。模型配置只从本机既有安全配置读取，不输出密钥、base_url或真实用户画像。

| 样例 | 目的 | 预期解释 |
| --- | --- | --- |
| chat：直接解释自变量，不出题 | 普通教材讲解基线 | 不应无故建立正式掌握或强制出题 |
| learning：按章导学第一章 | 路径草稿/来源基线 | 草稿不是确认，也不代表整章覆盖 |
| selection：第二章第二节固定页与归一化矩形 | 选区入口及服务端原文身份 | 保存具体document/version/rect；浏览器文字不当作证据 |
| practice_unavailable：当前心理学教材无独立题库 | 缺资源拒绝基线 | 不编造习题、作答和成绩；这不是有效练习评分验收 |
| ask / ask_resume | 暂停、文本答复恢复 | 尝试真实模型工具暂停；失败也记录，不能把未调用ask_user算恢复通过 |

记录首个临时正文、首个权威替换、正式返回耗时，实际模型/embedding HTTP尝试数，以及路径/目标位置/对话/练习数量前后快照。没有token的确定性/拒绝回合首字为null，不填0冒充快；单次样例不计算p95、不宣称提速。

这里是当前宿主基线，不是原生端到端、浏览器或全入口质量验收。失败/空首字/缺题库作为基线保留，不要求在TA0修复TA1—TA5的行为。

## 6. TA0完成核对（待本轮实测和稳定提交补齐）

1. 基线/实际运行身份/依赖核对：已完成只读盘点，源码快照由脚本固定。
2. 五入口的读取、事件与写入方：本文件和JSON已列明。
3. Q5/pending/evidence/review契约、旧缺省与删除边界：已列明，不新增同义库。
4. 基线样例/调用数/首字/耗时/状态与稳定SHA：等待本轮隔离实测及提交记录；完成前不标TA0通过。

本文件不授权开启原生评分、复习或切换正式服务；TA1及之后按顺序另行实施。
