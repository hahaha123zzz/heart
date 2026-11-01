# 第五层实施与首批接线

依据 RESPONSE_COMPOSITION_REUSE_RESEARCH_20261101.md，用户已授权开始实施。基线6122724，继续在现有工作分支完成；不覆盖其他窗口的文档改动。

## 分批范围

| 批次 | 交付与验收 | 当前状态 |
|---|---|---|
| C1 | 统一严格协议、确定性计划、同次多块生成、失败块修复与依赖失效、真实Q3接线、引用出版、保存/刷新、前端兼容 | 首批实现与隔离验收完成，默认关闭，未切正式服务 |
| C2 | 旧回答/练习/显式题卡等入口的组合契约适配，第三层任务与第四层证据包边界投影 | 入口接线与隔离验收完成；证据包适配不代表独立第四层执行器已替换生产检索，详见C2记录 |
| C3 | 复杂任务分批有界执行、块级持久化与中途断线恢复、冻结引用编号后的逐块提交 | 文本范围已实现并完成隔离故障恢复验收；视觉/题卡保留原整轮流程，详见C3记录 |
| C4 | 教学评价集、人工抽查、同配置延迟/成本对照、离线prompt优化 | 首批设施与试验完成，独立教师复核、扩样及有效候选验证未完成；详见C4记录 |

## C1实现

- models/learning_response.py：ResponsePlan、BlockSpec、ContentClaim、GeneratedBlock、PublishedBlock、LearningResponse。闭集字段，模型不能填授权/发布状态/私有答案。计划中的依赖必须唯一且指向前序块，防止未知依赖和循环。
- agents/response_composition.py：把既定策略/已解析任务编译成内容块，不再分析学生状态；按批次生成，不每块起一次LLM。源ID、引用、原文引句、像素要求、输入版本和局部修复缓存分别验证。失败上游使依赖块失效；必需块失败拒绝发布，可选块失败可省略并标partial。
- 来源与引用：所有claim都带真实source_id；生成案例/类比分别自动标“非教材原例/原文”。旧prompt的[n]只有与该claim来源相符时才可移除，再由出版器统一编号，陌生引用仍拒绝。保留现有Q2出版与引用去重；最终块文本必须与出版正文一致，否则拒绝保存。
- agents/agent_loop.py：在既有循环内追加内容输出约束，无新增Planner请求。候选JSON在progress通道中缓冲，不作为学生正文。沿用当前有界修订预算，结构错误只重做pending块；强制收尾同样验证协议。取消、guard和全轮预算保留。
- agents/agent_loop_service.py：开关 RESPONSE_COMPOSITION_ENABLED=1 时对textbook问答启用；普通聊天和进入Q3的文字选区共用。仅提示/不公开完整答案、已有待答题、明确教学检查、ask_user必要澄清与现有展示卡走原契约，不由组合层重建题目。模型探索/工具仍使用原协议，最终生成只消费已有证据。
- frontend/chat-renderer.js/app.js：按已发布block_id展示，验证正文同源及身份，非法/旧schema回退原正文；保存到原PDFCitationRow.reference.learning_response，刷新从同一历史恢复。不创建新库或前端框架。

普通成功路径不增加模型调用次数；额外token上限只为JSON结构留余量，原有正文字数门禁不变。是否减少总延迟需要C4对照。

## 复用边界

DeepTutor固定6cf793bd，Apache-2.0：参考book/blocks/base.py的类型分派、生成/发布区分及compiler.py的局部重试语义；保留本项目TaskService、LLMClient、证据出版和预算，未复制BookStorage或创建第二AgentLoop。OpenMAIC/OpenTutor仅适配协议与注册设计，不引入其React工作区、幻灯片HTML或默认重试策略。已有learning_cards和published_reference_map直接复用。

## 失败记录与修复

首次真实模型返回把只读plan/pending/output上下文回显为答案；第二次返回仍遵循旧prompt的[n]。原结构门禁拒绝并保留live-first/live-captured-ready及candidates记录。修复为明确区分只读输入和唯一输出顶层blocks，并只规范化与source_ids绑定一致的旧引用；没有接受任意包裹字段、没有放宽来源校验或增加重试次数。

随后发现旧blended模式允许没有来源直接讲解，与本批所有claim必须有来源的契约冲突；组合路径现明确要求教材依据并通过原共享检索预取。首轮无依据比较失败保留在live-third.json。现有第三层在明确“直接解释”时可能选explain覆盖contrast，因此真实多块样例采用明确比较/举例且不出题；没有在第五层新增关键词策略分类器，统一策略任务适配仍归C2。

初次扩展测试误写不存在的tests.test_input_understanding，保留失败日志；实际模块名为test_input_understanding_contracts，修正命令后复验。隔离服务启动期间的连接拒绝另行保留，不计为模型或产品功能通过。

## 验证命令

在应用目录使用既有环境：

```powershell
.venv-runtime/Scripts/python.exe -B -m unittest tests.test_response_composition tests.test_q3_agent_loop tests.test_q3_task_loop tests.test_learning_cards tests.test_answer_stream tests.test_selection_loop -q
.venv-runtime/Scripts/python.exe -B -m unittest tests.test_layer4_stage3 tests.test_evidence_execution tests.test_input_understanding_contracts tests.test_grounded_citations -q
node tests/response-composition.cjs
node tests/chat-transport.cjs
.venv-runtime/Scripts/python.exe -B scripts/check_response_composition.py --base-url http://127.0.0.1:8051 --output .runtime/layer5/live.json
```

真实验证只使用8051隔离服务、.runtime/layer5的宿主/课程SQLite，正式8000服务、原索引、.env及教材发布状态不变。默认开关为0，未进行正式切换。

## 验收结果

- 核心与文字选区回归84项通过（41.831秒），`.runtime/layer5/regression-delivery.log`；第四层/证据/输入契约/引用48项通过，`evidence-regression-corrected.log`。前端传输12项通过，内容块渲染与安全回退检查通过。
- 三轮真实HTTP任务全部answered，分别为教材第一章讲解、变量比较、生活化案例；分别生成1、2、1个内容块。单次耗时6.641、11.344、5.328秒，仅作本次观测，不是优化前后性能对照。每轮最终AgentLoop生成为1轮，不代表上游检索等完整调用链只有一次模型调用。
- `.runtime/layer5/live-fourth.json`保留完整结果；每轮验证正式正文/内容块一致、真实引用、相同请求重放不重复生成、历史保留同一learning_response。案例由模型生成后自动标记“非教材原例”。
- 375px真实页面读取上述真实模型历史，显示4个内容块与上标引用；刷新保持正文，无pageerror或JSON泄露。证据为`.runtime/layer5/browser.json`及`browser.png`。本次页面验收覆盖显示与刷新，不冒充所有入口浏览器验收。
- 真实运行后补充的数学不等号、安全失败文本、仅提示入口排除及partial提示，已由针对性回归验证；未将较早真实运行证据冒充所有最终文件完全冻结后的全量验收。

## 尚未完成

C2接线、复验和剩余验收边界见[第二批记录](RESPONSE_COMPOSITION_C2_ACCEPTANCE_20261101.md)。C3文本依赖前沿生成、逐批提交、检查点和跨进程恢复见[C3记录](RESPONSE_COMPOSITION_C3_ACCEPTANCE_20261101.md)，需要单独启用RESPONSE_BLOCK_STREAMING_ENABLED；C1/C2原整轮流程保持可用。视觉/题卡不冒充已有逐块恢复。[C4首批评价及未完成项](RESPONSE_COMPOSITION_C4_EVALUATION_20261101.md)已记录，教师复核和扩样仍未完成。程序可验证引用身份和格式，开放语义正确性仍需既有来源核验和后续教学评价，不能用provenance标签替代事实检查。研究来源审计中的宿主文件哈希对应6122724研究基线，保留原值，不以实现后的文件覆盖调研证据。
