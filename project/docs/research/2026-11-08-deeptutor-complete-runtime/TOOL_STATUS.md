# 100 个内置工具的推进状态

日期：2026-11-08。依据：`scripts/check_native_tools.py`（100/100 可实例化）、`scripts/check_native_chat_chain.py`（真实 HTTP 链路）与 vendor 源码依赖核对。

所有 100 个工具在固定上游中都有真实实现，没有 `NotImplementedError` 占位。分类按“运行条件”和“宿主是否已备好数据”划分。

## 用户最新范围调整

用户已明确：成功运行的工具保留；未跑通但当前项目需要的工具补接；当前不需要的工具停止验收，并从模型可选择范围隐藏。

本次已在 `integrations/deeptutor/tool_policy.py` 统一隐藏 31 项无关集成，模型候选目录从 100 项收敛至 69 项；关联的 6 个循环扩展不再激活。隐藏同时覆盖目录、schema、延迟工具发现、执行分发与扩展钩子；原版源码和用户 grants 保留，其他非宿主调用上下文不受影响。69 项是项目候选范围，不代表全部通过运行验收。

教材补读属于当前必需功能，已补接 `rag` → 本轮 `source_index` → 原版 `read_source`，并保留回合隔离与原生工具白名单。

## 总览

| 类别 | 数量 | 含义 |
| --- | --- | --- |
| 已真实跑通 | 19 | 已经过宿主 HTTP → 原生 AgentLoop → 工具执行 → 结果发布 |
| 已实现，建议补测 | 6 | 本地文件/服务即可执行，不需要新实现 |
| 需要宿主补接或验收 | 30 | 原生实现完整，但宿主还没有对应数据（题库、掌握学习、其余材料） |
| 需要外部服务 | 14 | 需要网络、API key、外部 CLI 或沙箱授权 |
| 已隐藏、不再要求跑通 | 31 | 外部产品集成、设置与调度；已从模型工具和关联扩展中隐藏 |

## 已真实跑通（19）

| 工具 | 验证方式 |
| --- | --- |
| `workspace_list` | 模型发起调用 → 原生执行 → 结果回填 → 回答落库 |
| `learning_status` | 自动挂载上下文工具，真实执行 |
| `reason` | 用户选择工具后真实挂载，并完成其内部模型调用 |
| `material_outline` | 沉浸阅读能力下读取已导入教材的真实目录 |
| `write_memory` | 写入学习者偏好 |
| `read_memory` | 写入后条件挂载并读回 |
| `brainstorm` | 用户选择工具后真实执行 |
| `learning_update` | 写入学习记录 |
| `solve_plan` | 解题能力下提交规划并返回下一步 |
| `course_overview` | 读取已导入的实验心理学课程大纲与资源 |
| `rag` | 通过宿主教材索引检索，返回真实章节与页码 |
| `kb_files` | 列出教材 11 章结构 |
| `read_skill` | 读取内置技能 SKILL.md |
| `read_source` | 同一原生回合内，模型在 rag 后用真实 source_id 补读完整教材原文 |
| `reader_goto` | 原版工具指令进入宿主正式结果，浏览器实际到达第 2 页并保存 applied 回执 |
| `solve_finish_step` | 真实模型在解题回合内标记步骤完成（事件 `tool_call`/`tool_result`） |
| `solve_replan` | 真实模型确认原计划不成立后重新规划（事件 `tool_call`/`tool_result`） |
| `submit_visualization` | 可视化能力生成 Chart.js 载荷；浏览器中渲染为 canvas |
| `ask_user` | 提问能力下暂停等待，答复后同一回合继续 |

能力验证：`chat`、`ask_questions`、`deep_solve`、`immersive_reading`、`course_study`、`deep_question`、`visualize` 已从真实入口跑通（后两项使用真实模型）。

## 已实现，建议补测（6）

不需要新增实现，具备本地数据或自带服务即可。

- 工作区：`workspace_read`、`workspace_search`、`workspace_present`、`workspace_export`
- 笔记本：`list_notebook`、`write_note`（需要先有笔记本）

## 需要宿主补接或验收（30）

原生实现完整，但宿主侧没有对应数据。

| 组 | 工具 | 缺什么 |
| --- | --- | --- |
| 掌握学习 | `mastery_*` 共 19 个 | 原生 mastery store 与宿主 Q5/adaptive 状态是两套；需要定单一数据源并迁移/映射 |
| 课程 | `course_material`、`course_edit`、`course_handoff` | 课程与大纲已导入；这三项还需按资源/编辑动作逐项验收 |
| 阅读与材料 | `reading_list_tabs`、`reading_switch_tab`、`search_material`、`read_material`、`view_figure`、`reader_annotate` | 教材材料已导入；这些按定位/批注动作继续验收 |
| 知识库 | `knowledge_frontier` | `rag`/`kb_files`/`read_source` 已通过真实链路；前沿检索仍需 arXiv |
| 题库 | `question_bank` | 需要导入题库；当前心理学课程题库为空 |

## 需要外部服务（14）

实现已完整，配置或授权后可测。

- 检索与网络：`web_search`、`paper_search`、`zotero_search`、`preprint`、`research_lit`、`research_audit`、`web_fetch`、`github`
- 生成与分析：`imagegen`、`videogen`、`geogebra_analysis`
- 子代理：`consult_subagent`
- 执行与动态工具：`exec`、`load_tools`（MCP/CLI provider）

## 已隐藏（31）

- Obsidian（9）、MarginNote（7）、IMA（5）
- 伙伴协作（5）：`propose_partner`、`invoke_other`、`partner_read`、`partner_memorize`、`partner_search`
- 设置（4）：`inspect_setup`、`apply_setting`、`request_credential`、`run_setup_job`
- 调度（1）：`cron`

## 已导入的课程与材料

- 教材：实验心理学 11 章 PDF 已导入原生阅读目录，得到 11 份材料、1 个阅读工作区；沉浸阅读能力可直接读目录。
- 课程：原生课程已写入宿主 11 章大纲，并挂上阅读工作区。
- 课程选择沿用宿主默认：`TUTOR_COURSE=experimental-psychology-3`。

## 建议顺序

1. 工作区与笔记本 6 项按当前安排暂缓：工作区需要能力产物，笔记本需要先创建课程笔记本。
2. 掌握学习组（19 项）需要先定数据源（原生 mastery store 与宿主 Q5/adaptive 状态二选一或做映射）。
3. 阅读材料组按定位/批注动作继续验收；题库需要导入数据。
4. 知识库已完成 `rag`/`kb_files` 适配；`read_source` 需要把本轮来源写入 source_index，`knowledge_frontier` 还需要 arXiv。
5. 外部服务按项目需要配置；不需要的 31 项已隐藏，不再挂载或要求执行验收。
