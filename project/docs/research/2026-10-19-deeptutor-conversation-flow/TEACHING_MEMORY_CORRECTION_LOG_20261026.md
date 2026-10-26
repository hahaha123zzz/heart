# 教学记忆更正、重复提交与删除传播

日期：2026-10-26。范围：TA2误解撤销及TA5的TE10/TE14局部验证。工作区未提交；未启动或切换正式服务、未操作正式数据库。不代表自然语言纠错全入口、原生学习统一或正式评分已完成。

## 问题与修复

现有调用链为记忆设置页面 → `memory_api.correct` → `MemoryManager.dispute_misconception` → `MemoryManagementRepository.dispute_misconception`。接口已有学生归属、测试账户、字段和更正说明校验，沿用原接口与返回结构。

原方法每次生成新的UUID事件，即使该误解已经dismissed且说明完全相同，也会再次添加证据/审计、清空当前知识点摘要。因此网络重试或重复点击可能清掉更正之后的新摘要。四项新增测试修复前均失败，记录`.runtime/teaching-modes/memory-correction-before.log`。

最小修复：在原写事务内，误解已dismissed时读取当前学生、知识点、误解ID最近一条显式更正事件；若说明完全相同，直接返回原event_id，不再写证据、清摘要或重建索引。不同说明继续保存；误解重新激活后，同一说明也可形成新更正。仅相同的最近已生效更正属于重试；不做跨生命周期或任意旧说明的全局去重。

继续将更正标为`student_statement`、非独立证据；不增加掌握分，不把学生否认判断当作正式测验成绩。没有添加表、参数、依赖或第二套学习存储。

## 隔离SQLite与实际API验证

新增`tests/test_teaching_memory_corrections.py`四项，验证：

- 相同更正重试返回原结果，事件/证据/审计数量不增加，后来产生的摘要与原掌握估计保留。
- 新说明和误解重新激活后允许新的更正，不错误重放旧命令。
- 两线程并发更正仅产生一条更正事件，沿用既有SQLite `BEGIN IMMEDIATE`事务。
- FastAPI真实ASGI接口重复提交返回一致；其他学生无法操作，空白说明仍拒绝。

扩展`tests/test_review_followups.py`：先有误解标签和历史回顾候选；显式更正后，review API不再返回旧误解标签，仍可返回中性回顾建议；删除知识点后建议消失，旧epoch的教学快照不能恢复。没有把更正误当成需要删除所有独立历史求助记录。

最终命令：

```powershell
& .venv-runtime/Scripts/python.exe -B -m unittest tests.test_teaching_memory_corrections tests.test_review_followups tests.test_teaching_evidence tests.test_learning_cards tests.test_teaching_modes -q
```

51项通过，20.993秒；日志`.runtime/teaching-modes/memory-correction-final.log`。所有测试使用临时SQLite，无真实学生数据或模型请求，未改变正式数据库。`git diff --check`通过。

## 保留失败与准确边界

扩展集合`test_teaching_memory_corrections / test_misconception_updates / test_review_followups / test_teaching_evidence`共40项，39通过、1错误。错误为`test_real_turn_wires_updates_and_legacy_boolean_does_not_clear`返回缺少`memory_commit`，日志`memory-correction-tests.log`。

为对账，在同一当前宿主仅将本轮修改的方法替换为HEAD版本后复跑该项，仍为同一KeyError，日志`memory-correction-old-method.log`，脚本`check_memory_correction_baseline.py`，均在`.runtime/teaching-modes/`。这只证明该失败不由本次方法变化引入，不是整份HEAD工作树回归，也不将错误标成通过。完整旧编排测试兼容问题仍待处理。

本轮没有新增UI，未跑真实模型或浏览器；验证范围是实际ASGI、事务、索引投影和历史epoch失效。并发证明仅针对本项目SQLite；其他数据库的并发语义未验收。NT3原生单写入方、正式题目/评分、复习调度及完整删除/取消矩阵仍未完成。
