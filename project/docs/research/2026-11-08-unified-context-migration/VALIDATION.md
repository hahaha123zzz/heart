> 2026-11-08 复核补充：本文记录的是选定上下文子集的迁入与验证，不代表第一部分原生上下文行为已全部替换。完整缺口和后续范围见 [第一部分复核](../2026-11-08-deeptutor-complete-runtime/PHASE1_AUDIT.md) 与 [第二部分方案](../2026-11-08-deeptutor-complete-runtime/PHASE2_MIGRATION_PLAN.md)。

# UnifiedContext 迁移验证

日期：2026-11-08。

## 结果

- 核心专项：235 项通过（13 个测试模块）。
- 扩展专项：55 项通过；明确排除 10 个已用 Git 原版逐项复现的既有失败。
- 新增统一上下文检查：19 项，包含在核心专项内。
- Python AST 语法检查通过；git diff --check 通过。
- 10 个迁入模块的来源哈希核对通过；core/context.py 与固定上游逐字节一致。

## 实际链路证据

`tests/test_unified_context_chain.py` 中的 `test_actual_task_entry_reads_teaching_skills_then_persists_and_replays_context` 执行 `main.py` 的真实 `_execute_task_turn` 分发函数，进入真实 TaskService 和 run_agent_loop_turn，再读取真实教学技能文件，使用离线模型替身完成生成、宿主保存和下一轮私有模型历史重放。

该测试提取并执行实际入口函数，避免导入 main 时初始化正式数据库；数据库使用独立临时 SQLite。它没有替代上下文构造器、提示词组装器或循环实现。其他专项覆盖文字选区、取消、任务幂等、暂停恢复、工具权限、分块发布、学习计划、事件与记忆隔离。

新增检查还覆盖：完整工具消息对重放；长消息不按字符截断；超过 40 条显示历史；摘要成功与失败；水位复用与分支失效；异步请求中的同步调用；同一上下文和工具可变命名空间；空工具白名单；学生与会话归属；公开历史、学习事件和记忆索引不含私有模型记录；遗忘偏好后仅清除当前学生的派生快照。

## 复现

在 `project/integration/discrete-math-tutor` 使用已安装依赖的 `.venv-gpu/Scripts/python.exe -X utf8 -B`。

新增专项：

```powershell
$env:LLM_MOCK = '1'
.venv-gpu/Scripts/python.exe -X utf8 -B -m unittest discover -s tests -p test_unified_context_chain.py -v
```

核心专项模块：test_unified_context_chain、test_conversation_context、test_q3_agent_loop、test_q3_task_loop、test_task_service_context、test_selection_loop、test_teaching_skills、test_q5_learning、test_memory_events、test_first_wave_tools、test_composition_execution、test_response_composition、test_input_understanding_task_api。

扩展专项模块：test_task_context、test_q3_q4_integration、test_memory_management，排除下面十个已复现的旧问题。

## 既有失败，不计入通过数

以下十项在独立 Python 进程中加载 Git HEAD 原版上下文、执行器与存储模块后，仍得到相同错误；没有恢复旧教材、伪造题库或修改正式检索配置来消除它们。

| 测试 | 原因 |
| --- | --- |
| test_task_context.test_exercise_version_and_part_are_validated_without_answers | 当前心理学课程题库为空，旧测试依赖离散数学题目 |
| test_task_context.test_selected_explanation_uses_task_and_does_not_advance_state | 缺少旧 chapter-07 文档 |
| test_task_context.test_selected_topic_switch_reuses_identification | 缺少旧 chapter-07 文档 |
| test_task_context.test_untrusted_selection_text_does_not_reach_context | 缺少旧 chapter-07 文档 |
| test_q3_q4_integration.test_next_topic_is_not_turned_back_into_clarification | 旧检索夹具报 retrieval_not_ready |
| test_q3_q4_integration.test_completed_loop_persists_cited_pdf_references | 旧模型脚本缺少必须的教学技能指南读取 |
| test_q3_q4_integration.test_loop_executes_q4_skill_tool_and_keeps_state | 同上 |
| test_q3_q4_integration.test_progress_callback_receives_string_details | 同上 |
| test_q3_q4_integration.test_resume_rebuilds_registry_with_current_grants | 同上 |
| test_memory_management.test_pdf_selection_deleted_mid_generation_is_not_saved | 旧 Mock 未实现教学技能准备阶段的工具调用结果 |

被直接修改的旧历史、任务暂停和分块测试更新了离线夹具：只测旧生成器提示词时替换技能准备；只测任务生命周期时隔离技能选择。新增真实入口测试则保留并执行正式技能读取要求，未放宽生产代码的要求。

## 未执行与风险

没有调用外部真实模型、没有浏览器或真实 HTTP 服务验收，没有重启现有服务。所有生成使用脚本化替身或明确的离线模式；使用临时 SQLite，不修改正式学生数据或实际 .env。

长历史首次超过预算时，完整 ContextBuilder 会通过宿主网关增加一次摘要模型调用。摘要失败不推进水位；最新完整回合仍保留。迁入文件均在启用的宿主主聊天/文字选区链路上使用，运行中的旧进程仍须重新加载代码。

图谱中的 Obsidian、IMA、MarginNote、伙伴等专用消费者保留原版 vendor 文件和已有原生入口，未宣称这些外部产品功能已默认接入宿主。详见 FILES.md 的逐文件清单。
