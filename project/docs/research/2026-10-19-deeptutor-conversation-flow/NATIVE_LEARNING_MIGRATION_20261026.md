# NT3首批：Q5到原生学习存储的隔离迁移候选

日期：2026-10-26。状态：隔离候选与复验完成，本批作为源码交付，未启用线上迁移。当前8000沿用已发布教学版本`94fd212`的运行链路；旧Q5仍是在线写入方，原生候选没有接入HTTP、任务或页面，不双写在线学习状态。

## 1. 实际复用

固定vendor提交`6cf793bd868ba5ecbe64722936d4be8fab5a01df`，Apache-2.0。命令逐项核对models/storage/service/objective_relations源码SHA与`UPSTREAM_SNAPSHOT.json`，并确认实际导入位置在vendor目录内。

直接调用原生`LearningStore(root=...)`、`LearningStore.transaction`、`LearningTransaction.put_topic/emit`、`LearningService`和`validate_objective_relations`。原生事务同时提交路径、来源和迁移事件；CAS、并发串行化、事件及回滚均由上游负责。没有复制或重写SQLite存储、学习模型、掌握算法、复习调度器或第二套循环。

新增：

- `integrations/deeptutor/learning_migration.py`：按学生/课程读取只读Q5快照，严格构建候选，调用原生事务导入。
- `scripts/check_native_learning_migration.py`：只允许输出到应用`.runtime/native-learning-migration/`下的独立子目录；复制只读输入用于固定复验，拒绝输入/作用域变化后复用旧目录。
- `tests/test_native_learning_migration.py`：使用实际Q5 SQLite与真实vendor存储/服务，不是store替身。

候选只接受已确认且active的`mastery_goal`。教材导航仍由Q2拥有；教材路径、草稿、位置无法对应、无来源、未知/循环先修关系均明确阻断，不能猜目标或静默回到第一项。

## 2. 字段映射与未无损部分

| Q5字段 | 原生候选 | 限制 |
| --- | --- | --- |
| student/course/path身份 | 确定性的native book_id及学生/课程独立store目录 | 尚未绑定原生正式账户/工作区授权 |
| 模块、目标及ID/关系 | 原生LearningModule/KnowledgePoint，保持ID | 用上游关系校验拒绝未知目标、自依赖、循环与重复ID |
| source_refs | 原生TopicSource及完整host元数据 | available=false，需宿主重新核验版本与授权，不能当已发布证据 |
| 当前模块/目标 | current_module_id/current_kp_index | 只保留精确位置；尚未证明原生策略与教材游标的继续语义相同 |
| explained与摘要 | explained_objectives | 不产生掌握分、测验记录或复习事件 |
| understood/时间 | 迁移事件中的原快照 | 不转成qualitative_mastery或learner_mastery_override |
| 路径revision | 迁移收据保留原值，原生版本从1开始 | 不把旧revision冒充原生CAS版本 |
| 会话绑定/模式/本次安排 | 迁移事件保留原快照 | 未建立原生session/path membership或恢复执行 |
| 画像、旧命令回执、宿主辅助待答题 | 明确列入unmapped | 没有暗中填入默认掌握、重建题目或迁移全部聊天为事实 |

候选topic标为archived，报告始终`activated=false / ready_for_cutover=false`。原生formal evidence、quiz attempts、掌握字典、遗忘状态和review queue均为空；这不是正式学习迁移完成声明。原快照完整保存在原生迁移事件内作为溯源，不是新增在线学习库；CLI另保留的SQLite输入副本包含原课程数据，仅为本机私有运行产物，禁止提交远端。

## 3. 幂等与一致性

- 迁移事件记录scope确定ID、snapshot_digest和原Q5快照。相同输入重跑返回already_imported，不改版本、不重置之后的原生改名。
- 新输入或无对应收据的同ID路径拒绝覆盖。新候选应使用新输出目录，不能强制覆盖已有原生事实。
- 同时导入由原生事务保证一条迁移收据；事务失败回滚路径、来源和收据。保留原生CAS拒绝旧版本覆盖的能力。
- 输入只读事务固定一次查询视图；SQLite连接明确关闭，避免Windows文件句柄阻止清理。源表缺失报错，不当作零路径通过。
- 没有符合条件的路径或存在阻断时，`candidate_verified=false`，命令退出2；candidate_verified仅表示本隔离步骤通过，不能作为正式切换许可。

## 4. 实际验证

```powershell
& .venv-runtime/Scripts/python.exe -B -m unittest tests.test_native_learning_migration tests.test_q5_learning -q
```

42项通过，59.005秒，含11项迁移专项。日志`.runtime/teaching-modes/native-migration-final-tests.log`。覆盖原生存储/服务重启读取、目标非首项时位置保留、原来源范围、理解不等于掌握、重复/并发导入、快照变化拒绝、原生改动保留、CAS、事务回滚及CLI输出边界。

使用部署前已有备份`.runtime/backups/teaching-20261026-211951/ai_tutor.experimental-psychology-3.db`中的实际路径，在`.runtime/native-learning-migration/20261026-q5-candidate/`建立隔离候选：**1条路径、4模块、4目标**，原生LearningService成功加载，正式学习证据数为0。重复执行返回already_imported，无新副本。原输入文件SHA保持不变，8000健康为ok、mock=false。

证据：候选目录`report.json / roundtrip-check.json`；控制台`.runtime/teaching-modes/native-migration-candidate-attempt1.log / native-migration-real-rerun.log`。含私有路径/画像的数据库和收据只保留本机，不加入源码交付。

复现命令（用本机明确的学生/课程ID替换占位值，不要在聊天发送个人记录）：

```powershell
& .venv-runtime/Scripts/python.exe -B scripts/check_native_learning_migration.py `
  --source-snapshot .runtime/backups/teaching-20261026-211951/ai_tutor.experimental-psychology-3.db `
  --student '<学生ID>' --course experimental-psychology-3 `
  --output .runtime/native-learning-migration/<独立运行ID>
```

初次测试因只读SQLite连接未关闭导致Windows临时文件清理失败；显式closing后修正。第二次有一项测试错误假设目标数组第一项就是首模块第一项；已改为按真实current_objective_id定位。两次失败日志均保留，不作为通过证据。

## 5. 下一步门槛

先完成原生账户/工作区与会话绑定、Q2教材导航权威、原来源实时授权、画像/本次安排/旧命令和辅助待答题映射，并验证删除epoch传播，才能把迁入路径设为原生单写入。切换时须冻结旧写入或有经验证的写入路由，不能让Q5与原生同时推进。

之后才能在原生同一题目生命周期上接正式题卡、作答、评分与复习。当前未跑真实模型/浏览器/正式学习服务切换；不重启8000或修改发布ready标记，不据此完成NT3、TA2或TA4整阶段。
