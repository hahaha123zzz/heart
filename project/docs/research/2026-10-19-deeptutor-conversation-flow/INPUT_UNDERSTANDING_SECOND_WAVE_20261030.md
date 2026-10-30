# 输入理解层第二批实现与验收记录

日期：2026-10-30。分支 `codex/input-understanding-v1`；首批基线 `5e143d8`。所有真实模型和页面验证使用独立服务、隔离 SQLite 和测试学生，未变更正式数据库或 8000 端口。开关默认关闭；本文记录不代表整项计划完成或已正式上线。

## 本批实现

- 结合当前学生、会话、有效期和记忆版本，绑定已发布回答中的示例、实验描述与明确陈述；有多个候选时澄清，选择后恢复原任务及对象。用户提供的教学示例不升级为教材事实。
- 增加服务端执行决策；模型可读取获授权的学习状态，学习状态变更仍由既有服务执行。多种状态写入混在一条请求中时拒绝自动执行。
- Q5 学习路径插问不推进原目标；同一明确偏好重复确认不重复写入审计记录。此项不等于所有状态命令已经实现跨请求幂等。
- 支持已验证教材图的连续追问：同一会话重新绑定对应原图，并以本轮实际送入模型的图像决定 `model_saw_pixels`。按图号先筛选候选，避免检查全书无关图。
- 统一教材来源验证所用的索引，避免同一句在全书多次出现时，与现有已发布引用的精确位置校验发生冲突；保留引用范围及身份校验。
- 复杂输入的规则升级、语义解析提示及受控证据预取补充了顺序、多对象和范围约束；继续保留解析失败和回答失败的明确状态。

## 检查结果

- 最终相关 Python 回归 188 项通过，日志 `.runtime/input-understanding-second-wave-20261030/final-consolidated.log`。前端 JS 语法和 interaction-style 检查通过。
- 100 条工程标注的输入与上下文组合通过规则回归，实际为 99 个不同文本、其中一个文本有不同上下文；这不是独立教师标注集，也不代表模型语义准确率。20 组多轮场景通过受控 HTTP、SQLite 与替身回答测试，不等同于 20 组真实模型页面验收。
- 原生学习授权相关回归 20 项通过，使用既有受控夹具；不代表原生正式题卡、复习按钮已完成本输入层页面验收。
- 真实浏览器测试：历史两例的候选澄清、刷新、选择第二项并恢复原任务通过；图 5-2 首问及追问和图 1-4 均回答成功，三轮实际模型请求均包含图像。PDF 文本选区页面链路和连续追问通过，选区坐标由真实 PDF 程序取得并传入页面处理器，并未模拟鼠标拖选。
- 真实模型复杂输入矩阵 8 项中 6 项回答、2 项解析回退后因模型输出内部工具协议被拒绝；记录在 `semantic-final/matrix.json`。不能将回答状态当成多维语义质量已通过。
- 10 个相同普通问题的新旧入口隔离对照：active 回答 9 条、1 条 `quality_rejected`（“什么是自变量？”模型输出内部工具协议），旧入口 10 条回答。包含失败样本的总耗时中位数分别为 2.921 秒和 2.772 秒；首字中位数分别为 1.569 秒和 1.489 秒。两组使用不同空会话与隔离库、串行运行、同教材和阅读位置，不是同一数据库快照，也未评判答案质量；不能据此断言加速或正式环境性能。结果保存在 `semantic-final/paired-active.json` 和 `baseline-paired/paired-off.json`。复杂解析回退的修复没有覆盖这次简单规则问题中的协议输出失败。
- `test_memory_management` 整组有 2 失败、1 错误；原工作区对同组仅复现其中 1 失败和 1 错误，另有环境和夹具差异尚需定位。相关的重复偏好确认专项通过，不能宣称整组回归通过。
- 首轮 30 条复杂输入保留了失败及解析回退；24 条发生模型解析，不满足 30 条观测计算分位数的条件。修复前固定版本的第二轮 30 条均回答，其中 29 条模型解析、1 条回退；30 次请求均发起解析，解析耗时 P95 2.925 秒（25 条一次调用、5 条两次调用），总耗时 P95 7.612 秒，首字 P95 6.159 秒。原始记录为 `semantic-final/performance-complex.json` 与 `deep-trace.jsonl`。这是单次隔离服务、不同题目的观测，不代表正式环境性能或语义正确率。
- 定位矩阵中两个内部工具协议失败时，复杂解析回退没有预取教材依据；新增回退时按原问题只读预取，相关集成及任务循环回归 28 项通过（`fallback-prefetch.log`），修复后同一 8 类真实模型矩阵均返回回答，其中两条仍是解析回退；日志 `semantic-final/matrix-after-fallback.json`。仅表明本轮可发布，尚未完成语义人工评分。

证据位于 `E:/项目/heart/.runtime/input-understanding-second-wave-20261030/`，包含成功与失败日志、浏览器截图和隔离数据库；其中 `acceptance2/reference-browser.json`、`figure-rerun/figure-live.json`、`figure-rerun/pdf-selection-browser.json` 分别对应上述页面、真实图像和 PDF 选区检查。运行产物和数据库不纳入 Git。

## 未完成与发布边界

1. 复杂语义解析仍存在回退；内部工具协议导致的两条复杂输入失败已定向修复并重测，但普通问题对照中仍有一条内部协议发布失败，需继续定位。尚需独立人工标注和语义质量评估。
2. E01—E16 尚未全部完成真实模型及页面验收；包括原生正式题卡/练习/复习、完整多窗口并发、流式取消与迟到写入、选区鼠标拖选和完整 Q5 页面流程。
3. 待完成同一状态快照的 shadow 新旧对照、10 组有可比条件的端到端速度对照，以及重启/关闭新入口后的 pending 恢复验证。
4. 现有重复确认优化不等于所有命令、断线和重试都已实现全事务幂等；新输入层未覆盖所有原生练习与评估入口。
5. 启用范围、清理旧判断、正式服务切换和主分支合并需要等计划内验收完成。本批保留原入口和默认关闭开关。

## 后续修复与重启验证

- 普通问题中模型把工具协议写成正文时，不解析或执行模型伪造的工具名称和参数；仅在本轮已授权教材检索、且没有其他未满足的必需工具时，以原始用户问题执行一次教材检索。成功后带原文和图片交给模型收尾；无来源时明确失败。该行为仍由既有 AgentLoop、授权和来源校验控制。
- 离线相关回归 `protocol-repair-final.log`：124 项通过；之后补充的图像临时消息调整及回归 `protocol-repair-final2.log`：54 项通过，两组有重叠。覆盖伪造工具参数、没有来源、必需工具、图像传入和非持久化。
- 真实模型定向测试注入一条模拟内部工具协议，随后的教材检索与回答调用真实系统和模型；自变量、因变量两条均 answered，均有 3 条来源。证据 `protocol-repair-live/forced-final-ready.json` 和 `deep-trace.jsonl`。这是受控故障注入，不是模型自然复现频率测试。启动尚未完成时两次连接失败保留在 `forced-final.json`、`forced-final-retry.json`。
- 隔离服务实际重启两次：先用真实模型生成两个例子并产生待澄清，关闭输入理解层后返回 `input_mode_disabled`；重新启用后在同一隔离数据库恢复原 task_id，选择第二个例子并得到对应解释。证据 `protocol-repair-live/restart-pending.json`、`restart-off.json`、`restart-on.json`。此项为真实 HTTP/模型验证，并未覆盖浏览器重启交互或所有待办类型。
- 修复后的 10 条普通问题真实模型自然运行均 answered，记录在 `protocol-repair-live/natural-10.json`；样本量有限，尚未人工评判回答语义。仍需完成独立语义评分、完整页面/原生入口、同快照影子对照、并发取消与状态幂等验收；原 `test_memory_management` 整组失败后续已定位并修复测试夹具，见下节。开关默认关闭，本轮没有更新正式服务或 main。

## 后续补验：记忆、shadow 和重启页面

- `test_memory_management` 先前在心理学配置出现 2 失败、1 错误，原因是原离散数学测试夹具只替换 `retrieve_hybrid`，心理学路径调用 `retrieve_course`；选区夹具也缺少心理学引用索引要求的 record。删除竞态专项现显式注入教材来源，并在该专项关闭引用索引；增加生成或检查确实已触发的断言，未更改生产代码和删除断言。修复后心理学、离散数学配置均为 17 项通过，日志 `memory-psych-fixture.log`、`memory-discrete-fixture.log`。这是隔离替身来源测试，不表示引用索引和真实模型的删除竞态已验收。原失败记录保留。
- 对同一 SQLite 备份快照分别执行 off 和 shadow，共 4 个输入（历史对象、否定选项、偏好、禁止出题）；受控 HTTP 与替身回答下两者的返回和对话记录一致，shadow 记录理解但不产生执行决策。`shadow-snapshot.log` 中 `test_input_reference_flow` 共 9 项通过。该对照不替代真实模型或全部入口的 shadow 评测。
- 真实浏览器与真实模型：先产生两个例子并等待对象澄清，停止并重启隔离服务，再以同一学生与会话重新打开页面，点击第二项后同 task_id 回答正确对象；无 pageerror。数据与截图在 `protocol-repair-live/browser-pending.json`、`browser-resume.json` 和对应 PNG；此前 off/on 回退为 HTTP 测试。
- 原生复习及来源授权 `tests.test_native_review`、`tests.test_review_authorization` 共 19 项通过，日志 `native-review-input.log`，运行于隔离环境与受控夹具；不代表输入理解层已经覆盖正式题卡或复习页面入口。
- Q5 真实模型与浏览器：生成 20 分钟、只讲解的计划 → 点击确认 → 插问信度 → 返回原活动，四步状态符合预期；插问前后 SQLite `session_plan` 完全一致，返回后 `current_item_id` 未改变，页面无错误。日志和截图 `protocol-repair-live/q5-browser.json`、`q5-browser.png`。此项未覆盖显式下一步、路径切换和复习评分页面。
- 最新联合回归 `recovery-shadow-final.log`：90 项通过，覆盖记忆管理、对象恢复、shadow、多轮、Q3 循环及任务；题卡/复习前端 `learning-cards.cjs`、`learning-card-actions.cjs`、`learning-review.cjs`、`learning-review-recovery.cjs` 共 4 个测试文件通过。这些是受控回归，不替代正式页面的实际题卡/复习操作。
- 鼠标框选真实浏览器和真实模型：在第二章第二节通过鼠标拖动选中 PDF 区域并点击“向 AI 提问”，以 80 字内解释及 60 字内追问，两轮 answered，传入的 document_id 和 rects 相同，页面无异常。证据 `protocol-repair-live/pdf-mouse.json` 和截图。首次未限制回答长度时，模型两次生成 267 字触发现有 260 字限制，最终 model_unavailable；失败保留在 `pdf-mouse-generation-failed.json`，不能据此声称任意长度的选区提问已稳定。前几次脚本还遇到折叠章节和选到不可见文字层，调试记录保留。

## 选区回答篇幅门禁修复与取消验收（2026-10-30 续）

- 问题：真实选区提问曾有两次生成 267 字，仅因超过 260 字预算被判不通过，最终以 `model_unavailable` 结束，用户拿不到本已通过事实核验的回答。
- 原因：`pdf_selection_tutor` 生成用 `reply_budget(...)`，但核验时未把同一 `reply_maximum` 传入 `QualityChecker`，检查器自行按默认偏好重算（详细选区请求时生成可到 500 字、核验却仍按 260 字，必然失败）；同时“仅篇幅超限”被当作硬失败，两轮后整轮丢弃。
- 修复：核验沿用生成预算（`context['reply_maximum']` 单一来源）；仅当全部 issue 都是“回复过长”、且超出幅度不超过预算 10% 时，在事实与引用已通过的前提下仍发布，并在结果中记录 `length_overrun_chars`；超过放宽上限或含任何事实/引用问题仍拒绝，错误消息改为带具体原因。
- 回归：`tests.test_reply_budget` 16 项通过，新增“小幅超限仍发布”“大幅超限仍拒绝”“含引用问题仍拒绝”三个用例，并校验检查器收到与生成一致的 `reply_maximum`（`selection-budget-tests.log`）。
- 真实模型/真实 PDF 坐标：以第二章第 3 页“操作性自变量”区域选区复测此前失败的同一句“解释我框选的这段教材，不要出题。”及一次追问，两轮均 answered（218、211 字，各 1 条教材来源，`length_overrun_chars` 为空）；记录 `protocol-repair-live/selection-live.json`。本轮未再触发超限分支，超限分支由上述单元测试覆盖。
- 取消验收补充：`tests.test_input_understanding_task_api.test_cancel_during_generation_cannot_publish_or_save` 通过——理解完成后、生成中被取消时，返回 `task_cancelled`，不写对话、任务保持 cancelled 且释放活动槽；与此前“理解阶段取消”用例共同覆盖取消的两个时间点（`cancel-generation.log`）。
- 联合回归：上述相关 16 个测试模块 209 项全部通过（`final-with-selection-budget.log`）。
- 观察到的遗留现象（未在本轮修复）：该选区回答中出现 `==不可操纵…==` 形式的高亮标记，页面可能原样显示；是否需要清洗属于渲染层排版问题，另行处理。
