# 回答体验专项执行记录

## UX0：真实基线与契约冻结（2026-10-20）

开发基线 `2b5d5d6aa6080588ed9ba927a59d568984e4bb7a`，按 RESPONSE_EXPERIENCE_IMPLEMENTATION_PLAN 顺序实施。起始源码 SHA 保存于 `.runtime/response-experience/20261020/baseline/source.json`。已有主计划、QUALITY_BASELINE、.env.example、worker 修改及教材删除保持原状；不修改其他 worktree 或现有 8000 服务。

采用现有 LLMClient、单一 Markdown 管线、TaskService 与 SSE，不迁移整个聊天应用、不等待 LightRAG。事件字段严格采用计划第 4 节：`answer_delta/answer_replace/answer_state` 的 task_id、task_revision、answer_id、round_id、seq；最终 answer/done 覆盖正文，草稿不入正式历史。来源保存仍用 `[n]` 与 pdf_references；媒体只取本条回答的授权集合。尚未实施的事件不能算现有能力。

四入口：普通/Q5 经 main→TaskService→agent_loop_service 或 Orchestrator；选区经 pdf_selection_tutor；练习聊天经 exercise_task_tutor→practice_api；练习页面有独立帮助与历史渲染。四条链分别验收，不把普通聊天通过算作全部通过。

隔离 8012、独立 host.db/course.db、测试学生、可见 Edge，使用 Playwright 技能运行器完成五个合成问题的真实请求，保存原始 SSE、原始页面消息及截图。模型 deepseek-flash；embedding 配置 cpu、rerank 配置 cuda（配置值不等于每次实际设备证明）；原 .env 未修改。原默认 LOCAL_AGENT_LOOP_ENABLED、Q5 开关未设置，本组是旧编排路径基线，后续 Q3 另验，不能混报。

| 合成样本 | 结果 | 页面总时间/秒 | SDK 调用数 | 返回 total_tokens | 引用 |
| --- | --- | ---: | ---: | ---: | ---: |
| 自变量概念（首次冷请求） | answered | 20.221 | 5 | 16369 | 4 |
| 被试内/被试间比较 | answered | 9.651 | 5 | 19692 | 4 |
| 韦伯定律公式 | evidence_rejected | 1.532 | 1 | 2555 | 0 |
| 三类变量表格比较 | answered | 12.768 | 5 | 19781 | 4 |
| 第一章详细规划 | evidence_rejected | 5.229 | 3 | 11718 | 0 |

五组均没有 `answer_delta`；保留两组真实失败，不算五组业务通过。首次请求单列，不与热请求平均后宣称加速。SDK 调用次数由隔离服务器捕获 create 边界；SDK 内部 HTTP 重试不可见，未伪报 0；未配置价格，不推算费用。原协议没有足够时间戳，未伪造每阶段耗时；后续事件补齐时再做同组对照。

结构化汇总见 RESPONSE_UX_BASELINE.json。原始证据、模型调用计数、环境、截图在 `project/integration/discrete-math-tutor/.runtime/response-experience/20261020/baseline`；启动器正常关闭测试服务。用户未提供原始失败请求，全部明确标记合成样本。选区/练习入口的独立基线和联合验收仍待补齐，不标记 UX0—UX5 整体完成。

## UX1：数字上标与按需证据

保留原 `[n]` 保存协议、DeepTutor Markdown 与原阅读器；正文渲染数字上标按钮，不再默认展开来源列表、原文和裁图。点击后显示本消息的原文、版本、定位精度；原文跨消息同号不串。引用采用稳定 renderKey，而非会随消息重排变化的数组下标。旧历史无编号时可按需选择其来源；未知编号不猜第一条；失效记录保留可读内容但禁用跳转。练习帮助复用同一个上标/弹层入口。

新增只读 `/api/course/citation-state` 在点击打开教材前复核文档、实际 PDF 字节及发布身份；不重定位或升级历史。富文本失败仍显示可读正文。新增 AST 处理为宿主适配，不更改 vendor 源码；源码、锁文件和原版权许可沿用，没有新增依赖。

发现并保留的失败：一条测试误把空 evidence 当作非空损坏协议；改用真正缺字段的协议夹具。首轮浏览器 12 个检查通过，最后窄屏检查因未切到对话视图失败，历史副本经核对有完整 10 条消息，并非数据库丢失。截图另发现上游主动跳过 `**术语**[n]` 的引用，补 AST 正文节点转换并加入“全部实际引用”断言；代码、数学、普通数值数组及链接保持原义。

验证：`npm run build:chat` 通过并同步产物；`node --check frontend/app.js`、基础文字降级测试通过；`python -m unittest tests.test_response_citations -q` 19 项通过（含导入的实际 PDF 基础用例）。可见 Edge、真实测试历史和实际教材接口：`.runtime/response-experience/20261020/ux1-release/citations.json` **18 项通过**，覆盖桌面/375px、键盘/焦点、精确原文、实际版本跳转、刷新、重复编号、跨消息重排、旧历史、失效/未知编号和练习入口夹具；两种视口截图已查看。首轮失败与后续运行分别保留。

本阶段不宣称真实正文流式、教材原图入正文或四入口模型验收完成。UX2—UX5 按计划继续；8000 服务未动。
# UX2：排版与任务预算（2026-10-20）

解除 RESPONSE 的统一三段限制及 Q3 的 400 字限制；普通概念与仅提示保持短预算，明确详细/全书规划说明使用 1800/2400 字、4800 tokens 上限，生成与质检共用。既有 Q5 结构化计划直接展示，不另调模型，11 章 132 目标的最后目标保留测试通过；这不代表全书规划业务完成。

现有 renderer 增加 streaming/settled 生命周期、缓存键与解析异常文字降级。复用固定 DeepTutor 源码已有 repairChineseEmphasis，解决中文标点相邻强调；未添加依赖、未修改 vendor。构建 555.63 kB / gzip 171.66 kB，许可产物保留。

验证：`python -m unittest tests.test_reply_budget tests.test_q3_entrypoint tests.test_q3_task_loop -q` 20 项通过；新增 Q5 完整投影后单独 `tests.test_reply_budget` 13 项通过。`node tests/browser/answer-emphasis.node.cjs`、`node --check frontend/app.js`、`npm run build:chat` 均通过。`tests/browser/response-format.cjs` 可见 Edge 中 8 个标准样本和 UX0 真实 concept 回复共 9 类通过逐字符增量、完成/历史一致、公式、表格、代码、中文强调、HTML/URL 和 375px 检查；截图已查看。

证据：`.runtime/response-experience/20261020/ux2/format.json`、`format-mobile.png`，同级 ux2 日志。首轮 runner 相对路径错误、缺少正式 KaTeX 样式的夹具溢出、中文强调实际失败记录保留。最终复验加载正式 reader.css。未用这些排版夹具代替 SDK 真流式或四入口真实模型验收；UX3—UX5 仍待实施。

## UX3：实际正文流与发布状态（2026-10-21，主体提交，联合验收未完成）

基于 `78fb20f`，保留全部原有教材和其他窗口改动。SDK stream→请求内 AnswerEvents→TaskService→现有 SSE→transport→稳定消息节点贯通；普通 ResponseGenerator、PDFSelectionTutor、Q3 探索/收尾及练习帮助接同一入口。直接练习按钮复用 `/api/chat/stream`，旧帮助接口兼容；评分仍走原确定性/JSON 路径。没有新增 token 持久表或额外答案生成。

迁入固定 DeepTutor `6cf793bd868ba5ecbe64722936d4be8fab5a01df` 的 `tool_call_stream.py`、`think_stream.py` 并保留 Apache-2.0 LICENSE；事件发布与宿主接线为本项目适配。工具参数、reasoning_content 和 think 标签不作为正文。stream_options 不兼容仅在首个流创建失败且明确 400/422 时回退一次；流开始后不自动重播。length/缺失结束标志/未执行的收尾工具调用不得发布成功。取消 guard 在迭代和提交前检查并关闭 SDK 流，断线仍使用原请求收据恢复；正式历史不存草稿。

事件协议仍为计划第4节；最终完整 answer/done 覆盖草稿。新增可选 ChatRequest.exercise_help、exercise_hint_level，旧调用无需传参。正文核验拒绝先清空草稿，最终显示拒绝原因。此事件上下文只在请求内存在，未绑定调用者仍取原完整返回值。

本次复查另发现真正的排版问题：保护文本恢复时 replaceAll 的字符串替换将 `$$` 解释为转义。改为回调原样恢复，补独立公式断言并重新构建（557.14 kB/gzip172.18 kB）；没有修改 vendor 或新增依赖。初期误读 runner 额外空行导致的堆栈偏移，已通过直接执行原文件定位；不是工作区版本不一致。

### 已留存的模型和页面证据

所有运行均为隔离 8012/独立 host.db 与 course.db，正式 8000 未切换；测试服务完成后关闭。路径位于应用 `.runtime/response-experience/20261020/`，目录日期沿用原基线，各阶段独立。

| 同组案例（ux3-five） | 请求完成秒 | 首次正文秒 | SDK调用/total_tokens | 结果 | 页面领先模型流关闭毫秒 |
|---|---:|---:|---:|---|---:|
| concept | 68.845 | 60.510 | 5/16237 | saved/刷新一致 | -50.310（本次未达提前显示门槛） |
| comparison | 42.204 | 29.013 | 5/19935 | saved/刷新一致 | 2714.784 |
| formula | 4.352 | 无 | 1/2554 | 来源拒绝 | 不适用 |
| table | 42.844 | 34.288 | 5/16486 | saved/刷新一致 | 1681.134 |
| planning | 10.713 | 无 | 3/11770 | 来源拒绝 | 不适用 |

不能宣称整体加速：concept 的 citation-selection 阶段约45.9秒；comparison/table 相比 UX0 总时间退化。SDK create 计数不代表内部所有 HTTP 重试可观测；stream 设置 max_retries=0。未提供计价，未猜费用。

`ux3-retry` concept 请求64.595秒，首次正文43.947秒，领先关闭335.395毫秒；旧页面计数71.176秒包含刷新，不当作请求时间。用户要求“重试”后 `ux3-user-retry-2` 请求41.707秒，首次正文36.090秒，模型实际流输入/输出和历史一致均留存。此前代理不通、错误案例参数、连接失败都保留，不改写为成功。

Q3 `ux3-q3` 三次真实流/工具调用但检索原文为空，门禁拒绝且未保存；`ux3-q3-chapter` 同样拒绝。不能把旧 Orchestrator 页面通过算成 Q3 来源接通。后续统一 Q3/Q5 search 边界处理，保留事实门禁。浏览器截图另暴露旧自动配图返回不相关二维码，记为 UX4 待修复。

### 定向验证和未通过项

`node --test tests/chat-transport.cjs` 9通过；76项后端组合已通过，新增收尾工具调用负例后重新运行结果见 `ux3-backend-final.log`。命令：`.venv/Scripts/python.exe -m unittest tests.test_answer_stream tests.test_reply_budget tests.test_q3_agent_loop tests.test_q3_task_loop tests.test_q3_entrypoint tests.test_quality_guard tests.test_task_api -q`。

真实 Edge 执行 `tests/browser/chat-lifecycle.cjs` 全部检查通过，日志 `ux3-lifecycle-final-v2.log`，覆盖进度/焦点/公式节点保留、拒绝、断线不重生成、删除失效、引用及练习兼容、390px。`tests/browser/response-format.cjs` 增量/重放/独立公式检查通过，报告 `ux3-format/format.json`。构建通过。SDK迭代器、取消后不保存、工具参数分片/配对、收据重放及练习提示级别由离线夹具验证。

仍待：PDF选区/实际练习/Q5路径/ask_user恢复/取消的真实模型页面联验、延迟关闭替身的浏览器端断言、工具线程实际退出时间、UX4像素/展示/历史链及 LightRAG 统一接线。当前心理学题库为空，未用旧数学题库测试伪造练习真实验收；test_interactive_practice 只同步其 mock 调用契约，未宣称整模块通过。UX3—UX5不标整阶段完成。

## UX4 / 公共检索接线增量（2026-10-21）

收尾状态更新：见 [UX0—UX5验收矩阵](RESPONSE_UX_CLOSEOUT_MATRIX.md)、[运行准备与回滚](RESPONSE_UX_ENABLEMENT_RUNBOOK.md)及指标JSON。业务基线be8daa7的已提交导出宿主重新验证161项后端、9项传输、生命周期和8类格式；f0886a0补上A07真实HTTP延迟关闭夹具，提交后完整浏览器重跑通过。5374个导出文件未改写，备份命令在2份隔离WAL库通过；正式库未备份/改动。真实课程11章练习仍为0。未新增网关调用、未重跑成功跨章Q5整条，不拼接历史子流程。8000当前未运行，主venv缺一般检索依赖，回答体验暂不整体启用；LightRAG独立判定为不可正式切换。

后续联合交付：见 [LIGHTRAG_JOINT_INTEGRATION_REPORT.md](LIGHTRAG_JOINT_INTEGRATION_REPORT.md)。已在e3b7073上合并完整LightRAG交付祖先链，接入CoverageNavigator/ContextualRetrieveCourseTool与Q3/Q5公共search。当前混合工作树161项通过；精确教材、PDF追问、ask_user恢复、取消/断线刷新、同图像素质检及页面分别有隔离实证。网关专用凭据缺失，原跨章检索、真实partial与成功跨章Q5闭环仍阻塞，不记为LightRAG通过；未切正式索引、服务或ready标记。早期失败与完整指标见上述报告。

本批交付详见 [RESPONSE_UX_LIGHTRAG_HANDOFF.md](RESPONSE_UX_LIGHTRAG_HANDOFF.md)，分别登记代码、真实模型和浏览器证据。以 d3d6a76 为接口候选基线，不切换正式检索。Q3/Q5共用search、关联候选、临时像素消息、正文媒体、版本与历史恢复已接入；图5-2真实像素/质检/页面/刷新和Q3精确教材讲解已验证，其余入口仍保留待验。

重点修复每个流式增量重算全书哈希的问题，同题隔离实测183.106秒→12.488秒；保留模型轮、核验与保存的完整版本门禁。旧313/339字失败草稿在最新门禁及真实事实质检通过；跨章缺第1章仍失败，未冒称覆盖改善。已确认二维码原图误配并过滤，当前178个pending/45个过滤项，未改变审核状态或原教材文件。

本次后端组合167项、追加Q5入口边界7项、Node transport9项通过；375px真实图5-2页面的上标、正文媒体、返回实际小节、410失效及刷新零额外生成5组通过。完整命令、原失败和剩余四入口联验、切换/回退边界均在交付文档，不标整阶段完成。
