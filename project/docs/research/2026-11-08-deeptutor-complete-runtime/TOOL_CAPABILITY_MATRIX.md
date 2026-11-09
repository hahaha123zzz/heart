# 全量 Tools / Capabilities 迁入矩阵

基线：D:/deeptutor 的固定源码提交 6cf793bd868ba5ecbe64722936d4be8fab5a01df。从 AST 读取注册表，不导入或执行工具。

**范围：100 个内置工具、11 个回合能力、14 个循环扩展，以及动态 MCP/CLI/plugin providers。**
“源码在 vendor”“名字相同”“元数据已登记”均不算真实链路已调用。宿主同名定义仅是静态存在性证据，尚需比较参数、返回协议、状态写入和实际执行。

## 100 个内置工具

| 工具 | 类别 | 迁入包 | 宿主同名定义 | 原生实现文件 |
| --- | --- | --- | --- | --- |
| brainstorm | 用户可选 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/builtin/__init__.py |
| rag | 上下文挂载 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/builtin/__init__.py |
| kb_files | 上下文挂载 | B1 通用工具与工作区 | agents/tools/first_wave_contracts.py:43 | deeptutor/tools/builtin/__init__.py |
| knowledge_frontier | 上下文挂载 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/builtin/__init__.py |
| web_search | 用户可选 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/builtin/__init__.py |
| reason | 用户可选 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/builtin/__init__.py |
| paper_search | 用户可选 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/builtin/__init__.py |
| zotero_search | 用户可选 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/builtin/__init__.py |
| read_source | 上下文挂载 | B1 通用工具与工作区 | agents/tools/first_wave_contracts.py:37 | deeptutor/tools/builtin/__init__.py |
| read_memory | 上下文挂载 | B1 通用工具与工作区 | agents/tools/first_wave_contracts.py:40 | deeptutor/tools/builtin/__init__.py |
| write_memory | 上下文挂载 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/builtin/__init__.py |
| read_skill | 上下文挂载 | B1 通用工具与工作区 | agents/tools/local_specs.py:17；agents/tools/skill_tools.py:85 | deeptutor/tools/builtin/__init__.py |
| load_tools | 上下文挂载 | B1 通用工具与工作区 | agents/tools/local_specs.py:18；agents/tools/skill_tools.py:129 | deeptutor/tools/builtin/__init__.py |
| web_fetch | 上下文挂载 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/builtin/__init__.py |
| list_notebook | 上下文挂载 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/builtin/__init__.py |
| write_note | 上下文挂载 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/builtin/__init__.py |
| question_bank | 上下文挂载 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/builtin/__init__.py |
| github | 上下文挂载 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/builtin/__init__.py |
| ask_user | 上下文挂载 | B1 通用工具与工作区 | agents/q3_tools.py:222 | deeptutor/tools/builtin/__init__.py |
| cron | 上下文挂载 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/builtin/__init__.py |
| geogebra_analysis | 用户可选 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/builtin/__init__.py |
| learning_status | 上下文挂载 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/learning_journal_tools.py |
| learning_update | 上下文挂载 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/learning_journal_tools.py |
| preprint | 上下文挂载 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/research_tools.py |
| research_audit | 上下文挂载 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/research_tools.py |
| research_lit | 上下文挂载 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/research_tools.py |
| exec | 上下文挂载 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/exec_tool.py |
| workspace_list | 工作区 | B1 通用工具与工作区 | agents/tools/local_specs.py:14；agents/tools/workspace_tools.py:83 | deeptutor/tools/workspace.py |
| workspace_read | 工作区 | B1 通用工具与工作区 | agents/tools/local_specs.py:15；agents/tools/workspace_tools.py:129 | deeptutor/tools/workspace.py |
| workspace_search | 工作区 | B1 通用工具与工作区 | agents/tools/local_specs.py:16；agents/tools/workspace_tools.py:183 | deeptutor/tools/workspace.py |
| workspace_present | 工作区 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/workspace.py |
| workspace_export | 工作区 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/workspace.py |
| submit_visualization | 能力专属/伙伴 | B4 可视化与媒体 | 未发现本地定义；vendor 有原版 | deeptutor/visualizers/tool.py |
| imagegen | 用户可选 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/media_gen_tool.py |
| videogen | 用户可选 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/media_gen_tool.py |
| mastery_topics | 上下文挂载 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/mastery_nav.py |
| mastery_sessions | 上下文挂载 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/mastery_nav.py |
| mastery_open_session | 上下文挂载 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/mastery_nav.py |
| mastery_new_session | 上下文挂载 | B1 通用工具与工作区 | 未发现本地定义；vendor 有原版 | deeptutor/tools/mastery_nav.py |
| mastery_status | 能力专属/伙伴 | B2 学习、阅读、课程 | agents/q5_tools.py:50 | deeptutor/capabilities/mastery/tools.py |
| mastery_quiz | 能力专属/伙伴 | B2 学习、阅读、课程 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/mastery/tools.py |
| mastery_note_explained | 能力专属/伙伴 | B2 学习、阅读、课程 | agents/q5_tools.py:108 | deeptutor/capabilities/mastery/tools.py |
| mastery_grade | 能力专属/伙伴 | B2 学习、阅读、课程 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/mastery/tools.py |
| mastery_skip_question | 能力专属/伙伴 | B2 学习、阅读、课程 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/mastery/tools.py |
| mastery_repair_question | 能力专属/伙伴 | B2 学习、阅读、课程 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/mastery/tools.py |
| mastery_defer_objective | 能力专属/伙伴 | B2 学习、阅读、课程 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/mastery/tools.py |
| mastery_assess | 能力专属/伙伴 | B2 学习、阅读、课程 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/mastery/tools.py |
| mastery_build | 能力专属/伙伴 | B2 学习、阅读、课程 | agents/q5_tools.py:70 | deeptutor/capabilities/mastery/tools.py |
| mastery_mode | 能力专属/伙伴 | B2 学习、阅读、课程 | agents/q5_tools.py:160 | deeptutor/capabilities/mastery/tools.py |
| mastery_profile | 能力专属/伙伴 | B2 学习、阅读、课程 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/mastery/tools.py |
| mastery_revise | 能力专属/伙伴 | B2 学习、阅读、课程 | agents/q5_tools.py:253 | deeptutor/capabilities/mastery/tools.py |
| mastery_paths | 能力专属/伙伴 | B2 学习、阅读、课程 | agents/q5_tools.py:197 | deeptutor/capabilities/mastery/tools.py |
| mastery_switch | 能力专属/伙伴 | B2 学习、阅读、课程 | agents/q5_tools.py:212 | deeptutor/capabilities/mastery/tools.py |
| mastery_leave | 能力专属/伙伴 | B2 学习、阅读、课程 | agents/q5_tools.py:234 | deeptutor/capabilities/mastery/tools.py |
| solve_plan | 能力专属/伙伴 | B3 解题与研究 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/solve/tools.py |
| solve_finish_step | 能力专属/伙伴 | B3 解题与研究 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/solve/tools.py |
| solve_replan | 能力专属/伙伴 | B3 解题与研究 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/solve/tools.py |
| obsidian_search | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/obsidian/tools.py |
| obsidian_read | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/obsidian/tools.py |
| obsidian_list | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/obsidian/tools.py |
| obsidian_backlinks | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/obsidian/tools.py |
| obsidian_links | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/obsidian/tools.py |
| obsidian_tags | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/obsidian/tools.py |
| obsidian_create_note | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/obsidian/tools.py |
| obsidian_append | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/obsidian/tools.py |
| obsidian_set_property | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/obsidian/tools.py |
| marginnote_search | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/marginnote4/tools.py |
| marginnote_read | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/marginnote4/tools.py |
| marginnote_list | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/marginnote4/tools.py |
| marginnote_documents | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/marginnote4/tools.py |
| marginnote_links | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/marginnote4/tools.py |
| marginnote_tags | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/marginnote4/tools.py |
| marginnote_cards | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/marginnote4/tools.py |
| consult_subagent | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/subagent/tools.py |
| ima_list | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/ima/tools.py |
| ima_read | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/ima/tools.py |
| ima_note_search | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/ima/tools.py |
| ima_add_url | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/ima/tools.py |
| ima_write_note | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/ima/tools.py |
| reading_list_tabs | 能力专属/伙伴 | B2 学习、阅读、课程 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/reading/tools.py |
| reading_switch_tab | 能力专属/伙伴 | B2 学习、阅读、课程 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/reading/tools.py |
| material_outline | 能力专属/伙伴 | B2 学习、阅读、课程 | agents/tools/first_wave_contracts.py:28 | deeptutor/capabilities/reading/tools.py |
| search_material | 能力专属/伙伴 | B2 学习、阅读、课程 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/reading/tools.py |
| read_material | 能力专属/伙伴 | B2 学习、阅读、课程 | agents/tools/first_wave_contracts.py:32 | deeptutor/capabilities/reading/tools.py |
| view_figure | 能力专属/伙伴 | B2 学习、阅读、课程 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/reading/tools.py |
| reader_goto | 能力专属/伙伴 | B2 学习、阅读、课程 | agents/tools/first_wave_contracts.py:48 | deeptutor/capabilities/reading/tools.py |
| reader_annotate | 能力专属/伙伴 | B2 学习、阅读、课程 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/reading/tools.py |
| inspect_setup | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/setup/tools.py |
| apply_setting | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/setup/tools.py |
| request_credential | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/setup/tools.py |
| run_setup_job | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/setup/tools.py |
| propose_partner | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/partner_authoring/tools.py |
| invoke_other | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/partner_group/tools.py |
| course_overview | 能力专属/伙伴 | B2 学习、阅读、课程 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/course_study/tools.py |
| course_material | 能力专属/伙伴 | B2 学习、阅读、课程 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/course_study/tools.py |
| course_edit | 能力专属/伙伴 | B2 学习、阅读、课程 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/course_study/tools.py |
| course_handoff | 能力专属/伙伴 | B2 学习、阅读、课程 | 未发现本地定义；vendor 有原版 | deeptutor/capabilities/course_study/tools.py |
| partner_read | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/tools/partner_memory.py |
| partner_memorize | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/tools/partner_memory.py |
| partner_search | 能力专属/伙伴 | B5 外部知识、配置与伙伴 | 未发现本地定义；vendor 有原版 | deeptutor/tools/partner_memory.py |

处理规则：已有且等价的底层服务/适配器保留；同名自实现但不同协议的工具替换成原生工具，宿主只提供授权和数据边界。所有工具进入同一原生注册器、挂载规则、参数守卫与调度器；不能继续由默认主链路调用本地旧循环。

## 11 个回合能力

| 能力 | 完整阶段 | 所需工具（描述器） | 原生入口 |
| --- | --- | --- | --- |
| chat | exploring → responding | brainstorm, web_search, paper_search, zotero_search, reason, geogebra_analysis, imagegen, videogen | deeptutor/agents/chat/capability.py |
| ask_questions | responding | ask_user | deeptutor/capabilities/ask_questions/capability.py |
| deep_solve | responding | solve_plan, solve_finish_step, solve_replan, rag, exec, geogebra_analysis, reason | deeptutor/capabilities/solve/capability.py |
| deep_question | ideation → generation | rag, web_search, exec | deeptutor/agents/question/capability.py |
| deep_research | rephrasing → decomposing → researching → reporting | rag, web_search, paper_search, preprint, research_audit, research_lit, exec | deeptutor/agents/research/capability.py |
| math_animator | concept_analysis → concept_design → code_generation → code_retry → summary → render_output | 阶段内部实现，仍需迁入整个 pipeline | deeptutor/agents/math_animator/capability.py |
| visualize | analyzing → generating → reviewing → concept_analysis → concept_design → code_generation → code_retry → summary → render_output | submit_visualization | deeptutor/agents/visualize/capability.py |
| mastery_path | responding | mastery_status, mastery_quiz, mastery_note_explained, mastery_grade, mastery_skip_question, mastery_repair_question, mastery_defer_objective, mastery_assess, mastery_build, mastery_mode, mastery_profile, mastery_revise, mastery_paths, mastery_switch, mastery_leave, rag, read_source, ask_user | deeptutor/capabilities/mastery/capability.py |
| immersive_reading | responding | reading_list_tabs, reading_switch_tab, material_outline, search_material, read_material, view_figure, reader_goto, reader_annotate, web_search, exec, reason | deeptutor/capabilities/reading/mode.py |
| course_study | responding | course_overview, course_material, course_edit, course_handoff, rag, web_search, exec, reason | deeptutor/capabilities/course_study/mode.py |
| audio_overview | retrieving → script_writing → voice_generation → publishing | rag | deeptutor/capabilities/audio_overview/capability.py |

每项还必须包含 pipeline/coordinator/agents、config schema、双语提示词、域服务、产物发布和对应前端结果适配，不能只迁入 capability.py。

## 14 个循环扩展

| 扩展 | 专属工具 | 原生实现 |
| --- | --- | --- |
| ask_questions | 无专属工具，仍有实际钩子行为 | deeptutor/capabilities/ask_questions/loop.py |
| mastery | mastery_status, mastery_quiz, mastery_note_explained, mastery_grade, mastery_skip_question, mastery_repair_question, mastery_defer_objective, mastery_assess, mastery_build, mastery_mode, mastery_profile, mastery_revise, mastery_paths, mastery_switch, mastery_leave, read_source | deeptutor/capabilities/mastery/loop.py |
| solve | solve_plan, solve_finish_step, solve_replan | deeptutor/capabilities/solve/loop.py |
| obsidian | obsidian_search, obsidian_read, obsidian_list, obsidian_backlinks, obsidian_links, obsidian_tags, obsidian_create_note, obsidian_append, obsidian_set_property | deeptutor/capabilities/obsidian/capability.py |
| marginnote4 | marginnote_search, marginnote_read, marginnote_list, marginnote_documents, marginnote_links, marginnote_tags, marginnote_cards | deeptutor/capabilities/marginnote4/capability.py |
| subagent | consult_subagent | deeptutor/capabilities/subagent/capability.py |
| ima | ima_list, ima_read, ima_note_search, ima_add_url, ima_write_note | deeptutor/capabilities/ima/capability.py |
| immersive_reading | reading_list_tabs, reading_switch_tab, material_outline, search_material, read_material, view_figure, reader_goto, reader_annotate | deeptutor/capabilities/reading/capability.py |
| course_study | course_overview, course_material, course_edit, course_handoff | deeptutor/capabilities/course_study/capability.py |
| explore_context | 无专属工具，仍有实际钩子行为 | deeptutor/capabilities/explore_context/capability.py |
| setup | inspect_setup, apply_setting, request_credential, run_setup_job | deeptutor/capabilities/setup/capability.py |
| partner_authoring | propose_partner | deeptutor/capabilities/partner_authoring/capability.py |
| partner_group | invoke_other | deeptutor/capabilities/partner_group/capability.py |
| visualization_generation | submit_visualization | deeptutor/visualizers/loop_capability.py |

## 动态工具提供者

- MCP：沿用原生 server/config/OAuth/catalog/按用户授权、延迟 schema 加载和工具调用；清单按当前实际注册的 server 展开。
- CLI：沿用原生 CLI 应用描述器、命令解析、工作目录与执行边界；按实际安装和用户授权挂载。
- Plugin：保留 entry point、manifest、兼容性、生命周期和前端桥接，不能只保留名字列表。
- 动态工具数量不固定，不混入 100 个内置工具计数。缺少配置可以呈现 missing_config，但不能标记为已真实调用。
