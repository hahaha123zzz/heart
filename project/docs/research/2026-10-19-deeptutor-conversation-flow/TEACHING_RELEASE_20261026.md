# 教学能力首批整合发布（2026-10-26）

本次从main基线`3a0b0fbcfec54a05102898b1c65660955ee5cb39`整合本会话已完成的教学改动。交付范围是教学业务、前端卡片、相关测试和本批记录；不包含本地教材删除、运行数据库/缓存、密钥、原生worker候选修改或其他窗口尚未交付内容。

## 已整合

- 直接讲解、引导、练习、复习的轻量教法选择，消费现有偏好，不新增必经模型分类调用。
- 真实提示/示例/解释辅助记录、原题关联与暂定反馈；不把辅助作答和“我懂了”当正式掌握。
- 分步展开、概念对比及只读学习记录卡，正文/来源一致，历史保存与展开恢复。
- 基于持久进度卡的回顾建议，显示原因及历史位置，临时任务过期后保留；点击准备问题，不自动发送或评分。
- ask_user恢复使用当前宿主系统约束，保留原任务、工具配对、引用和累计预算。
- 相同已生效误解更正不重复写证据或清后续摘要；新说明/误解重新出现仍可更正。删除知识点使旧回顾和旧epoch教学快照失效。

## 验证

发布前联合集合181项通过，102.284秒；应用日志`.runtime/teaching-modes/release-regression.log`，命令：

```powershell
& .venv-runtime/Scripts/python.exe -B -m unittest tests.test_review_followups tests.test_learning_cards tests.test_teaching_evidence tests.test_teaching_modes tests.test_task_execution tests.test_adaptive_tutoring tests.test_q3_agent_loop tests.test_q3_task_loop tests.test_q3_entrypoint tests.test_q5_learning tests.test_selection_loop tests.test_teaching_memory_corrections -q
```

卡片Node检查、`node --check frontend/app.js`、差异空白检查通过。此前真实模型、问题卡/选区及16项页面检查详见[多入口验收](TEACHING_ENTRYPOINT_ACCEPTANCE_20261026.md)，回顾建议及更正证据见对应实施记录。不同集合不相加成全库通过；已记录的旧编排`memory_commit`缺失错误仍保留。

## 本地运行

切换前8000无监听，使用已有`.venv-runtime`和`scripts/start_server.py --port 8000`启动当前本地应用。正式配置已设`LOCAL_AGENT_LOOP_ENABLED=1 / ADAPTIVE_TUTORING_ENABLED=1 / SELECTED_TEXT_AGENT_LOOP_ENABLED=1 / Q5_LEARNING_ENABLED=1`，启动清理保持`CLEANUP_EXPIRED_ON_STARTUP=0`，未复制或提交.env。

两个原SQLite已通过SQLite backup API备份并校验integrity_check，位置：应用`.runtime/backups/teaching-20261026-211951/`，包含原数据库与独立心理学数据库及数量清单。未用隔离测试库覆盖原库；无本批新增表或迁移。启动日志确认embedding/reranker均为CUDA provider，现有全书LightRAG运行时可加载；教材ready/审核状态未作修改，不据此宣称原生完整迁入完成。

实际8000教学冒烟证据在`.runtime/teaching-modes/release-smoke.json`，服务日志`release-server.log / release-server-error.log`。服务运行目录仍为原项目，其他本地未提交内容保持原样；这些内容不属于本次Git发布。

## 剩余与回退

原生NT3统一学习写入、正式评分、到期复习/延后/完成及全入口故障矩阵仍未完成。本次不是TA0—TA5整计划完成声明。

回退优先关闭教学增强开关`ADAPTIVE_TUTORING_ENABLED`并重启；如需回退代码，在保留当前库的独立检出中运行旧稳定提交，不能直接覆盖本地未提交内容或用旧备份覆盖新增学生记录。备份用于故障恢复，数据库恢复前须停服务并另存切换后的数据。
