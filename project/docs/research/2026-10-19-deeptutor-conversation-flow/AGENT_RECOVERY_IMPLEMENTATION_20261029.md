# 教学对话恢复与工具协议修复

日期：2026-10-29。基线：7439ba5，分支 codex/ta5-acceptance-20261029。

本轮实现上一轮调研确定的四项修复；不代表 TA5 整阶段通过，不自动启用原生统一入口或切换正式数据库。

## 实现边界

1. 宿主预检索仍通过原 ToolRegistry/dispatch 执行，但结果以系统上下文进入模型，不再伪造 assistant/tool 调用历史。预检索原图仍以临时消息送入模型，像素不写入 loop_state。模型实际生成的工具调用及配对结果保持原协议。
2. 补齐章节导学附带“直接讲解、不出题、从第一个知识点开始”的识别。已选目标与回答发布分开：navigation_recent 单独读取失败任务的位置，失败内容不混入成功聊天历史。恢复必须匹配学生、会话、epoch 和当前目录版本；取消、过期、删除、换版不能恢复旧位置。当前目标尚未讲解成功时，“下一步”重试当前内容；成功后才允许继续真实目录。不增加 covered 或 mastery。
3. ask_user 增加结构化 answers，请求绑定原 task_id/revision；按 questionId 校验问题全集、重复/陌生问题、必答和闭集选项，替换原工具结果后继续同一任务。前端支持多题、单选、多选、自由文本和键盘提交；草稿按课程、学生、会话、任务、revision 保存在 sessionStorage。失败保留，成功/取消清理；旧 options 和纯文本答复保留兼容。
4. 临时宿主授权网络故障返回 503，不再伪装为永久 409。账户/教材/epoch 冲突继续拒绝。未确认的复习命令在当前会话存储原 command_id、参数及 revision，刷新后重用；成功或明确冲突清理。沿用原生事务内既有 HMAC 参数校验、回执优先与去重机制，不另建命令库。

## 参考来源

- DeepTutor 6cf793bd868ba5ecbe64722936d4be8fab5a01df：AskUserOptions.tsx、use-card-submission.ts，Apache-2.0。适配问题 ID 与交互语义，无 React 组件整段复制，来源补入 third_party/DeepTutor/NOTICE。
- OpenMAIC d128ef67c920571a86ce8a7c0430185689ab3d45：run/store.ts、generation-run-client/follower.ts，MIT；仅借鉴回执与恢复思路，未复制源码。
- OpenTutor a890519f3632efa14cf24449b366b3b9d901eecf：guided_session.py、react_loop.py，MIT；仅借鉴显式阶段状态，未迁入另一套学习库、文本工具解析或自动推进。
- DeepSeek 官方 https://api-docs.deepseek.com/guides/tool_calls/：区分模型生成的调用和客户端插入调用。修改预检索表达不等于证实全部 DSML 的唯一原因。

## 已取得的实际证据

- 最小同模型 SDK 对照：auto/required × 流式/非流式四组均返回结构化 retrieve_course。provider-recovery-probe.json，不含密钥。
- 修复章节尾句识别前，实际请求仍 quality_rejected/navigation_required，保留 recovery-navigation-before-parser.json。未增加重试次数、未解析执行模型正文 DSML。
- 修复后：第一轮“实验心理学的含义” ch1:s1:b6，第二轮“什么是科学” ch1:s1:b81，均 answered，有 3/2 条实际引用，约 3.172/1.797 秒。recovery-navigation-live.json。这是功能样例，不是性能基准或所有问句通过。
- 真实模型恰好两题 ask_user → 按 questionId 回复 → 同任务继续并带 7 条教材引用 → 相同请求重放无新回合，ask-recovery-live.json。
- 浏览器实际页面、API 夹具：两题、单/多选、自由文本、刷新恢复、键盘提交、503 保留选择、同 request_id 重试、成功收起，pageerror 为空。recovery-browser.json；此项不是浏览器真实模型联合样例。
- 额外完成实际页面 + 实际模型联合样例：375px，双问题、3 个选择、刷新后恢复、提交原任务继续、回答保存且有 5 条教材引用、pageerror 为空。ask-recovery-browser-live.json/png。与上一条 API 夹具证据分别保留。
- 实际完整原生 worker：旧 finish 命令连续两次 HTTP 200，revision 均为 19，耗时约 3.937/1.766 秒，finish-recovery-live.json。证明该持久回执重放，没有把它算作新增复习评分案例；历史首次失败缺少响应，不能倒推已唯一定位根因。

证据在应用 .runtime/ta5/，最终回归统计见后续结果记录。

保留失败：首轮宿主回归发现隔离测试建表早于 Q5 模型登记，补齐夹具的 schema 导入后复验；初轮原生回归各模块通过，但执行期间还在修复预检索原图注入，源码身份变化被门禁拒绝，不能计为最终通过。Playwright skill 的 run.js 试图在只读技能目录写临时文件而失败，改用已安装的同一 Playwright 库直接执行 Temp 脚本，无安装或技能目录改写。

扩展回归 test_q3_q4_integration 有 3 个既有失败：CitationPersistenceTests.test_completed_loop_persists_cited_pdf_references、HostNavigationTests.test_next_topic_is_not_turned_back_into_clarification、RegistryIntegrationTests.test_loop_executes_q4_skill_tool_and_keeps_state。以 git show 读取基线 7439ba5 的相关原模块，在独立进程内加载再执行同3例，复现相同1失败/2错误；没有改动工作树来做对照。当前与基线日志分别为 recovery-q3q4-current.log、recovery-q3q4-baseline.log，原62项组合运行保留于 recovery-navigation-media-frozen.log。它们不能写成全绿，也不能据此声称发布门禁通过。

## 验证命令

在应用目录执行；两套虚拟环境沿用已有依赖：

```powershell
.venv-runtime/Scripts/python.exe -B scripts/check_ta5_acceptance.py --layer host --output .runtime/ta5/recovery-host-frozen.json
.venv-deeptutor/Scripts/python.exe -B scripts/check_ta5_acceptance.py --layer native --output .runtime/ta5/recovery-native-frozen.json
node tests/ask-user-form.cjs
node tests/learning-review.cjs
node tests/learning-review-recovery.cjs
$env:NODE_PATH='C:\Users\free\.agents\skills\playwright\node_modules'
$env:RECOVERY_URL='http://127.0.0.1:8043'
node tests/browser/ask-user-recovery.cjs
```

浏览器脚本只对指定页面使用 API 夹具，无模型、评分、账户写入。需要已有本机页面服务；不能据此声称真实后端通过。真实服务复验使用隔离端口 8043/8044，数据库和原生 home 均在 .runtime/ta5；不触碰正式服务。

## 仍属于原计划的发布条件

NT3 普通聊天统一原生执行、NT8 跨库删除传播与竞争，以及 TA5 人工教学内容/视觉/键盘全矩阵、严格性能对照仍保留。不能用本轮恢复修复冒充这些已完成，也不能因此打开正式开关、改变 ready 或重建教材索引。

## 最终回归结果

- 冻结代码宿主回归：211项通过；原生回归：106项通过，无跳过。两份 frozen.json 的 source_digest 与当前源码一致，不拼接之前源码变化中的运行。
- 目录导航与原图：33项通过，recovery-navigation-media-clean.log；这组与宿主有共享模块，不合计为独立教学案例。
- 前端 SSE 传输：11项通过；ask-user-form、learning-review、learning-review-recovery、learning-card-actions、learning-cards 脚本通过。语法检查和 git diff --check 通过。
- 3个既有 Q3/Q4 兼容用例失败按上文保留，不纳入全绿统计。
- 隔离8043/8044服务已停止，正式服务、数据库、教材索引及开关未切换。未提交教材、.runtime、.env、模型或其他窗口改动。
