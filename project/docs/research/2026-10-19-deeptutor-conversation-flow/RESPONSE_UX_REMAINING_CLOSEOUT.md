# 回答体验剩余收尾（2026-10-22）

业务版本 **421f87192b1c39a01c417ef4e54aa3f4a7a17640**，已推送。基线7143e2f，保留99aadf2官方DeepSeek查询迁移及完整LightRAG交付链。没有覆盖主目录已有计划、质量基线、worker、.env.example及教材删除；未复制其他worktree未提交代码。

本轮补齐真实partial、native取消/截止超时/晚到门禁，修复取消身份，并在修复后的同一提交完整重跑Q5。另准备本项目独立环境、固定代码和教材副本，一般本地检索已真实模型/浏览器通过。**8000没有启动，正式LightRAG没有切换，staging/ready=false不改。**

## 修复与接口

首次真实取消时，HTTP DELETE已取消数据库任务，但native仍继续，最终保存guard阻止发布。根因：新任务的原始ChatRequest.task_id为空，循环按request_id注册取消令牌，页面按已claim的task.id取消，二者不同。

421f871仅在`agents/task_service.py`执行边界构造请求副本，把已有task.id/revision传给三种executor调用（Q5、previous兼容、普通），没有改请求原件、持久化payload、HTTP协议、数据库或前端。调用方`run_agent_loop_turn`现按相同task.id注册/释放令牌，LightRagNavigator、CoverageNavigator和backend收到同一Cancellation。其他executor收到的也是既有字段，暂停恢复、幂等、Q5和入口回归均通过。

回归新增`tests/test_q3_task_loop.py::test_fresh_executor_cancellation_uses_claimed_task_identity`，先复现`None != 已claim任务ID`，修复后通过。相关111项49.569秒通过；独立安装环境/导出421f871再次111项61.106秒通过。

命令：`python -B -m unittest tests.test_q3_task_loop tests.test_q3_entrypoint tests.test_task_service_context tests.test_course_search_bridge tests.test_q5_learning tests.test_lightrag_backend tests.test_lightrag_coverage tests.test_lightrag_q3_adapter tests.test_lightrag_deepseek_query -q`。两次分别使用隔离库，日志见证据路径；datetime弃用警告保留。

## 真实模型与页面

汇总：[RESPONSE_UX_REMAINING_EVIDENCE.json](RESPONSE_UX_REMAINING_EVIDENCE.json)。最终native实例显式关闭SDK关键词缓存，真实请求`https://api.deepseek.com`；仅进程内global_config变化，没有修改候选policy、原文或核心索引。取消/晚到没有最终backend_calls时，以SDK起止事件记账，缺usage不当作零费用。下表外层SDK计数不含native，SDK边界也不等于全部HTTP重试。

| 独立故障用例 | 总秒 / 首个草稿秒 | 外层SDK次数 / 返回tokens | native SDK次数 | 实际结果 |
|---|---|---|---:|---|
| 缺一方 | 35.257 / 31.945 | 5 / 11152 | 3 | 第1章实验程序有证据，第2章火星玄武岩晶体结构无证据；3次检索、1次补查后partial，明确缺口，不编造联系；只有第1章有效上标；保存及刷新一致 |
| native中取消 | 4.941 / 无 | 1 / 2390 | 1 | 观察到真实SDK进行中才DELETE；SDK/query结束为CancelledError，取消后backend实际退出0.062秒；历史无助教回答，刷新无复活，Q5完全不变 |
| native截止超时 | 26.399 / 25.469 | 3 / 7500 | 3 | 进入真实SDK后注入50ms截止时间；3次有界尝试后质检拒绝，所有SDK与native查询已结束，无保存/推进/刷新复活 |
| 真实晚到结果 | 11.437 / 无 | 1 / 2392 | 1 | 真实检索得到6条来源后暂扣；取消后释放6条真实原文，backend退出0.025秒，外层guard拒绝；无发布/保存/推进/刷新复活 |

超时是明确标注的隔离故障注入，不冒充网关自然超时。不能由本次退出速度承诺所有不可中断底层工作都能强制终止。TLS策略仍是SDK内部重试0、adapter最多3次；先前故障/单测记录保留，本轮没有人为破坏官方TLS或无限重试。

取消和晚到的最终响应可能是task_conflict，而非task_cancelled；取消API返回task_cancelled、数据库guard拦截旧revision，不能只凭UI提示判通过。本次同时核对实际SDK/query/finalize/backend退出、无历史回答、刷新和完整Q5状态。

### 修复后单次完整Q5（关闭关键词缓存）

| 同一次流程 | 总秒 / 首个可见草稿秒 | 外层SDK / 返回tokens | 后端 |
|---|---|---|---|
| 生成计划 | 1.584 / 无 | 0 / 0 | 结构化待确认 |
| 确认与讲解 | 9.209 / 5.416 | 4 / 13358 | q2_exact |
| 原跨章题 | 44.034 / 1.209 | 8 / 17170 | lightrag；2次检索、0补查、无fallback |
| 返回原目标 | 7.080 / 2.823 | 4 / 11390 | q2_exact |
| 下一部分 | 11.986 / 7.503 | 5 / 17599 | q2_exact |

原题“第一章的实验程序和第二章的自变量控制有哪些联系？”：双方原文实际进入同一个正文模型请求，最终双方均有有效上标，6个带本轮原文链接的关联候选被消费且evidence_eligible=false。native另有2次成功官方keyword调用，usage单列在JSON。

1.209秒是可撤回的探索草稿，不是已证实正文。取得双方原文后的SDK首内容40.519秒、页面首增量40.524秒；不能用探索首字声称教材答案已更快。

插问前后完整Q5状态相等；返回同一objective_id；下一部分到“笛卡儿的哲学思想”且mastered=false；最后刷新一致。五轮来自一个新学生/新数据库/同次运行，不拼接旧结果。没有证明全书长期路径、全部教学循环或阅读器自动跟随目标翻页。

## 独立运行准备

- 本项目`.runtime/response-release-20261022/.venv`全新安装仓库requirements-lightrag.txt、requirements-local-rag.txt，pip check无冲突；sys.path不含其他worktree或主项目venv。完整发行版版本保留preparation.json。依赖范围未全量锁死，故这份已安装环境和快照才是本次实测对象。
- 从git archive导出421f871到同目录`code/project/integration/discrete-math-tutor`，5380个已提交文件测试后哈希不变。仅读本工作区教材，复制457项原始输入到独立目录并逐项核对哈希；不包含裁图缓存。独立输入测试后哈希不变，不重建原索引。
- 原临时fastembed缓存已缺失。公开embedding/reranker恢复到本项目`.runtime/model-cache/fastembed`；embedding匹配原候选签名才继续。主目录、其他worktree依赖不安装/修改。独立环境使用CPU，不能借CUDA旧结果宣称独立GPU部署通过。
- 独立8013、新live.db/live-course.db，实际调用官方模型与**local_llamaindex一般检索**，不是q2_exact/LightRAG/回退：17.225秒，首增量13.315秒，2次一般检索、6条引用，上标与刷新一致。该结果不算LightRAG通过。
- 主配置解析为两份SQLite文件。已用只读连接/online backup备份ai_tutor.db与ai_tutor.experimental-psychology-3.db，完整性均ok，源字节未改。备份位于`.runtime/response-release-20261022/backup-before-enable-verified`，摘要JSON含大小/哈希，库不入Git。准备脚本20秒faulthandler记录显示当时在逐项读归档文件，并非数据库备份失败；最终5380项对账完成。
- 8012/8013均已停止，8000无监听。固定运行来源、私有启动器及回滚步骤见[启用方案](RESPONSE_UX_ENABLEMENT_RUNBOOK.md)最新段。

## 失败与限制

首轮缺模型缓存，未进入native。最早夹具对partial校验不足，曾打印passed=true，该条无效，不计本次通过。随后保存门禁生效但native未停止的真实失败，促成421f871。另一次断言把合法no_evidence当失败，修正为显式允许success/no_evidence后从新库完整重跑。所有旧目录保留；热缓存运行也保留，不冒充关闭缓存后的冷调用证据。

独立安装最后的pip自身版本检查遇到TLS EOF，安装exit0、pip check和独立111项/真实检索通过；这不是模型/LightRAG故障，未反复重试。

**回答体验可启用范围**：已准备使用固定421f871、独立环境、local_llamaindex、CPU、Q3=1、Q5=0、后台记忆/额外生成图关闭的文本首批配置。一般检索、模型与页面、备份已有实证；具体8000启动尚未执行。原图、选区、AI练习保持已有功能与分项记录，但未在新独立环境全部重跑，不能说全部入口整体上线已通过。

**LightRAG切换结论**：仍不正式切换。partial/native退出/晚到及固定Q5已补齐，不再列作阻塞；剩余是候选绝对sidecar URI的部署可迁移性（本次仍用隔离读取视图重定位），独立环境LightRAG/全部入口联验及正式发布条件。不得把文件存在改成ready；教材仍staging/ready=false。全章概述、长期路径、Q5正式评分不在本轮扩展。

## 原始证据与复核

以下路径相对`E:\项目\heart`：

1. `project/integration/discrete-math-tutor/.runtime/deepseek-query-20261021/edge-regression.log`：111项共享回归；同目录serve_edges.py/run_edges.py/summarize_edges.py为本地隔离夹具/汇总断言。
2. `project/integration/discrete-math-tutor/.runtime/response-experience/20261020/deepseek-edges-421f871-fresh`：edges.json、四份SSE、native-events.jsonl、model-calls.jsonl、server.log、四张页面截图。浏览器断言已保存在`tests/browser/lightrag-native-lifecycle.cjs`，需上述专用/_edges隔离夹具，不指向正式服务。
3. 同级`deepseek-q5-421f871-fresh`：flow.json、五轮SSE、实际模型tool_inputs、原文与关联候选、阶段/usage、q5.png。原有lightrag-joint-flow.cjs执行，DS_QUERY_FRESH=1、DS_QUERY_PHASE为目录名。
4. `.runtime/response-release-20261022`：独立venv、install.log、independent-tests.log、固定archive/code、input-copy.json、preparation.json及preparation-check.log、一般检索general.json/SSE/png、server.log、model-starts.jsonl、私有启动器与两份只读备份。general.png、partial.png及q5.png已查看。

最终7项候选核心图/向量/原文/状态签名不变。检索缓存可有新项，冻结policy与正式索引不改。没有新建第二套循环、学习路径或LightRAG后端。
