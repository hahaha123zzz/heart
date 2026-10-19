# Q1 对话质量收尾与并行验收记录

日期：2026-10-19。分支：`codex/q1-dialogue-finish`。工作树：`E:\项目\heart-worktrees\q1-dialogue-finish`。基线：`2d4b4d0`（包含 Q1 提交 `dc278fe`、`3fac21d` 与 Q2 提交 `2d4b4d0`）。

本记录只追加 Q1 收尾结果，不覆盖主工作区的 `IMPLEMENTATION_PLAN.md`、`QUALITY_BASELINE.md`、`EXECUTION_LOG.md` 或其他窗口的 Q2 记录。

## 1. 工作树与未提交依赖

主工作区保留原状，未提交改动未搬入本分支。以下依赖只作本机验收用，未提交：

| 依赖 | 处理 |
| --- | --- |
| `.env`（模型凭据、`TUTOR_COURSE` 等） | 从主工作区读取到进程环境变量，未复制、未打印、未提交。 |
| `knowledge/courses/experimental-psychology-3/`（未跟踪教材、索引、PDF、裁图） | 通过目录 junction 只读指向主工作区；验收结束后移除，未复制、未提交。 |
| `data/` 下未跟踪设置 | 文本对话验收不需要；未复制。 |
| `.venv-gpu` | 使用主工作区现有虚拟环境解释器，未复制。 |
| 主工作区未提交的 `main.py`、`worker.py`、`.env.example`、文档和教材删除 | 未纳入本分支。`git diff main.py` 在检查时为空；`worker.py` 的原生入口移除属于其他窗口未提交工作，本分支不代为提交。 |

因此本分支的 Q1 验证不能证明主工作区未提交的 worker/native 改动已验收。

## 2. 计划状态矛盾核对

| 计划项 | 计划标记 | 实际核对 |
| --- | --- | --- |
| Q1.1 复现 6 组连续对话与 9 类黄金集文本案例 | 未勾选 | 计划文字“6 组连续对话 + 7 个文本黄金案例”与运行器一致：`answer/hint/refusal` 共 7 个文本案例，`selection/vision` 不在文本集合。选区/视觉仍未通过，Q1.1 保持未完成。 |
| Q1.2 上下文、预算、提示词块 | 已勾选 | 代码与测试均存在；本轮未改 `agents/conversation_context.py`、`agents/prompt_blocks.py`、`agents/course_prompts.py`。 |
| Q1.3 Router/TaskContextBuilder/ResponseGenerator/Orchestrator 改造 | 已勾选 | 本轮未改 `conversation_router.py`、`task_context_builder.py`、`response_generator.py`、`orchestrator.py`；只改 `task_execution.py`、`reply_budget.py` 和 `followup_context.py`。 |
| Q1.4 换说法、简化、比较承接、明确指令 | 已勾选 | 原有测试通过；本轮新增“只确认单对象”“换种解释/通俗/简化表达”“区分三类变量”回归，并完成真实模型复验。 |
| Q1.5 原文、引用、公式、失败反馈 | 已勾选 | 质检失败仍以 `quality_rejected` 停止发布；公式案例在扩大多子问题预算后通过，并保留引用与“不编造数据”约束。 |
| Q1.6 页面和多轮前后对照 | 已勾选 | 实际证据是隔离端口 `8010` 上的“失败→修复→复验”，不是同一模型/教材的迁入前 vs 迁入后受控对照。`IMPLEMENTATION_PLAN.md` 第 165 行“Q1.6 仍缺浏览器页面级前后对照”与第 100 行勾选、第 102 行 M1 说明存在口径冲突。按严格口径，Q1.6 只能算“页面失败/修复复验完成，完整前后对照未完成”。 |
| M1 | 已声明达成 | 普通文本对话与连续追问已走本地迁入模块；选区/视觉、Q2—Q6 未完成，不能把 M1 当作 Q1 整阶段或整套能力完成。 |

## 3. 本轮代码修改

| 文件 | 修改 |
| --- | --- |
| `agents/followup_context.py` | 补“换种解释/换个解释/通俗/简化表达/浅显”等简化追问别名；把“只确认/只想再确认某个对象”识别为缩小范围，同时排除“每类只讲一个要点/只解释一遍”等数量限制。 |
| `agents/task_execution.py` | “区分/区别/辨析”明确转为 `explain`，不改成连续追问；显式完整解释不再重复追加 `explain`；最后对意图去重。 |
| `agents/reply_budget.py` | 多子问题检测补 `、` 和“两个/两类……区别”；含公式、符号列表的多子问题提高到目标 480 字、上限 500 字。 |
| `scripts/check_conversation_quality.py` | 独立样本使用独立学生与会话历史；仅 `follows` 依赖样本继承父样本历史，避免跨样本“教学动作连续 3 轮未变化”污染。 |
| `tests/test_conversation_context.py` | 新增简化别名、单对象缩小、Router 覆盖、数量限制保留比较、完整解释不重复意图测试。 |
| `tests/test_task_execution.py` | 新增“区分三类变量”必须解释的测试。 |
| `tests/test_reply_budget.py` | 新增公式符号列表预算测试。 |
| `tests/test_conversation_quality_harness.py` | 新增独立样本不共享学生历史测试。 |
| `tests/test_task_resource_execution.py` | 新增选区裁图同时进入生成、质检和证据充分性检查的接口测试。 |

未修改 `orchestrator.py`、`conversation_router.py`、`conversation_context.py`、`response_generator.py`、`task_context_builder.py`，避免与其他窗口的共享模块改动冲突。

## 4. 离线验证

命令（宿主目录）：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONPATH=(Get-Location).Path
& 'E:\项目\heart\project\integration\discrete-math-tutor\.venv-gpu\Scripts\python.exe' -B -m unittest `
  tests.test_conversation_context tests.test_conversation_quality_harness tests.test_quality_guard `
  tests.test_task_execution tests.test_task_service_context tests.test_reply_budget `
  tests.test_routing_validation tests.test_multiturn_feedback tests.test_interaction_style tests.test_citation_guard `
  tests.test_task_resource_execution.TaskResourceExecutionTests.test_pdf_selection_passes_resolved_crops_to_generation_and_quality
```

结果：`129` 项通过，日志 `.runtime/q1-core-clean-tests.log`。其中选区裁图接口测试单独运行通过（1.24 秒）。

未纳入干净集合的既有失败：

- `tests.test_task_context` 4 项因工作树缺少离散数学 PDF/习题目录失败（`chapter-07` 不存在、习题目录为空）。主工作区同样缺少这些未跟踪/已删除数据，属于既有数据漂移，不计为本轮回归。
- `tests.test_quality_parallel` 在心理学课程模式下 4 项失败（证明核验被课程模式关闭）；在 `TUTOR_COURSE=discrete-math` 下 4 项全部通过。该失败在主工作区同样复现，属于既有课程模式测试假设，不是本轮改动引入。

## 5. 真实模型本地链路

运行器：`scripts/check_conversation_quality.py --live`，使用本地 `TutorOrchestrator`、真实模型、隔离 `DATABASE_URL`/`COURSE_DATABASE_URL`，不委托独立 DeepTutor 应用。

### 5.1 失败与修复过程

| 运行 | 结果 | 说明 |
| --- | --- | --- |
| `.runtime/q1-final/20261019T125027Z-78f3c7` | 8/11 活动案例通过，3 失败；2 项延后 | 旧运行器让所有独立样本共享学生和历史；`comparison_followup`、`accuracy_is_not_hint` 被前序样本的“连续 3 轮教学动作未变化”拒绝，`explicit_hint_then_explain` 第二轮受历史污染被证据拒绝。此运行保留，不拼成绿色结果。 |
| `.runtime/q1-final-isolated/20261019T130740Z-bb999c` | 3/3 通过 | 隔离运行 `comparison_followup`、`accuracy_is_not_hint`、`explicit_hint_then_explain`，证明失败来自运行器样本隔离缺陷。 |
| `.runtime/q1-final-clean/20261019T131440Z-9e7b9c` | 9/11 活动案例通过，2 失败；2 项延后 | 修复样本隔离后的完整运行：`accuracy_is_not_hint` 因 260 字预算拒绝；`variables` 因“区分三类变量”未进入解释任务而改为追问被拒绝。 |
| `.runtime/q1-targeted/20261019T133324Z-3e209b` | `variables` 通过，`accuracy_is_not_hint` 仍拒绝 | “区分”修复生效；公式案例在 360 字上限下仍被拒绝。 |
| `.runtime/q1-targeted2/20261019T133606Z-e649f6` | 通过 | 公式符号列表预算提高到 500 字后，完整解释 X、St、PSE、N、两个公式参照点与 CE 条件，保留引用，未编造数据。 |
| `.runtime/q1-targeted3/20261019T133711Z-f5e3d7` | 通过 | “区别”进入解释任务后，操作性/选择性自变量与年龄性别分组边界完整回答。 |

没有一份“最终代码、单次运行、全部 11 个文本案例同时通过”的报告；上表按运行分别记录，不把不同运行拼成一次绿色运行。

按案例合并，11 个文本案例在最终代码上都有通过记录：完整运行覆盖 9 个，修复后定向复验覆盖 `accuracy_is_not_hint`、`variables`、`classification`，并另以隔离运行复验 `comparison_followup`、`explicit_hint_then_explain`。这是多次运行的合并事实，不是单次全绿。

### 5.2 逐项行为核对

| 行为 | 样本 | 结果与人工核对 |
| --- | --- | --- |
| 连续追问 | `explicit_hint_then_explain` | 首轮 `hint_only=true`、只给提示、不出新题；次轮 `hint_only=false`、完整解释随机分配、保留引用、无重复 `explain` 意图。 |
| 换种解释 | `simplify_without_switching`、`followup` | “没听懂，请换一种更简单的说法”保留上一轮自变量对象，不改成末尾检查题，不引入新章节；新增“换种解释/通俗/简化表达”离线回归。 |
| 简化表达 | `simplify_without_switching` | 第二轮回复简化为“研究者自己安排、自己改变的那个条件”，保留教材引用。 |
| 比较对象承接 | `comparison_followup` | 第二轮只回答被试内设计，不再展开被试间设计；新增“只确认被试内设计”不带“不要引入其他”的离线回归。 |
| 用户明确指令 | `hint`、`explicit_hint_then_explain`、`accuracy_is_not_hint` | 仅提示不泄露完整结论；明确完整解释覆盖上一轮仅提示；“不要编造数据”仍为完整解释，不是 hint。 |
| 公式/符号忠实 | `accuracy_is_not_hint` | 解释 X、St、PSE、N、两式参照点，明确“现有摘录未给出两式数值大小关系”，不编造实验数据。 |
| 三类变量区分 | `variables` | 自变量、因变量、额外变量逐项解释并分别引用；不再以追问代替讲解。 |
| 分类边界 | `classification` | 操作性/选择性自变量及年龄性别分组边界通过，引用 4 条来源。 |
| 拒答 | `refusal` | `evidence_rejected`，无引用、无步骤推进，未编造人数/p 值。 |
| 澄清/偏好撤销 | `clarify_and_continue`、`correct_and_forget` | 仍分别延后到 Q3、Q5，未标记通过。 |

## 6. 选区/视觉样本与接口要求

样本来自 `tests/data/deeptutor-golden.json`，本轮未标记通过，也未将旧验收记录折算为 Q1 通过。

| 样本 | 输入 | 当前接口 | 通过所需条件 |
| --- | --- | --- | --- |
| `selection`：`请解释我选中教材里的自变量含义，并引用本次选区。不要出题。` | `ChatRequest.selection`：`document_id`、`version`（64 位哈希）、`kind=text`、`rects`；服务端 `resolve_selection` 校验版本/页码/坐标/文件 SHA 并读取选中文本。 | `main._execute_task_turn` → `agents.pdf_selection_tutor.explain_selection`；`resolved['images']` 进入证据充分性、生成和质检。 | 选区命中真实原文；回答引用 `[1]`；`selection_ref`/`pdf_references` 可回原页；不得用通用检索替代选区。 |
| `vision`：`请解释我框选的两个差别感觉阈限DL公式：X、St、PSE、N分别是什么，两个公式的参照点有什么区别？引用这个选区，不要编造实验数据。` | `ChatRequest.selection.kind=area`，单页单框；服务端裁图生成 PNG（≤8 MB，最多 2 张），并校验 `crop_path` 内容哈希。 | `LLMClient.chat(image_paths=...)` → 视觉模型 `OPENAI_VISION_MODEL`；同一批图片进入 `QualityChecker`；接口测试已验证图片同时进入生成、质检、证据检查。 | 真实 PDF 原图可读；回答逐项解释 4 个符号、两式参照点和 CE 条件；引用选区；不得在图片不可读时悄悄退回纯文本或编造公式。 |

选区/视觉仍未完成的部分：

- Q2.4 的 `visual_assets/source_visuals` 迁入、原图与 `source_visuals` 身份映射；当前只验证了现有 PDF 裁图路径，不能声称 Q2 视觉资产链路完成。
- Q2.5 的教材版本发布、索引进度/就绪和换版绑定；当前 `version` 校验是单文件 SHA，不等于完整发布清单。
- Q2.6 的概念/比较/同义/跨章/图表公式/未命中/换版检索验收。
- 页面阅读器的选区→聊天请求、流式事件、裁图展示和失败提示的浏览器级验收。
- 选区内的连续追问（“再简单点”）尚未接入 `followup_directive`/`history_summary` 的完整契约；Q1 这轮只验证了普通聊天入口的连续追问。

因此 Q1.1 的选区/视觉两类保持未完成，不能用旧 `.runtime` 结果或本轮接口测试代替真实接通。

## 7. 未通过项与集成依赖

| 项目 | 状态 | 依赖/说明 |
| --- | --- | --- |
| Q1.1 选区/视觉 2 类 | 未通过 | Q2.4/Q2.5/Q2.6 + 页面阅读器接通。 |
| Q1.6 严格前后对照 | 部分完成 | 已有页面失败/修复复验；缺迁入前基线与同一模型/教材的受控对照。 |
| 澄清与任务恢复 | 未验证 | Q3 `ask_user`、任务 revision、事件恢复。 |
| 偏好撤销/遗忘 | 未验证 | Q5 偏好与删除语义。 |
| 浏览器页面级选区/视觉 | 未验证 | 现有页面运行只覆盖普通对话和连续追问。 |
| 主工作区未提交 worker/native 改动 | 未纳入 | 本分支不携带、不代为提交。 |

## 8. 复现与环境说明

- 离线核心集合：见第 4 节命令，129 项通过。
- 真实模型单案例：

```powershell
& 'E:\项目\heart\project\integration\discrete-math-tutor\.venv-gpu\Scripts\python.exe' -B `
  scripts/check_conversation_quality.py --live --include-golden --case accuracy_is_not_hint `
  --output .runtime/q1-targeted2
```

- 隔离运行会在 `.runtime/<output>/<run>/` 生成 `course.sqlite3` 和 `report.json`；不写入正式学习库。
- 本工作树通过 junction 使用主工作区未跟踪教材；提交前已移除 junction，未提交教材、数据库或运行产物。

## 9. 提交边界

本轮只提交第 3 节列出的代码/测试和本记录。不合并主分支，不覆盖主工作区，不提交 `.env`、教材、数据库、`.runtime` 报告或其他窗口的 Q2 改动。
