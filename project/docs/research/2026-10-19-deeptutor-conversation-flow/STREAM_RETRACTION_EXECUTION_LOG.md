# 流式撤回专项执行与隔离交付

日期：2026-10-24。结论：功能代码及隔离验收可供集成；**不等于正式8000上线，也不满足无条件切换**。保留冷启动失败、旧基线失败和测试设施失败；未放宽事实、引用、视觉或260字门禁。

## 1. 身份与范围

- worktree：`E:/项目/heart-worktrees/stream-retraction`；分支：`codex/stream-retraction`。
- 实施基线：`9d5f5f6a49c7fda01932c63bef22d84e9d003641`；最终复核main已为`2803d8d7b7eae7bf160e367e2cc06a0e064cdba4`，没有自动合并或追赶main。
- 真实对照功能版本：`4cb2064bef8dac4451c865ddff99d6107de543df`；修复失败收据后的功能版本：`a693dfb3934a985720cb3d5b265a7b86d5d5025a`。浏览器断线脚本提交：`fb4f3ae02a58207afb485e4c877796ba515a927e`。文档提交见本分支最新日志。
- 原记录PID43028已失效；最终按8000监听复核为PID43308，cwd仍为`E:/项目/heart/.runtime/response-portable-20261022/code-proof-2ae1e5f/project/integration/discrete-math-tutor`，实际进程创建时间1792804788.4782672。没有操作该进程。不能以main版本代替运行版本。
- 使用18985/18986顺序对照、18987故障与Q5宿主、18988练习宿主，各自独立SQLite和测试学生；未复制正式学生库。reader源码及构建未改，旧reader哈希见原始身份记录。

## 2. 实际改动与调用点

| 调用层 | 改动 |
|---|---|
| `llm/client.py` | LLMError保留partial/finish/usage；读流及close错误均保留已收片段；finally关闭；SDK重试仍为0；连接、空闲和活动预算分别有界 |
| `llm/answer_events.py` | progress/answer角色、轮次归属、定点撤回；begin不清空全部正文；终态明确中断、截断、超时、取消 |
| `agents/agent_loop.py`及service | 教材问题先工具取证，保留ask_user等合法工具；有证据后关工具流式讲解；partial不第三次生成；空输出仅在有效证据下恢复一次；原门禁修订仍有界 |
| `agents/task_service.py` | 同轮120秒/显式比较跨章180秒共享预算；执行器整体watchdog；暂停只存策略，恢复重建deadline；超时及旧选区/练习模型异常保存失败收据、教材版本快照；取消保持原task_conflict契约并增加task_state |
| tool_dispatch/quality_checker | 线程传播上下文；检查晚到结果，阻止后续调用与提交 |
| course_search/grounded_citations/coverage/answer_media | 检索、来源选择、覆盖、媒体阶段共用剩余预算及观测；图号只能匹配当前有效来源的唯一同名原图，不模糊替代，pending不变为已审核 |
| frontend/app.js、practice.js、chat-transport.js | 探索不进入正文，按轮次撤回；未发布草稿只展示转义纯文本，无引用卡/图片激活；收据恢复保持单次POST |

没有新增AgentLoop、业务表或逐token数据库；没有改main.py、阅读器、Q5内部实现、教材和正式索引。前端为现有直接提供的静态JS，必须与后端同一导出部署；本次不需要重建reader。

上游来源固定`D:/deeptutor`的`6cf793bd868ba5ecbe64722936d4be8fab5a01df`。复用控制分支/模式并适配同步SDK，未整体复制StreamBus/BookEngine；文件哈希、改动说明见`STREAM_RETRACTION_SOURCE_REUSE.json`，许可证沿用`third_party/DeepTutor/LICENSE`与NOTICE。没有新增依赖。实装版本：lightrag-hku1.5.7、openai3.36.1、httpx0.28.1、fastapi0.159.1、sqlalchemy2.1.6、onnxruntime1.31.0。

## 3. 隔离数据与全部证据

- 原始全部尝试：`E:/项目/heart/.runtime/stream-retraction-20261023`，包括失败日志、旧版/中间版SSE及截图。
- 最终可复核小体积证据副本：同目录`final-evidence`；`sha256-manifest.json`列每个文件签名。`attempt-summary.json`记录最终C盘所有report中的每次尝试、时长、首次实际进度/正文、SDK调用、后端、收据；原SSE/报告保留完整尝试。
- 最终隔离运行原件：`C:/Users/free/AppData/Local/Temp/sr24`。baseline、modified为独立代码导出；candidate-baseline、candidate-modified为封存索引副本，仅允许SDK查询缓存写入。
- 两套教材各515文件逐项SHA256一致；索引7个核心文件均与原封存签名一致，见`final-integrity.json`。未重建LightRAG，未改变staging/ready=false，图片pending仍为pending。
- 冻结教材清单：原根`textbook-snapshot.json`；候选来源及7个核心签名：`candidate-integrity.json`。完整候选在原根candidate及C盘上述两套目录，不提交Git。
- 密钥始终从本机现有`ds.env`运行时读取，没有复制或打印。代码Git、文档、浏览器脚本均无密钥、教材、模型、索引和数据库。

资源事故如实保留：E盘曾耗尽，serial-modified报告0字节，部分JSON截断，不能判通过；中间导出目录完整迁至`C:/Users/free/AppData/Local/Temp/heart-stream-retraction-20261024-exports`，原快照、候选、缓存未删除。旧并行对照RAM达92.8%、两个RAG进程约各2.1GB，故最终改为顺序单宿主对照。最终启动RAM占用基线80.3%、新版79.1%，不是稳定性能基准。资源探测跳过GPU，不能据此声称本机没有GPU。

## 4. 同组真实模型对照

deepseek-flash、相同冻结教材/候选初始缓存、CPU embedding/rerank、各2线程，顺序独立进程；冷启动单列。下表为提交至页面完成（含收据读取）；首正文来自真正answer_delta，非进度。不同网络时段且故障测试有短时重叠，**不能宣称普遍加速**。

| 案例 | 旧版整轮秒 | 新版整轮秒 | 首正文旧/新秒 | 状态及正文清空 |
|---|---:|---:|---:|---|
| 冷启动概念 | 212.011 | 121.484 | 209.885 / 无 | 旧拒绝、新超时；新版旧快照收据410，是保留失败 |
| 热概念 | 101.187 | 96.094 | 86.460 / 80.073 | 两者saved；工具引起清空2→0；检索各一次 |
| 图1-4原句 | 40.128 | 41.272 | 21.627 / 22.518 | 两者saved、image-01-0006实际像素；清空2→0 |

新版概念：取证结束约79.234秒，来源映射/选择18.937秒，答案流79.281–82.078秒，质检82.078–87.297秒；图题：取证约8.938秒，媒体选择/载荷至21.313秒，答案流21.328–25.313秒，质检至36.313秒。嵌套阶段不能相加作为总耗时；完整阶段及保存开始见收据/最终SSE。持久化收据指标是提交前快照，最终响应含save.completed，不伪装收据内已有完成计时。

新版热概念观测4个主SDK调用、9293 tokens；图题4次、10060 tokens，已含来源选择/质检；循环汇总不再与SDK指标相加。旧循环可得7344/6669 tokens只覆盖循环，不能当全链成本比较。原生LightRAG用量另见backend_calls，缓存命中时原生模型调用可为0，本地embedding按batch记录。服务未返金额，费用未知，未估算成实测。

## 5. R01–R12矩阵

| 项 | 证据及结果 | 边界 |
|---|---|---|
| R01 原图 | modified-browser/figure14及verified-asset-label，saved；原图像素有效 | pending不等于已审核 |
| R02 概念 | 热概念saved、一次检索、无工具前正文清空 | 冷启动仍超时，不算通过 |
| R03 延迟工具 | 单元及transport测试通过，探索文字隐藏/参数不入正文 | 未构造真实供应商延迟tool_calls流 |
| R04 修订 | verified-repair saved31.287秒；超长候选触发原门禁后定点撤回 | 原260字限制保留 |
| R05 初连 | verified-connect rejected0.227秒、一次POST、失败收据200 | 连接错误由隔离SDK注入 |
| R06 部分流 | verified-partial interrupted37.342秒；草稿details1、链接0、无历史；流close、无第三个答案流 | 工具和选证仍真实，断流注入 |
| R07 deadline | verified-slow-final timeout3.499秒、失败收据200；慢工具晚到不保存；56项回归含选证/执行器边界 | 旧verified-slow收据410保留；a693已修复版本快照；真实冷启动需最终宿主再复验 |
| R08 暂停 | verified-ask 3.467秒暂停、14.895秒恢复保存；同task、revision递增，单元验证策略序列化 | ask工具选择注入、恢复讲解模型真实；verified-ask-long-wait另实等121.010秒，恢复27.159秒saved，同任务与新活动预算有效 |
| R09 断线 | verified-disconnect-retry saved31.217秒、POST1、GET收据200、刷新一致 | 截断最终SSE事件模拟浏览器断线，不是物理拔网 |
| R10 取消 | verified-cancel cancelled8.785秒；无保存；410为取消后的来源/身份保护 | 多标签/epoch/晚到主要由既有任务测试及transport测试覆盖，未全量真人多窗口验收 |
| R11 既有入口 | verified-selection saved8.975秒，selection-partial interrupted4.165秒；verified-practice提示/讲解2次POST、刷新恢复、正式评分409；verified-q5五步真实模型saved/暂停，跨章插问不改变游标 | AI练习明确测试/未审核；不作为教材原题或掌握判定 |
| R12 无依据/失效 | verified-stale明确rejected；verified-absent缺图5.302秒拒绝；verified-no-basis真实无依据问题20.664秒拒绝，实际LightRAG返回0来源、fallback=false | 版本错误注入返回对象，未改教材原件；未绕过原门禁；未改教材文件制造版本失效 |

最终测试：Python核心56项、Q5/任务服务33项、discrete-math任务上下文/质量27项通过；transport11项及前端语法检查通过。对应日志位于final-evidence。此前来源引用17项、质量7项与并行质量4项记录保留，不与最新测试重复累加宣称覆盖。

保留异常：澄清29项中的`test_inflight_duplicate_returns_busy_not_executing_metadata`预期task_busy、实际request_conflict，在基线同样复现，不放宽断言。错误地混用心理学课程运行旧test_task_context得到4个错误，后在正确discrete-math下27项通过。初次浏览器runner权限失败无POST；初次断线测试误等answer而宿主只发done，脚本错误已修复后重测，不能记为服务故障。自动审批超时的批次没有执行。旧final-fault-*漏请求头，实际是正常模型请求，**不能作为故障通过证据**，已独立登记invalid-header-*。

## 6. 交付判定

可以集成代码并复验；不可直接宣称正式页面或整阶段通过。必须在最新稳定宿主处理共享文件冲突、同版部署前后端、完成冷启动超时/最终收据及R03真实延迟工具及R10真人多标签页覆盖后，依据明确切换授权操作。详见`STREAM_RETRACTION_SWITCH_RUNBOOK.md`。
