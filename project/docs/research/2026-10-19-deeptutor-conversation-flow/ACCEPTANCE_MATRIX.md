# 整套代码集成验收矩阵

日期：2026-10-19。配套：[实施计划](IMPLEMENTATION_PLAN.md)。

范围保持 11 个顶层能力、14 个循环扩展、100 个内置工具。修订只改变集成方式：将实现迁入本项目并接本项目接口、数据和页面，不把整轮功能路由到完整 DeepTutor 应用。阶段改用 Q0—Q6，详见 [修订计划](IMPLEMENTATION_PLAN.md) 和 [代码集成契约](LOCAL_REUSE_CONTRACT.md)。已有网关及原生 worker 实验不折算为代码集成完成，当前各项仍保持未开始。阶段证据见 [执行记录](EXECUTION_LOG.md)；来源与挂载条件见 [完整清单](TOOLS_CAPABILITIES.md) 和 SOURCE_AUDIT.json。

状态：未开始 → 适配中 → 隔离验证通过 → 真实验证通过；依赖缺失记录待配置或受阻。阶段表示主要负责阶段，不取消其他阶段的前置依赖。每项更新时附提交、检查命令/案例、依赖、作用域、结果及产物位置。

## 11 个顶层能力

| 能力 | 阶段 | 必须验证的行为 | 状态 |
| --- | --- | --- | --- |
| `chat` | Q1/Q2/Q3 | 概念、比较、追问及明确章节学习；第一章/第1章应能按真实目录启动学习，迁入模块接本项目流程，失败不冒充成功 | 未开始 |
| `ask_questions` | Q3 | 问题卡→等待→用户答复→继续原任务；刷新与重复答复不重复生成 | 未开始 |
| `deep_solve` | Q5 | 计划→完成步骤→受限重规划→回答；不能跳过状态门槛 | 未开始 |
| `deep_question` | Q5 | 生成题组、作答及题目追问；正式题目的答案与发布规则生效 | 未开始 |
| `deep_research` | Q5 | 确认/编辑提纲→分解研究→报告与来源；失败保留真实状态 | 未开始 |
| `math_animator` | Q6 | 生成/重试代码→受控渲染→可播放产物；渲染失败明确反馈 | 未开始 |
| `visualize` | Q6 | 实际提交有效载荷、Viewer 可用；无效载荷不能空画布冒充完成 | 未开始 |
| `mastery_path` | Q5 | 学习/测试/复习、题卡、评分和下一目标；重复作答不重复推进 | 未开始 |
| `immersive_reading` | Q5 | 目录/读取/原图/跳转/批注；空阅读器与失效 revision 不伪造资料 | 未开始 |
| `course_study` | Q5 | 课程状态→推荐→可操作交接；无课程时明确缺口 | 未开始 |
| `audio_overview` | Q6 | 教材取材→讲稿→真实 TTS→音频/转录；未配置语音不能假成功 | 未开始 |

## 14 个循环扩展

每项均验证：应激活时生效，不应激活时不泄漏工具或规则，资源变化后重新绑定。

| 扩展 | 阶段 | 关键检查 | 状态 |
| --- | --- | --- | --- |
| `ask_questions` | Q3 | 激活问题策略与首轮交互，并能恢复后续执行 | 未开始 |
| `mastery` | Q5 | 模式过滤、权威状态、评分种子及完成约束均实际生效 | 未开始 |
| `solve` | Q6 | 计划与重规划状态绑定正确、预算有效 | 未开始 |
| `obsidian` | Q4 | 绑定 vault、专属工具及和其他知识库共存 | 未开始 |
| `marginnote4` | Q4 | 绑定数据与专属读取，不越权访问未选来源 | 未开始 |
| `subagent` | Q4 | 连接与调用预算正确、外部运行器有真实就绪状态 | 未开始 |
| `ima` | Q4 | 知识库绑定、查询与写入动作的资源范围正确 | 未开始 |
| `immersive_reading` | Q5 | 材料/模式/视口激活，预定位及引用来源有效 | 未开始 |
| `course_study` | Q5 | 课程绑定激活、状态预读和交接结果正确 | 未开始 |
| `explore_context` | Q3 | 来源存在才触发，真实只读调查结果进入回答 | 未开始 |
| `setup` | Q4 | 仅设置上下文激活，配置与凭据交互不泄漏服务端秘密 | 未开始 |
| `partner_authoring` | Q4 | 伙伴创建上下文激活、提案与实际业务确认一致 | 未开始 |
| `partner_group` | Q4 | 组上下文、成员预算、正式回答和中间说明区分 | 未开始 |
| `visualization_generation` | Q6 | 工具载荷提交、模式完成检查与可视化输出有效 | 未开始 |

## 100 个内置工具

每项记录四类证据：①挂载与拒绝条件；②实际参数/资源和返回；③页面或下游消费；④失败/超时/重复/越权行为。涉及写入、评分、外发、定时任务或文件的工具另查对应授权、幂等与撤销。只读工具不要求编造无关写入测试。

| 工具 | 阶段 | 状态 | 证据/实际依赖 |
| --- | --- | --- | --- |
| `brainstorm` | Q4 | 未开始 | 待实施记录 |
| `rag` | P2 | 未开始 | 待实施记录 |
| `kb_files` | P2 | 未开始 | 待实施记录 |
| `knowledge_frontier` | P2 | 未开始 | 待实施记录 |
| `web_search` | Q4 | 未开始 | 待实施记录 |
| `reason` | Q4 | 未开始 | 待实施记录 |
| `paper_search` | Q4 | 未开始 | 待实施记录 |
| `zotero_search` | Q4 | 未开始 | 待实施记录 |
| `read_source` | Q3 | 未开始 | 待实施记录 |
| `read_memory` | Q5 | 未开始 | 待实施记录 |
| `write_memory` | Q5 | 未开始 | 待实施记录 |
| `read_skill` | Q4 | 未开始 | 待实施记录 |
| `load_tools` | Q4 | 未开始 | 待实施记录 |
| `web_fetch` | Q4 | 未开始 | 待实施记录 |
| `list_notebook` | Q5 | 未开始 | 待实施记录 |
| `write_note` | Q5 | 未开始 | 待实施记录 |
| `question_bank` | Q5 | 未开始 | 待实施记录 |
| `github` | Q4 | 未开始 | 待实施记录 |
| `ask_user` | Q3 | 未开始 | 待实施记录 |
| `cron` | Q4 | 未开始 | 待实施记录 |
| `geogebra_analysis` | Q4 | 未开始 | 待实施记录 |
| `learning_status` | Q5 | 未开始 | 待实施记录 |
| `learning_update` | Q5 | 未开始 | 待实施记录 |
| `preprint` | Q4 | 未开始 | 待实施记录 |
| `research_audit` | Q4 | 未开始 | 待实施记录 |
| `research_lit` | Q4 | 未开始 | 待实施记录 |
| `exec` | Q4 | 未开始 | 待实施记录 |
| `workspace_list` | Q4 | 未开始 | 待实施记录 |
| `workspace_read` | Q4 | 未开始 | 待实施记录 |
| `workspace_search` | Q4 | 未开始 | 待实施记录 |
| `workspace_present` | Q4 | 未开始 | 待实施记录 |
| `workspace_export` | Q4 | 未开始 | 待实施记录 |
| `submit_visualization` | Q6 | 未开始 | 待实施记录 |
| `imagegen` | Q4 | 未开始 | 待实施记录 |
| `videogen` | Q4 | 未开始 | 待实施记录 |
| `mastery_topics` | Q5 | 未开始 | 待实施记录 |
| `mastery_sessions` | Q5 | 未开始 | 待实施记录 |
| `mastery_open_session` | Q5 | 未开始 | 待实施记录 |
| `mastery_new_session` | Q5 | 未开始 | 待实施记录 |
| `mastery_status` | Q5 | 未开始 | 待实施记录 |
| `mastery_quiz` | Q5 | 未开始 | 待实施记录 |
| `mastery_note_explained` | Q5 | 未开始 | 待实施记录 |
| `mastery_grade` | Q5 | 未开始 | 待实施记录 |
| `mastery_skip_question` | Q5 | 未开始 | 待实施记录 |
| `mastery_repair_question` | Q5 | 未开始 | 待实施记录 |
| `mastery_defer_objective` | Q5 | 未开始 | 待实施记录 |
| `mastery_assess` | Q5 | 未开始 | 待实施记录 |
| `mastery_build` | Q5 | 未开始 | 待实施记录 |
| `mastery_mode` | Q5 | 未开始 | 待实施记录 |
| `mastery_profile` | Q5 | 未开始 | 待实施记录 |
| `mastery_revise` | Q5 | 未开始 | 待实施记录 |
| `mastery_paths` | Q5 | 未开始 | 待实施记录 |
| `mastery_switch` | Q5 | 未开始 | 待实施记录 |
| `mastery_leave` | Q5 | 未开始 | 待实施记录 |
| `solve_plan` | Q6 | 未开始 | 待实施记录 |
| `solve_finish_step` | Q6 | 未开始 | 待实施记录 |
| `solve_replan` | Q6 | 未开始 | 待实施记录 |
| `obsidian_search` | Q4 | 未开始 | 待实施记录 |
| `obsidian_read` | Q4 | 未开始 | 待实施记录 |
| `obsidian_list` | Q4 | 未开始 | 待实施记录 |
| `obsidian_backlinks` | Q4 | 未开始 | 待实施记录 |
| `obsidian_links` | Q4 | 未开始 | 待实施记录 |
| `obsidian_tags` | Q4 | 未开始 | 待实施记录 |
| `obsidian_create_note` | Q4 | 未开始 | 待实施记录 |
| `obsidian_append` | Q4 | 未开始 | 待实施记录 |
| `obsidian_set_property` | Q4 | 未开始 | 待实施记录 |
| `marginnote_search` | Q4 | 未开始 | 待实施记录 |
| `marginnote_read` | Q4 | 未开始 | 待实施记录 |
| `marginnote_list` | Q4 | 未开始 | 待实施记录 |
| `marginnote_documents` | Q4 | 未开始 | 待实施记录 |
| `marginnote_links` | Q4 | 未开始 | 待实施记录 |
| `marginnote_tags` | Q4 | 未开始 | 待实施记录 |
| `marginnote_cards` | Q4 | 未开始 | 待实施记录 |
| `consult_subagent` | Q4 | 未开始 | 待实施记录 |
| `ima_list` | Q4 | 未开始 | 待实施记录 |
| `ima_read` | Q4 | 未开始 | 待实施记录 |
| `ima_note_search` | Q4 | 未开始 | 待实施记录 |
| `ima_add_url` | Q4 | 未开始 | 待实施记录 |
| `ima_write_note` | Q4 | 未开始 | 待实施记录 |
| `reading_list_tabs` | Q5 | 未开始 | 待实施记录 |
| `reading_switch_tab` | Q5 | 未开始 | 待实施记录 |
| `material_outline` | Q5 | 未开始 | 待实施记录 |
| `search_material` | Q5 | 未开始 | 待实施记录 |
| `read_material` | Q5 | 未开始 | 待实施记录 |
| `view_figure` | Q5 | 未开始 | 待实施记录 |
| `reader_goto` | Q5 | 未开始 | 待实施记录 |
| `reader_annotate` | Q5 | 未开始 | 待实施记录 |
| `inspect_setup` | Q4 | 未开始 | 待实施记录 |
| `apply_setting` | Q4 | 未开始 | 待实施记录 |
| `request_credential` | Q4 | 未开始 | 待实施记录 |
| `run_setup_job` | Q4 | 未开始 | 待实施记录 |
| `propose_partner` | Q4 | 未开始 | 待实施记录 |
| `invoke_other` | Q4 | 未开始 | 待实施记录 |
| `course_overview` | Q5 | 未开始 | 待实施记录 |
| `course_material` | Q5 | 未开始 | 待实施记录 |
| `course_edit` | Q5 | 未开始 | 待实施记录 |
| `course_handoff` | Q5 | 未开始 | 待实施记录 |
| `partner_read` | Q4 | 未开始 | 待实施记录 |
| `partner_memorize` | Q4 | 未开始 | 待实施记录 |
| `partner_search` | Q4 | 未开始 | 待实施记录 |

## 每项必须记录的代码集成证据

- 来源固定 SHA/文件、目标文件、许可证/NOTICE 与修改说明。
- 必要依赖及其裁剪/适配：模型、上下文、工具、资源、存储、事件分别接到哪个项目接口。
- 本项目实际调用方，以及被保留、合并或替换的旧调用点；不能只记录复制文件或调用上游应用接口。
- 真实资源与权限、成功/失败案例、页面/下游处理、模型与运行成本、当前限制和验证产物。

## 总体验收门槛

- M1（Q1）：当前页面中的普通对话和追问使用迁入模块，有同模型同教材的质量对照；不是整套完成。
- M2（Q3）：检索/工具、必要澄清、继续、核验、保存/恢复在本项目任务内闭环，不以完整 DeepTutor 应用委托代替。
- M3（Q6）：11/14/100 整套覆盖逐项完成代码集成、依赖与真实运行验收；不缩为只验核心工具。
- MCP、CLI、插件及其他动态提供者配置后另增行，不与上述100个静态内置工具混计。
- 未配置外部服务如实标记待配置/受阻；代码迁入、可挂载、实际可用和真实验证通过分别记录。
- 上游已知测试失败、历史夹具缺口与本次集成问题分别记录；历史 worker/网关测试不折算为当前路线已通过。
