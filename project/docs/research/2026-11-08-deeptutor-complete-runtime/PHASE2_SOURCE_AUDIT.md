# 第二部分：图谱、架构与双方源码复核

日期：2026-11-08。结论：**尚未完全迁入；即使按用户批准的按需范围收敛后，也仍有实际接线缺口，不能只归为未补测试。**

本轮检查、复现并记录问题，没有修改业务代码。用户已批准隐藏的 31 个工具及其关联 6 个扩展不再作为完成阻塞。

> 本文件保留修复前的发现与复现。四处缺口已在后续修复，见 [PHASE2_REPAIR_VALIDATION.md](PHASE2_REPAIR_VALIDATION.md)；其余能力未全部验收的结论仍有效。

## 1. 依据与边界

检查了 D:/deeptutor/.ua/knowledge-graph.json、D:/deeptutor/ARCHITECTURE.html、D:/deeptutor 当前源码，以及项目 vendor、宿主适配和前端源码。

- D 盘图谱：635 个节点、1080 条边、193 个不同 filePath，基于 commit 6cf793bd868ba5ecbe64722936d4be8fab5a01df。图谱明确只分析 runtime/capabilities/core 加根配置文档，没有覆盖全部 app、agents 和 services/session，不能单独作为完整依赖闭包。
- D 盘已提交源码与图谱 commit 无差异，但存在 llm/factory.py 等本地修改；本项目图谱也早于本轮迁移，有 60 条非图谱工作区变更。因此图谱用于定位，结论按当前源码核实。
- 架构图仍写 7 个可选工具；当前源码实际为 8 个，说明图中数量不能直接当验收标准。
- 图中的 providers.json/setup.json 是 D 盘本地配置，不是缺失的 Python 实现；没有复制凭据或用户配置。

## 2. 源码包与主干

| 核对项 | 结果 | 能证明什么 |
| --- | --- | --- |
| 固定源码包 | 3764 个登记文件均存在 | 原版包没有被拆成少数单文件迁入 |
| 固定包哈希 | 按 local_changes 中 4 个已声明补丁校验，额外漂移 0 | 不能把已记录的学习证据补丁误报为来源损坏 |
| 静态候选依赖 | 975 个文件缺失 0 | 静态依赖文件齐全；不是动态服务已经可用的证明 |
| 与 D 盘比较 | policy.py、multi_user/paths.py、utils/secret_files.py 三处差异，均是已声明补丁 | 保留宿主已有适配，没有盲目覆盖 |
| 原版展示组件 | 构建清单 16 个上游源文件哈希一致 | VisualizationViewer、Manim 等依赖来自固定副本；未证明全部产物都已可用 |
| 原生主干 | main._run_turn → run_native_turn → HTTP worker → NativeTurnBridge.start → DeepTutorApp.start_turn → 原版会话执行器/能力/AgentLoop/工具 | 新代码在默认主入口中实际调用，不只是留在 vendor |

默认开关见 integrations/deeptutor/runtime_config.py，原生入口见 main.py:193 与 native_bridge.py:302。显式关闭原生开关仍可进入兼容链路，不把兼容分支视为默认生成器。

## 3. 实际复现的接线缺口

### A. 出题结构在宿主结果投影中丢失

上游 agents/question/pipeline.py 的 _build_result_payload 将题目存入 summary.results，题数、成功状态等也在 summary 中；response 在 custom 模式下可能只保存出题前言，原版前端另用 QuizViewer 显示题目。

宿主 integrations/deeptutor/native_executor.py:41 的 _public_result 对普通出题只保留 response，丢弃 summary/mode；frontend/native/entry.tsx 目前接画布与文件，没有 QuizViewer 接线。

最小复现：输入 response + summary(success=True, completed=1, results 含题目) + mode，输出只有 response。

影响：原生能力生成过题目，也可能在宿主页面只剩“现在开始出题”。此前“deep_question 出题成功”的完成表述需要撤回，不能只根据 answered 判定。同时需要将语义完成状态纳入能力验收，而不只检查 native turn 是否 completed。

修复边界：通过现有题卡/私有答案权限边界映射题目与状态，再接原版题卡呈现；不能简单公开包含答案的全部内部结构。

### B. RAG 来源没有进入正式引用发布

heart_rag.py 已将原文写入本轮 source_index；原版 read_source 可补读。NativeTurnBridge.status 也会返回 native sources。

但 native_executor.py:247 构造 LoopResult 时只使用 binding.sources；native_grounding.prepare_selection 在非选区请求下返回空数组。state.sources 只进入交付物投影，没有被还原为宿主正式引用来源。

最小复现：原生回合 completed、sources 含 1 条 RAG 来源、正文使用 [1]、宿主 binding.sources 为空，最终得到 quality_rejected，提示没有教材引用来源。

影响：证明 rag 工具读到原文，不等于“有引用的正式回答可保存并在 PDF 中定位”。19 项 HTTP 验收的受控模型最终返回不带引用的普通文本，没有覆盖这个失败条件。

修复边界：保留稳定教材块 ID/文档版本，将原生来源映射回现有原文证据与发布门禁；不能靠放宽引用核验解决。

### C. 原生阅读材料缓存缺少用户、工作区与版本作用域

course_reading.py:11 定义进程级 _CACHE；第 38 行仅以 course_id 命中，第 70 行也只按 course_id 保存。命中前没有核对当前 owner/workspace/source version。材料查找还按 filename 复用。

最小复现：同一进程中 A 的原生目录返回 reading-A，随后切换为 B、其目录本应返回 reading-B，ensure_course_reading 仍返回 reading-A，而且是同一个缓存对象。

影响：第二名学生可能拿到第一名学生的原生材料/工作区 ID，导致归属核验失败；同名教材换版也可能复用旧导入。本次没有声称已发生跨用户内容泄露，尚未验证下游权限是否拦截。

修复边界：缓存和复用校验必须绑定真实用户、工作区、课程与教材版本；不能靠关闭权限校验让错误 ID 通过。

### D. 原生阅读定位指令没有接到宿主页面

原版 capabilities/reading/tools.py 的 reader_goto 通过 ToolResult.metadata 返回 reader_action=goto、material_id、locator 等，原版 UI 据此移动阅读器。

宿主 native_executor._consume 只处理进度、ask_user 与 done，没有投影这些阅读指令；传入的 answer_event 回调也没有调用。

最小复现：输入真实契约形状的 reader_goto tool_result，再输入 done；结果 answered，但 answer_event 回调次数为 0，结果也无 reader_actions。

影响：原生工具可以返回“Reader moved”，宿主阅读器实际上没有获得跳转指令。material_outline 成功不能代表阅读整条交互链已经接完。

## 4. 按当前范围判断完成度

| 层 | 状态 |
| --- | --- |
| 原版源码、依赖文件、注册表 | 完整保留，固定包校验通过 |
| 原生上下文/运行内核主入口 | 已接入并调用；不是仅复制源码 |
| 工具 | 100 个实现保留，31 个按用户要求隐藏，69 个候选中 18 个有执行证据；51 个尚未逐项证明可用，不自动判为都需要实现 |
| 循环扩展 | 6 个隐藏、8 个保留；有 solve 等实际调用证据，但未逐项完成所有激活/钩子验收 |
| 回合能力 | 11 个登记；chat/ask_questions/deep_solve/阅读目录/课程概览/可视化有执行或结果证据；出题呈现存在 A 项缺口 |
| 学习、研究、媒体 | mastery_path/deep_research/math_animator/audio_overview 尚未逐项完成真实入口与产物验收；旧学习状态迁移模块仍是隔离候选，不能视为在线切换完成 |
| 宿主正式来源和阅读交互 | 存在 B、C、D 项实际缺口 |
| 不需要的集成 | 隐藏已落实，不要求再跑通其业务服务 |

## 5. 验证证据与限制

本次重新执行 tests.test_native_tool_policy 与 tests.test_native_executor，**12 项通过**。另外执行了 A/B/C/D 的内存最小复现；替身只替换外部边界/目录与保存对象，直接调用当前源码，没有写正式学习数据或调用外部模型。

既有完整 HTTP 报告 .runtime/native-chat-chain/20261108-215701/report.json 的 19 项检查通过，本次重新读取核对；本轮没有重跑外部真实模型、完整浏览器或全部能力流水线。

已有通过用例与本次发现并不矛盾：前者覆盖了单用户、无引用最终文本、目录读取等路径；没有覆盖结构化题目透传、带教材引用的正式发布、跨用户阅读缓存和页面跳转。

建议修复顺序：C 阅读归属 → B 正式引用 → A 题目/完成状态 → D 阅读指令，再按实际教学需求验收保留的能力和工具。
