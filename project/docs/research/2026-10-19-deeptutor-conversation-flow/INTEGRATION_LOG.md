# Q3/Q4 集成与真实导航验收记录

日期：2026-10-19。Worktree：`E:\项目\heart-worktrees\integration-q1-q4`。分支：`codex/integration-q1-q4`。

## 1. 集成基线

- 主分支基线：`6e9dd58`（Q2 目录导航）。
- 已合并：Q1 `b0ac2c2`、Q4 `93186e0`、Q3 `be8b952`。
- 合并提交：`731f9d0`、`89047ba`、`20ae6a7`。
- 合并时唯一需要手工处理的是 `agents/reply_budget.py`：同时保留 Q2 目录导航预算和 Q1 公式/符号预算。
- `agents/task_service.py` 由 Git 自动合并；已核对 Q2 的 `course_navigation`、Q3 的 `previous`/`loop_paused` 同时存在。

## 2. 本轮代码改动

| 文件 | 改动 | 目的 |
| --- | --- | --- |
| `agents/q3_tools.py` | 使用 Q4 `ScopedToolRegistry` 建立每回合授权工具视图；加入 `retrieve_course`/`ask_user` 覆盖工具；检索来源编号跨调用全局连续；同批次检索串行编号、重复来源去重；单回合来源预算 24 | Q4 真正进入 Q3 任务链；避免多次检索后 `[n]` 指向不同片段或重复片段 |
| `agents/agent_loop.py` | `LoopRequest.tool_state`；向 `ToolContext.state` 注入工作区/技能根；每轮同步 `source_offset`；引用/格式失败允许一次有界修订 | Q4 工具执行需要可信的任务资源；引用错误可修复一次 |
| `agents/agent_loop_service.py` | 优先使用 Q2 `course_navigation` 作为权威目标；主机已解析的下一目标不再被 Q3 重新澄清；优先读取精确目标块；结果写入 `knowledge_point`/`memory_commit`/`course_navigation`；`pdf_references` 只发布正文实际引用的 sources | 修复“继续下一个知识点”被 Q3 重新拦截、答偏到同节其他内容，以及未引用来源被展示为引用卡 |
| `agents/quality_checker.py` | 新增 `agent_loop` 模式：只把教材事实、引用支持、明确问题未回答、编造内容列为 issues；措辞/扩展/未要求出题只放 suggestions | 避免普通 AgentLoop 问答被结构化教学审计误拒；引用核验仍然保留 |
| `scripts/check_q3_loop.py` | 新增 `--mode live_navigation`：通过 `TaskService` 跑“第一章→继续下一个知识点”两轮 | 真实页面同路径的可复现验收 |
| `tests/test_q3_q4_integration.py` | 新增 11 项集成测试：Q4 注册表、技能/工作区授权、Q3 工具循环、全局来源编号、预算、主机导航、质量门禁 | 覆盖本轮新增接口与失败模式 |

## 3. 验证结果

### 3.1 真实模型

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 单轮教材问答 | `.venv-gpu/Scripts/python.exe -B scripts/check_q3_loop.py --mode live` | `20261019T152836Z-10943f`：`answer_status=answered`，8 个来源，2 轮，1 次工具调用；畸形引用格式门禁已生效；`exit=0` |
| 第一章→下一知识点 | `.venv-gpu/Scripts/python.exe -B scripts/check_q3_loop.py --mode live_navigation` | `20261019T152811Z-a12b09`：两轮均 `answered`；第一轮 `ch1:s1:b6`、2 个来源、6.875 秒、引用[1]；第二轮 `ch1:s1:b20`、3 个来源、9.000 秒、引用[1]；`navigation_advanced=true`，引用编号与 sources 顺序一致；`exit=0` |

运行日志：`.runtime/q3-live-navigation-4.log`、`.runtime/q3-live-integration-2.log`。运行目录：`.runtime/q3-live/20261019T152811Z-a12b09`、`.runtime/q3-live/20261019T152836Z-10943f`。

失败与修复记录（保留，不改写成通过）：

- `20261019T152155Z-dbcb44`：导航两轮 answered，但第一轮同批次两次 `retrieve_course` 都从 offset 0 编号，12 个来源只有编号 1–6，引用 `[n]` 含义重复。修复：检索工具用 `_RETRIEVE_LOCK` 串行分配全局编号，并在成功后推进 `source_offset`；新增同批次并行检索测试。
- `20261019T152617Z-e2e937`：导航两轮 answered，但第二轮虽读取 `ch1:s1:b20`，回答内容落到同节的“科学方法”，未围绕解析出的目标块。修复：主机已解析目标时优先 `read_target` 精确目标块，再回退到节内检索。
- `20261019T152406Z-23fa95`：单轮 live 曾返回 `[1 第二组检索结果第1条…]` 畸形引用但门禁通过。修复：新增 `_citation_format_issues`，只接受 `[n]`/`[n,m]`/`[n-m]`，畸形数字引用触发一次有界修订或拒绝。

### 3.2 离线回归

```powershell
$env:PYTHONPATH=(Get-Location).Path
& 'E:\项目\heart\project\integration\discrete-math-tutor\.venv-gpu\Scripts\python.exe' -B -m unittest `
  tests.test_q3_agent_loop tests.test_q3_task_loop tests.test_q3_entrypoint `
  tests.test_q4_tool_foundation tests.test_q3_q4_integration -v
```

结果：**89 项通过，0 失败**。日志：`.runtime/q3-q4-tests-current.log`。

```powershell
& 'E:\项目\heart\project\integration\discrete-math-tutor\.venv-gpu\Scripts\python.exe' -B -m unittest `
  tests.test_reply_budget tests.test_conversation_context tests.test_task_execution `
  tests.test_quality_guard tests.test_course_navigation tests.test_grounded_citations -v
```

结果：**109 项通过，0 失败**。日志：`.runtime/q3-q4-regression-current.log`。

此前 207 项集成回归的结论来自本窗口之前的快照；本轮按窗口要求复跑了上述两组，未把旧结果当作本轮通过。worktree 缺少 `.venv-gpu`/`.env`，命令使用主项目虚拟环境；脚本只读加载主项目 `.env`，数据库为隔离 `.runtime/q3-live`。

### 3.3 提交

- `39abe13`：Q3/Q4 集成前序提交（Q4 工具授权、全局引用编号、导航接线、集成日志）。
- `9a6f8da`：本窗口最终修复（同批次全局编号、Q2 目标块优先、畸形引用门禁、集成测试与脚本指标）。
- `928f410`：引用收敛后续提交（只发布正文实际引用的 sources、重复检索去重、探索轮数 4）；Q3/Q4 89 项、相关回归 109 项通过。



## 4. 明确边界与遗留

- `LOCAL_AGENT_LOOP_ENABLED` 默认仍为 `0`；现有页面默认仍走原入口，开启后才走 Q3。
- 第二轮真实导航已改为优先读取 Q2 的精确目标块；最终复验回答围绕 `主要讲心理学实验方法的教材`，不再落到同节的“科学方法”。本轮未修改 Q2 `knowledge/*`、`orchestrator.py` 或 `frontend/*`。
- Q3 只在 `answered` 且 `memory_commit=committed` 时写入 `course_navigation(explained=true)`；不把讲解当掌握。
- Q4 只挂载 `retrieve_course`、`ask_user`，以及显式授权时的只读工作区/技能工具；其余工具仍按 Q4 台账推进。
- 未做浏览器页面级验收；真实模型验收走的是 `TaskService → TutorOrchestrator → run_agent_loop_turn` 的宿主链路，不是独立 DeepTutor 应用。不能把本轮结果写成页面通过。
- 未合并 `main`、未推送、未修改主工作区 `E:\项目\heart`。
