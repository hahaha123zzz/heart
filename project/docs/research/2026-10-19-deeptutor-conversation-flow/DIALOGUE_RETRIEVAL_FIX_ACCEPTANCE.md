# 草稿状态与指定教材对象检索修复交付

日期：2026-10-23。结论：本轮代码及隔离验收已完成；正式 8000 尚未更新，不能宣称用户当前页面已经生效。原图“返回教材”的精确位置修复仍是独立待实施项。

## 提交及采用顺序

1. `e34ce01`：区分工具取证中间态与最终未发布，补齐原生检索轨迹和单对象缺口。
2. `c3b86f6ddefc1c75fcd693cfb9c8a08713e957d7`：页面小节范围修复、指定图号原文读取、有界扩查及 Q5 插问写入保护。

两项均已 push origin/main。本轮业务验收基于最终 `c3b86f6` 的 git archive 导出，不是直接运行含其他窗口修改的主工作树。导出包含已提交的阅读器滚轮构建；未复制其他 worktree 未提交代码。main.py、TaskService、教材、正式数据库和正式索引均未修改。

## 已接入行为与接口

- 普通页面目标不再硬锁小节：章内作为初始偏好，没有可核验来源时最多全书补查一次。显式章节仍约束检索；Q2 精确目标读取及失效拒绝继续保留。
- 显式点名的新概念问句、图号及跨章问题与路径位置分开。Q5 插问移除写入工具，且不记录当前目标已讲解、理解或推进；“下一步推导/继续这个例子”等指代追问保留原目标。
- 心理学图号请求先通过现有资产目录确定原图，再按登记块读取真实原文，继续走 choose_evidence/发布核验。图不存在或同号歧义不拿近似图、旧主题片段补答；单轮最多两张原图。
- 图像继续使用既有 selected_media、临时模型图片消息及同图质检；不新增图片编码、视觉发布、AgentLoop 或存储体系，不把 pending 改 approved。
- 采用 DeepTutor read_material/view_figure 的“点名对象→读取原文/像素”约定，主体实现复用本项目现有 SourceVisual、TextbookChunk、SourceRef 和已接入的临时图片链。本轮没有整套复制上游 ReadingStore 或新建另一套 view_figure 循环。
- SSE answer_state 新增 `retrieving`。清空工具回合临时内容不再发 rejected；rejected 保留为最终未发布。网页和练习入口均识别新状态；追加、替换、身份/revision/seq、保存和取消门禁未移除。旧前端忽略未知状态仍可接收最终收据，但完整体验需部署前后端并刷新。
- CourseSearch 调用记录新增 search_scope、retrieval_count、supplemental_count；原图路径 actual_backend=`q2_figure`，精确学习读取为 `q2_exact`，LightRAG 仍明确标记 `lightrag`。原有 SourceRef、bind_result、TaskContext.course_navigation、source_visuals 与 course_release 接口未替换。
- CoverageNavigator 保留原生阶段 trace 的独立拷贝，避免污染 backend 记录；单对象无来源报告 no_evidence 和具体 missing，而非空缺口。每次调用记录保留，不将末次 coverage 计数当作全轮总数。

## 隔离环境与命令

证据根 **H**：`E:/项目/heart/.runtime/dialogue-fix-c3b86f6-20261023`。

可审查的结构化摘要：[DIALOGUE_RETRIEVAL_FIX_EVIDENCE.json](DIALOGUE_RETRIEVAL_FIX_EVIDENCE.json)。原始对话及 SQL 快照保留本机，不随报告提交。

- 8013，独立 host.db/course.db；LightRAG 候选为 H/candidate 的独立副本；教材与原有 Q2 索引从已核对宿主输入复制，无重建。
- 官方 DeepSeek，Mock 关闭。本机 ds.env 仅由进程读取，未把密钥写入日志或 Git；不访问旧网关。
- 复用现有只读模型缓存；本轮是隔离功能验收，不声称空白机器独立安装证明。
- 服务启动器只设置环境、导入 main 并运行 uvicorn，没有查询、SDK、来源替换、故障注入或测试路由。

```powershell
# 固定导出目录下执行，结果 H/offline-final.log
& 'E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe' -B -m unittest tests.test_course_search_bridge tests.test_lightrag_coverage tests.test_answer_media tests.test_answer_stream tests.test_q3_agent_loop tests.test_citation_publication tests.test_grounded_citations -q

# 浏览器观测脚本由 Playwright 技能 run.js 执行；URL 明确为隔离 8013
node C:/Users/free/.agents/skills/playwright/run.js C:/Users/free/AppData/Local/Temp/playwright-test-dialogue-fix.cjs
$env:UX_TEST_URL='http://127.0.0.1:8013'
$env:UX_OUTPUT='E:/项目/heart/.runtime/dialogue-fix-c3b86f6-20261023/q5-utf8'
$env:UX_FLOW='q5'
$env:PYTHONIOENCODING='utf-8'
node C:/Users/free/.agents/skills/playwright/run.js C:/Users/free/AppData/Local/Temp/playwright-test-dialogue-q5.cjs

& 'E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe' -B 'E:/项目/heart/.runtime/response-dialogue-audit-20261023/verify_acceptance.py'
```

临时脚本还保存在 H/browser-run.cjs、H/q5-run.cjs。重复验收应新建证据目录/测试账号，不覆盖原记录。以上不是正式服务启动命令。

## 验收矩阵

同一稳定版本 103 项离线测试通过；阶段一 25 项包含在这 103 项内，不相加。浏览器调用真实模型/原生检索，不使用模型、查询或来源替身。

| 场景 | 总耗时/首次未核验正文（秒） | 实际读取/来源 | 结果 |
| --- | --- | --- | --- |
| 第二节页面问“图1-4讲的是什么” | 18.976 / 12.934 | q2_figure，2 条引用 | 正确解释科学研究过程；展示 image-01-0006；model_saw_pixels=true、visual_quality_checked=true；pending 保留，刷新正文一致 |
| 同页“给我解释一下被试反应” | 35.353 / 30.240 | LightRAG，5 条引用 | answered，保存与刷新一致；非旧小节锁定 |
| 同句重复提问 | 24.523 / 19.375 | LightRAG，3 条引用 | answered，保存与刷新一致 |
| “图1-999讲的是什么”负例 | 8.484 / 2.416 | q2_figure，0 引用 | quality_rejected，未发布无依据解释，未推进；拒绝是预期结果 |
| Q5 计划 | 1.301 / — | 计划接口 | awaiting_clarification |
| Q5 确认讲解 | 12.268 / 5.083 | q2_exact，3 引用 | answered，保留精确目标读取 |
| Q5 新概念插问 | 24.909 / 18.969 | LightRAG，4 引用 | answered；路径、模块、目标、进度完整快照与插问前一致 |
| Q5 图 1-4 插问 | 15.088 / 8.895 | q2_figure，2 引用 | answered；上述快照仍完全一致 |
| Q5 原跨章题 | 51.645 / 2.355 | LightRAG 两次，5 引用；covered | 双章引用均有效；上述快照仍完全一致 |
| Q5 返回原目标 | 11.948 / 2.727 | q2_exact，3 引用 | 原 objective/module 不变；正常更新本次讲解摘要与时间 |
| Q5 “我懂了，下一部分” | 15.899 / 11.723 | q2_exact，1 引用 | 切到下一目标；刷新正文一致，不宣称通过正式掌握度评分 |

Q5 最终证据来自 **H/q5-utf8/flow.json 的一次完整七步运行**，未与其他运行拼接。普通四项来自 H/browser/report.json；每项均保留 SSE、截图。普通页 chapter/section 始终为 1/2。Q5 三种插问完整 SQL 快照逐项一致，不只是 UI 标题相同。

“首次正文”是草稿实际出现时间，尚未核验，可能随后替换，不能当作正式回答就绪时间。普通成功案例只出现 generating/retrieving/checking/saved，没有中途 rejected；缺图负例才最终 rejected。

调用计数及 trace 见 H/verified.json：普通四项各一次读取、0 补查，循环生成回合分别 2/2/3/3；前两次概念真实 LightRAG 的 SDK 各记录 1 次关键词模型调用。Q5 六个回答读取分别为 1/1/1/2/1/1、均 0 补查；SDK 日志使用候选副本缓存，记录原生 LLM 调用 0，不冒称每次都进行了原生模型推理。外层真实生成及质检仍执行。循环回合与 SDK 调用是不同口径，不相加冒充全部生成/证据选择/质检调用。

## 失败记录及核对

- 初次尝试 pytest 时当前 venv 没有 pytest，未安装新依赖，改用项目 unittest 运行；最终固定导出 103 项通过。
- 初轮 Q5 观测子进程用本机默认编码输出中文、Node 按 UTF-8 解码，导致观测摘要乱码，未损坏业务数据库。保留 H/q5；设置 PYTHONIOENCODING=utf-8 后完整重跑，最终采用 H/q5-utf8，不以首次乱码快照冒充完整中文证据。
- 汇总脚本最初要求“返回原目标重新讲解”后整个 SQL 快照也完全不变，因正常讲解摘要/时间/路径 revision 更新而失败。保留 H/verification-initial-failure.json；改为校验原目标/模块及理解/掌握标记不变。三次插问的完整快照相等要求没有放宽。没有为此修改业务代码。
- 最终 verify_acceptance.py exit 0：普通四项、单次七步 Q5、原图与来源、刷新、路径保护均通过；隔离与正式候选 7 个核心文件哈希均不变，隔离 Q2 索引与原宿主索引哈希一致。

## 部署状态与剩余事项

正式 8000 仍为原固定宿主与已登记阅读器覆盖，本轮没有重启、替换文件或操作正式数据库。故用户当前打开的页面仍可能出现旧行为。8013 只为本轮临时验收，完成后停止；关闭记录见 H/shutdown.json。

下一次运行更新应从包含 c3b86f6 的稳定提交导出完整代码，保留完整宿主教材与现有索引，复核候选/来源身份和前后端哈希，使用最新正式学习库的一致性备份，再按已批准的进程身份受控替换；不能把旧启动器 setup 仍指向 2ae1e5f 当作更新。回滚恢复上一已核对代码和阅读器，继续沿用最新学习库，不用旧备份覆盖新记录。本轮尚未创建新的正式切换启动器或执行切换。

以下不在本轮通过结论内：

1. [原图返回位置计划](TEXTBOOK_IMAGE_RETURN_LOCATION_PLAN.md)的页码/区域解析、历史点击兼容仍未实施；本轮解决“能否找到和解释该图”，不能据此说返回按钮已精确定位。
2. TLS、原生超时/取消、断线重连、PDF 连续选区、练习和 ask_user 完整真实链路未在本轮重跑；保留此前证据，不冒充本轮全入口通过。
3. 新概念插问识别支持已测试的显式问句与点名对象，不宣称任意隐含换题均已解决。模糊指代、图号歧义和真实缺图仍应诚实澄清或拒绝。
4. 本轮真实案例未触发扩大检索补查；一次补查预算及保持目标的行为由离线测试覆盖，不能说真实补查效果已全面验收。
5. LightRAG 仍为明确候选模式，staging/ready=false、pending 状态不变。耗时会波动，本轮跨章 51.645 秒，不宣称性能优化完成。
