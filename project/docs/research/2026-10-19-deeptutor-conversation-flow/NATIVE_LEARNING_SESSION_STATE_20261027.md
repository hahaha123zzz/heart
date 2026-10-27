# NT3隔离候选的会话状态恢复

日期：2026-10-27。状态：会话模式与兼容记录恢复已实现；在线统一学习与正式评分尚未完成。本批未提交或部署。

## 源码复用和边界

继续使用固定vendor `6cf793bd868ba5ecbe64722936d4be8fab5a01df` 的 `LearningStore`、会话存储和 `mastery.mode.MODES`；未修改vendor或新增表/循环/账户系统。

原生 `request_preparer` 从会话偏好读取 `mastery_path_id / mastery_session_mode`，只绑定LearningStore会话路径还不足以恢复模式。本批在已有 `bind_candidate_sessions` 中补充原生会话偏好恢复，写入路径ID和outline/study/review模式。使用原生 `update_session_preferences` 并检查返回值与重读结果，不使用会吞掉持久化错误的best-effort助手。

`heart_q5_session_migration` 是原生会话偏好中的兼容迁移收据，保存原快照摘要、原路径身份、旧教学顺序、自报理解及本次安排的ID/revision/当前位置。完整旧安排仍保存在既有LearningStore迁移事件的原快照内，不把活动正文/原始来源复制到会话偏好，也不迁入宿主待答题或答案键。

## 状态语义

- 自报理解只保存目标ID和时间，不写 `mastery_levels / qualitative_mastery / learner_mastery_overrides / learning_evidence`。尤其不使用原生“自报掌握”跳过目标，因为这与旧Q5“我懂了”的语义不同。
- `teaching_strategy` 先保存在兼容收据；尚未合并到原生路径级LearnerProfile，避免不同会话顺序偏好覆盖同一路径画像。
- 可选本次安排使用既有 `SessionStudyPlan` 校验结构/预算，再检查学生、课程、会话、路径和目标归属。保持原活动ID/位置/状态；单独标记 `session_plan_requires_revalidation=true`，不自动执行、不把其active状态解释为原生服务已启用。
- 未知模式或顺序拒绝，不偷偷回到默认模式。所有来源计划仍需执行前重新核验；旧revision的安排可以作为历史保留，不因此授权执行。

## 冲突、重跑与失败

- 在创建账户/工作区之前校验所有旧会话状态；坏模式、非法/跨学生/跨会话安排先拒绝。
- 原生会话已有不同路径/明确模式时拒绝覆盖。首次恢复前存在活跃回合也拒绝。
- 同摘要同内容收据重跑返回 `already_restored`，不重置后来由原生修改的模式或其他偏好。收据内容冲突直接失败。
- 偏好写入失败或重读不一致不会报告恢复成功；可在同一只读快照上重试。
- 这不是跨LearningStore和session数据库的原子事务；失败可能留下未激活的候选路径，重试复用原迁移收据恢复。仅用于停止在线写入的隔离候选，正式并发切换仍须请求级revision/租约、删除epoch和回退编排。

## 验证证据

- 初批会话/绑定12项通过，21.469秒，`.runtime/teaching-modes/native-session-state-tests.log`。
- 会话状态/绑定/迁移/来源/Q5/本次安排联合80项通过，102.600秒，`.runtime/teaching-modes/native-session-state-regression.log`。随后收紧会话偏好中安排内容为位置白名单，专项复验单独记录；不将多轮重叠集合累加为全库测试。
- 位置白名单收紧后，最终会话状态专项7项通过，14.397秒，`.runtime/teaching-modes/native-session-state-final.log`；定向 `git diff --check` 通过。
- 实际只读备份：对既有 `20261027-q5-bound-candidate` 连续执行两次 `--bind-sessions --verify-sources`。第一次会话状态 `restored`，第二次 `already_restored`；两次结构与来源核验均通过，源备份SHA未变。日志 `.runtime/teaching-modes/native-session-state-first.log / native-session-state-repeat.log`。
- 专项覆盖原生模式与路径偏好、自报理解不成为掌握、不同会话不同模式、已有模式保护、后续模式修改不被重跑重置、合法安排保留/外来安排拒绝、写入失败及重试恢复。

未调用真实模型、未启动服务器或浏览器，未改正式数据库。私有备份、原生候选库和会话收据只留本机.runtime，不提交。

## 仍未完成

正式请求中的会话安排消费与来源重新核验、路径级画像/会话级偏好作用域统一、教材导航适配、删除传播/epoch、唯一写入与回退仍待完成；正式题卡/评分/复习仍未启用。本批不据此宣布TA0或NT3整阶段完成。
