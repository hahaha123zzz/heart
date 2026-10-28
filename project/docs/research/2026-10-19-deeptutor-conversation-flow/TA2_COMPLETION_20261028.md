# TA2：正式题目、证据与误解记录交付

日期：2026-10-28。基线为TA1提交 `3ee1cb3a8e150aa8c52a133f989ad8b34bb5d856`。本批完成原生受管账户的测评代码及隔离验收；不切换正式服务、正式数据库或NT3写入方，不把代码接入等同于正式启用。

## 要求与落点

| TA2要求 | 本批实现 |
| --- | --- |
| 正式题目与私有答案 | 复用原生PendingQuestion、LearningService和LearningStore。宿主可信调用者提交题干、私有答案/参考答案、审核者、键版本及Q2来源；来源必须通过现有verified_sources且与任务教材版本一致。HMAC绑定学生、课程、会话、删除epoch、版本、完整题目、rubric和审核信息，防存储篡改。普通模型工具没有批准题目的能力。 |
| 出题结束与待答 | 原生MasteryQuizTool继续产生公开卡片并执行end_turn_on_card。已登记题目优先复用；无审核题目回滚，不能靠模型自报答案创建正式题。普通题卡下一轮的LearningTurnAdapter提交也接同一命令门禁，非受管账户沿用上游。 |
| 作答、插问、跳过、延后 | 冻结原始学生作答；有限自然语言规则复用教法、求助、自报识别，插问不清题或评分。跳过/延后走原生生命周期，不算掌握。选择题沿用原生选项文本/字母解析；含糊输入要求澄清。 |
| 实际帮助程度 | 仅实际published帮助写事件；记录三级提示、例子、完整解释、查看来源及发生时间。重复命令不重复计数。原生讲解发生在出题之后时，也保守排除独立性，不虚构提示次数。 |
| 正式证据与自评 | 使用原生LearningEvidence和原生规则评分，不新增评分器或学习表。记录原答、版本、审核来源、独立/辅助、提示次数；confidence沿用学生自报字段。公开摘要只给核验证据数量、独立/辅助数量、最近时间及未核验数量，不生成精确可信概率。旧辅助记录不升级正式成绩。 |
| 误解假设 | 补充信度/效度、相关/因果、自变量/额外变量三类规范类型。必须绑定已审核错误作答及原话子串；始终是候选假设，支持dismiss/resolve。修订答案键撤销相关假设，作废移除或撤销相应证据。 |
| 概念/设计与不可靠证据 | 开放题需要审核过的逐项rubric，评分绑定冻结原答和完整criterion集合；复用原生定性评估事务。unavailable保留未评分，不扣掌握。视觉题当前一律拒绝正式登记：原图来源尚未形成测评级像素证据接口，不把原图ID当看过图。 |

## 接口与权限

`integrations/deeptutor/assessment_api.py`注册四个私有POST接口：

- `/internal/heart/native/assessment/register`：可信宿主批准题目；接收EvidenceDecision，拒绝mock、缺来源和证据不足。
- `/internal/heart/native/assessment/status`：白名单公开投影、证据摘要及恢复。
- `/internal/heart/native/assessment/action`：present/message/answer/help/grade/review/skip/defer/void及误解假设动作。
- `/internal/heart/native/assessment/correct`：可信宿主复核后修订选择题答案键；概念题修改rubric须作废并新建审核题。

沿用桥接token、原生开关、任务revision、学生/课程/会话、教材版本和memory_epoch授权。每次操作前后重新授权，写事务仍使用原生SQLite和既有提交授权。注册/复核是持有宿主凭据的服务权限，不是学生按钮或LLM工具参数；本批没有教师登录/审核页面，隔离验收中的审核者为明确受控输入。

`AssessmentCommands`调用原生服务；`HostAssessmentStore`只在同一原生事务中加入门禁及收据。选择题结果必须与原生grade_answer对冻结原答的结果一致。并发评分依赖原生事务去重；command_id绑定动作和参数，旧命令重放不能跳过另一道新题。帮助、评分或审核失败，状态、事件和成绩一起回滚。

公开投影不含expected_answer、参考答案、私有解释、审核seal或命令收据。来源失效时隐藏题目正文并返回unavailable；登记、作答及评分均不能用失效证据。旧任务遇到删除epoch变化立即拒绝读写；跨库物理删除及新epoch完整历史重建仍按NT3/NT8交付，不据本批宣称完成。

## 上游复用

固定DeepTutor提交 `6cf793bd868ba5ecbe64722936d4be8fab5a01df`，Apache-2.0。实际复用：learning/pending.py、grading.py、service.py、storage.py、capabilities/mastery/tools.py及session/turns/learning_adapter.py。六个文件的SHA256与UPSTREAM_SNAPSHOT一致，登记在NATIVE_FULL_SOURCE_NOTICE.json。未修改vendor，没有第二个AgentLoop、全局替换LearningStore或新增模型必经调用。

## 验证

- 原生联合：41项通过，182.105秒，`.runtime/ta2/final-native-tests2.log`。包含正式题注册回滚、原工具出题结束、原答冻结、同题评分、并发一次证据、rubric、纠错、误解撤销、来源失败、私有HTTP和既有授权/提示回归。
- 补齐原生普通题卡提交适配后：18项定向通过，92.354秒，`.runtime/ta2/entrypoint-final-tests.log`。包含实际LearningTurnAdapter方法接线、插问保留、原生选项文本作答、重复提交和原工具权限隔离。
- 宿主最终回归：226项通过，89.176秒，`.runtime/ta2/host-regression-final.log`。覆盖教法、提示、辅助证据、偏好、现有卡片、Q3循环/入口、Q5、选区及检索桥接；集合与TA1同范围。没有把相互重叠的集合相加为测试总数。
- 真实Q2来源/真实模型作答/私有HTTP：`.runtime/ta2/live-final.json`，passed=true。使用当前第二章真实来源，版本`840d14cbc821fe3ea5b3735da78c76c51ad021abed9c57bcf8d5a18d945fa0e7`；真实模型仅收到公开题干与选项，返回原答A；评分正确，1次原生attempt、1条LearningEvidence，重复grade结果相同；两次插问保留同题。新桥接及新客户端从SQLite恢复结果完全一致。审核批准是受控输入，不能称为真实教师审核或浏览器通过。

专项测试使用真实原生应用/SQLite及真实宿主授权ASGI，模型和教师输入受控，Q2来源核验单测用明确夹具。私有HTTP测试实际经过FastAPI路由及白名单序列化，不能称为浏览器验收。

复验命令（应用目录，原生环境）：

```powershell
& .venv-deeptutor/Scripts/python.exe -B -m unittest tests.test_native_assessment tests.test_native_assessment_commands tests.test_native_learning_tool_adapter tests.test_native_learning_authorization tests.test_native_teaching_prompt -q
& .venv-deeptutor/Scripts/python.exe -B scripts/check_ta2_assessment.py --source-json .runtime/ta1/live-20261028/9b2502d2b2-direct.json --output .runtime/ta2/live-recheck.json
```

真实验收脚本加载现有真实宿主来源记录，并重新核验当前原文/版本；创建临时原生账户、临时宿主数据库与真实HTTP接口，不写正式库。真实模型只扮演学生，不作为教师批准来源；恢复使用新桥接/新HTTP客户端读取SQLite，不依赖页面本地缓存。

保留首轮真实脚本的原报告：它向模型提供教材原文却归类独立作答，不作为独立测评通过依据。最终脚本仅发送公开题干与选项，删除该提示后复验；未改写首轮结果。此前两次无完整结束标记的测试日志也保留，不计通过。

## 完成边界

本批交付可调用的原生测评闭环，不代表正式8000已启用正式评分。TA3题卡与教师动作页面、TA4调度、TA5真实学生多入口联合验收继续分阶段实施。真实教师审核、图像像素正式评分、跨进程服务重启和长期学习效果未验收；不能宣称“所有图表题可评分”或“学生已经掌握”。

正式迁移仍须按NT3/NT8核验单写入、删除及回退；未改ready标志或发布冻结输入，不迁移教材，不提交运行产物、密钥或数据库。

交付在TA1基线上创建独立本地分支`codex/ta2-assessment-20261028`；本轮不合并main或推送。TA2核心代码/隔离闭环完成，正式启用、真实教师/视觉及TA5全入口验收状态分别保留，不勾选后续阶段。
