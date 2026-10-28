# TA1：宿主教学偏好与来源表达

2026-10-28更新：本文保留上批历史状态；原生接线及后续验收已完成，当前结论和边界以[TA1完成记录](TA1_COMPLETION_20261028.md)为准。

基线为本地 TA0 分支 `bb277769`。本批尚未提交、推送或部署。

原有界面 next/session 覆盖和长期偏好仍通过 `style_overrides` 与画像进入任务；本批在同一任务上下文上增加确定性、本轮有效的有限自然语言识别，明确的少/多提问、多/少举例及只举例可覆盖该轮有效值，不额外写入画像或创建设置。下轮恢复原设置；永久修改仍需要使用现有确认流程。语句识别不是通用自然语言理解，不能声称所有同义表达均支持。

只举例时不新增检查，已有待答题保留，不调用评分；测试覆盖本轮结束后原偏好恢复。教材重点、关系表达提示补充到宿主普通循环及原心理学提示，区分教材、考纲/教师依据、教学建议和模型推断；这是生成约束，尚无结构化来源类别校验，不保证模型每次遵守。

`python -B -m unittest tests.test_teaching_modes tests.test_adaptive_tutoring tests.test_teaching_hint_lifecycle tests.test_task_execution tests.test_interaction_style.StyleTests -q`：78 项通过。

另一次包含 `test_task_context` 与 `test_q3_q4_integration` 的 119 项运行有 1 失败、6 错误：4 项依赖当前缺失的离散数学教材或习题；另外两项分别涉及检索未就绪和引用记录为空，一项技能测试期望另一课程的技能。后 3 项尚未确认基线原因，该次不计为通过。尚未跑真实模型、浏览器及全部入口的本批验收。

原生 DeepTutor `AgenticLoopPipeline` 通过上游 prompt assembler 构建上下文；当前宿主 `NativeTurnBridge` 尚无受控的逐轮偏好与策略输入，且原生正式入口仍受 NT3 单写入和删除传播约束。不得把宿主提示修改视为原生链路已统一；须接入并验证安全隔离、恢复、取消和来源后再完成 TA1。
