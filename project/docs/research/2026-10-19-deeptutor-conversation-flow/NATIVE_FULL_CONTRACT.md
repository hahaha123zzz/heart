# 原生完整执行与学习所有权契约

日期：2026-10-27。状态：TA0规范基线；不是原生正式启用声明。

本文件与[TA0基线和写入契约](TA0_BASELINE_AND_WRITE_CONTRACT_20261027.md)、[机器可检验所有权清单](TA0_STATE_OWNERSHIP.json)共同约束后续实现。最终架构沿用主计划第21节和原生完整迁入计划；旧NATIVE_CONTRACT.md里“保留宿主Q3作为最终引擎”等相反叙述仅为历史。

## 执行与状态

- 当前：宿主TaskService/Q3执行；Q5/SessionStudyService写现有学习位置；原生只允许隔离候选。现有练习评分是独立业务，不能据此声称原生掌握评估已开启。
- 未来：每会话固定一个执行引擎，原生TurnApplicationService负责活动回合及事件，原生LearningService负责目标路径/正式题目/掌握/复习。宿主负责账户与删除控制、任务收据和页面投影，Q2仍负责教材身份及目录导航。
- 切换以对象/路径的写入权交接为界，不能让Q5与原生同时推进同一目标。原生失败不得隐式回到Q3重新生成并双写。原生暂停不是创建宿主新任务的理由。

## 请求与身份

服务端映射 `student/course/session/request/task/revision/epoch` 到 `native user/workspace/course/session/submission/turn/seq`。浏览器不能指定内部账户、根、任意工具或密钥。

当前类型以 `integrations/deeptutor/native_contract.py` 为准：NativeTurnStart携带epoch与教材版本快照，NativeTurnCursor按seq恢复，NativeTurnReply目前仅text，NativeTurnCommand使用command_id。多题answers尚未实现，不将现有text-only契约伪称全量恢复能力。

同request内容变化拒绝；同请求重发返回原收据，不透明重试失败回合。显式新重试需新身份。授权失效后start/恢复/答复/发布均拒绝；取消与回滚清理保留。完整物理删除与跨库提交竞争在原生正式写入前解决。

## 来源、证据与公开数据

原生completed只代表执行事实。来源/教材版本、原图和宿主发布核验尚未通过时，只能为pending_verification/partial/失败，不能直接保存成source_verified正文。

宿主小检查、提示后作答及暂定诊断为host_formative/ai_provisional；旧understood为自报，不迁成正式掌握或learner_mastery_overrides。正式题目必须绑定可信题干、私有答案或rubric、来源版本与交互身份。答案键不进入公开卡片、流事件或UI历史。

回顾建议只是只读派生，不等于到期复习队列。全局账户偏好与目标LearnerProfile作用域分开，不能双向无约束同步。旧记录缺字段时保留未知/未评，不补造模型历史、得分或复习时间。

## 迁移、失败与回退

迁移保留旧ID、来源、当前目标、原快照摘要及幂等收据。未满足映射/来源/归属时保留待处理或拒绝，不能猜下一目标、默默回第一项。私有备份与迁移原文只放隔离.runtime，不随代码发布。

正式切换前先完成隔离验收与原写入方停写。回退保留新原生事件、学习记录和对话；无法安全续写的路径先只读，不能整库覆盖旧备份。NT3/NT8负责真正实施与验收；TA0只固定该契约和当前基线。
