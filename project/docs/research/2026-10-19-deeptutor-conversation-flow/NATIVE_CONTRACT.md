# 原生对话接入契约 v1

本契约约束 P1—P3 的实现。当前阶段只接内部原生运行时；在宿主生命周期、发布和删除适配通过前，不接学生页面、不切默认入口。以下是目标契约，具体完成状态见 EXECUTION_LOG.md。

## 身份与存储

宿主是学生/账户、课程资源版本、task/revision 和删除 epoch 的权威。浏览器不能提交原生 user/workspace、文件路径、模型凭据或任意工具。worker 的私有接口沿用共享凭据，不能取代宿主对归属与资源的检查。

沿用 SessionBridge 的 student→user 映射与学生角色。每个学生/课程使用独立的原生 workspace，在该 scope 内创建原生课程及会话；原生会话采用 heart_native_ 命名，与已有 heart_ 会话、heart_turn_ 投影分开。正文和模型协议将持久化在这个新的作用域，不能继续声称上游只存元数据。

回合映射包含 student/course/host session/request、task ID/revision、原生 workspace/course/session/turn，以及请求摘要、教材版本和删除 epoch。查询、事件、答复和取消必须重查映射，不接受孤立的 turn_id。恢复不创建新身份或会话。

## 执行与幂等

唯一执行入口为 DeepTutorApp / TurnApplicationService，继续使用 TurnRequestPreparer、TurnExecutor、ContextBuilder、TurnEngine 与原生协调器。不能调用旧语义路由/教学规划后再套一次原生流程，也不能用 agentic_bridge 的受限循环替代应用层。

host request 映射为稳定 client_submission_id。同一请求、同一内容重发只返回原回合；内容、目标版本或 task/revision 冲突要明确拒绝。上游 start_turn 对失败/取消 submission 允许重试，因此适配层必须先查询已有映射及 submission，即使它已失败也不能因宿主重发而自动重新生成。显式重试应有新的宿主身份。

先登记待启动收据，再调用原生应用层并补写 turn 映射。若进程在两者之间中断，按既有 submission 认领，不创建第二次执行。模型运行和 ask_user 等待不能占用宿主学生锁或适配层登记锁。

## 状态、事件与交互

状态沿用 queued/running/waiting_input/completed/failed/cancelled，seq 沿用原生持久化游标。DONE 后仍可能有 session_meta，不能一收到 DONE 就丢弃后续 metadata。

ask_user 答复属于原 turn，携带稳定 command_id，由原生协调器去重和投递；不作为新的用户问题启动另一回合。取消必须发送到执行 worker，并报告接受和终态，不能只禁止宿主保存。没有租约的等待/执行回合由原生应用层回收，不宣称能恢复丢失的 Python 协程。

旧 heart_snapshot 投影只能表示旧流程的结果，不能占用、取消或覆盖真实原生回合。原生查询也不能把投影的 DONE 当成模型执行证据。

## 结果发布与学习事实

内部原生正文、工具事件和模型历史都是执行产物，不能直接当成已核验教材答案。宿主发布状态单独使用 pending_verification/published/rejected/cancelled/invalidated；原生 completed 不等于 published。

P3 发布前校验归属、task/revision、删除 epoch、教材版本、原文/引用以及适用的语义要求。失败草稿不进入正式历史重放和学生能力事实；修订反馈回原生链，预算有限。P5 负责将撤销/删除传播至新增原生正文与摘要；未完成前保持内部入口关闭。

学习事实按统一作答身份幂等提交，不允许宿主与原生引擎各记一次成绩。上游完成但宿主未发布时，可重试核验/发布，不能重跑生成。

## 阶段边界

P1 先以替身引擎和临时数据库验证真实应用层持久化、暂停、恢复、取消、去重与隔离。通过不代表真实 LLM、原生 RAG、工具授权、前端呈现或质量提升已完成。P2 接原生教材来源，P3 才接宿主执行分支、发布检查与页面。继续按 11/14/100 台账如实验收。
