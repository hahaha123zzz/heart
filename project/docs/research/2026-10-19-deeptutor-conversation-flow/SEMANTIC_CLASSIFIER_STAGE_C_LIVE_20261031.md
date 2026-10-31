# 阶段 C：同初始状态真实模型对照（2026-10-31）

性质：探索性小样本（每开关 5 例），进程内 HTTP + 真实 DeepSeek + 真实教材检索。**不宣称统计显著或教学效果提升**。

## 1. 运行条件

| 项 | 值 |
|---|---|
| 入口 | `scripts/accept_semantic_labels_live.py`（FastAPI TestClient → `/api/chat`） |
| 课程 | `TUTOR_COURSE=experimental-psychology-3` |
| 教材 | `knowledge/courses/experimental-psychology-3`（RAG 索引 15MB，检索正常） |
| 数据库 | 每次运行新建 `artifacts/semantic-live-<run>-<switch>-<value>.sqlite3`；已移除 `COURSE_DATABASE_URL` |
| 隔离 | 未使用 8000、未写正式库、未改教材；每个样本独立 student/session，无历史 |
| 开关 | `INPUT_UNDERSTANDING_MODE=active`、`SEMANTIC_LABELS_ENABLED=1`、`INPUT_UNDERSTANDING_SEMANTIC_ENABLED=0`；对照开关单独开 |
| 模型 | 真实网关；预检通过；单请求超时 40s；未记录密钥 |
| 证据 | `.runtime/baseline-20261031/live2-policy-*.log`、`live-structure2-*.log`、`live-turn-*.log`；原始 JSON 在 `artifacts/` |

off/on 各自新建数据库与全新会话，属“同初始状态”而非同一快照续跑。

## 2. LABELS_POLICY（策略定向）

5 例：先问教材概念，再问“分不清/搞混”。统计取第二轮。

| 条件 | answered | 策略分布 | 引用数 | 回复字数 | 耗时(s) |
|---|---|---|---|---|---|
| off | 5/5 | break_down 3、worked_example 2 | 0,3,0,0,1 | 315,325,343,318,398 | 2.2–3.6 |
| on | 5/5 | **contrast 5** | 2,3,0,0,1 | 313,279,365,294,295 | 2.4–3.1 |

结论：开关按设计生效，**5/5 从轮换变为对比**；时延无可辨差异（样本太小）。第二轮仍有 2 例无引用（沿用上一轮证据但未重新标注来源），属既有 `reuse_evidence` 行为，不是本开关引入。

## 3. LABELS_STRUCTURE（回答结构）

5 例：设计/评估/分析，均要求结合教材。

| 条件 | answered | 其他 | 回复字数 |
|---|---|---|---|
| off | 4/5 | 1 例 `quality_rejected`（34 字，“没有教材引用来源”） | 397,34,397,399,318 |
| on | 5/5 | — | 296,420,414,509,320 |

定性对照（`structure-compare.md`）：

- 设计题：on 出现“先定变量→排流程→最后查混淆”并把“自查”单列；off 是常规“目的/变量/流程/结论边界”。
- 评估题：on 先给四条评价标准，再逐条对照，最后给“部分合理、整体不够严谨”；off 在被拒后没有产出答案。
- 分析题：两者都按教材列内部效度因素，差异不大。
- 第 4 例 on 多出“伦理与事后说明”和“自查”两段。

结论：结构开关**可观察**，且在 1/5 例上避免了质量门禁失败；但样本小，不能归因于开关本身（off 的拒绝也可能是随机生成问题）。

## 4. LABELS_TURN（回合边界）

5 例：第二轮为“不想做了/跳过/要答案但禁止披露”。

| 条件 | turn_move | 回复字数 | 引用 |
|---|---|---|---|
| off | teach 5 | 138,348,125,54,372 | 全 0 |
| on | **check_skipped 3**、teach 2 | 101,332,160,53,291 | 0,4,0,0,0 |

- 3 例 skip 全部从 `teach` 变为 `check_skipped`，状态变化确定。
- 文本差异不大：off 时模型本身也会顺着“不做了”收尾，说明模型文本层常已合规，开关主要修的是**状态与后续衔接**。
- “直接告诉我答案，不要给我完整答案”：on/off 都只给提示，未泄露完整答案（n=1，不能当泄露率）。
- “先给答案再解释”未被规则识别为 `answer_seeking`（规则要求“直接/干脆”），因此 on/off 一致——这是已知的规则漏检，不是开关失败。

## 5. 失败记录

| 位置 | 现象 | 归因 |
|---|---|---|
| structure off #2 | `quality_rejected`，34 字，提示“没有教材引用来源” | 生成/引用门禁既有失败；on 同样输入通过，说明与生成随机性有关，未定位 |
| turn #4 第一轮（off/on 均） | “请结合教材解释双盲设计”被 `quality_rejected` | 与开关无关，两次都失败 |
| policy 第二轮 2 例 | 无 `pdf_references` | 既有 `reuse_evidence` 行为：沿用上一轮证据但不重复引用 |

上述失败均未通过改测试或放宽门禁消除。

## 6. 能说什么、不能说什么

能说：

- 三个开关在真实模型与真实教材检索下均按设计改变**策略/结构提示/回合状态**。
- 教材链路可用：首轮回答引用 1–4 条教材来源。
- 没有观察到答案泄露（仅 1 例相关样本）。

不能说：

- 不能说标签提升了学习成绩或回答质量（无量表、无对照评分、n=5）。
- 不能把 `quality_rejected` 的 1 例差异归因于结构开关。
- 不能把“5/5 contrast”当作准确率——样本是按规则选出来的。

## 7. 未完成

- 真实浏览器页面“分不清→对比”一轮（本轮只有进程内 HTTP）。
- 主对话与侧栏隔离的页面级验证。
- 15 例以上的扩大样本与人工质量评分。
- 答案泄露率、连续同策略率、动作集合 Jaccard 的正式分母统计。

## 8. 决策契约与防重复实现后的复测（2026-10-31 晚）

改动：`TeachingTurn` 增加 `state['decision']`（纯记录）+ 困难轮次防重复（最近两轮同策略则换候选）。未改提示词与检索。

复测 `LABELS_POLICY` off/on（新隔离库，各 5 例两轮）：

| 条件 | 第二轮策略 | 变化 |
|---|---|---|
| off | break_down 3、worked_example 2 | 与改动前一致 |
| on | **contrast 4、worked_example 1** | 改动前为 contrast 5/5 |

唯一的 worked_example 出现在第 1 例：该会话第一轮“解释信度和效度的区别”已经用了 `contrast`，第二轮“我还是分不清这两个概念”如果再上 `contrast` 就是重复，于是换 `worked_example`。这是防重复规则的预期行为，不是失败。

结论：防重复只在“上一轮同策略”时生效；新会话首轮仍按标签选 contrast。两轮样本无法验证三轮以上的效果，需要更长对话。

证据：`.runtime/baseline-20261031/live3-policy-{0,1}.log`。

**未验证**：`decision` 只在 `context.tutoring` 内，`public_state` 未暴露，页面与 SSE 看不到；本轮通过单测断言其字段，没有在真实请求里读取数据库状态字段。
