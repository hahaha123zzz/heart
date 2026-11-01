# 第三层教学策略决策器：第一轮实现

基线：`94ba9ca0223b164ac44cabdcb424b759b5e6e116`（用户指定，分支 `codex/ta5-acceptance-20261029`）。开发分支：`feat/teaching-strategy-engine-20261031`。

## 选择及权威

采用既有 TeachingTurn + LocalAgentLoop 内增强的方案。另建服务或更换 LangGraph 会增加状态迁移与副作用重放成本，本轮不采用。13 个策略 ID 仍仅来自 `knowledge/teaching_strategies.json`；`agents/teaching_strategy.py:decide` 是开启 ADAPTIVE_TUTORING_ENABLED 的 Q3 教材链路唯一策略入口。`analyze_teaching_turn` 只提供兼容的请求特征与证据需求，不再轮换最终策略。模型在已有 teaching_step 调用内通过可选 strategy_id 选择合法候选，兼容的 9 名 strategy enum 保留，不新增模型调用。

旧 TeachingPlanner/StrategyRouter 仅保留在未启用 Q3 的旧管线；独立题库 ai_parts 与原生 DeepTutor 管线仍是单独的执行入口。本轮不宣称它们已统一；全面替代需另做题库、原生与旧管线的适配和验收。不得将本轮称为成熟首版全部完成。

## 决策与约束

输入复用已授权 TaskContext、GroundedTurn 六维只读投影、用户明确教法、题目公共身份、辅助评分和同目标已发布历史。优先级为用户限制/披露政策、有效题目生命周期、作答反馈、困难原因、上轮方法。标签开关继续生效；缺失不补能力、疲惫或负荷推测。部分正确使用引导修正，明确错误才允许纠正/反例；正确的辅助答案仍不授予正式掌握。复习默认整理解释，只有获准互动时才允许提取练习。

完整 13 策略均有动作、要求与退出条件，测试验证所有 ID 在合法情境可达。按需注入至多三个候选片段；每轮至多六个计划动作，teaching_step 至多三次不同登记，其余循环预算/授权沿用 Q3/Q4/Q5。有明确困难才降低上一方法优先级，不再固定按目录轮换。模型越界、兼容名称不一致、重复身份、跨任务恢复均拒绝。

## 状态与发布

TeachingStrategyPlan 保存 decision_id、策略/注册表版本、学生/会话/任务/revision/目标、合法候选、有序 moves、深度、互动边界、可观测退出条件和回退 ID。计划保存在原 context.tutoring，由 TaskService 原事务、epoch、revision 和 guard 管控，不另建状态库。

teaching_step 成功仅为 prepared，不能当作已发布或学生理解。只在现有发布检查通过后，commit_sources 保存 publication_receipt、回答 SHA256、来源 ID、工具回执及有界历史。重复发布和相同工具参数不重复登记。只有可由来源或已登记题目证实的动作标记 published；语义讲解动作标记 not_observed，模型声明放在 reported_strategy。后续反馈与上轮发布关联，但不自动写偏好、掌握或因果效果。

ask_user 暂停后保存原 plan、登记收据、待答题与执行标记；恢复绑定同任务/会话/目标并更新 revision，不重新批改旧输入、不重新登记已做动作。LocalAgentLoop 状态同时保存成功工具回执，恢复后不把已完成的必需工具当未调用。取消仍由原 Cancellation/guard 阻断；失败或取消不产生发布回执。选区的披露/不出题约束在生成前收窄同一计划。

## 复用与许可证

本轮直接调用现有 `agents/deeptutor_learning` 的 pending/policy/学习记录及原 ToolDispatcher/TaskService 的授权、去重和暂停协议，来源、固定版本和许可证继续见 `agents/deeptutor_learning/SOURCE_NOTICE.json` 与现有 notices。新增策略代码为项目内实现，没有从 OpenTutor/OpenMAIC 直接复制代码或素材，因而没有新增复制文件的 SHA256 清单。按需策略片段、动作预算/回执的设计参考用户已提供的源码审计结论，不声称迁入这些项目的执行器。

## 验证和未完成事项

新增契约测试覆盖 13 策略合法可达、具体困难响应、明确约束优先、候选越界无副作用、模型选择、发布/工具幂等、反馈因果边界、取消、跨任务隔离、暂停恢复、答案键隔离和工具回执恢复。旧轮换测试更新为新行为断言，正式掌握与题目生命周期断言保留。

当前独立检出没有心理学 manifest/教材数据库、发布证据包和模型运行配置。测试使用 TUTOR_COURSE=discrete-math，仅验证适配器和模拟工具契约；它不证明心理学真实教材、真实模型延迟或页面教学效果。真实模型/页面验收、模型次数与耗时基线、受控教学效果评估、资料缺口后的自动局部修订、全部旧入口收敛仍待完成。fallback 字段为声明性安全路径，不宣称具备自动重试所有失败动作的执行器。

## 本轮实际验证记录

- Python：`C:/Users/xinzi/AppData/Local/Programs/Python/Python311/python.exe`。默认 python 为 Anaconda 3.6，不用于项目验证。
- 配置：仅测试进程设置 `TUTOR_COURSE=discrete-math`，未修改项目 .env 或全局环境。
- 策略/模式/标签/循环/目录兼容回归：99 passed，39 subtests passed（test_adaptive_tutoring、test_teaching_modes、test_label_consumers、test_teaching_decision、test_q3_agent_loop、test_strategy_catalog、test_runtime_strategy_parity）。
- 新增统一策略测试：最终 22 passed（test_teaching_strategy_engine）；包括通过真实 LocalAgentLoop 协议的 teaching_step → ask_user → 恢复 → 发布，以及登记摘要更新不丢失原检查动作。
- 选区/输入理解/提示/辅助证据/任务上下文/任务执行：73 passed，3 subtests passed（test_selection_loop、test_input_understanding_integration、test_teaching_hint_lifecycle、test_teaching_evidence、test_task_service_context、test_task_execution）。
- 合计 194 个独立测试和 42 个子测试通过。`git diff --check` 通过。增加 tests/__init__.py，防止本机第三方同名 tests 包抢占项目测试导入。
- 选区与任务上下文测试在进程启动时，将 `knowledge.textbook.load_textbook.__wrapped__.__defaults__` 设为本机原有的 `C:/Users/xinzi/Desktop/agent-extracted/integration/discrete-math-tutor/knowledge/textbook_text`。只为旧测试提供实际存在的离散数学目录，没有复制或重新发布教材。其余测试使用模拟模型/临时 PDF。
- 扩大回归中的 test_teaching_memory_corrections API/TestClient 用例长时间未返回，已中止该测试进程；不计入通过数，未改动该 API。没有运行完整全仓回归。
- 没有真实模型/页面/正式心理学教材验收结果，也没有教学增益或延迟改善结论。没有提交、推送或部署业务变更。

## 2026-11-01 后续进展

已取得用户提供的 Release 数据并完成真实教材/快照与 deepseek-flash HTTP 验证，随后实施第二轮多入口接入。第一轮本文的“未具备测试数据”与“只有 Q3 统一”描述是当时状态。最新结果、失败和剩余限制见 [第二轮实施与验收](2026-11-01-teaching-strategy-engine-round2.md)。
