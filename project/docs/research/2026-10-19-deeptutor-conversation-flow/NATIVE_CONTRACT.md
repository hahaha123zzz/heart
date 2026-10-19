# 原生对话接入契约 v1

> 历史契约，2026-10-19 已停止作为实施目标。用户要求整套代码集成到本项目，纠正整轮请求委托给 DeepTutor 应用的方式，未缩减功能范围。当前以 [代码集成契约](LOCAL_REUSE_CONTRACT.md) 和 [修订计划](IMPLEMENTATION_PLAN.md) 为准。下文保留此前实验的设计记录，不能继续据此推进原生应用路由。

本契约约束 P1—P3 的实现。当前阶段只接内部原生运行时；在宿主生命周期、发布和删除适配通过前，不接学生页面、不切默认入口。以下是目标契约，具体完成状态见 EXECUTION_LOG.md。

## 身份与存储

宿主是学生/账户、课程资源版本、task/revision 和删除 epoch 的权威。浏览器不能提交原生 user/workspace、文件路径、模型凭据或任意工具。worker 的私有接口沿用共享凭据，不能取代宿主对归属与资源的检查。

复用 SessionBridge 的注册表与登记锁。旧投影的合成学生身份没有原生模型授权，完整运行时使用保留前缀 heart_native_ 的普通用户账户，通过上游 identity/grants/catalog 服务登记和授权；没有已知登录密码，不提升为管理员。每个学生/课程使用独立的原生 workspace，在该 scope 内创建原生课程及会话；原生会话采用 heart_native_ 命名，与已有 heart_ 会话、heart_turn_ 投影分开。正文和模型协议持久化在原生 data/users 下，不能继续声称上游只存元数据。

回合映射包含 student/course/host session/request、task ID/revision、原生 workspace/course/session/turn，以及请求摘要、教材版本和删除 epoch。查询、事件、答复和取消必须重查映射，不接受孤立的 turn_id。恢复不创建新身份或会话。

## 执行与幂等

唯一执行入口为 DeepTutorApp / TurnApplicationService，继续使用 TurnRequestPreparer、TurnExecutor、ContextBuilder、TurnEngine 与原生协调器。不能调用旧语义路由/教学规划后再套一次原生流程，也不能用 agentic_bridge 的受限循环替代应用层。

host request 映射为稳定 client_submission_id。同一请求、同一内容重发只返回原回合；内容、目标版本或 task/revision 冲突要明确拒绝。上游 start_turn 对失败/取消 submission 允许重试，因此适配层必须先查询已有映射及 submission，即使它已失败也不能因宿主重发而自动重新生成。显式重试应有新的宿主身份。

先登记待启动收据，再调用原生应用层并补写 turn 映射。若进程在两者之间中断，按既有 submission 认领，不创建第二次执行。模型运行和 ask_user 等待不能占用宿主学生锁或适配层登记锁。

## 状态、事件与交互

状态沿用 queued/running/waiting_input/completed/failed/cancelled，seq 沿用原生持久化游标。DONE 后仍可能有 session_meta，不能一收到 DONE 就丢弃后续 metadata。

固定上游在游标已经越过 DONE、没有新事件时，仍可能返回 metadata.synthesized=true 的终态包。它不是新执行，也不是新增的持久化正文；消费端不能拿此包推进持久化事件游标。适配层保留原生事件，不伪造新的生成活动。

ask_user 答复属于原 turn，携带稳定 command_id，由原生协调器去重和投递；不作为新的用户问题启动另一回合。取消必须发送到执行 worker，并报告接受和终态，不能只禁止宿主保存。没有租约的等待/执行回合由原生应用层回收，不宣称能恢复丢失的 Python 协程。

旧 heart_snapshot 投影只能表示旧流程的结果，不能占用、取消或覆盖真实原生回合。原生查询也不能把投影的 DONE 当成模型执行证据。

## 结果发布与学习事实

内部原生正文、工具事件和模型历史都是执行产物，不能直接当成已核验教材答案。宿主发布状态单独使用 pending_verification/published/rejected/cancelled/invalidated；原生 completed 不等于 published。

P3 发布前校验归属、task/revision、删除 epoch、教材版本、原文/引用以及适用的语义要求。失败草稿不进入正式历史重放和学生能力事实；修订反馈回原生链，预算有限。P5 负责将撤销/删除传播至新增原生正文与摘要；未完成前保持内部入口关闭。

学习事实按统一作答身份幂等提交，不允许宿主与原生引擎各记一次成绩。上游完成但宿主未发布时，可重试核验/发布，不能重跑生成。

## 阶段边界

P1 先以替身引擎和临时数据库验证真实应用层持久化、暂停、恢复、取消、去重与隔离。通过不代表真实 LLM、原生 RAG、工具授权、前端呈现或质量提升已完成。P2 接原生教材来源，P3 才接宿主执行分支、发布检查与页面。继续按 11/14/100 台账如实验收。

## 当前私有接口

worker 新增 POST `/internal/heart/native/start|status|events|reply|cancel`，全部要求共享凭据和 DEEPTUTOR_NATIVE_ENABLED=1（默认0）。start 接收宿主身份、任务版本、内容、chat/ask_questions、memory_epoch 和 material_versions；拒绝上游身份、路径、任意能力/工具及模型配置。其余接口必须携带完整宿主任务身份，events 另带 after_seq，reply/cancel 另带稳定 command_id。events 使用 NDJSON，reply 当前只收文字，多问题卡结构化答案在 P3 接入。

模型 profile 和普通账户 grant 只由服务端写入，账户 grant 的 built-in/MCP/CLI 列表为空、exec 禁用；后续 P4 按所需能力挂载。凭据保存在 worker 的管理员 catalog，不在请求收据/事件响应中。此阶段只登记资源快照，尚未对接宿主权威版本、删除 epoch 和正式发布检查；所有回合都返回 pending_verification，保持学生入口关闭。
