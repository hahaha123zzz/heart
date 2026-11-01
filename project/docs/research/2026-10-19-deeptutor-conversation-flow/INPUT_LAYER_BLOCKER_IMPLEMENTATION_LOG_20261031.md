# 输入层阻塞改造实施记录

2026-10-31，基于主工作区既有未提交六维代码继续实现；未重置或提交其他改动。

## 已实现

- frontend/chat-transport.js：收到合法 done 事件立即结束读取并释放 reader，不再要求连接先关闭。继续沿用请求收据恢复、取消和版本规则。
- scripts/check_input_labels_page.cjs：检查隔离本机端口；等待待办恢复完成；提交前监听新 POST 并核对消息；通过原 TutorChatTransport 的完成结果读取 SSE 回合，不 clone 整条流；核对正文、第二轮困难标签与刷新后回答，保存 report.json、trace.zip、page.png。失败也保存证据。
- scripts/check_semantic_shadow.py：默认只执行规则；--live 显式调用现有 resolve，支持无 case_id 的旧样本。记录基线/候选标签、任务/约束/引用差异、旧适配投影差异与调用次数。候选始终 promoted=false，不进入任务、成绩或画像。该脚本只比较无额外状态的文本样本，不代表完整活动快照迁移对照。
- agents/input_understanding/semantic.py：模型解析得到的标签来源由服务端固定为 model，不能让模型自称 rule。
- 既有 annotation_agreement.py 修复维度并集、重复 ID、空维度和无定义 κ，沿用上批实现。

复用边界：直接调用现有 resolve、understand、legacy_routing、TutorChatTransport；未复制上游代码或安装新依赖。Rasa/Playwright/Langfuse 的机制依据见 INPUT_LAYER_BLOCKER_REUSE_AUDIT_20261031.md。

## 验证

- Python：tests.test_semantic_shadow、tests.test_annotation_agreement、tests.test_input_understanding_semantic、tests.test_input_understanding_labels、tests.test_semantic_boundaries 共 39 项通过。
- Node：node --test tests/chat-transport.cjs，12 项通过；包含 done 已到达而连接保持打开的真实 ReadableStream 用例。
- shadow：旧 30 条样本离线执行，model_calls=0，全部 baseline_unchanged=true；已有留出集已污染，结果仅作工程验证。
- 真实模型：先后两次各 3 条短句请求（后一次复核来源修正），各自 3 次调用且基线不变。首轮模型补出标签，但个别标签和旧工程标注不同，不能称为语义质量通过。后一次结果在 .runtime/psy6d-implementation/shadow-live-provenance.json。
- 真实模型 shadow 未启用生产兜底；简单问题额外理解调用预算未更改。

## 复验命令

在应用目录执行：

```powershell
node scripts/check_input_labels_page.cjs http://127.0.0.1:8151 E:/项目/heart/.runtime/psy6d-implementation/page
.venv-runtime/Scripts/python.exe -B scripts/check_semantic_shadow.py --input tests/fixtures/holdout_v1.jsonl --out E:/项目/heart/.runtime/psy6d-implementation/shadow-off.json --limit 30
```

页面脚本使用本机已有 Playwright；必要时通过 NODE_PATH 指定安装目录。真实模型 shadow 额外传 --live，仅在隔离评测中使用。

## 页面实际结果

- 隔离 8151、本地检索、独立 .runtime/psy6d-implementation/course.db；未使用正式库。
- 首次验收监控包装安装太晚：app.js 已在 466 行缓存 streamChat，脚本没有截获结果而误等 120 秒。trace 中应用早已返回教材依据不足；该失败保存在 page/。
- 修复为 addInitScript 在 TutorChatTransport 赋值时安装监控，并等待 taskRecoveryNeeded=false。第二次使用第一章“实验法/观察法”两轮，确实捕获两个新 POST。
- 第一轮 answered、contrast、3 条来源，约 8 秒，页面正文/上标可见；第二轮约 3 秒 quality_rejected，页面明确“回答没有有效证据引用，或引用编号超出本轮证据”。报告、截图和 trace 在 .runtime/psy6d-implementation/page-fixed/。
- 因第二轮引用发布失败，刷新恢复及整组页面验收不记为通过。故障已从验收等待条件推进到真实后端引用发布错误；未放宽证据门槛。

## 发布边界

## 引用失败续修

- 失败快照显示第二轮保留了首轮3条完整原文来源（loop_state.sources），不是检索来源丢失。发布器先进入 EvidenceBundle，正文缺可识别编号时抛出通用错误；循环已有修订规则没有处理此原因。
- agent_loop_service.py 将引用格式/缺编号检查移到原文发布之前，给出可操作原因；删除后面的重复检查。固定书模式原有无上标发布策略保持原行为。
- agent_loop.py 复用现有一次修订预算：已有来源且缺引用/编号不属于本轮时，只用现有编号和原文修订，不调用工具、不硬贴来源；再次失败继续拒绝。
- 离线：tests.test_q3_agent_loop、tests.test_first_wave_integration、tests.test_teaching_modes、tests.test_input_understanding_integration 共88项通过（心理学、本地检索、固定书预热关闭）。首轮更宽集合曾因本机LightRAG配置和离散数学数据缺失报错，未记为通过；本次不恢复教材或改这些断言。
- 页面：全新隔离库下，实验法/观察法→分不清→刷新通过；两轮均answered，各3条来源，策略contrast→worked_example，pageerror为空。证据 .runtime/psy6d-citation-repair/page/{report.json,page.png,trace.zip}。
- 本次自然页面第二轮1次模型调用、0次工具调用，没有自然触发修订分支。因此另做受控故障注入：强制首版无编号，第二版使用真实模型，结果completed=true、2轮、0工具调用，证据 .runtime/psy6d-citation-repair/forced-live.json。它证明修订分支可工作，不代表自然失败率已测定。
- 隔离8151服务已停止；正式服务、数据库与开关未动。

## 快照对照与会话隔离续做

- check_semantic_shadow.py 支持 context/request 快照输入；每条路径使用独立深拷贝，输出 context_unchanged。--live --legacy 显式运行旧 ConversationRouter 与新解析/兼容投影，旧路由单次15秒、零格式重试，单独统计调用；报告 student_move、intent、learning_intents、target_refs、answer_constraints 等差异。状态/对象/约束差异纳入关键项；无法投影的复合任务单列，不伪算为一致。
- 新增快照不变、待答/偏好保持、旧路由约束差异可见测试；相关语义边界、任务API、多轮、标注工具44项通过。后续仅调整汇总字段，再跑4项shadow专项通过。
- 真实模型5条工程快照，合计11次理解调用（新解析6次，旧路由5次）；上下文全部不变。4条可比较中1条learning_intents差异（旧compare，新explain+compare），关键对象/约束差异0；1条复合回题无法投影为单项旧任务。小样本可比较差异1/4，未达原计划2%门槛，eligible_for_removal=false。数据与报告：.runtime/psy6d-snapshot-20261031/{snapshots.jsonl,live-legacy.json}。这些是工程构造快照，不是独立学生盲测。
- 页面验收脚本新增同学生第二标签页：须分配新session、空消息、无pending；原会话刷新后正文仍在。真实模型+浏览器复验通过，两轮answered后新标签 messages=0、hasPending=false，无pageerror。证据 .runtime/psy6d-session-isolation/page/{report.json,page.png,trace.zip}。这是跨session标签页验收；未创建另一套“独立侧栏聊天”协议。
- .env.example 补充SEMANTIC_LABELS_ENABLED与LABELS_POLICY/STRUCTURE/TURN默认值说明，未修改本机.env或生产开关。短句模型补充继续停留在只读评测；未把未校准候选直接推进正式任务。
- 隔离8151服务已停止，正式8000和库未动；本轮未提交、推送或合并。

## 当前剩余条件

独立第二标注者与新盲测集仍缺；旧路由真实快照差异尚未达删除阈值；正式shadow/灰度、完整Q5/原生入口与更大真实样本仍待验收。本轮完成的页面和快照工具不代替这些证据。

第二人独立标注及新盲测、侧栏页面隔离、更大真实样本、新旧完整活动快照对照与正式灰度。单组页面通过不等于阶段C全部完成。

未修改 .env、8000、正式数据库或教材索引；未删除旧路由、未合并提交。独立人工一致性、完整活动快照的旧链路对照与灰度仍需完成；脚本和单测不等于教学效果达标。
