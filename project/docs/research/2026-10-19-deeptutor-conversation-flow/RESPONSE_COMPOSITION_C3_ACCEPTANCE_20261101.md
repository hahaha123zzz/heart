# C3：文本内容块执行、检查点与恢复

基线c84593b，沿用C1/C2内容协议与现有TaskService/AgentLoop。实现范围为有原文证据的文本内容组合；视觉、练习题卡、ask_user及其他宿主快照仍保留原整轮流程。没有新建AgentLoop、数据库表、外部服务或全局任务调度器。

逐批入口要求：至少两个计划块，纯文字证据齐备，无必须先完成的其他工具动作；满足C1普通生成条件。单块、仅提示、待答题、显式卡片或附带像素资源的回合保留C1/C2路径，不强行拆开原有业务契约。

## 实现与边界

- `agents/composition_execution.py`：在现有循环取证就绪后，按有限依赖图的就绪前沿分批生成。同一前沿合并为一次模型请求，不对每个独立块分别起模型；依赖块等前置内容核验完成后才生成。全计划最多6块、累计最多8次生成，每批最多一次修订，沿用原活动时限和总字数预算。
- C1的ResponseComposer直接负责结构/来源/引句核验；复用Q2出版门禁。部分发布暂不宣称完成跨章/多对象覆盖，最后仍执行完整覆盖门禁。只发布通过核验的前缀，不把JSON token当正文。
- 按剩余模块分配批次字数，明确后续模块的职责，避免第一批提前生成所有案例并耗尽预算。此前已发布块不可改写；结构修订只处理本批失败部分。模型中断、缺证或调用预算耗尽保留合法检查点，不编造完成态。
- 原文引用按教材版本、原文范围和媒体身份合并。每批在已核验来源上追加稳定编号；后续出版器即使重排其临时编号，也不得改变已发布前缀。只保留实际引用，不为冻结编号展示无关底部来源。
- `database/learning_tasks.py`在原任务context保存检查点：计划、来源指纹、已核验块、已发布前缀、调用次数和累计活动用时。先原子保存，再发`answer_blocks`。ready任务在首次检查点进入executing，保持同一任务revision，兼容Q3未经过旧routing intercept的入口。
- 恢复前检查student/session、任务revision、TTL、记忆epoch、全部后续来源的PDF原件/版本及教材release_id；拒绝块身份重绑、缺失依赖、源数据变更和已删除对话。运行中任务120秒租约未过期时拒绝接管；接管递增revision，旧执行不能继续写入。
- 活动用时和生成次数跨进程保留。崩溃时尚未结束的调用按保守预留扣除，最多90秒且不超过原剩余时限；因此接近超时的活动可能只能查看部分内容、取消后重新提问，不能通过反复恢复刷新预算。完整对话已提交时允许仅补任务回执，不再生成。
- 最终完整对话与`final_result`标记处在同一个既有数据库事务；中断发生在对话提交后、任务回执提交前时复用原conversation_id，不再插入或生成一次。标记失败会回滚该次对话。Q5讲解记录使用稳定task_id命令键，避免恢复重复记一次讲解；不产生掌握分。

## 页面与兼容

- `frontend/chat-transport.js`消费`answer_blocks`：检查任务身份、revision、序号和正文/块一致性；拒绝乱序、重复、改写已提交前缀及取消后的迟到块。过程态显示“部分已核验，整轮未完成”，不冒称完整对话已经保存。
- 刷新读取宿主检查点，恢复原问题、正文、引用及继续/取消操作；明确点击继续才接管执行。断线只读取已有结果/检查点，不重新提交生成。
- `/api/chat/composition/pending`及`/api/chat/tasks/{id}/composition/resume`复用现有学生/会话和任务校验。已取消任务不能恢复。原文失效返回410，不能忽略。旧后端尚无可选C3接口的404/503只禁用恢复展示，不阻塞原对话，支持先更新静态文件。
- 两个开关同时为1才启用：`RESPONSE_COMPOSITION_ENABLED=1`与`RESPONSE_BLOCK_STREAMING_ENABLED=1`。默认均为0；只关闭基础组合开关时，恢复也停用，不会退回旧链路重做已保存内容。

## 验证证据

证据均在应用目录`.runtime/layer5/`，使用独立8051进程和`course.sqlite3`课程库。DATABASE_URL另指向未使用的host.sqlite3预留路径；心理学模式实际使用COURSE_DATABASE_URL指定的course.sqlite3。正式8000未重启，正式库和.env未修改；未重建或切换教材索引。

1. C1/C2/C3与任务/选区/流式相关核心回归112项通过，20.230秒，`c3-final-regression.log`。最终对话事务标记、删除后拒绝重放、任务回执窗口重用原conversation_id及标记失败回滚，最终C3专项16项通过，`c3-final-contract-current.log`；后补的小范围保护以专项为准，不将较早真实运行冒充全部最终文件冻结后的全量复验。
2. 前端传输15项通过，`c3-final-node.log`；包括旧后端兼容、410不可忽略、前缀稳定、幂等、断线只恢复、取消拒绝迟到块。内容渲染检查、Python编译和JS语法检查通过。
3. 真实模型普通两块发布通过，`c3-live-budget-fixed.json`：第一块3.938秒，第二块5.704秒，最终回执5.735秒。重复原请求复用同一对话与内容协议。这是单次观测，不能代替C4同配置延迟评测或保证后续模型延迟。
4. 跨进程故障注入：收到首块后终止本轮隔离宿主，客户端连接中断；4.453秒首块及中断记录见`c3-crash-fast.json`。重启8051后375px浏览器恢复同一前缀，刷新不丢失；等待租约过期后点击继续，只调用一次模型补剩余块，检索调用为空，首块文字和引用不变，最终刷新只有两个块。`c3-browser-recovery.json`、`c3-partial-recovered.png`、`c3-resumed-final.png`。
5. 真实取消负例通过：清除旧检查点后pending为空，再恢复返回410，`c3-negative-live.json`。错误会话恢复返回404也由真实浏览器验证。换版/release、记忆版本和最终对话删除使用隔离夹具验证，没有修改真实教材来制造失败。
6. 最终对话提交窗口使用真实临时SQLite事务测试：提交标记与对话一起保存，重新调用宿主服务不调用模型、不新增对话；标记写失败时会话插入回滚。该特定窗口未额外进行真实模型进程强杀，不冒充浏览器故障注入覆盖了所有毫秒窗口。
7. 最终事务标记接线后再跑真实两块问答与重复请求，`c3-final-live.json`通过；375px最终页面与刷新恢复通过，`c3-final-page.json`，无pageerror。隔离8051服务已停止。

## 保留失败与限制

- 第一条多动作真实输入“先比较自变量和因变量，再解释它们的联系”在进入C3前，现有覆盖拆分误取到“先”，导致RAGQueryTooShortError。`c3-live-first.json`保留；本批没有把这个第三/四层查询拆分问题写成已解决，应纳入C4缺陷与端到端评测。
- 初次例子生成把后续案例写入首块并占尽字数，后续块被拒绝。修复批次职责/预算；首次ready状态写检查点被误拒也已修复并有回归。失败分别保留在`c3-live-example.json`、`c3-live-fixed.json`，没有改写成通过。
- 首次进程检查脚本因系统权限不能读取进程信息，未计作有效故障注入；后续只终止已核对启动日志PID的本轮隔离进程，未操作8000。`c3-crash.json`保留。另一次真实首块耗时109.609秒，见`c3-crash-real.json`，说明外部模型波动仍存在；该检查点最终用于取消负例，未把它算成恢复成功。
- 旧澄清测试单独运行时受Q5表注册/环境影响；固定开关后65项中60通过、5失败。将TaskService恢复到c84593b源码、相同环境重跑这5项，同样5失败，见`c3-baseline-five.log`。这只是旧服务模块回放，不是整仓库detached验证；旧reader_action_replay字段等测试漂移没有在本批修改。
- 当前为文本有向依赖图前沿批处理，不是多模型并发工作流。图片像素解释与宿主题卡仍走原整轮发布，未宣称它们具有逐块恢复能力。C4教学效果评价、人工抽查与延迟/成本基准仍未实施。

## 复验

```powershell
.venv-runtime/Scripts/python.exe -B -m unittest tests.test_composition_execution tests.test_response_composition_adapters tests.test_response_composition tests.test_q3_agent_loop tests.test_q3_task_loop tests.test_learning_cards tests.test_answer_stream tests.test_selection_loop -q
node tests/chat-transport.cjs
node tests/response-composition.cjs
.venv-runtime/Scripts/python.exe -B scripts/check_composition_stream.py --base-url http://127.0.0.1:8051 --output .runtime/layer5/c3-live.json
```

故障注入仅针对自己启动的隔离进程，不复制日志中的旧PID执行终止。未切正式服务、未合入main、未推送。

## 2026-11-02 当前版本复验

- 当前基线为 `7b752ad`，包含第四、五层合并及第六层首批变更。工作区存在其他窗口的前端和文档未提交修改，本次未改动这些文件。
- 在当前工作区运行上述 C3 核心 Python 测试，**113 项通过**；`node tests/chat-transport.cjs` 的15项通过，`node tests/response-composition.cjs`通过。测试覆盖文本组合、检查点、恢复、任务、选区、流式传输和已有卡片适配；不等于全部浏览器场景实测。
- 使用单独的8054服务、隔离 SQLite 和现有教材索引，显式开启内容组合与逐块开关。健康检查为真实模型、固定教材索引就绪；`scripts/check_composition_stream.py` 实际返回 answered、两块内容，第一块13.609秒、第二块16.984秒；重复相同请求复用相同对话与内容协议。证据保存在应用目录 `.runtime/layer5/c3-current-20261102/live.json`。时间仅为一次观测，不构成性能比较。
- 本轮服务由其隔离关闭接口停止，未操作正式8000、正式数据库、`.env` 或索引。此次未重新进行浏览器跨进程故障注入，历史记录中的故障注入仍是 `c84593b` 后续实现时的隔离证据，不能当作当前版本新测。
- C3 的原定**有教材证据的文本分批执行与恢复范围已实现并完成上述复验**；视觉、题卡和 ask_user 保留原整轮流程。开关默认关闭。C4 的人工教学复核和充分的性能成本对照仍未完成，不据此声称已完成正式启用验收。
