# 本次学习安排实施记录

2026-10-23；起点 main `974617d`。按 Q5_SESSION_STUDY_PLAN_IMPLEMENTATION.md 执行，不改变长期路径、正式评分或 LightRAG 索引。

## SP0 调用链冻结

实际入口为 TaskService._run → Q5Runtime.propose_chapter_plan/plan_result → Q5LearningService → Q5TurnAdapter.loop_binding → Q3 run_agent_loop_turn → 现有 clarification/聊天卡。

当前缺口已核实：has_path 阻止再次规划、未向 LLMPlanGenerator 传本次约束、调整只改首目标名、无 session_plan 字段。章节目录草稿保留为章节导学；通用本次安排另接现有生成器，不新建循环或路径引擎。

固定六类输入：

| 输入 | 期望 |
| --- | --- |
| 今天一小时，想学自变量和因变量，基础弱，先讲不要考试 | 本次约束进入生成器、总时长≤60、无强制测试 |
| 已有路径时“今天怎么安排” | 选既有目标，不覆盖路径 |
| 改成20分钟，只学自变量 | 结构化调整，保留已讲事实 |
| 只讲解不考试 | 不生成必做测试 |
| 计划中插问图1-4，再返回 | 活动与长期位置不推进 |
| 什么是自变量 | 普通问答，不创建计划 |

SP0 已核对；SP1—SP5 按各次提交/测试记录逐项更新。正式服务与正式库保持不变。
