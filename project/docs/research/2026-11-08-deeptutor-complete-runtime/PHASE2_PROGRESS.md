# 第二部分实施进度与验收

> 最新复测：[PHASE2_MIXED_CHAIN_REPAIR.md](PHASE2_MIXED_CHAIN_REPAIR.md)。出题后翻第 2 页、applied 回执及刷新恢复题卡已通过真实模型验证；其余能力仍未全部验收。

> 2026-11-09 真实模型补验：[PHASE2_LIVE_VALIDATION.md](PHASE2_LIVE_VALIDATION.md)。教材引用、题卡和独立阅读通过；出题后切换阅读仍出现错误页码，尚未全部通过。

日期：2026-11-08。对应方案：[PHASE2_MIGRATION_PLAN.md](PHASE2_MIGRATION_PLAN.md)。

> 最新修复记录：[PHASE2_REPAIR_VALIDATION.md](PHASE2_REPAIR_VALIDATION.md)。源码复核提出的题目、正式引用、阅读归属缓存和阅读指令四处缺口已修复；研究/媒体/掌握学习等其余能力仍未全部验收。

## 本次范围收敛

按用户最新指令，成功运行的工具保留；未跑通且项目需要的补接；不需要的 31 项已从模型目录、schema、延迟加载、执行分发和关联扩展中隐藏，不再要求跑通。原版注册表仍保留 100 个实现；宿主目录现在展示 69 个候选工具和 8 个循环扩展。

已补接当前教学需要的 `rag` → 本轮 `source_index` → 原版 `read_source` 全文读取；不允许跨回合读取或扩大原生工具白名单。

## 已完成并接通真实入口

| 项目 | 实现 | 实际调用路径 |
| --- | --- | --- |
| 默认执行内核 | `integrations/deeptutor/native_executor.py` | `main._run_turn` → `run_native_turn` → worker `DeepTutorApp` |
| worker 生命周期 | `integrations/deeptutor/runtime_config.py` | 应用 lifespan 自动启动/停止独立 worker，`DEEPTUTOR_AUTOSTART=0` 可接管 |
| 完整回合请求 | `native_contract.py` 的 `NativeTurnOptions` | 能力、工具、配置、知识库、技能、MCP、附件、选区、阅读/掌握/媒体引用均随请求进入原生 `TurnRequest` |
| 权限保留 | `native_bridge.start` | 不再把工具/知识库固定为空，也不再在每次提交时清空已有 grants |
| 原生目录 | `native_bridge.catalog`、`POST /api/deeptutor/catalog` | 原版保留 100 个工具与 14 个扩展，宿主按需展示 69 个工具与 8 个扩展、11 个能力；资源来自原生 `resource_catalog`，只列当前用户可见项 |
| 页面能力选择 | `frontend/native-controls.js` | 能力下拉、按 `request_schema` 生成的配置项、用户可选工具、知识库/技能/MCP 复选框，随聊天请求提交 |
| 问题卡续答 | `native_executor` + `native_authorization` | 续答沿用同一原生 turn，宿主任务版本递增不影响原 turn 授权；旧选项被拒绝且不改任务 |
| 事件与重放 | 事件游标写入任务 context | 断线按 `after_seq` 重放；同一 request 不会二次生成 |
| 正式发布 | 复用 `_publish_gate` 与学习事件写入 | 原生回答仍经过引用/质量核验后才保存；取消或删除后不再发布 |
| 失败重试 | 启动前保存 `binding["start"]` | 首次启动失败后重试沿用同一原生收据，不新建回合 |
| 交付物 | `artifact_auth.py`、`/api/deeptutor/tasks/{task}/artifacts/{item}` | 服务端 HMAC 签名绑定学生/会话/任务/文件；错误签名在读取任务前即 403 |
| 可视化/媒体 | `frontend/vendor/deeptutor-renderers/` | 直接构建固定上游 `VisualizationViewer` 与 Manim 组件，产物经签名 URL 展示；构建记录见 `SOURCE_NOTICE.json` |
| 教材选区 | `native_grounding.py` | 已核验原文以原生笔记本记录进入材料系统，引用仍回到宿主证据 ID 与版本 |
| 检索预热 | `heart_rag.warm_retrieval` | worker 启动时加载索引缓存，首个 `rag` 请求不再等待模型加载；worker 无 CUDA 时自动把 `RAG_*_DEVICE` 降为 cpu |

## 已验证

- 宿主回归：254 项通过（14 个模块，含统一上下文、Q3 循环、任务暂停恢复、组合生成、任务 API 边界）。
- 原生协议与执行器：18 项通过（`test_deeptutor_native_runtime.py`、`test_native_executor.py`），需 `.venv-deeptutor`。
- 原生授权、学习卡、测评命令与提示边界：35 项通过（5 个模块），需 `.venv-deeptutor`。
- 真实 HTTP 链路（`scripts/check_native_chat_chain.py`，本机受控模型 + 真实 worker）：
  1. 目录返回 100 工具 / 14 扩展 / 11 能力；
  2. 宿主聊天 → 原生 AgentLoop → `workspace_list` → 工具结果回填 → 回答落库；
  3. 同一 request 重放不再追加模型调用；
  4. 自动挂载工具 `learning_status` 真实执行；
  5. 用户选择工具 `reason` 真实执行并完成其内部模型调用；
  6. `deep_solve` 能力被真实路由并产出正式回答；
  7. 教材 PDF 导入后，`immersive_reading` 能力的 `material_outline` 返回真实目录；
  8. `write_memory` 写入偏好，下一轮 `read_memory` 读回；
  9. `brainstorm` 经用户选择真实执行；
  10. `learning_update` 写入学习记录；
  11. `solve_plan` 在解题能力下提交规划；
  12. 课程大纲与阅读工作区导入后，`course_study` 能力的 `course_overview` 返回 11 章结构；
  13. `rag` 通过宿主教材索引返回真实章节与页码（1600+ 字符原文）；
  14. `kb_files` 列出教材 11 章；
  15. `read_skill` 读取内置技能 SKILL.md；
  16. `ask_user` 暂停 → 页面答复 → 同一原生 turn 续跑完成。
- 课程与材料导入：实验心理学 11 章 PDF 进入原生阅读目录（11 份材料、1 个工作区）；原生课程写入 11 章大纲并挂上阅读工作区；课程默认沿用 `TUTOR_COURSE=experimental-psychology-3`。
- 真实模型 + 浏览器验收（隔离宿主，`deepseek-flash`，`LLM_MOCK=0`）：
  1. `deep_question` 原生调用返回完成（60.4 秒）；本轮复核确认题目结构被宿主投影丢弃，不能计为出题页面完整成功；
  2. `deep_solve` 解题成功（43.9 秒），原生事件确认 `solve_plan`、`solve_finish_step` 的 `tool_call` 与 `tool_result`；
  3. 引导模型发现原计划不成立后，事件确认 `solve_replan` 执行；
  4. `visualize` 生成 Chart.js 载荷（11.1 秒），事件确认 `submit_visualization`；
  5. Playwright 打开聊天页：`.native-viewer` 内渲染出 Chart.js `canvas`，无脚本错误；整页截图保存到 `.runtime/live-browser/visualize.png`。
- 注册表完整性（`scripts/check_native_tools.py`）：100 个工具可实例化且定义名一致；11 个能力可实例化且名称/阶段与注册表一致；14 个扩展可实例化，名称、专属工具集合与 `is_active` 等钩子齐全。
- 文件签名：错误签名在读任务前 403；签名绑定四个身份字段。
- `git diff --check` 通过；改动文件 Python/JS 语法检查通过。

## 尚未完成（不得计为已通过）

1. 11 个能力中 `chat`、`ask_questions`、`deep_solve`、`immersive_reading`、`course_study`、`deep_question`、`visualize` 已真实跑通；`deep_research`、`math_animator`、`audio_overview`、`mastery_path` 尚未逐项执行验收。
2. 100 个内置工具均可实例化；真实执行已验证 19 个（见 `TOOL_STATUS.md`），其余尚无逐项执行证据。
3. 知识库：`rag`、`kb_files` 已用宿主实现覆盖内置并通过真实链路；`read_source` 已补接本轮 `source_index`，`knowledge_frontier` 仍需 arXiv。
4. 14 个循环扩展未做 `is_active`/钩子执行验收。
5. 工作区 4 项与笔记本 2 项按当前安排暂缓：工作区缺能力产物，笔记本需先创建。
6. MCP、CLI、plugin 动态提供者未验收；缺少外部服务时目录会如实显示不可用。
7. 旧执行器遗留的待答任务会返回“请取消后重新提问”，未做历史回合导入。
8. 长历史触发原生摘要时的一次模型调用，未用真实模型验收（离线替身已覆盖成功/失败路径）。

## 工具范围收敛专项验证

最新完整 HTTP 验收：`.runtime/native-chat-chain/20261108-215701/report.json`，19 项检查全部通过；确认所有测试回合的模型 schema 均不含被隐藏工具。模型为本机受控服务，worker、原生循环与工具为真实实现。

- `tests.test_native_tool_policy`：5 项通过。覆盖模型 schema/目录隐藏、手工调用阻断、预加载延迟工具过滤、异步子任务作用域、无关扩展不激活、工具白名单不扩大，以及本轮原文索引读取和跨回合隔离。
- `tests.test_native_executor`：7 项通过，保留原生执行、重放、续答、删除与签名边界回归；目录断言调整为 69 个候选工具、31 个隐藏工具、8 个启用扩展。
- 真实 HTTP 已验证 `rag` → `source_index` → 原版 `read_source` 的完整补读；模型工具 schema 在回合开始时固定，因此检索与补读一起挂载，不能等检索结束后才追加。

## 复现

```powershell
# 注册表完整性（需带 deeptutor 依赖的环境）
.venv-deeptutor/Scripts/python.exe -X utf8 -B scripts/check_native_tools.py
# 真实 HTTP 链路（会启动隔离宿主、原生 worker 和本机受控模型）
.venv-gpu/Scripts/python.exe -X utf8 -B scripts/check_native_chat_chain.py
```

## 环境与风险

- `test_native_executor.py`、`test_deeptutor_native_runtime.py` 需在 `.venv-deeptutor` 运行；其余宿主测试在 `.venv-gpu`。
- `tests/__init__.py` 默认关闭原生执行与外部检索，需要它们的测试显式打开。`test_task_api` 在类级别固定这些开关，避免同进程顺序污染。
- 默认 `DEEPTUTOR_NATIVE_ENABLED=1`：宿主启动会拉起 worker，60 秒内未就绪则启动失败；需要回退时设 0。
- 宿主改用非 8000 端口时，必须同步设置 `DEEPTUTOR_HOST_URL`；worker 用它回调宿主做任务核验，未同步会返回 503。
- worker 内教材检索使用词法索引；向量模型（fastembed）保留在宿主 GPU 环境，避免 CPU 向量推理把单个回合拖到 20 秒以上。worker 启动时预热索引缓存。
- 原生回答必须先通过宿主发布核验；未通过的回合保存为 `quality_rejected`，不会作为正式回答显示。

本轮增补验证：37 个不同用例通过，真实 HTTP 22 项检查通过，浏览器题卡与实际 PDF 跳转/回执通过。详细范围及隔离条件以 PHASE2_REPAIR_VALIDATION.md 为准。
