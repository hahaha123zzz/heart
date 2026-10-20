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
