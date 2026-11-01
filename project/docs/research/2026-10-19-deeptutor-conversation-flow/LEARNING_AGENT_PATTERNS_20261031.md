# 学习 Agent 对照调研：可借鉴的 8 个模式（2026-10-31）

目的：看同类学习 Agent 怎么处理“状态 → 教学动作 → 内容 → 评估”，找出能直接改进 psy-6d-v1 剩余工作的模式。
范围：只读源码/文档；未运行对方项目；未复制 GPL/AGPL 代码。

## 1. 读了什么

| 项目 | 版本/许可 | 实际读的文件 |
|---|---|---|
| DeepTutor（本地 `D:\deeptutor`） | `6cf793bd` / Apache-2.0 | `runtime/capability_routing.py`、`runtime/turn_engine.py`、`services/mastery_hints.py` |
| OpenMAIC（本地 `F:\openmaic\OpenMAIC`） | `d128ef67` / MIT | `lib/pbl/v2/runtime/learner-state.ts` |
| **tutor-mcp**（`ArnaudGuiovanna/tutor-mcp`） | MIT，2026-10-31 仍在更新 | `docs/algorithms.md`、`engine/action_selector.go`、`engine/orchestrator.go`、`client/src/studyRequests.ts`、`client/src/learningActivityModel.ts` |
| **OpenTutor**（`zijinz456/OpenTutor`） | MIT | `apps/api/services/agent/state.py`、`tests/test_agent_state_machine.py`、`apps/api/services/loom_mastery.py` |
| tutor-gpt / ChatTutor / GenMentor | GPL-3.0 / AGPL-3.0 / CC0 | **只看仓库描述与许可，未读代码**（GPL/AGPL 不适合拷代码） |

## 2. tutor-mcp：把“决策”做成可审计的纯函数流水线

它的 `get_next_activity` 不是“理解用户 → 回答”，而是：

```
状态+目标+证据 → PhaseController(FSM) → Gate(约束) → ConceptSelector → ActionSelector → DecisionContract → 记忆/教练上下文
```

`docs/algorithms.md` 里一句话值得抄进我们的设计原则：

> The LLM supplies the conversation and generated content; the runtime owns model updates, prerequisites, review timing and the evidence used for progress claims.

和我们的“标签不得写掌握”一致，但它做得更彻底：连**下一步做什么活动**都由 runtime 决定，LLM 只负责措辞。

## 3. 八个可借鉴模式

### A. 纯函数决策 + 显式优先级级联 + 回退计数

`engine/action_selector.go`：

- `SelectAction` 是纯函数：不读库、不联网、不取 `time.Now()`，输入是 `(concept, ConceptState, misconception, ActionHistory)`。
- 文件头直接写“**隔离是契约**”：`SelectConcept` 可以改而不影响 `SelectAction`。
- 非有限数值（NaN）不是静默兜底，而是走 REST 并累加 `NaNFallbackCount`，把“上游数据坏了”变成可观测指标。

我们的现状：`analyze_teaching_turn` 是纯函数，但 `TeachingTurn` 把决策、状态、工具、提示词揉在一个 700 行类里；`parser=fallback` 只写进结果，没有计数。

借鉴：把“决策”抽成 `decide(turn, snapshot) -> TeachingDecision`（纯函数），`TeachingTurn` 只执行；fallback 原因进计数器或 trace，而不是只留在字符串里。

### B. PreviewOnly：只投影决策，不落状态

`OrchestratorInput` 里有 `PreviewOnly bool`：`project FSM transitions and select an activity without persisting phase changes`。它专门给“学习协商”这类界面用。

我们的 `shadow` 只在输入理解层，教学决策没有对应的“预演”开关。P3 的真实模型对照现在靠“off/on 两次跑”，成本翻倍。

借鉴：给 `TeachingTurn` 加 `preview=True`，算出策略/结构/回合决策但**不写 `pending_question`、不推进 stage、不记 `used_strategies`**。这样影子对照可以在一次运行里同时得到两套决策。

### C. 决策契约（Decision Contract）

`tools/activity.go` 把“选了哪个知识点、用了哪版课程/策略、带了什么约束”写进一条可审计记录，让后续评估能绑定到真正的决策，而不是事后猜。

我们完全没有：`teaching` 状态里有 `last_strategy`/`used_strategies`，但没有“为什么选它、依据哪版标签/策略库”。

借鉴：`state['decision'] = {decision_id, strategy, source: rule|label|rotation|assessment, policy_version, ontology_version, candidate_set, reason}`。纯记录，不改行为；同时解决 P5 争议——先有契约，才能谈删 `move` 和改 enum。

### D. 稳定性窗口 / 滞回，防策略乒乓

`action_selector.go`：

- `HighMasteryStabilityWindow = 3`：连续 3 次高于阈值才进入高掌握轮换；否则会在 0.86→挑战→失败→0.84→练习→0.86 之间振荡。
- Phase FSM 有滞回带：进入 maintenance 要全部 ≥0.85，退出只要一个 <0.70。

我们的实测数据：`LABELS_POLICY=off` 的 5 条“分不清”样本（各自独立会话）策略是 `break_down, worked_example, break_down, break_down, worked_example`。这不是同一会话内的乒乓，而是“每轮都从轮换表重新挑”，连续三轮以上“还是不懂”时会重复回到同一策略。`used_strategies[-6:]` 已经存了历史，但只有旧 `StrategyRouter` 用 `recent_moves[-2:]` 扣分。

**已实现（2026-10-31）**：`TeachingTurn._avoid_repeat()`——困难轮次中，若当前策略出现在最近两轮 `used_strategies`，换 `SUPPORT_CHOICES` 里第一个未用过的候选；非困难轮次不干预。真实模型复测见 `SEMANTIC_CLASSIFIER_STAGE_C_LIVE_20261031.md` §8。

### E. 保留 envelope、严格解析、永不展示

`client/src/studyRequests.ts` / `learningActivityModel.ts`：

- 模型把结构化请求写进代码块围栏（`tutor-study-request`），客户端用**键白名单 + 字节上限 + 枚举校验**解析，任何多余键直接拒绝。
- `visibleStudyText()` 把所有保留 envelope 从展示文本中剥离，注释写明“reserved envelopes are transport data, never product copy”。

我们踩过同类坑：模型把工具协议写进正文，最后靠“协议修复 + 重试检索”兜。

**结论：不采用剥离，保留现有拒绝。** `agents/agent_loop_service.py` 已用正则拦下 `DSML` / `<tool_call`，判定失败并拒绝发布（line 158）；这是“宁可少发一条，也不发半成品”。tutor-mcp 的剥离适用于“envelope 由自家客户端生成”的场景，我们的协议文本来自模型违规输出，剥离会把违规内容混进正文。记录为已知差异，不实施。

### F. 辅助模型调用的边界：小任务模型、超时、缓存、空值是合法答案

DeepTutor `services/mastery_hints.py`：

- 用 `task_llm_scope(TaskKind.MASTERY_ASK_HINT)` 走**小任务模型**，不占用主对话模型。
- 12 秒超时，失败返回空；调用方注释写明“empty is a real answer, not an error”。
- 缓存键是 `(path_id, knowledge_point, transcript_length)`，重开页面不重复生成。
- `_sanitize` 只做一件事：必须以问号结尾，否则丢弃——**用最便宜的信号校验模型是否遵守了任务**。

这正好回答我们阶段 C 的悬案：如果要做“短句标签的模型兜底”，应当按这个模式做——小模型、短超时、按 `(raw_text, ontology_version)` 缓存、失败即弃权，并把调用计入预算。

### G. 状态投影边界：extract / apply 分开

OpenMAIC `learner-state.ts`：

- `extractLearnerState(project)` 从权威项目里抽取运行时可用的学习状态；`applyLearnerState` 反向合并。
- `usableAssessment()` 把“形状不合法的已存评估”在**读取和写入两端**都当作不存在，避免坏数据复活。

我们的 `ontology.build()` 是 extract（只读投影），但没有 apply，这是对的（标签不写回）。值得补的是 `usableAssessment` 式防御：`annotations` 里形状不合法时应当整条忽略，而不是让整个 `GroundedTurn` 校验失败。

### H. 输入需求声明 + 满足检查

OpenTutor `services/agent/state.py` 的 `InputRequirement`：每个 key 带 `question/options/check`，`check` 是“这个输入是否已经满足”的纯函数；未满足才向用户澄清。

我们的 `missing_slots` 只有枚举，没有“怎么问、什么算满足”。借鉴：把 `missing_slots` 从字符串列表升级为 `{key, question, options, satisfied(turn)}`，澄清文案就能按槽位生成，而不是一句通用“请补充对象”。

## 4. 不建议借鉴

| 项 | 原因 |
|---|---|
| BKT / FIRe / FSRS 数值模型（OpenTutor、tutor-mcp） | 需要真实作答序列校准；我们已有 `LearningEvidence`，再加一套会变成两个掌握度来源 |
| 14 个 `TaskPhase` + agent swarm（OpenTutor） | 那是执行编排状态，不是教学状态；我们的 `TaskService` 已有等价物 |
| 多 Agent 规划器（GenMentor 等） | 我们只有一个教学回合，多 Agent 只增加调用与不一致 |
| LangGraph 迁移 | `towardsai/ai-tutor-app` 描述里写 LangGraph，实际代码是 `chat_service.py` 手写流程；没有证据表明图编排带来收益 |
| GPL/AGPL 项目的代码 | tutor-gpt、ChatTutor 只能看思路 |

## 5. 对我们剩余工作的映射

| 我们的问题 | 对应模式 | 最小落地 |
|---|---|---|
| P5 不敢删 `move`/改 enum | C 决策契约 | 先记录 `decision`，用真实数据比较“投影 vs 旧结果”，再谈删除 |
| 策略乒乓（实测已存在） | D 稳定性窗口 | 最近 2 轮同策略则换；locus 变化则允许 |
| 灰度只能 off/on 两次跑 | B PreviewOnly | `preview=True` 同轮产出两套决策 |
| 短句标签漏检、又怕加延迟 | F 辅助调用边界 | 小模型 + 8s 超时 + 按文本缓存 + 失败弃权 |
| 工具协议进正文 | E envelope 剥离 | 发布前剥离保留块，补单测 |
| 澄清文案千篇一律 | H 输入需求声明 | `missing_slots` 带 question/options |

## 6. 三个最小改动的实施结果

| 顺序 | 改动 | 状态 | 说明 |
|---|---|---|---|
| 1 | 决策契约（`state['decision']` 纯记录） | **已实现** | 字段 `{strategy, source, label_strategy, avoided_repeat, policy_version, ontology_version}`；`source ∈ assessment/label/rotation`。不存 `difficulty_locus` 值，避免标签泄进会话状态（边界测试已锁） |
| 2 | 策略稳定性窗口 | **已实现** | 困难轮次最近两轮同策略则换候选；非困难轮次不动。真实模型复测：on 由 5/5 contrast 变为 4/5 contrast + 1 worked_example（该例上一轮已是 contrast） |
| 3 | Envelope 剥离 | **不实施** | 现有发布门禁直接拒绝 `DSML/tool_call` 协议文本，比剥离更安全；剥离会发布半成品 |

测试：`tests/test_teaching_decision.py` 4 项；分类器相关 63 项、教学 67 项通过。

## 7. 许可与合规

- 可直接参考实现：DeepTutor（Apache-2.0）、OpenMAIC / tutor-mcp / OpenTutor（MIT）。
- 只可看思路：tutor-gpt（GPL-3.0）、ChatTutor（AGPL-3.0）。
- 本报告没有复制任何代码；若移植 Go/TS 逻辑，需记录来源仓库、commit 与改写范围。
