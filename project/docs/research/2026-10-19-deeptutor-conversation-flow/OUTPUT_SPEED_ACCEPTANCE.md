# 输出速度验收矩阵与交付

验收日期：2026-10-24；收尾更新：2026-10-25。独立worktree：`E:\项目\heart\.worktrees\output-speed`；分支`codex/output-speed`。业务验收提交：`073f814f77689a87e11c9aa7dc51ad80e59bd384`。后续只有计时运行器/测试与报告，不把报告提交当作不同业务版本。

## 结论与版本

OS0—OS5的核心代码已落地；最终隔离宿主通过相关离线回归和真实页面联合流程。**OS6不能标全量完成：各类20%目标未全部达到，最终教学整合版本尚无每类5对的新性能队列，正式启用另受Q4运行分支及数据库兼容门槛限制。**

8000现为并行窗口发布的Q4 `e8edcf4`固定导出，不是旧2ae1e5f；本窗口未改8000、正式学习库或索引。main.py/app.js/retrieval.py与e8edcf4规范化内容一致。只读核对见`.runtime/output-speed-20261024/formal-readonly-audit.json`、`formal-code-audit.json`。

完整提交顺序：`0bd95c0`（采用流式4bf24d9全部依赖）→`a9471c2`→`45212b7`→`df33688`→`70076b1`→`79460d3`→`49cd0cc`（合入main到2803d8d的教学/会话/选区完整链）→`7747969`→`3065d76`→`073f814`。没有复制其他worktree未提交生产代码；Q4现网分支未擅自合入。

采用DeepTutor `6cf793bd868ba5ecbe64722936d4be8fab5a01df`，来源及Apache-2.0记录见[复用台账](OUTPUT_SPEED_SOURCE_REUSE.json)。用户在冲突处理中明确选择“按DeepTutor来”：普通教学实时输出，协议探索不作正文，拒绝回合按身份撤回；保存依然经过事实、引用、视觉质检和任务版本门禁。没有采用保存后再分块模拟实时生成。

## 最终隔离条件

- 宿主/数据库/候选/完整教材均在`C:\Users\free\AppData\Local\Temp\heart-output-speed-20261024\candidate-073f814`；端口8018。代码由git archive导出，setup.json登记SHA、路径和7个候选核心哈希。
- 官方DeepSeek端点，仅从本机ds.env注入；LLM_MOCK=0，LOCAL_AGENT_LOOP_ENABLED=1，Q5_LEARNING_ENABLED=1，Q3_RETRIEVAL_MODE=lightrag，ADAPTIVE_TUTORING_ENABLED=1，SELECTED_TEXT_AGENT_LOOP_ENABLED=1；模型缓存只读复用现有CPU缓存。未向旧网关发送官方密钥。
- 核对范围是宿主业务代码，不修改LightRAG SDK或冻结图谱。serve-faults.py正常请求仅做观测；只有明确测试头native-read-timeout才把原生网络read设为0.001秒，保留失败结果和缓存命中。没有重写sidecar、伪造来源/结果或绕过质检。
- pending图片仍pending，staging/ready=false保持原值。SDK关键词缓存可命中：llm_calls=0不能说成新的原生网络调用，但实际图/向量查询及embedding仍有独立计时。回退、Q2精读和缓存结果分开报告。

## OS01—OS16

| 项目 | 代码 / 离线 | 同一业务提交真实模型、页面或限制 | 证据 |
| --- | --- | --- | --- |
| OS01 定义/知识点 | 已实现、离线通过 | 普通概念页面通过；性能20%未全面通过 | browser-073f814；下方成对表 |
| OS02 校验/权重 | 已实现、离线通过 | 每次原生查询仍有前后完整内容校验；阶段可见，权重重叠路径去重 | offline-073f814.log；backend_calls.usage.stages |
| OS03 换版失效 | 离线通过 | 同大小同mtime替换、来源映射/宿主身份不一致拒绝；本轮未在真实服务篡改教材 | test_output_speed / lightrag_backend / relocation |
| OS04 查询中变化 | 离线通过 | 真实回调中篡改替身测到拒绝；不弱化为文件属性缓存 | test_query_checks_content_twice_and_rejects_inflight_same_stat_change |
| OS05 连接复用 | 已实现、离线通过 | 多回合真实复用；端点/代理/凭据轮换仅离线测，未用假密钥请求外部 | transport_pool_cumulative；20项提速测试 |
| OS06 独立会话 | 离线通过、真实原生查询通过 | 原生同候选有界串行；引用搜索不持全局锁，不宣称同候选并行吞吐翻倍 | final-native/report.json |
| OS07 编号/恢复 | 离线通过、ask_user页面通过 | 同任务恢复；原子去重/迟到来源拒绝由针对性测试覆盖；原文编号审计无异常 | flows-073f814；delivery-audit.json |
| OS08 双章比较 | 离线、真实模型、浏览器通过 | Q5插问就是原题；双方相关原文进入模型，正文双方引用有效，非硬塞章节 | q5-073f814/interjection.sse；graph/tool观测 |
| OS09 缺一侧 | 离线、真实检索通过 | 缺失“量子纠缠实验控制”，只补查1次，3次原生检索后partial，保留第一章原文 | final-native/partial.json |
| OS10 图1-4/5-2 | 离线、真实模型、浏览器通过 | 生成与视觉质检使用相同像素SHA；页面和刷新通过；未审核图不升级 | browser-073f814；delivery-audit.json |
| OS11 PDF追问 | 离线、最终真实页面通过 | 选区解释→没听懂换说法→刷新同一证据范围；先前反问拒绝保留，修正提示契约后完整重跑 | flows-073f814；flows-7747969 / flows-3065d76失败 |
| OS12 Q5安排 | 离线、完整真实页面通过 | 生成→调整→确认→讲解→继续→暂停→刷新；没有正式掌握分 | q5-073f814/report.json |
| OS13 插问返回 | 离线、完整真实页面通过 | 原跨章题前后本次活动快照深度相等；返回同ID，下一部分才换活动 | q5-073f814/report.json |
| OS14 澄清/取消/断线 | 离线、真实链路验证 | ask_user同任务恢复；真实正文中断网后1次POST恢复；原生取消单独记录底层结束与零保存。未在最终宿主注入半截模型输出，相关分支仅离线通过 | flows / disconnect / native-cancel |
| OS15 总预算/质检 | 离线通过；真实超时有界观测 | 短read故障与缓存命中分开；不能把缓存成功记为网关恢复。最终活动总预算自然耗尽及无缓存超时拒绝终态仍缺真实专门样本 | native-timeout-report.json；execution_metrics |
| OS16 页面/重启/启用 | 页面与隔离重启验证 | 实际运行SHA一致；本轮正式不启用，Q4对账/两项数据库迁移待交付 | restart-073f814；[切换回滚](OUTPUT_SPEED_SWITCH_PLAN.md) |

## 成对性能：保留未达标类别

以下是**合并前优化提交79460d3与be7cc9c**，8类×5对、前后交替，共80次；不能当作最终073f814教学整合版本的性能通过。每次独立模拟学生、同问题/模型端点/教材/独立候选；缓存为热运行自然状态。机器仍运行其他窗口，非独占硬件，网络及重排有波动。无p95声明。

首字只计最后saved回合的answer_delta；旧基线工具探索和被撤回候选不算。原始收据保持不变，accepted-round-summary.json由收据重新审计；改进运行器补了“撤回轮不算有效首字”测试，审计后本表聚合值不变。

| 类别 | 完成中位秒 前→后 | 有效首字中位秒 前→后 | 完成变化 | 失败 前→后 |
| --- | --- | --- | --- | --- |
| 定义 | 17.875→18.891 | 13.406→14.735 | 慢5.7%，未通过 | 0/5→0/5 |
| 图1-4 | 8.937→10.547 | 5.265→6.156 | 慢18.0%，未通过 | 0/5→0/5 |
| 图5-2 | 11.547→9.688 | 7.187→5.953 | 快16.1%，未达20% | 0/5→0/5 |
| 原跨章题 | 31.469→23.547 | 25.766→19.734 | 快25.2%，首字快23.4% | 0/5→0/5 |
| 缺一侧证据 | 无成功样本→25.328 | 无成功样本→22.313 | 只能比较完成率，不能称提速 | 5/5→0/5 |
| 学习第一章 | 9.422→7.563 | 4.953→3.313 | 快19.7%，完成未达20% | 0/5→0/5 |
| PDF解释 | 7.625→7.609 | 4.485→4.672 | 完成基本持平，首字慢4.2% | 0/5→0/5 |
| Q5草案 | 8.796→8.531 | 不适用 | 快3.0%，未达20% | 0/5→0/5 |

最大值、调用数、来源覆盖、每次SSE和失败均在paired-79460d3目录；JSON汇总随本报告登记哈希。不能把更快拒答、Q2精读或缓存当原生实时网络提速。PDF局部剖析64.531→13.125秒只说明逐字符页面元数据热点修复，不代表上述端到端收益。最终版本仍保留完整哈希、重排、原文映射、生成和质检开销，后续应按阶段数据定位，不能继续删门禁换指标。

## 接口与资源范围

- Q3/Q5共用CourseSearch/search边界保持；Q2 read_target、bind_result、TaskContext.course_navigation、source_visuals与course_release语义不变。CoverageNavigator旧select/judge回调仍兼容，生产合并为每对象一次decide。
- LightRagBackend.validate新增可选snapshot，原返回manifest不变；Metrics增加stages/transport_pool_cumulative等附加字段。索引身份及来源协议不改。
- LoopRequest新增可选prefetch_query、requires_evidence、answer_ready，默认兼容旧调用。唯一宿主接线agent_loop_service使用answer_ready协调“teaching_step已登记+证据就绪/明确blended”与正文角色；不是第二套循环，不能跳过publish_gate。
- 传输池最多保留8项，按内存凭据/endpoint/代理/TLS环境隔离，活跃请求归还后才关闭淘汰项，lifespan/atexit关闭。消息、Metrics、画像、取消和来源不共享。模型文件继续每请求内容哈希，没有跨请求mtime缓存。
- 检索去重仅本请求，容量16；候选队列每候选8个持有/等待、最多32个候选，默认180秒并服从活动剩余时限；跨进程所有权锁保留。普通活动120秒、跨章180秒，网络/工具取剩余预算。父阶段includes_children不可直接与子阶段相加。
- 本次没有迁移正式表；main继承的会话列自动迁移和Q5本次安排增量迁移是正式启用依赖，不可借启动服务暗中执行。当前正式库缺少conversations.session_id和q5_learning_bindings.session_plan，现网Q4分支另需集成对账。

## 可复核命令与失败保留

完整命令见OUTPUT_SPEED_EXECUTION.md，固定导出以现有venv运行unittest的257项集合；后续计时审计测试20项另通过。pytest不作为必要依赖。浏览器使用已安装Playwright run.js，显式URL8018；真实模型/页面不以离线测试替代。

保留E盘导出WinError112、冷基线224.687秒失败、早期执行中断的paired-45212b7/paired-70076b1、旧离散数学教材测试9项漂移、Q5 Mock fixture未设boolean导致错分支、合并质检分支else错误、7747969无正文delta、PDF反问拒绝、浏览器首次跨role比较误报等全部原始日志。未将这些失败拼接成最终通过。最终Q5流程使用单个新学生连续完成，不拼接多次运行。

11章原题库仍全部0题；本轮未生成AI题冒充教材原题。未做30样本p95、正式切换、正式迁移或无缓存活动总超时自然终态验收。详细机器可读结果、文件哈希与最终实测时间见OUTPUT_SPEED_ACCEPTANCE.json。


## 最终实测与归档

073f814页面：概念有效首字13.361秒/完成17.265秒；图1-4为8.414/14.716秒；图5-2为7.804/13.238秒。均在本正文回合质检前流出，保存后刷新一致。PDF选区8.197秒、换说法8.341秒；ask_user暂停2.056秒、同任务恢复34.657秒。Q5单次七步12.921/9.519/26.993/42.277/28.265/60.852/5.062秒，插问前后活动不变，返回后才按指令继续；该样本不是五对性能结论。

最终原生partial：27.844秒，3次查询、1次缺口补查；两个独立会话18.765/24.906秒，均有1次实际原生关键词网络调用，第二请求候选等待6.453秒。原生取消的准确单调时钟为726899.703发取消、726899.750确认、原生query结束726899.750、本机网络线程实际结束726900.296；任务cancelled且对话零保存。取消请求返回task_cancelled，旧修订的原请求返回task_conflict是任务版本guard生效，不是取消失败；首次测试只接收task_cancelled因而误报，原记录仍保留。

显式read超时测试22.391秒，3次原生query均结束；前两次APITimeoutError每次最多2个网络尝试，末次关键词缓存命中后读到真实教材原文并保存回答。`test_expected_rejection_passed=false`原样保留：这证明有界失败、日志和缓存路径可观察，不证明无缓存超时拒绝终态。未计为LightRAG网关实时成功。

8018从原PID60788停止后，用同一073f814、同一数据库重新启动；restart-073f814/report.json通过，原学生/会话的计划与重启前深度相等，POST数0。断网刷新场景POST数1。两张原图生成/质检像素哈希完全相同；全部最终PDF引用编号审计合法、无重复evidence_id；正式历史/任务JSON中data:image/计数0。正式候选和隔离候选7个核心文件最终哈希均未变。

证据已从C盘临时目录另行归档到`E:\项目\heart\.runtime\output-speed-20261024\evidence-final`，169个文件逐项SHA256见manifest.json及OUTPUT_SPEED_ACCEPTANCE.json。教材、数据库、密钥和原始提示未提交Git；Git只有汇总与哈希。失败与中间样本留在原位置及归档，不清理其他窗口。
