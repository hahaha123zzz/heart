# DeepTutor 教学闭环：完成与验收记录

日期：2026-10-24。当前本机地址：http://127.0.0.1:8000/ 。

## 已完成

- 从固定 DeepTutor commit 6cf793bd868ba5ecbe64722936d4be8fab5a01df 迁入六个纯代码模块。
  models/policy/pending 真实执行，不是仅参考提示词。原版模型和策略测试随代码迁入。
  原文件哈希、机械 import 变更和 Apache-2.0 许可证均保留并有一致性测试。
- 接入现有 TaskService、LocalAgentLoop、DeepSeek、教材原文核验和任务提交。
  教法由模型依据上一轮解释及反馈调整，不再按困难次数固定升级。
- 一个待答开放式检查：存题、后续原题反馈、插问保留、原样恢复、明确跳过。
  等价表述可被认可；未知、评估失败和帮助请求不当作答错。
- “懂了”不等于掌握；辅助证据标为 AI 暂定和已获帮助，不写正式 Q5 成绩。
- 显式先讲不考、已确认的不主动提问偏好、已确认的本次不练习安排均有代码约束。
  撤销交互偏好不会被旧快照锁死；权威活动目标变化会丢弃旧题。
- 客户端、路由提示和工具诊断协议不暴露参考答案键。
- 合并已检查的 origin/main 9cb54318c8a0c07cfada27f81969fa778199fbc0；
  同时保留主线的会话安排与长期讲练偏好。修复规划阶段意外异常时的任务清理边界。

本地功能提交：74362db。主线衔接提交：aea5e9c。
没有推送 GitHub；.env、密钥、数据库和教材没有加入提交。
原来 scripts/parse_converted_textbook.py 的部署改动保留，未覆盖、未混入本次提交。

## 验证结果

最终相关自动化回归：244 passed，6 subtests passed。
证据：.runtime/adaptive-final-tests.xml 。

真实 DeepSeek + 真实心理学教材检索 + HTTP，多轮场景：

1. 自变量/因变量讲解，登记一道室温与作答时间的小检查。
2. “没听懂”后换讲法；原题 ID 和内容不变，复用已重新核验的证据，没有重复检索。
3. 插问控制变量；新取证回答，原题保留，不产生辅助评分。
4. 实际重启测试服务；从数据库恢复同一道题。服务端原样重现，模型调用为 0。
5. 用等价措辞回答原题，判定 correct，保存为 practiced_with_help，不授予正式掌握。
6. “先讲不考”，不出题、不反问，清除待答检查。

最初恢复回合曾被普通教材引用门禁拒绝。已修复为“固定前缀 + 已保存原题”的受限服务端动作；
不是允许任意无引文模型输出。失败回合不覆盖上一条已提交状态。
原始失败和复验成功记录都保留在 .runtime/adaptive-http-20261024/ 。

主线合并后，在实际 8000 入口再次验证 SSE：
answered，teaching.schema=deeptutor-teaching-v2，formal_mastery=false，
4 个 AgentLoop 模型轮次、2 个工具轮次，local_llamaindex 实际检索，2 个当前有效引用。
31.47 秒；这是该次实测，不是性能承诺。
证据：.runtime/adaptive-stream-20261024/stream-verification.json 。
页面 HTTP 200，注入课程配置 experimental-psychology-3。

loop_summary.rounds 仅统计 AgentLoop 内的模型轮次。
证据选择、质量核验、辅助答案评估可能另有模型调用，不能把这个数字当总 API 请求数或总费用。

## 本机部署与恢复

.env 已设置 ADAPTIVE_TUTORING_ENABLED=1，原 DeepSeek 配置保持不变。
LOCAL_AGENT_LOOP_ENABLED=1。直接复用迁入代码，不需要启用另一套 DeepTutor bridge 服务或 bridge token。

启动脚本：当前任务目录 work/start-psychology.ps1。
后台启动宿主 PID 25416，实际服务器 PID 19632（记录时有效）。
日志：
- .runtime/adaptive-server-8000.stdout.log
- .runtime/adaptive-server-8000.stderr.log

部署前一致性备份：
.runtime/pre-adaptive-20261024T005212Z.db 。
已运行主线自带的幂等迁移，仅为 q5_learning_bindings 添加 session_plan JSON 字段；
用户学习记录没有被 QA 数据库覆盖。QA 使用独立 .runtime/adaptive-qa-20261024.db。

功能回退：将 ADAPTIVE_TUTORING_ENABLED 改为 0 并重启；无需删除数据库。
数据库备份保留供恢复，但不要在正常学习期间直接覆盖正在写入的数据库。

## 仍未声称完成的范围

- 这不是整套 DeepTutor 应用/全部工具的部署。其正式测评、长期掌握地图和间隔复习 UI 未整套迁入。
- 本期接普通助教对话；PDF 划选解释、作业题、专用互动图仍走各自原流程。
- 只提供开放式辅助检查；模型反馈仍需按 AI 暂定结果看待。
- 辅助待答状态沿用现有任务有效期，默认 1800 秒；不是跨天长期待答档案。
  任务过期、删除或切换课程/章节后不复活旧题。原有长期 Q5 路径不受此限制。

建议手工测试：新会话依次说“解释自变量和因变量，给一个小检查”、
“没听懂，换个例子”、“先插问控制变量是什么意思”、“回到刚才的小检查”，
再回答原题，最后说“先讲不考”。
