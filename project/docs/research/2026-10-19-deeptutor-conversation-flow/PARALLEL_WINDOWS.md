# 并行窗口提示词

日期：2026-10-19。基线：`codex/integration-q1-q4`（已合并 Q1/Q4/Q3，Q3/Q4 接线改动尚未提交）。

使用原则：一个窗口一个 worktree；共享文件只允许一个窗口修改；禁止 `git add -A`；教材 junction、数据库、`.runtime`、`.env` 不提交。

## 窗口 A：Q3/Q4 集成与真实导航验收

工作区：`E:\项目\heart-worktrees\integration-q1-q4`  
分支：`codex/integration-q1-q4`

```text
项目：E:\项目\heart
集成 worktree：E:\项目\heart-worktrees\integration-q1-q4
分支：codex/integration-q1-q4
上游源码：D:\deeptutor
计划目录：E:\项目\heart\project\docs\research\2026-10-19-deeptutor-conversation-flow

你接手 Q1/Q3/Q4 集成窗口。不要改主工作区 E:\项目\heart，不要合并或推送。

开始前：
1. 阅读 AGENTS.md、IMPLEMENTATION_PLAN.md、Q3_INTERFACE_CONTRACT.md、Q3_PARALLEL_LOG.md、Q4_PARALLEL_LOG.md、Q4_TOOL_LEDGER.md、TEACHING_LOOP_GAP_AUDIT.md。
2. 在集成 worktree 执行 git status、git log -5，确认当前未提交文件：
   agents/agent_loop.py、agents/agent_loop_service.py、agents/q3_tools.py、agents/quality_checker.py、
   scripts/check_q3_loop.py、tests/test_q3_q4_integration.py。
3. 不要 git add -A；knowledge/courses 是本机只读 junction，禁止提交。

当前已完成：
- 已合并 Q1、Q4、Q3。
- Q3/Q4 测试 78 项通过；Q1/Q2 相关 109 项通过；新增集成测试 11 项通过。
- 已把 Q4 ScopedToolRegistry 接入 Q3 回合；已把 Q3 质量门禁限定为教材可发布性检查。
- 已修复多次 retrieve_course 调用的引用编号重复：来源编号跨工具调用全局连续，并限制总来源数。
- 但修复后的真实导航复验被中断，尚未确认通过。

本轮任务：
1. 在 project/integration/discrete-math-tutor 下运行：
   .venv-gpu/Scripts/python.exe -B scripts/check_q3_loop.py --mode live_navigation
   目标：两轮都 answered：
   - 我想要学习教材第一章的内容
   - 继续下一个知识点
   记录两轮的 answer_status、knowledge_point、course_navigation.id、sources、耗时。
2. 如果失败，按 systematic-debugging 定位；保留失败日志，不得把失败改写成通过。重点检查：
   - 第二次是否使用 Q2 已保存的 course_navigation 继续；
   - 引用编号是否与最终 sources 顺序一致；
   - 质量门禁是否只拒绝教材事实/引用/未回答/编造问题。
3. 通过后运行：
   .venv-gpu/Scripts/python.exe -B scripts/check_q3_loop.py --mode live
   以及 Q3/Q4 测试：
   python -B -m unittest tests.test_q3_agent_loop tests.test_q3_task_loop tests.test_q3_entrypoint tests.test_q4_tool_foundation tests.test_q3_q4_integration -v
4. 运行相关回归：
   tests.test_reply_budget tests.test_conversation_context tests.test_task_execution tests.test_quality_guard tests.test_course_navigation tests.test_grounded_citations
   已知数据漂移导致的失败要单独列出，不能算本轮回归。
5. 只提交本窗口代码、测试和记录；提交信息写清“Q3/Q4 集成与真实导航验收”。不合并 main、不推送。
6. 更新 Q3_PARALLEL_LOG.md 或新增 INTEGRATION_LOG.md，写：提交 SHA、命令、结果、失败日志路径、剩余问题。

边界：
- 不修改 Q2 的 knowledge/*、orchestrator.py、frontend/*。
- 不修改 task_service.py，除非发现集成阻塞；如必须改，先记录原因并单独提交。
- 不把模拟结果、替身结果或未重放的旧结果写成真实页面通过。
- 不使用 git add -A。
```

## 窗口 B：Q2 教材检索、引用与学习导航

工作区：`E:\项目\heart`（主工作区，已有未提交 Q2 改动）  
分支：`main`

```text
项目：E:\项目\heart
工作区：主工作区 E:\项目\heart
分支：main
计划目录：E:\项目\heart\project\docs\research\2026-10-19-deeptutor-conversation-flow

你负责 Q2：教材检索、引用、学习导航、视觉资产与页面验收。不要动集成 worktree
E:\项目\heart-worktrees\integration-q1-q4，也不要修改 Q3 文件：
agents/agent_loop*.py、agents/q3_tools.py、agents/quality_checker.py、agents/reply_budget.py。

开始前：
1. 阅读 AGENTS.md、IMPLEMENTATION_PLAN.md 的 Q2 部分、Q2_CITATION_STAGE.md、
   Q2_NAVIGATION_STAGE.md、Q2_RETRIEVAL_STAGE.md、QUALITY_BASELINE.md。
2. 运行 git status --short，确认当前 20 个修改文件、4455 个删除文件和未跟踪资料；
   不要 git add -A，不要覆盖现有未提交改动。
3. 只提交 Q2 相关文件；教材删除、knowledge/courses、数据库、.runtime、.env 不提交。

本轮优先级：
1. Q2.10：普通问答/圈选学习都能绑定真实教材路径；“我懂了，下一部分”“下一步”“继续”
   等自然表达能进入导航；不要求每次圈选。
2. Q2.9：新回答统一使用新版证据协议；重复引用按教材版本+实际原文范围去重；
   正文编号、来源、点击定位同步；旧历史不伪升级。
3. Q2.4/Q2.5：视觉资产/原图映射、发布与换版绑定；没有真实资源时明确记录缺口。
4. Q2.6：概念、比较、同义、跨章、图表公式、未命名、换版检索验收。

约束：
- 保留当前未提交 Q2 改动，不覆盖。
- 共享文件 task_service.py、orchestrator.py 如要改，先记录并尽量小改；集成窗口可能稍后合并。
- 真实页面验收用独立端口和隔离数据库，不碰 8000 服务和正式学习库。
- 失败结果保留，不拼成一次全绿。

完成后报告：提交 SHA、修改文件、测试命令与结果、真实模型/页面验收、未通过项、
需要集成窗口配合的接口。
```

## 窗口 C：Q5 学习计划与掌握评估设计

工作区：`E:\项目\heart-worktrees\q5-learning-design`  
分支：`codex/q5-learning-design`

```text
项目：E:\项目\heart
设计 worktree：E:\项目\heart-worktrees\q5-learning-design
分支：codex/q5-learning-design
基线：codex/integration-q1-q4 最新已提交；如果不存在，使用 main 6e9dd58

你只做 Q5 学习计划与掌握评估设计，不写业务代码。

阅读：
- IMPLEMENTATION_PLAN.md 的 Q5.7—Q5.12
- TEACHING_LOOP_GAP_AUDIT.md
- Q3_INTERFACE_CONTRACT.md
- models/student_state.py、agents/lesson_planner.py、knowledge/course_navigation.py
- D:\deeptutor\deeptutor\learning\policy.py
- D:\deeptutor\deeptutor\capabilities\mastery\*
- D:\deeptutor\deeptutor\services\courses_state.py

交付：
1. Q5_LEARNING_DESIGN.md：学习计划生成、路径/模块/知识点、当前目标、下一目标、
   讲解/测评/复习模式、插问恢复、计划局部修改、跳题/延后/纠错、掌握门槛、课程交接。
2. Q5_INTERFACE_CONTRACT.md：与 Q2/Q3/Q4 的接口、数据结构、持久化、幂等、权限、失败语义。
3. Q5_ACCEPTANCE.md：验收矩阵，覆盖 Q5.7—Q5.12 和“学习第一章→我懂了→下一部分”场景。
4. 明确哪些是 DeepTutor 已有、哪些需要本项目适配、哪些不做；不把设计写成已实现。

边界：不修改业务代码；不合并、不推送；不虚构测试结果。
```

## 可选窗口 D：Q1 选区/视觉验收

工作区：`E:\项目\heart-worktrees\q1-visual-acceptance`  
分支：`codex/q1-visual-acceptance`

```text
项目：E:\项目\heart
worktree：E:\项目\heart-worktrees\q1-visual-acceptance
分支：codex/q1-visual-acceptance
基线：codex/integration-q1-q4 最新已提交

你负责 Q1 剩余的选区/视觉验收，不改 Q2 检索内部实现，不声明未真实接通的通过。

阅读：
- IMPLEMENTATION_PLAN.md 的 Q1.1、Q1.6
- Q1_PARALLEL_LOG.md 第 6 节
- Q2_CITATION_STAGE.md
- agents/pdf_selection_tutor.py、knowledge/pdf_reader.py、frontend/app.js

任务：
1. 核对 selection/vision 两个黄金案例的真实接口：选区命中原文、引用、页码/坐标、
   裁图进入生成和质检、前端展示与刷新恢复。
2. 准备独立端口和隔离数据库的页面验收脚本；不要碰 8000 服务和正式学习库。
3. Q2.4/Q2.5 未完成时，只记录阻塞和接口要求，不标记通过。
4. 失败结果保留；完成后报告真实通过项、阻塞项和需要的 Q2 接口。

边界：不修改 Q3 文件；不合并、不推送；不使用 git add -A。
```
