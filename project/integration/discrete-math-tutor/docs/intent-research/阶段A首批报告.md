# 意图识别实施：阶段A首批报告

日期：2026-10-12。状态：首个20段离线批次完成；阶段A整体尚待扩样、独立人工审核和真实模型基线。后续B–F未实施。

## 已完成

1. RoutingResult 增加ok/unknown/parse_error/unavailable独立状态，保留旧五类流程intent。严格检查枚举、有限置信度、类型、长度及move_status一致性。空JSON、NaN/Inf及非法输出不再静默变为正常continue；缺失切换目标返回unknown。
2. 网关新增LLMJSONError（仍继承LLMError），区分不可解析JSON和模型服务失败，保留现有调用重试机制，不额外增加一次Router重试。
3. Orchestrator在失败状态下停止检索与教学，不记录学习证据、更新掌握度或推进课程；保留失败结果的reply和SSE进度接口。当前账户确保/创建逻辑仍在路由前执行，不将其误报为“完全零数据库操作”。本批测试只使用内存/临时数据库。
4. 新增seed20.jsonl：同一句指代在不同上下文、教材公式/证明/图片/表格、只给提示、作答检查、情绪+数学问题、换目标、纠正和未知能力。全部标记agent_authored、agent_reviewed_pending_human；不冒充真实学生数据或独立人工金标准，当前全属development，尚无盲测。
5. 新增scripts/eval_intent.py，支持mock、录制预测replay和显式real模式；默认mock不发外部请求、不初始化业务数据库。记录数据/路由版本摘要、按字段分母、动作宏F1、必要/误澄清、失败状态及扩展任务字段未支持情况。

## 验证结果

42项测试通过：tests.test_routing_validation、tests.test_intent_evaluation、tests.test_quality_guard、tests.test_evidence_recovery_flow、tests.test_memory_events。覆盖错误路径、真实隔离记忆不变化、旧构造兼容、评测分母与模板泄漏、教材引用/质检和学习事务。git diff --check通过。

修正一项既有测试断言：引用保存已在commit_learning_turn事务中，原test_evidence_recovery_flow仍检查旧append调用。使用HEAD旧Orchestrator复现相同失败后，改为检查事务参数selection_ref；未修改业务引用实现。

## 离线基线说明

修改前捕获既有mock预测，修改后以同组案例复测，旧四个字段结果一致：流程intent 15/20、student_move 15/20、needs_context 10/20、明确标注topic 1/1。

这些数字衡量的是旧的确定性mock夹具，**不是DeepSeek或本地小模型准确率**。本阶段解决输出可靠性和评测基础，没有宣称语义识别提升。新增learning_intents、answer_constraints、target_refs、missing_slots和能力状态暂未支持，评测明确列出。

生成报告：../../artifacts/intent/baseline-mock.json、validated-mock.json、legacy-mock-seed20.json。artifacts目录按项目现有规则被Git忽略；回归数据和脚本仍在tests/data/intent及scripts，可重新生成报告。

## 复现

在项目目录的PowerShell运行（以下默认离线）：

~~~powershell
$env:DATABASE_URL = 'sqlite:///:memory:'
$env:LLM_MOCK = '1'
.\.venv\Scripts\python.exe -X utf8 -m unittest tests.test_routing_validation tests.test_intent_evaluation tests.test_quality_guard tests.test_evidence_recovery_flow tests.test_memory_events
.\.venv\Scripts\python.exe -X utf8 scripts/eval_intent.py --output artifacts/intent/validated-mock.json
.\.venv\Scripts\python.exe -X utf8 scripts/eval_intent.py --mode replay --predictions artifacts/intent/legacy-mock-seed20.json --output artifacts/intent/baseline-mock.json
~~~

real模式需配置现有模型网关，可用--limit限制请求数量；本批未调用真实模型、未启动GPU模型或重启现有服务。测试存在原有datetime.utcnow弃用提醒，与路由修复无关。

## 接下来

扩展到120段并建立会话/模板隔离的60/30/30划分；独立审核标签与真实模型基线仍待完成。统一任务上下文是下一项功能改造：读取章节、选区/练习稳定ID和明确回答约束，向现有Router传入，避免只靠最近4轮猜测。阶段C持久化澄清与前端按钮尚未落地。
