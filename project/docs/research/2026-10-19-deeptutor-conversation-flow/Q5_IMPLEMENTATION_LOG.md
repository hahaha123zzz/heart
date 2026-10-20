# Q5 首批业务实现记录

日期：2026-10-20。Worktree：`E:\项目\heart-worktrees\q5-learning-design`；分支：`codex/q5-learning-design`。

## 1. 基线

- 设计提交：`4bb7921`（Q5 设计、接口、验收矩阵）。
- 集成分支最新已提交：`aef246b`（`codex/integration-q1-q4`）。
- 本批合并提交：`8601a78`（`Q5: 引入集成分支 Q3/Q4 最新提交作为实现基线`）。
- 未复制其他窗口未提交工作树；未修改主工作区 `E:\项目\heart`。

## 2. 上游来源与许可证

固定上游：`D:\deeptutor`，提交 `6cf793bd868ba5ecbe64722936d4be8fab5a01df`，Apache-2.0。上游根目录无 NOTICE；本项目 `third_party/DeepTutor/LICENSE` 保留，NOTICE 追加 Q5 说明。

| 上游文件 | SHA-256 | 本批用途 |
| --- | --- | --- |
| `deeptutor/learning/models.py` | `66e8188c601cee457a0bc17d66b3a20e0181a2b2a0c51355b2ef9225ca5e3f4a` | 路径/模块/目标/进度/画像字段参考 |
| `deeptutor/learning/policy.py` | `07f4f8cf5911c1c383a674844c84adfd7355a2b28cfd1620742272514138e91c` | 当前/下一目标、讲解/覆盖/掌握分离语义 |
| `deeptutor/learning/service.py` | `db80368e5fdbae06228193a09d65edf25375dd6f79fc2e75d92af6d18ea6e35b` | 目标身份、局部修订、计划命令语义参考 |
| `deeptutor/learning/storage.py` | `1f07c18ac1f59b621b5c565984f7f6876e0e7c42eb2efc538e02a577ef04a94b` | 路径/绑定的存储边界参考（未复制 JSON 存储） |
| `deeptutor/learning/scheduler.py` | `07146a2075a9230a5be7cea8b23f38d227c2390b2636cfa82c9d238f46303864` | 后续复习批次参考，本批未启用 |
| `deeptutor/capabilities/mastery/tools.py` | `b6be3c50425472056c4744f7d80917a6a2e3ccd8226f752e1d9e4092608c3872` | `mastery_status`/`build`/`note_explained`/`mode`/`paths`/`switch`/`leave`/`revise` 语义参考 |
| `deeptutor/capabilities/mastery/mode.py` | `00f9794d49e34d4ff6273c3509c8cc9eb07368d133d017402c1f77f0e0ce9a31` | outline/study/review 模式边界 |
| `deeptutor/capabilities/mastery/capability.py` | `53312360f451fbe9f60976490026714b33201c21041a1d309380ef14856864dc` | 路径绑定/租约边界参考（未复制应用容器） |
| `deeptutor/capabilities/mastery/prompts/zh/mastery_loop.yaml` | `4df64164ad95ff0fcd3072bb65cf7811c16c2fa0d65db9c33efbb627a18acffd` | intake/大纲/讲解/模式语义参考；未复制提示词运行时 |
| `deeptutor/services/courses_state.py` | `d5a31ecd4ba7de06af25d8cf9a81532cbe4d6fef2b6e65fff05565ff861b39c3` | 课程状态/交接后续批次参考 |

本批**没有**复制上游账户、会话、`LearningStore` JSON、工作区路径服务、应用容器或完整 DeepTutor 应用。

## 3. 本项目实现

| 文件 | 内容 |
| --- | --- |
| `database/q5_learning.py` | 首批 6 张表：`q5_learning_paths`、`q5_learning_modules`、`q5_learning_objectives`、`q5_learning_progress`、`q5_learning_bindings`、`q5_learning_commands`；`ensure_q5_schema()` |
| `agents/q5_learning.py` | `LearningScope`、`PlanDraft`/`ObjectiveDraft`、`Q5LearningService`：生成/保存草稿、确认、模式、讲解记录、教学位置推进、路径切换/离开、局部改名保护、来源校验、命令幂等、恢复 |
| `agents/q5_plan_generator.py` | `LLMPlanGenerator`：通过项目 LLM 客户端生成计划 JSON；系统提示要求来源、模块能力句、知识类型，不产生掌握分 |
| `agents/q5_tools.py` | Q3 `BaseTool` 首批工具：`mastery_status`、`mastery_build`、`mastery_note_explained`、`mastery_understood`、`mastery_mode`、`mastery_paths`、`mastery_switch`、`mastery_leave`、`mastery_revise`；`build_q5_registry` 用 Q4 `ScopedToolRegistry` 授权挂载 |
| `agents/q5_turn_adapter.py` | 集成窗口最小接线：生成计划、确认开始、绑定 Q2 教材目标/圈选来源、返回 Q3 target/registry/tool_state；不修改 main.py/TaskService |
| `tests/test_q5_learning.py` | 29 项隔离 SQLite 测试 |
| `database/database.py` | `init_db()` 增加 Q5 模型 import，确保建表（一行集成改动） |

### 3.1 已实现语义

- 生成计划（注入 generator；`LLMPlanGenerator` 为真实 LLM 适配器）→ 校验模块/目标/类型/来源 → 保存 `draft` → 绑定当前会话。
- intake：`intake_gaps` 只返回缺失的基础/目标/时间/偏好字段，已有值不重复问；集成窗口用 Q3 `ask_user` 呈现。
- 并发保护：`mark_understood` 支持 `base_revision`；旧 revision 返回 `path_conflict`，不推进。
- 展示/确认：`confirm_plan`，或 `mastery_mode(study, confirm=true)` 在用户明确认可后确认；未确认不能 study。
- 讲解：`mastery_note_explained` 只写 `explained`，不写 `mastered`。
- “我懂了，下一部分”：`mastery_understood`/`mark_understood` 只推进**教学位置**；`mastered` 始终 false。形式掌握门槛留后续。
- 圈选来源：`bind_selection` 将 Q2 解析后的 document/version/unit/page 转为 source ref；可新建单目标路径或按来源绑定已有路径，后续无需重复圈选。
- Q3 导航：`Q5Navigator` 只返回 Q5 当前教学位置，不重新解析教材；检索仍由 Q2 callback 提供。
- 教材目录导航：`bind_textbook_target` 只投影 Q2 当前目标（id/title/chapter/section/version/source_version/release_id），不计算下一目录项；`mastery_understood` 在教材路径返回 `requires_navigation=true`，下一步由 Q2 决定，避免本地第二套目录游标。
- 集成适配：`Q5TurnAdapter` 给集成窗口提供 generate/confirm/bind/loop_binding，不修改公共入口。
- 刷新/重启：新 `Q5LearningService` 实例从同一绑定/路径/进度恢复当前目标。
- 重复命令：`q5_learning_commands` 按 `(student_id, command_id)` 返回首次结果，`replayed=true`，不重复推进。
- 路径切换/离开：会话绑定切换；路径自身 `current_objective_id` 保留，切回恢复；不串进度。
- 来源失效：`status` 返回 `source_unavailable`；`mark_understood` 抛 `source_unavailable`，不推进。
- 局部修改：未确认草稿可改目标名；已确认需 outline 模式；已讲解/已理解目标拒绝修改。
- Q3/Q4：Q5 工具通过 Q3 `BaseTool` 协议和 Q4 `ScopedToolRegistry` 挂载；测试跑真实 `LocalAgentLoop` + `dispatch_tool_calls`；未另建循环或工具协议。

### 3.2 数据库

新增表均在项目 SQLAlchemy `Base` 下，学生删除级联；不覆盖现有表。旧 `learning_tasks`/`task_requests` 未改；`init_db()` 负责创建 Q5 表。测试使用临时 SQLite，未触碰正式库。

### 3.3 Q2 接口依赖（未复制主工作区未提交 Q2 代码）

- 最新 Q2 `course_navigation` 的 `resolve`/`bind_result` 返回含 `id`、`title`、`chapter_id`、`section_id`、`version`、`source_version`、`source_valid` 的 cursor。Q5 `bind_textbook_target` 接受这些字段，只保存当前目标投影，不计算下一目录项；下一步由 Q2/Q3 决定。
- 最新 Q2 `course_release` 提供 `release_id`、`status`、`ready`、`gaps` 和 `validate(expected)`。Q5 source ref 保留 `release_id`/`source_version` 字段；集成时应先用 `course_release.validate` 校验，再把有效来源交给 Q5。
- 本批只读主工作区最新 Q2 接口，没有把其未提交的 `course_navigation.py`/`course_release.py` 复制进 Q5 分支。Q5 不解析目录、不重写检索，也不依赖图谱状态。

### 3.4 接口/集成点（尚未接入 TaskService/main）

本批不修改 `main.py`、`TaskService`、前端公共入口或 `agent_loop_service.py`。集成窗口需要的最小接线：

1. 任务开始前：用 `Q5LearningService.status(scope)` 判断是否已有计划；普通单次问答不自动建计划。
2. 需要建计划时：`generate_plan(...)` 或 `mastery_build` 工具；展示、确认后 `set_mode("study")`。
3. 构造 Q3 `LoopRequest` 时：
   - `target = service.current_target(scope)`
   - `tools = build_q5_registry(service, scope)`（或合并到现有 Q4 registry）
   - `tool_state = service.tool_state(scope)`
4. 循环后读取 `service.status(scope)` 保存/展示当前位置；Q3 任务 revision/取消仍由 TaskService 管理。
5. 不建议把 Q5 服务放进 `TaskService` 内部；保持 Q5 领域服务与 Q3 循环、Q4 工具、任务身份分离。

## 4. 验证

### 4.1 隔离 Q5 测试

```powershell
$env:PYTHONPATH=(Get-Location).Path
& 'E:\项目\heart\project\integration\discrete-math-tutor\.venv\Scripts\python.exe' -B -m unittest tests.test_q5_learning -q
```

结果：**29 项通过，0 失败**。使用临时 SQLite（`.runtime` 之外临时目录），未触碰正式数据库。覆盖：

- 计划生成/确认/开始/目录/来源版本；
- 讲解/理解推进/不产生掌握；
- 刷新恢复；
- 重复命令幂等；
- 路径切换/离开/恢复；
- 来源失效阻止推进；
- 局部修改保护；
- Q3 真实 `LocalAgentLoop` + Q4 `ScopedToolRegistry` 调用 `mastery_note_explained`、`mastery_understood`；
- 插问式单轮不移动教学位置；
- `mastery_build` 工具保存草稿并通过 `mastery_mode(confirm=true)` 确认；
- 圈选 source ref 建路径/绑定已有路径；
- Q2 当前教材目标投影，不在 Q5 另算下一目录项；
- `Q5Navigator` 只读当前目标，不重新解析；
- intake 只返回缺失字段，不重复询问已有画像；
- 同路径教学位置推进的 revision 冲突保护；
- `Q5TurnAdapter` 生成→确认→loop_binding。

### 4.2 Q3/Q4/Q5 联合回归

```powershell
& 'E:\项目\heart\project\integration\discrete-math-tutor\.venv-gpu\Scripts\python.exe' -B -m unittest `
  tests.test_q3_agent_loop tests.test_q3_task_loop tests.test_q3_entrypoint `
  tests.test_q4_tool_foundation tests.test_q3_q4_integration tests.test_q5_learning -q
```

结果：**121 项通过，0 失败**（使用 `.venv-gpu`，因为 Q2/Q3 集成测试依赖 `llama_index`；Q5 自身测试也可在 `.venv` 运行）。未跑真实模型、浏览器或正式服务。

### 4.3 Q1/Q2 相关回归

```powershell
& 'E:\项目\heart\project\integration\discrete-math-tutor\.venv-gpu\Scripts\python.exe' -B -m unittest `
  tests.test_reply_budget tests.test_conversation_context tests.test_task_execution `
  tests.test_quality_guard tests.test_course_navigation tests.test_grounded_citations -q
```

结果：**109 项通过，0 失败**。日志中的 PDF 质检打印是测试预期输出，不是失败。

### 4.4 未执行/未声明

- 真实模型计划生成（`LLMPlanGenerator` 只用测试 LLM 验证 schema/解析）。
- 页面/浏览器、TaskService 端到端、SSE、刷新真实页面。
- 正式题卡、评分、掌握门槛（0.9/定性）、间隔复习、教师审核、视觉证据、课程交接。
- 并发路径租约/多窗口同时写；本批只做命令幂等和绑定隔离。
- 圈选入口的真实接线：服务已提供 `bind_selection` 和 source_ref 适配，但尚未修改 Q2 选区入口/TaskService 自动调用；需要集成窗口接线。

## 5. 剩余范围

- Q5.7：真实模型计划质量、intake 问题卡、完整展示/反馈 UI。
- Q5.8：review 模式、teach_first/probe_first 的完整行为、到期复习提示。
- Q5.9：路径列表/切换 UI、已确认计划的局部修订、re-target/新身份、路径租约。
- Q5.10—Q5.12：题卡/评分/纠错、掌握门槛/教师审核/复习、课程与阅读交接。
- 与集成窗口的 `TaskService`/页面接线和真实页面验收。

本记录只证明首批隔离链路；不表示 Q5 整阶段完成。
