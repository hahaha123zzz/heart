# Q3 并行执行记录

日期：2026-10-19。分支：`codex/q3-agent-loop`。Worktree：`E:\项目\heart-q3`。基线：`2d4b4d0`（包含 Q1 收尾 `3fac21d` 与 Q2 首批 `2d4b4d0`）。

## 1. 基线核对

- 上游源码：`D:\deeptutor`，调研记录提交 `6cf793bd868ba5ecbe64722936d4be8fab5a01df`。
- 本项目主工作区未提交改动未复制、未覆盖；Q3 只在 worktree 内修改。
- 教材课程目录 `knowledge/courses` 在主工作区未跟踪，worktree 用本机 junction 指向主工作区只读数据用于基线；不提交教材文件。
- 基线测试（worktree，宿主 `.venv-gpu`）：
  `tests.test_task_api tests.test_task_context tests.test_conversation_context tests.test_local_rag`
  → 73 项，69 通过，4 项既有数据漂移错误（`chapter-07` 文档不存在；与 Q1 记录一致），日志 `.runtime/q3-baseline.log`。

## 2. 上游来源与 SHA-256

| 文件 | SHA-256 |
| --- | --- |
| `deeptutor/agents/loop/agent_loop.py` | `8d388f5772937ae72d6f39313fff2460e8d594e96f406c4acc96ca674c9c7a78` |
| `deeptutor/agents/loop/pipeline.py` | `8ec2ec26777c3bf5166dde992e4e093528d0961071a1d502f475663677752041` |
| `deeptutor/runtime/agentic/tool_dispatch.py` | `d7e8ab2a8e8020ef621c41bda33c3b67eea11304fc4b24e3519034bb5b2437d5` |
| `deeptutor/core/tool_protocol.py` | `6a456e2db36e816b5dfb8ce0f94ee5137756088d6e2565f6dd9ff080cce9dd54` |
| `deeptutor/tools/ask_user.py` | `e8ab4d4f5002728e4ca55707cc41ecfa469d67bfb95e51db886b81712bddeb29` |
| `deeptutor/services/session/ask_user_trace.py` | `1b3b36fdc5cc5bcf6d533299620b1fdd144e7d0a0a15e074230a06f0b073c6b8` |
| `deeptutor/services/session/model_history.py` | `335aaab5cfbf2aba6b50172e18d98eaf3d01cd27045bfdf96588dcd23473afbc` |

## 3. 接口契约

先写 [Q3_INTERFACE_CONTRACT.md](Q3_INTERFACE_CONTRACT.md)，明确工具协议、Q2 学习导航/检索调用点、ask_user 暂停接续、取消恢复、事件和验收分层。实现不得把整轮交给 `DeepTutorApp`/`TurnApplicationService`。

## 4. 实施顺序

- [x] Q3-A 工具协议与调度：ToolDefinition/Registry、去重、并发、超时、失败结果、pause 信号（`agents/tool_protocol.py`、`agents/tool_dispatch.py`）。
- [x] Q3-B LLM 工具调用协议：`LLMClient.chat_with_tools` 解析 OpenAI tool_calls，不改变现有 `chat` 行为。
- [x] Q3-C 本地 AgentLoop：探索/收尾预算、工具回合、ask_user 暂停、取消检查、强制收尾、长度修订一次（`agents/agent_loop.py`）。
- [x] Q3-D 任务接续：`TaskService` 保存/恢复 `loop_state`，答复替换原工具消息，重复答复与取消不重复执行；选择项也可接续。
- [x] Q3-E 教材/Q2 接点：`LearningNavigator` 先 resolve 再 search；Q2 本地检索通过 `Q3_RETRIEVAL_MODE=local` 显式启用，默认替身。
- [x] Q3-F 质量发布门禁：循环输出经过 `QualityChecker`/`citation_issues` 后才发布；失败保留 `quality_rejected`，长度问题允许一次压缩修订。
- [x] Q3-G 测试与记录：27 项 Q3 测试通过；150 项回归中仅 4 项既有数据漂移错误。

## 5. 实际实现

| 模块 | 内容 |
| --- | --- |
| `agents/tool_protocol.py` | ToolParameter/Definition/Result、Cancellation、ToolContext、ToolRegistry |
| `agents/tool_dispatch.py` | 单条 assistant 最多 15 个调用；参数校验、同批去重、普通工具并发、pause 工具最后执行、失败/超时 role=tool 结果 |
| `agents/ask_user_contract.py` | ask_user 问题卡结构、v2/legacy 参数校验、答复格式化与原工具消息替换 |
| `agents/tool_protocol.py` / `q3_tools.py` | `retrieve_course`（Q2 检索边界）、`ask_user`；未挂载工具拒绝执行 |
| `agents/agent_loop.py` | 单轮探索→工具→继续→收尾；8 轮探索/3 轮收尾；首轮失败直接失败，后续失败有界收尾；取消检查；ask_user 暂停；发布门禁与一次长度修订 |
| `agents/q3_navigation.py` | LearningTarget/NavigationDecision/SourceRef；Q3 先 resolve 目标；Q2 回调适配与替身导航 |
| `agents/agent_loop_service.py` | 接 `TaskContext`、任务保存、Q2 检索、来源映射、对话写入、质量门禁 |
| `agents/task_cancellation.py` | 进程内取消令牌；数据库 cancelled 状态作为兜底 |
| `agents/loop_prompts.py` | 课程约束、循环协议、当前目标、工具清单 |
| `scripts/check_q3_loop.py` | `stub` / `local` / `live` 三种可复现检查 |

共享入口改动（单独提交）：`agents/task_service.py`（loop pause/previous/ask_user 选项）、`main.py`（`LOCAL_AGENT_LOOP_ENABLED` 开关、取消令牌）、`agents/quality_checker.py`（Q3 有界 500 字门禁覆盖）、`llm/client.py`（tool-call 协议）。

## 6. 验证结果

### 离线

命令：

```powershell
& 'E:\项目\heart\project\integration\discrete-math-tutor\.venv-gpu\Scripts\python.exe' -B -m unittest `
  tests.test_q3_agent_loop tests.test_q3_task_loop tests.test_q3_entrypoint -v
```

- 27 项通过，日志 `.runtime/q3-final.log`。
- 覆盖：工具去重/未知工具/参数缺失/异常、ask_user v2/legacy、答复替换、循环工具回合、预算强制收尾、首轮失败、后续失败收尾、取消、质量拒绝、长度修订、导航先于检索、页面入口开关、选区不进入 Q3、任务 pause/resume/重复答复/取消/选项答复、对话保存。
- 回归：150 项，146 通过，4 项既有 `chapter-07`/空练习目录数据漂移错误，与基线一致；日志 `.runtime/q3-regression-final2.log`。

### 替身与 Q2 接口

- `python scripts/check_q3_loop.py --mode stub`：暂停→选项答复→同一任务继续，通过。
- `python scripts/check_q3_loop.py --mode local`：使用 Q2 `knowledge.local_rag.course_retrieval`，返回 1 条真实来源（`stub=false`），通过；这不是页面/真实模型验收。
- Q2 未提供“下一目标”回调时，`StubLearningNavigator`/`CallbackNavigator` 返回 `clarify` + `missing=("target",)`；Q3 不猜章节顺序。

### 真实模型联调（失败保留）

- `20261019T131213Z-dc50e4`：worktree 无 `.env`，首次运行缺少 API key；脚本修正为只读加载主项目 `.env`，未复制密钥。
- `20261019T132031Z-6a246e`：真实模型调用 `retrieve_course` 在 30 秒超时，工具返回失败，最终因无来源被门禁拒绝；已将 Q3 工具超时调到 120 秒，并修复超时线程仍等待的问题。
- `20261019T132407Z-42eb8c`、`20261019T132915Z-89b42f`：真实模型成功检索到 Q2 来源并进入工具循环，但回答超过质量门禁字数（先 260，后 500）；一次压缩修订后仍超限，最终 `quality_rejected`。后续 `sources` 已在失败结果中保留；该结果保留为真实失败，不写成通过。
- 真实模型运行使用隔离 `.runtime/q3-live` 数据库，未修改正式学习库、现有 8000 服务或教材索引。Q2 检索接口本身在 `--mode local` 和真实模型运行中均实际执行，但页面级真实验收尚未完成。

## 7. 依赖与未完成

- **Q2**：本地检索接口已可用于 Q3 工具；`LearningNavigator.resolve` 的“下一目标”仍等待 Q2.8 课程路径实现。Q3 不会自行解析章节或猜全局顺序。
- **Q4**：工具注册目前只挂载 `retrieve_course`/`ask_user`；完整 100 工具、MCP/CLI、权限和并发策略仍由 Q4 接入。
- **Q5**：Q3 只保存讲解对话，不更新掌握度/评分/学习路径；`append_exchange` 不调用 `commit_learning_turn`。
- **页面**：`LOCAL_AGENT_LOOP_ENABLED` 默认 0；打开后普通聊天进入 Q3，选区/练习/可视化仍走原入口。问题卡复用了现有 `clarification.options`，完整卡片组件和跨刷新 UI 需后续前端接入。
- **跨进程**：取消的即时唤醒是进程内注册表；跨进程以数据库 revision/status 和循环 `guard()` 兜底。丢失执行租约的进程不能无缝恢复内存中的工具调用。
- **真实页面/真实教材验收**：尚未完成；真实模型联调已失败在质量门禁，不能宣称 Q3 整阶段完成。

## 8. 提交边界

只提交本 worktree 的 Q3 模块、测试、脚本和 Q3 文档；不提交 `knowledge/courses` junction、`.runtime`、`__pycache__`、主工作区未提交改动。共享入口改动单独提交并列出依赖，不自动合并 `main`。

- `f154bb0`：Q3 工具协议、本地循环、ask_user 契约、导航边界、Q3 服务、LLM tool-call、脚本与 15 个核心文件。
- `1271e0b`：依赖 `f154bb0` 的 TaskService/main/QualityChecker 集成与任务/入口测试。
- 当前分支 `codex/q3-agent-loop`，基线 `2d4b4d0`；未推送、未合并主分支、未覆盖主工作区。`knowledge/courses` 仅为本机测试 junction，保持未跟踪。

