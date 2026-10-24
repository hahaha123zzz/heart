# DeepTutor 纯学习引擎迁移与宿主适配

日期：2026-10-24。用户已同意实施，不是新一轮设计提案。

## 源码复用边界

固定来源为项目自带 HKUDS/DeepTutor 快照，commit
6cf793bd868ba5ecbe64722936d4be8fab5a01df，Apache-2.0。

agents/deeptutor_learning 内 models.py、policy.py、pending.py、
scheduler.py、grading.py、text_display.py 整文件迁入，仅机械修改 import 命名空间。
SOURCE_NOTICE.json 记录原始文件 SHA-256，LICENSE 保留完整许可证。
test_deeptutor_source_notice.py 会逐文件比对原件和迁入件；不是把自行编写的策略声称为上游源码。
grading.py 作为同组纯依赖保留，本期开放式检查不用模糊字符串评分。

| 原版能力 | 本地接入点 | 本期作用 |
|---|---|---|
| LearningProgress / LearnerProfile | TeachingTurn 私有进度快照 | 当前目标、先教后测偏好、辅助观察 |
| PendingQuestion / public_pending_question | teaching_step / public_state | 固定题目 ID，答案键只留服务端 |
| learning_stage / next_objective | 每次 _sync | 从实际证据计算阶段和下一教学动作 |
| MasteryNoteExplained 生命周期 | TeachingStepTool 适配实现 | 记录讲解覆盖，不授予掌握 |
| quiz/assess 生命周期 | 存题、下一回合 _assess、保存证据 | 核对原题和学生原话，插问保留原题 |
| mastery_loop 中文 playbook | instructions 语义适配 | 先教后测、题后停轮、插问不批改、解释不等于掌握 |

上游数据库服务和完整应用没有启动，也没有被直接搬入。工具生命周期和提示词是宿主适配，不声称逐字复制。
已复制的 scheduler 是 policy 的纯依赖，当前没有把定期复习调度接到正式学习记录。
Q5 原有路径、成绩与权限保持独立，辅助回答不调用正式 mastery_grade/mastery_assess。

## 数据流和提交条件

TaskService 根据学生、会话和记忆 epoch 读取最近有效已提交状态。
被拒绝/模型失败的回合不覆盖前一个成功快照，也不能作为新的能力证据。
TeachingTurn 用真实 LearningProgress 恢复目标及原题，重新核验原 PDF 的版本、字节哈希和引文。
DeepSeek 组织讲解；teaching_step 暂存本轮教法、摘要和最多一个开放式小检查。
普通知识回答仍须通过原文发布、引用和质量门禁；之后把状态随现有任务 context 保存。
工具本身不写第二个数据库。

下一轮学生作答使用保存的题目 ID、题干、服务端参考答案及该题的原始来源核对。
move=question/unclear、模型失败、非逐字学生引文不会消费原题或写成错误证据。
明确插问先由代码保护，其余使用结构化模型判断。
辅助证据与 QuizAttempt 显式标为已获帮助、AI 暂定；不设置 qualitative_mastery，
不计算正式 mastery_levels，不写 learner_mastery_overrides。
普通“懂了/继续”不算作答；跳过不算答错；先讲不考关闭检查，可明确重新允许。

插问的新检索结果不替换原题证据。恢复请求只允许服务端固定前缀加原题原文，
且必须已重新核验原题来源；不会把任意模型文本作为免检回答。
所有私有答案键从客户端 teaching、路由 prompt_payload、诊断 loop_state 工具参数中剔除；
SSE 工具参数沿用 sensitive 标记。

## 验证和部署

迁入原版 test_models.py / test_policy.py（仅改 import），加适配层、源码一致性和原入口回归。
scripts/check_adaptive_tutoring.py 使用独立数据库、真实 DeepSeek、真实教材检索和 HTTP 入口；
prepare/resume 两阶段之间实际重启服务，证据保存在 .runtime/adaptive-http-20261024。
原题恢复不需要教材引用卡，因为没有新增教材断言；其他知识回答必须有有效引用。

启用条件：LOCAL_AGENT_LOOP_ENABLED=1 且 ADAPTIVE_TUTORING_ENABLED=1。
默认示例配置关闭；本机通过验收后单独开启。设置 ADAPTIVE_TUTORING_ENABLED=0 并重启可回退，
不删除学习记录，不改 DeepSeek 密钥。

## 明确限制

本期接普通 AgentLoop 对话；PDF 划选解释、作业题、专用互动图仍走原流程。
不把完整 DeepTutor 的出题卡、长期掌握地图和间隔复习 UI 一并声称上线。
只支持开放式辅助检查，模型判断仍可能出错，不能作正式评价。
辅助状态沿用现有任务有效期（默认 1800 秒）；任务过期、删除或切换课程/章节后不会复活旧题，
因此本期不是跨天的长期成绩/待答档案。已有长期 Q5 路径不受此有效期影响。
