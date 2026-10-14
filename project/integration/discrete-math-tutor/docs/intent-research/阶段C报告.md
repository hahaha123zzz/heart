# 阶段 C：可恢复澄清任务报告

日期：2026-10-12。状态：后端任务状态与接口批次完成；教材任务执行约束和前端完整交互待阶段 D/E。

## 1. 本轮结果

原先澄清只返回一句追问，下一次输入可能丢失原问题。现在服务端持久化原问题、待补字段、候选对象、经过验证的资源请求及任务版本。补充“第二个”或明确选项会恢复原问题与所选资源，然后重新识别本轮任务，而不是单独检索“第二个”。

借鉴调研中的槽位补充、有限状态机与检查点恢复思路，沿用当前 SQLAlchemy、Pydantic、MemoryManager 与 SQLite 事务实现；本轮没有复制开源项目源码或引入完整 Rasa/LangGraph。

## 2. 实现

|模块|变化|
|---|---|
|database/models.py|新增 LearningTaskRow、TaskRequestRow；学生删除级联；会话活跃任务与请求编号唯一约束|
|database/learning_tasks.py|认领、版本校验、收据重放、恢复、取消、到期内容清理；按学生和会话限定操作|
|agents/task_service.py|合并原问题与补充、候选选择、否定纠正、换题、澄清上限和失败收尾|
|models/chat_request.py|增加 task_id/task_revision/selected_option，校验配对关系|
|main.py|HTTP/SSE 使用相同任务控制层，提供待澄清恢复及取消接口|
|orchestrator.py、agents/pdf_selection_tutor.py|在教材生成前拦截澄清，在执行及保存前检查任务版本|
|memory/memory_manager.py|对话及学习事件保存事务内检查任务，防止取消/删除后的晚到写回|
|database/memory_management.py|知识点遗忘同时删除所属任务和收据；只有待澄清任务的知识点也可以删除|

状态为 ready / executing / awaiting_clarification / completed / failed / cancelled / expired。默认有效期 30 分钟、最多两次澄清，可通过 TaskService 的构造参数调整。没有足够信息时停止并要求重新选择；识别失败不会自动视为继续学习。

模型调用期间不持有数据库写锁。恢复前检查原任务，认领时再检查版本；选择新资源时重新绑定任务知识点与删除版本。最终对话/证据写入在同一事务内检查有效任务，新增任务存储本身不代表学生已经掌握。

重复 request_id 与相同输入返回任务最新结果，处理中返回 task_busy；同编号不同输入返回 request_conflict。初始请求在补充完成后重发，也不会返回旧版本的澄清问题。

## 3. 接口契约

首次提问沿用 POST /api/chat 或 /api/chat/stream，可增加 session_id 与 request_id。旧请求的会话仍为 legacy。

待澄清响应包含 reply、answer_status=awaiting_clarification、task_id、task_revision、clarification.question/options/missing_slots。补充请求携带同一 session_id 和 task_id/task_revision；可输入补充文字、“第一个/第二个”，或传 selected_option。

- GET /api/chat/tasks/pending?student_id=...&session_id=...：仅返回当前待澄清响应，不暴露原始任务上下文。
- DELETE /api/chat/tasks/{task_id}：请求体为 student_id、session_id、task_revision。
- 明确“我想学…”“换个…”等新任务表达在未指定旧 task_id 时启动新任务，取消该会话旧活跃任务。
- 老客户端未传 task_id 时，在该会话只有一个 pending 的情况下可自动接回任务；新版前端将明确传任务版本。

会话隔离复用现有学生身份边界，不构成新增用户认证。当前课程进度、掌握状态仍按学生共享。

## 4. 验证结果

最终综合回归 **106 项通过**，另追加 **1 项跨进程恢复检查通过**，共 107 项不同检查。完整输出见 [阶段C测试输出](阶段C测试输出.txt)。均使用临时数据库/模型替身，没有调用真实模型或改写实际学生数据库。

|组别|数量|
|---|---:|
|任务状态、恢复及删除边界|29（其中跨进程恢复单独追加运行）|
|HTTP/SSE 接线|6|
|上下文与资源校验|15|
|严格路由校验|10|
|隔离评测脚本|4|
|回答质量门控|6|
|教材证据恢复|3|
|学习事件事务|19|
|记忆管理与删除|15|
|合计|107|

具体覆盖：原问题保留；多对象“第二个”；否定旧对象；重复请求不执行；同编号改输入拒绝；两条并发补充只有一条认领；不同学生/会话无法操作任务；取消、过期及旧版本拒绝；识别或执行失败停止；生成中取消阻止对话与掌握度/证据提交；账户删除后不重建账户；知识点遗忘级联任务和收据；换选资源后删除范围同步；加法式建表不改变既有学习状态。独立 Python 进程读取同一临时 SQLite 文件，成功恢复原待澄清响应。

复现全部检查（PowerShell，在项目目录执行）：

~~~powershell
$env:DATABASE_URL = 'sqlite:///:memory:'
$env:LLM_MOCK = '1'
.\.venv\Scripts\python.exe -X utf8 -m unittest tests.test_clarification_tasks tests.test_task_api tests.test_task_context tests.test_routing_validation tests.test_intent_evaluation tests.test_quality_guard tests.test_evidence_recovery_flow tests.test_memory_events tests.test_memory_management
~~~

## 5. 当前边界

1. 这是后端确定性验证，不是 DeepSeek 意图识别准确率或教材解释效果验收。API 测试替换了生成器，未测试真实教材答案质量。
2. 当前浏览器尚未接入新 session_id、澄清选项和取消按钮；旧前端继续走 legacy。实际两个标签页的隔离交互待阶段 E，不把后端会话隔离当成已上线的标签页隔离。
3. 完整候选任务分流、仅提示/回答顺序的执行消费、练习按钮接线待阶段 D。当前恢复重新进入原有教材/PDF执行路径。
4. 到期内容在该会话下次提问或 pending 查询时惰性清理，保留收据编号和哈希。没有请求的会话尚无全局定时清理；账户清理仍会级联删除。中断的 executing 不自动重跑，原 request_id 返回忙碌到期；用户可以新 request_id 发起任务。
5. 并发验证针对本项目 SQLite 的 BEGIN IMMEDIATE，不代表已经验证 MySQL/PostgreSQL 多进程部署。
6. 未重启 8000 服务或操作实际数据库；启动新版时由已有 init_db 加法建表。真实发布与回滚开关验收仍待阶段 F。

## 6. 下一批次

阶段 D：让任务结果真正约束检索和回答。优先接入“仅提示、不透露完整答案”“解释/证明/例子”的执行差异，以及保守指代改写；保留教材原文、公式/定理号与 PDF 引用。随后阶段 E 把会话、选项和取消入口接到现有聊天气泡。
