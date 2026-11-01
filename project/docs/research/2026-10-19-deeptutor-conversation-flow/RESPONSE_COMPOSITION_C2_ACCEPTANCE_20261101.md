# 第五层 C2：入口适配与上游契约消费

基线：首批提交 ef9c896。延续既定 C2 范围，不新增规划模型、AgentLoop、评分器或前端框架。正式服务8000、正式数据库、教材索引及.env不变，RESPONSE_COMPOSITION_ENABLED仍默认0。

## 实现边界

1. `response_composition_adapters.response_plan`统一消费有效GroundedTurn、TeachingTurn、TeachingPlan和TaskExecution。明确的内容任务优先于默认讲解策略，保留任务顺序、task_frame_ids、target_ref及内容任务间依赖；hint_only/no_full_answer优先于完整比较和例题。shadow解析和待确认的长期提案不参与生成决策。原输入授权、澄清及非内容动作仍归原任务服务。
2. 普通Q3讲解沿用C1的生成协议。旧Orchestrator、旧PDF选区、聊天小题、练习页面帮助、Q3已登记检查题/恢复原题/反馈/显式卡片，原样投影为host_snapshot。它只表示原入口已经允许发布，不把整段正文伪装为新核验教材claim；不增加一次改写模型调用。题目与评分仍由原服务生成、登记、核验及保存。
3. PublishedBlock区分generated与host_snapshot：前者必须有来源claim，后者必须有服务端authority_ref且不含生成claim。模型输出仍使用GeneratedBlock闭集结构，不能自行填写host_snapshot或authority_ref。原题私有答案、评分键与学生完整状态不复制进展示协议。
4. ResponseComposer支持第四层EvidencePackage边界：重验包结构、精确匹配任务上下文，必需证据不完整/取消不得组合；包外来源或相同ID的文档版本/正文变化拒绝。当前正式检索仍使用原共享检索与出版链路的sources，未将第四层独立execute_requirements整体替换为生产执行器；包适配测试不冒称新执行器已全入口运行。
5. 引用出版、Q5状态行和覆盖不足提示全部完成后再生成learning_response，避免提示前缀使已保存正文与内容块不一致。快照保留原空白、引用和题干，不在展示层重新推断内容类型或生成新题。
6. 所有新增入口在原对话/选区引用记录中保存同一learning_response。聊天小题同时传递原session_id，避免提示进入其他标签页。练习页面帮助记录与对话保持同一快照，保留原辅导使用记录，不新增正式评分或掌握分。

## 验证与证据

- 核心/任务/卡片/流式/选区及C2入口测试96项通过，33.842秒：`.runtime/layer5/c2-delivery-final.log`。最终提示类型、前置知识策略保留和证据包像素/位置不可替换边界微调后，C1/C2专项22项再次通过：`c2-source-final.log`。不把前面的真实运行记录当作最终微调后所有文件冻结的复验。
- 任务消费、预算、自适应教学、第四层对象、EvidencePackage、输入契约与引用补充回归109项通过：`c2-regression-extra.log`。
- C2专项使用临时SQLite验证旧PDF提示、聊天小题、练习帮助按钮的正文与快照保存一致、只生成一次、session隔离且不产生评分。旧Orchestrator用现有质检事务夹具验证原生成/保存路径。上述为可控模型与材料夹具测试，不等同于真实题库模型验收。
- `node tests/response-composition.cjs`通过，包括原题快照不重复正文、不展示authority_ref、安全转义及旧协议回退；`node tests/chat-transport.cjs`12项通过。Python编译检查通过。
- 真实8051隔离服务4轮通过：对比卡、检查题、恢复原题、提示；分别13.844、6.109、0.297、4.828秒。原题恢复0轮模型生成；其他回合仅使用既有循环，未追加快照改写模型。每轮相同request重放及历史保存一致，原题未被替换。证据：`c2-live-first.json`。这组INPUT_UNDERSTANDING_MODE=off，不用其证明active任务解析或每次“仅提示”都被上游正确标为hint。
- 375px可见浏览器读取上述真实模型历史，4个内容块、上标引用正常；刷新后相同正文，无pageerror。证据：`c2-browser.json`、`c2-browser.png`。本次未通过浏览器重新出题/评分，不据此宣布全部教学入口页面验收完成。
- INPUT_UNDERSTANDING_MODE=active、INPUT_UNDERSTANDING_SEMANTIC_ENABLED=1另跑5轮真实HTTP链路：比较卡→出题→恢复原题→仅提示→先解释操作性定义再回到原题。全部answered，重放/历史一致；最后一轮input_resume_question_id匹配原题且正文以原题结束，待答题ID和题干全程不变。分别11.219、5.563、0.297、3.219、5.422秒；恢复题目0轮模型生成，提示块标记hint。证据`c2-live-active-five.json`；此前4轮active记录`c2-live-active.json`也保留。
- active五轮的375px页面5个内容块与刷新恢复通过，无pageerror：`c2-browser-active.json`。这组验证现有页面读取真实模型结果，不冒充所有题库/旧PDF入口真实模型联验。8051隔离服务已停止，未触碰正式8000。

## 保留的失败

- 初次EvidencePackage重验直接从dict加载，strict SourceRef拒绝dict。改为使用既有checkpoint的JSON重验；专门验证跨session、缺证、原文变化仍拒绝。日志`c2-adapter-tests.log`与修复日志均保留。
- 首次资源测试误把给模型的轻量get_history当成页面历史，随后改为读取实际PDFCitationRow验证保存。原错误保留`c2-adapter-resources.log`，没有改写失败日志。
- 扩展Q3/Q4旧集合出现1失败/2错误：数学技能与当前心理学课程不匹配、未初始化固定教材检索、旧引用夹具没有产生预期引用。将服务模块恢复到ef9c896源码在相同环境重放这3项，得到相同失败，见`c2-baseline-three.log`；这只是旧服务模块回放，不冒充整仓库detached验收。强行改用discrete-math又因本机缺少旧教材目录失败，见`c2-integration-isolated.log`。均未改测试预期或标为通过。

## 运行命令

```powershell
.venv-runtime/Scripts/python.exe -B -m unittest tests.test_response_composition_adapters tests.test_response_composition tests.test_q3_agent_loop tests.test_q3_task_loop tests.test_learning_cards tests.test_answer_stream tests.test_selection_loop -q
.venv-runtime/Scripts/python.exe -B scripts/check_response_composition.py --base-url http://127.0.0.1:8051 --batch c2 --output .runtime/layer5/c2-live.json
node tests/response-composition.cjs
node tests/chat-transport.cjs
```

## 未包含

C3逐块正式发布、持久化半成品/跨进程恢复、复杂DAG执行及C4教学效果/同配置性能评价保持待实施。C2复用原入口核验结果，不能修复所有上游意图识别或hint分类问题；程序结构校验也不替代教材语义核验。正式切换、main合并、推送均不属于本轮操作。
