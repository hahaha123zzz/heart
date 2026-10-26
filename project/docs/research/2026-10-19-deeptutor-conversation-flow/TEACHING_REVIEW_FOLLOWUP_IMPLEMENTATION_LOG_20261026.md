# TA4首批：持久化回顾建议实施记录

日期：2026-10-26。当前为未提交工作区改动；未切换8000正式服务、正式数据库或发布状态。此批仅接通回顾候选，不代表TA4正式间隔复习完成。

## 实现范围

- 在现有“练习与复习”页显示回顾原因和上次章节位置，覆盖留有待答检查、辅助反馈需核对、曾请求换一种讲法三类情况。
- 复用已发布进度卡及既有对话保存：物理位置为`PDFCitationRow.reference.learning_cards`，历史API以`selection_ref`暴露。卡片增加可选的课程、回顾原因、历史位置及记忆epoch字段，无新增表、依赖或迁移。
- `agents/review_followups.py`只读取当前学生最近200条助教引用元数据，最多返回20项；同会话/目标只取最新快照，较新的无建议快照抑制旧建议。过滤其他课程、无明确元数据、已删除/旧epoch及畸形记录。不推测或回填旧历史。
- 保留既有薄弱项、错题入口，同知识点的旧薄弱项优先，避免重复显示。不调用模型、教材全书校验、记忆worker或正式复习调度器。
- 点击只打开聊天并填写复习问题，不自动发送、不强制出题、不恢复过期待答题、不改变阅读位置或学习路径；发送后重新走现有教材取证链路。候选明确标记`formative_unverified / requires_retrieval=true / mastery_credit=false`。
- 修复从学习页准备复习问题后输入框仍被工作区CSS隐藏的问题；用户消息不再误显示从共享引用记录继承的“旧来源”标签，助教引用保留。

## 实际定位及修正

最初读取临时任务快照。真实浏览器打开页面会调用既有pending接口，任务TTL清理会清空过期任务context/result，导致建议消失；该失败保留在`.runtime/teaching-modes/live/review-browser-before.json`。

最终改为读取已提交对话的最小进度卡元数据，保持任务清理契约，不延长临时任务寿命、不复制答案键。仅已成功保存的进度卡产生建议；历史位置只是上次记录，不声明教材当前版本仍有效。真正复习时须重新取证。

## 验证证据

应用目录：`project/integration/discrete-math-tutor`，使用已有`.venv-runtime`。

最终相关回归：

```powershell
& .venv-runtime/Scripts/python.exe -B -m unittest tests.test_review_followups tests.test_learning_cards tests.test_teaching_evidence tests.test_teaching_modes tests.test_task_execution tests.test_adaptive_tutoring tests.test_q3_agent_loop tests.test_q3_task_loop tests.test_q3_entrypoint tests.test_q5_learning -q
```

162项通过，92.826秒；日志`.runtime/teaching-modes/review-final-tests.log`。回顾与卡片专项20项通过；覆盖真实引用表读写、TTL过期、删除epoch、学生/课程隔离、最新快照抑制、API只读、旧薄弱项去重。`node tests/learning-cards.cjs`及`node --check frontend/app.js`通过。此前批次已记录的基线兼容失败不因本集合通过而改写。

真实模型运行`2f671d432c`：新建隔离合成学生，实际教材解释answered、1条来源、7.84秒。随后仅将该学生隔离任务的expires_at设为过去，通过真实pending接口执行清理；任务context确实清空，回顾建议保持不变。报告`.runtime/teaching-modes/live/2f671d432c-review-summary.json`；脚本`.runtime/teaching-modes/check_review_live.py`。该耗时为单次记录，不是性能保证。

Playwright使用同一真实历史完成13项检查：建议/原因/位置、无虚构日程或答案键、用户消息无错误旧来源标签、桌面和375px手机输入框可见、无强制出题、准备重新取证问题、章节/会话位置不变、无横向溢出、读取前后建议一致、零自动生成请求、无pageerror。报告`.runtime/teaching-modes/live/review-browser-final.json`，截图同目录`review-browser-final-list.png`、`review-browser-final-desktop.png`、`review-browser-final-mobile.png`；复现脚本`.runtime/teaching-modes/playwright-review-followups.cjs`。

所有运行只使用8026及`.runtime/teaching-modes/live/host.sqlite3`、`course.sqlite3`；本轮隔离服务在交付前停止，未操作正式8000。浏览器验证的是建议展示与准备问题，没有声称完成正式复习作答/评分流程。

## 未完成与后续依赖

TA4正式到期队列、RetentionScheduler/SpacedRepetitionScheduler联动、延后/完成/提醒、复习评分及掌握证据仍未实现；需先完成NT3原生学习服务单一写入方与正式证据契约。没有用辅助反馈冒充正式评分，没有另建第二套遗忘曲线或学习存储。

当前有界历史投影只覆盖最近200条带引用的助教记录，旧进度卡缺少明确协议字段时不产生新建议；如需完整长期队列，应在NT3统一存储中实现，不放宽扫描为全量历史。
