# 完整对话复用验收矩阵

日期：2026-10-19。配套：[实施计划](IMPLEMENTATION_PLAN.md)。

这里跟踪新原生主链接入，已有网关或试点测试不直接计作新主链完成。P0 基线与接入契约已完成，P1 私有运行时已接通；使用受控能力验证真实应用层，不计作下列真实能力/工具完成，仍保持未开始。尚缺宿主生命周期、原生教材服务和页面。阶段证据见 [执行记录](EXECUTION_LOG.md)。源代码入口和挂载条件见 [完整清单](TOOLS_CAPABILITIES.md) 与 SOURCE_AUDIT.json。

状态：未开始 → 适配中 → 隔离验证通过 → 真实验证通过；依赖缺失记录待配置或受阻。阶段表示主要负责阶段，不取消其他阶段的前置依赖。每项更新时附提交、检查命令/案例、依赖、作用域、结果及产物位置。

## 11 个顶层能力

| 能力 | 阶段 | 必须验证的行为 | 状态 |
| --- | --- | --- | --- |
| `chat` | P3 | 概念、比较、追问；实际调用原生上下文与教材工具，失败不冒充成功 | 未开始 |
| `ask_questions` | P3 | 问题卡→等待→用户答复→继续原任务；刷新与重复答复不重复生成 | 未开始 |
| `deep_solve` | P7 | 计划→完成步骤→受限重规划→回答；不能跳过状态门槛 | 未开始 |
| `deep_question` | P6 | 生成题组、作答及题目追问；正式题目的答案与发布规则生效 | 未开始 |
| `deep_research` | P7 | 确认/编辑提纲→分解研究→报告与来源；失败保留真实状态 | 未开始 |
| `math_animator` | P7 | 生成/重试代码→受控渲染→可播放产物；渲染失败明确反馈 | 未开始 |
| `visualize` | P7 | 实际提交有效载荷、Viewer 可用；无效载荷不能空画布冒充完成 | 未开始 |
| `mastery_path` | P6 | 学习/测试/复习、题卡、评分和下一目标；重复作答不重复推进 | 未开始 |
| `immersive_reading` | P6 | 目录/读取/原图/跳转/批注；空阅读器与失效 revision 不伪造资料 | 未开始 |
| `course_study` | P6 | 课程状态→推荐→可操作交接；无课程时明确缺口 | 未开始 |
| `audio_overview` | P7 | 教材取材→讲稿→真实 TTS→音频/转录；未配置语音不能假成功 | 未开始 |

## 14 个循环扩展

每项均验证：应激活时生效，不应激活时不泄漏工具或规则，资源变化后重新绑定。

| 扩展 | 阶段 | 关键检查 | 状态 |
| --- | --- | --- | --- |
| `ask_questions` | P3 | 激活问题策略与首轮交互，并能恢复后续执行 | 未开始 |
| `mastery` | P6 | 模式过滤、权威状态、评分种子及完成约束均实际生效 | 未开始 |
| `solve` | P7 | 计划与重规划状态绑定正确、预算有效 | 未开始 |
| `obsidian` | P4 | 绑定 vault、专属工具及和其他知识库共存 | 未开始 |
| `marginnote4` | P4 | 绑定数据与专属读取，不越权访问未选来源 | 未开始 |
| `subagent` | P4 | 连接与调用预算正确、外部运行器有真实就绪状态 | 未开始 |
| `ima` | P4 | 知识库绑定、查询与写入动作的资源范围正确 | 未开始 |
| `immersive_reading` | P6 | 材料/模式/视口激活，预定位及引用来源有效 | 未开始 |
| `course_study` | P6 | 课程绑定激活、状态预读和交接结果正确 | 未开始 |
| `explore_context` | P3 | 来源存在才触发，真实只读调查结果进入回答 | 未开始 |
| `setup` | P4 | 仅设置上下文激活，配置与凭据交互不泄漏服务端秘密 | 未开始 |
| `partner_authoring` | P4 | 伙伴创建上下文激活、提案与实际业务确认一致 | 未开始 |
| `partner_group` | P4 | 组上下文、成员预算、正式回答和中间说明区分 | 未开始 |
| `visualization_generation` | P7 | 工具载荷提交、模式完成检查与可视化输出有效 | 未开始 |

## 100 个内置工具

每项记录四类证据：①挂载与拒绝条件；②实际参数/资源和返回；③页面或下游消费；④失败/超时/重复/越权行为。涉及写入、评分、外发、定时任务或文件的工具另查对应授权、幂等与撤销。只读工具不要求编造无关写入测试。

| 工具 | 阶段 | 状态 | 证据/实际依赖 |
| --- | --- | --- | --- |
| `brainstorm` | P4 | 未开始 | 待实施记录 |
| `rag` | P2 | 未开始 | 待实施记录 |
| `kb_files` | P2 | 未开始 | 待实施记录 |
| `knowledge_frontier` | P2 | 未开始 | 待实施记录 |
| `web_search` | P4 | 未开始 | 待实施记录 |
| `reason` | P4 | 未开始 | 待实施记录 |
| `paper_search` | P4 | 未开始 | 待实施记录 |
| `zotero_search` | P4 | 未开始 | 待实施记录 |
| `read_source` | P3 | 未开始 | 待实施记录 |
| `read_memory` | P5 | 未开始 | 待实施记录 |
| `write_memory` | P5 | 未开始 | 待实施记录 |
| `read_skill` | P4 | 未开始 | 待实施记录 |
| `load_tools` | P4 | 未开始 | 待实施记录 |
| `web_fetch` | P4 | 未开始 | 待实施记录 |
| `list_notebook` | P5 | 未开始 | 待实施记录 |
| `write_note` | P5 | 未开始 | 待实施记录 |
| `question_bank` | P6 | 未开始 | 待实施记录 |
| `github` | P4 | 未开始 | 待实施记录 |
| `ask_user` | P3 | 未开始 | 待实施记录 |
| `cron` | P4 | 未开始 | 待实施记录 |
| `geogebra_analysis` | P4 | 未开始 | 待实施记录 |
| `learning_status` | P5 | 未开始 | 待实施记录 |
| `learning_update` | P5 | 未开始 | 待实施记录 |
| `preprint` | P4 | 未开始 | 待实施记录 |
| `research_audit` | P4 | 未开始 | 待实施记录 |
| `research_lit` | P4 | 未开始 | 待实施记录 |
| `exec` | P4 | 未开始 | 待实施记录 |
| `workspace_list` | P4 | 未开始 | 待实施记录 |
| `workspace_read` | P4 | 未开始 | 待实施记录 |
| `workspace_search` | P4 | 未开始 | 待实施记录 |
| `workspace_present` | P4 | 未开始 | 待实施记录 |
| `workspace_export` | P4 | 未开始 | 待实施记录 |
| `submit_visualization` | P7 | 未开始 | 待实施记录 |
| `imagegen` | P4 | 未开始 | 待实施记录 |
| `videogen` | P4 | 未开始 | 待实施记录 |
| `mastery_topics` | P6 | 未开始 | 待实施记录 |
| `mastery_sessions` | P6 | 未开始 | 待实施记录 |
| `mastery_open_session` | P6 | 未开始 | 待实施记录 |
| `mastery_new_session` | P6 | 未开始 | 待实施记录 |
| `mastery_status` | P6 | 未开始 | 待实施记录 |
| `mastery_quiz` | P6 | 未开始 | 待实施记录 |
| `mastery_note_explained` | P6 | 未开始 | 待实施记录 |
| `mastery_grade` | P6 | 未开始 | 待实施记录 |
| `mastery_skip_question` | P6 | 未开始 | 待实施记录 |
| `mastery_repair_question` | P6 | 未开始 | 待实施记录 |
| `mastery_defer_objective` | P6 | 未开始 | 待实施记录 |
| `mastery_assess` | P6 | 未开始 | 待实施记录 |
| `mastery_build` | P6 | 未开始 | 待实施记录 |
| `mastery_mode` | P6 | 未开始 | 待实施记录 |
| `mastery_profile` | P6 | 未开始 | 待实施记录 |
| `mastery_revise` | P6 | 未开始 | 待实施记录 |
| `mastery_paths` | P6 | 未开始 | 待实施记录 |
| `mastery_switch` | P6 | 未开始 | 待实施记录 |
| `mastery_leave` | P6 | 未开始 | 待实施记录 |
| `solve_plan` | P7 | 未开始 | 待实施记录 |
| `solve_finish_step` | P7 | 未开始 | 待实施记录 |
| `solve_replan` | P7 | 未开始 | 待实施记录 |
| `obsidian_search` | P4 | 未开始 | 待实施记录 |
| `obsidian_read` | P4 | 未开始 | 待实施记录 |
| `obsidian_list` | P4 | 未开始 | 待实施记录 |
| `obsidian_backlinks` | P4 | 未开始 | 待实施记录 |
| `obsidian_links` | P4 | 未开始 | 待实施记录 |
| `obsidian_tags` | P4 | 未开始 | 待实施记录 |
| `obsidian_create_note` | P4 | 未开始 | 待实施记录 |
| `obsidian_append` | P4 | 未开始 | 待实施记录 |
| `obsidian_set_property` | P4 | 未开始 | 待实施记录 |
| `marginnote_search` | P4 | 未开始 | 待实施记录 |
| `marginnote_read` | P4 | 未开始 | 待实施记录 |
| `marginnote_list` | P4 | 未开始 | 待实施记录 |
| `marginnote_documents` | P4 | 未开始 | 待实施记录 |
| `marginnote_links` | P4 | 未开始 | 待实施记录 |
| `marginnote_tags` | P4 | 未开始 | 待实施记录 |
| `marginnote_cards` | P4 | 未开始 | 待实施记录 |
| `consult_subagent` | P4 | 未开始 | 待实施记录 |
| `ima_list` | P4 | 未开始 | 待实施记录 |
| `ima_read` | P4 | 未开始 | 待实施记录 |
| `ima_note_search` | P4 | 未开始 | 待实施记录 |
| `ima_add_url` | P4 | 未开始 | 待实施记录 |
| `ima_write_note` | P4 | 未开始 | 待实施记录 |
| `reading_list_tabs` | P6 | 未开始 | 待实施记录 |
| `reading_switch_tab` | P6 | 未开始 | 待实施记录 |
| `material_outline` | P6 | 未开始 | 待实施记录 |
| `search_material` | P6 | 未开始 | 待实施记录 |
| `read_material` | P6 | 未开始 | 待实施记录 |
| `view_figure` | P6 | 未开始 | 待实施记录 |
| `reader_goto` | P6 | 未开始 | 待实施记录 |
| `reader_annotate` | P6 | 未开始 | 待实施记录 |
| `inspect_setup` | P4 | 未开始 | 待实施记录 |
| `apply_setting` | P4 | 未开始 | 待实施记录 |
| `request_credential` | P4 | 未开始 | 待实施记录 |
| `run_setup_job` | P4 | 未开始 | 待实施记录 |
| `propose_partner` | P4 | 未开始 | 待实施记录 |
| `invoke_other` | P4 | 未开始 | 待实施记录 |
| `course_overview` | P6 | 未开始 | 待实施记录 |
| `course_material` | P6 | 未开始 | 待实施记录 |
| `course_edit` | P6 | 未开始 | 待实施记录 |
| `course_handoff` | P6 | 未开始 | 待实施记录 |
| `partner_read` | P4 | 未开始 | 待实施记录 |
| `partner_memorize` | P4 | 未开始 | 待实施记录 |
| `partner_search` | P4 | 未开始 | 待实施记录 |

## 总体验收门槛

- M1：P0—P3 完成，普通原生对话、教材检索、澄清、发布与恢复在现有页面真实可用。
- 工具/能力不只核对注册：必须有匹配资源的实际执行、前端/下游处理和失败案例。
- MCP、CLI、插件及其他动态提供者在配置后另增行，不与上述 100 个静态内置工具混计。
- 11/14/100 覆盖项没有受阻/未配置冒充完成，才可宣称整套复用完成。未就绪外部依赖保持真实状态，M1 可独立试用。
- 上游已知异步事件收集测试失败、历史离散数学夹具缺口与迁移新增问题分别记录，不能互相覆盖。
