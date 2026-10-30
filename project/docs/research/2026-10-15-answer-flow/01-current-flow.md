# 当前回答流程核对

日期：2026-10-15。只读分析当前工作区；不导入main，不启动服务，不修改学习数据库。

## 与前次调研的差异

knowledge/course_config.py现默认课程为experimental-psychology-3。心理学教材、提示词、检索、预制图解和跨会话记忆已有后续实现。2026-10-12报告中的离散数学基线不能原样套用；默认课程来自代码，实际进程环境本轮未查询。

## 实际链路

main._run_turn按学生分到64个进程内锁，TaskService校验身份、请求幂等、澄清状态、任务版本和图对象快照，再分发三条路径：

1. 普通聊天/辅助图：TutorOrchestrator.handle_turn。
2. PDF选区：pdf_selection_tutor.explain_selection；换目标时可复用已识别结果回普通路径。
3. 指定小题：exercise_task_tutor.explain_exercise→practice_api.ai_parts，并标记已使用辅导。

普通路径：识别→教材召回/原页→长期记忆→依据充分性→必要补召回及复核→课程计划→学生证据分析→TeachingPlanner→StrategyRouter→任务要求覆盖→条件生成诊断题→回答→质检/有界重写→StateUpdater→引用定位→预制或按需图解→事务提交→done。

选区路径：对象/版本确认→识别→记忆→选区依据核验→生成与至多一次重写→引用→图解→保存。该路径不把提问直接写成掌握或课程推进。

## 需要优化而非重复建设的地方

- 已有TaskService、TaskExecution、TeachingPlan、来源和删除/并发保护，不需要再造通用Agent引擎。
- 普通知识解释仍会创建/读取LessonPlan、提取学生证据、规划、策略选择及StateUpdater，即使当前任务无需测量。这些是静态可见的额外步骤；收益与耗时须逐阶段实测，不能宣称已证明浪费。
- 教学决策受plan、move、execution及卡住/自述理解等规则多次影响。应形成单次最终决策并供生成/质检共享，避免后续字段互相覆盖。
- chat_stream的SSE目前发送progress、done、error及ping，不是正文token流；done要等状态分析和图解后才到达。
- 动态图解有独立40秒预算，且已经优先心理学预制；不能再把“加预制”称作从零新增能力。
- QualityChecker已对需证明的两个独立检查并行；本轮不能再推荐把同一并行优化做一次。
- 三条路径存在相似的生成/核验/保存过程，应该先统一任务、结果和校验约定，避免为了去重把各自的对象限制、引用和帮助标记抹掉。

## 本轮不据此下结论的范围

不把静态调用数当作延迟测量；不把来源充分性等同回复正确；不把合法JSON、可点引用或模型passed等同学生学习收益。工作区有大量未提交迁移变更，本轮不还原、不提交、不推送这些改动。
