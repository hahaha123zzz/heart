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
| `agents/q3_tools.py` | 使用 Q4 `ScopedToolRegistry` 建立每回合授权工具视图；加入 `retrieve_course`/`ask_user` 覆盖工具；检索来源编号跨调用全局连续；单回合来源预算 24 | Q4 真正进入 Q3 任务链；避免多次检索后 `[n]` 指向不同片段 |
| `agents/agent_loop.py` | `LoopRequest.tool_state`；向 `ToolContext.state` 注入工作区/技能根；每轮同步 `source_offset`；引用/格式失败允许一次有界修订 | Q4 工具执行需要可信的任务资源；引用错误可修复一次 |
| `agents/agent_loop_service.py` | 优先使用 Q2 `course_navigation` 作为权威目标；主机已解析的下一目标不再被 Q3 重新澄清；目标范围内检索并按章节/小节过滤；结果写入 `knowledge_point`/`memory_commit`/`course_navigation` | 修复“继续下一个知识点”被 Q3 重新拦截，以及导航位置不持久化 |
| `agents/quality_checker.py` | 新增 `agent_loop` 模式：只把教材事实、引用支持、明确问题未回答、编造内容列为 issues；措辞/扩展/未要求出题只放 suggestions | 避免普通 AgentLoop 问答被结构化教学审计误拒；引用核验仍然保留 |
| `scripts/check_q3_loop.py` | 新增 `--mode live_navigation`：通过 `TaskService` 跑“第一章→继续下一个知识点”两轮 | 真实页面同路径的可复现验收 |
| `tests/test_q3_q4_integration.py` | 新增 11 项集成测试：Q4 注册表、技能/工作区授权、Q3 工具循环、全局来源编号、预算、主机导航、质量门禁 | 覆盖本轮新增接口与失败模式 |

## 3. 验证结果

### 3.1 真实模型

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 单轮教材问答 | `.venv-gpu/Scripts/python.exe -B scripts/check_q3_loop.py --mode live` | `answer_status=answered`，16 个来源，2 轮，1 次工具调用；`exit=0` |
| 第一章→下一知识点 | `.venv-gpu/Scripts/python.exe -B scripts/check_q3_loop.py --mode live_navigation` | 两轮均 `answered`；第一轮 `ch1:s1:b6`，第二轮 `ch1:s1:b20`；第二轮使用已保存的 `course_navigation`；`exit=0` |

运行目录：`.runtime/q3-live/20261019T152240Z-a3fa37`（导航两轮）；`.runtime/q3-live/` 下另有单轮运行。日志：`.runtime/q3-nav-live3.log`、`.runtime/q3-live-final.log`。

### 3.2 离线回归

命令：

```powershell
$env:PYTHONPATH=(Get-Location).Path
.venv-gpu/Scripts/python.exe -B -m unittest `
  tests.test_q3_agent_loop tests.test_q3_task_loop tests.test_q3_entrypoint `
  tests.test_q4_tool_foundation tests.test_q3_q4_integration `
  tests.test_reply_budget tests.test_conversation_context tests.test_task_execution `
  tests.test_conversation_quality_harness tests.test_course_navigation `
  tests.test_grounded_citations tests.test_quality_guard tests.test_psychology_presets -v
```

结果：**207 项通过，0 失败**。日志：`.runtime/integration-regressions-final.log`。

首次运行 `test_psychology_presets` 的 2 项失败是因为 worktree 缺少被 `.gitignore` 排除的 `artifacts/` 目录；创建该运行目录后 8 项全部通过。该失败属于环境准备问题，不是代码回归。

未纳入上述集合的既有数据漂移：`tests.test_task_resource_execution` 在当前 worktree 缺少离散数学习题目录时会出现 8 项错误；与 Q1 记录一致，未改写测试。`tests.test_citation_publication.py` 仍是主工作区未跟踪的 Q2 文件，不在集成分支。

## 4. 明确边界与遗留

- `LOCAL_AGENT_LOOP_ENABLED` 默认仍为 `0`；现有页面默认仍走原入口，开启后才走 Q3。
- 第二轮真实导航的目标标题显示为“主要讲心理学实验方法的教…”，回答内容进入“科学方法及其特点”。这是 Q2 教材叶子标题/正文范围的数据质量问题，不是 Q3 未接续；需要 Q2 窗口修正标题抽取或学习点映射。
- Q3 只在 `answered` 且 `memory_commit=committed` 时写入 `course_navigation(explained=true)`；不把讲解当掌握。
- Q4 只挂载 `retrieve_course`、`ask_user`，以及显式授权时的只读工作区/技能工具；其余 96 个工具仍按 Q4 台账推进。
- 未做浏览器页面级验收；真实模型验收走的是 `TaskService → TutorOrchestrator → run_agent_loop_turn` 的宿主链路，不是独立 DeepTutor 应用。
- 未合并 `main`、未推送、未修改主工作区 `E:\项目\heart`。
