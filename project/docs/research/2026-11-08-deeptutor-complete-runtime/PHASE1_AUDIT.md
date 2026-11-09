# 第一部分复核：已接通的子集与尚未完成的原生行为

复核日期：2026-11-08。

## 结论

**没有完成“第一部分所有相关文件与行为的完整替换”。** 当前完成的是选定的 10 个上下文模块迁入并接通宿主主聊天/文字选区的本地循环；两个已有公共辅助模块保留。文件完整性通过，不代表上游上下文运行链路已等价替换。

本轮重新检查原 `.ua` 图谱、根目录 `ARCHITECTURE.html`、源码注册表和宿主实际入口，并重跑 19 项既有上下文测试，全部通过。此前 235/55 项属于上一轮专项结果，本轮没有重新运行，也不能据此推断未覆盖的原生功能已经完成。

原图谱的提交与 D 盘 HEAD 均为 `6cf793bd868ba5ecbe64722936d4be8fab5a01df`。D 盘 `services/llm/factory.py` 有未提交修改；图谱只分析 core/runtime/capabilities，未完整覆盖 services/session 与 agents/loop。本轮用实际源码补齐这些范围，没有只依赖图谱的入边。

## 10 个已迁入模块逐项检查

全部文件存在且符合 `SOURCE_NOTICE.json` 的当前本地哈希；其中 6 个保持上游原字节，4 个做导入或摘要模型边界适配。它们均可从宿主调用链找到消费位置，不能称为只是未被调用的副本。

| 上游文件 | 内容核对 | 实际接入与缺口 |
| --- | --- | --- |
| deeptutor/core/context.py | 原字节一致 | 原版数据类型已使用；附件、KB、人设、工作区等字段未在宿主普通回合完整装配。 |
| deeptutor/capabilities/protocol.py | 导入/摘要边界适配 | PromptBlock 在用；保留协议定义不等于 LoopExtension 的钩子已运行。 |
| deeptutor/core/stream.py | 原字节一致 | 摘要事件使用原版类型；主 SSE 仍走宿主 EventCollector，未统一为原生 StreamBus/事件日志。 |
| deeptutor/core/trace.py | 原字节一致 | 摘要 trace 在用；尚未统一原生回合 usage/cost/trace 生命周期。 |
| deeptutor/services/session/context_builder.py | 导入/摘要边界适配 | 完整算法经宿主适配在用；_HistoryStore 是临时适配，非上游完整会话/分支存储。 |
| deeptutor/services/session/model_history.py | 原字节一致 | 工具问答归组与重放在用；provider route/binding、上下文快照语义未完整对齐。 |
| deeptutor/services/session/ask_user_trace.py | 原字节一致 | 原生提取函数在上下文构建器中；实际暂停接续仍是本地循环，未使用原生等待队列与交互钩子。 |
| deeptutor/services/session/provider_response_state.py | 原字节一致 | 校验函数在用；本地 _initial_messages 会移除 _provider_response_state，不能算完整 provider replay。 |
| deeptutor/agents/loop/prompt_blocks.py | 导入/摘要边界适配 | blocks/render 在用；split_for_replay 没有在宿主主循环接通。 |
| deeptutor/agents/loop/context_budget.py | 导入/摘要边界适配 | 实际请求的用量读数在用；不是窗口裁剪，原生 _guard_context_window 仍未迁入执行链。 |

另外，`agents/context_window.py` 与 `agents/prompt_language.py` 已有对应迁入实现；运行逻辑一致，保留，不再次复制。

## 不能标为完成的 9 项

1. **统一请求与上下文全量装配**：原生 `core/turn_request.py`、`app/contracts.py`、`services/session/turns/request_preparer.py`、`context_assembler.py`、`executor.py` 未替换宿主的实际装配入口。`assemble_turn()` 只填部分字段，默认能力固定 chat；KB、附件、persona、原生 workspace、reading/mastery 引用、配置和语言偏好等没有贯通。
2. **运行时快照重放**：原生 pipeline 调用 `split_for_replay()`，按命名片段追踪更新、为空时显式撤销旧片段；宿主只渲染块，并在历史中移除 `_context_snapshot`。缺少的是执行行为，不是再复制一个 prompt 文件。
3. **provider 私有状态与路由一致性**：宿主移除 `_provider_response_state`，构造摘要配置时 `binding=None`；未完整接入换 provider/model 后的私有状态清理和原生 wire 协议重放。
4. **运行中上下文窗口保护**：当前接入的 context_budget 是读数；原生 pipeline 的 `_guard_context_window()` 还未进入宿主模型循环，连续工具调用的输入窗口行为不同。
5. **会话存储、分支与崩溃恢复**：当前 `_HistoryStore` 从宿主对话行临时构造、通过私有引用保存摘要水位；不是原生 SessionStoreProtocol + TurnRuntimeManager + coordinator/event journal 的完整链路，也未支持对应的编辑分支叶节点查询。
6. **交互生命周期**：本地 ask_user 的暂停恢复能运行，但仍由 `LoopResult.state()` 和 TaskService 驱动，尚未接通原生 runtime.wait_for_user_reply、交互队列以及扩展的 pause/resume 钩子。
7. **工具选择语义**：宿主 LoopRequest 将 enabled_tools 和 allowed_builtin_tools 都作为整个工具集合的过滤条件；原生 builtin 白名单只影响自动挂载工具，不影响用户可选工具与 capability-owned 工具。等价替换需要原生组合器和 registry，不能只保留 dataclass 字段。
8. **事件、usage 与终态 envelope**：主链路仍是宿主事件收集和结果映射；原生 StreamBus、usage ledger、emit_capability_result、完成事件与重放未统一。复制 stream.py/trace.py 并不完成这些行为。
9. **主入口仍使用自实现内核**：main._execute_task_turn → run_agent_loop_turn → LocalAgentLoop、宿主 tool_dispatch/registry；没有默认进入 TurnApplicationService → TurnEngine → ChatOrchestrator → 原生 capability/pipeline。

## 关键源码证据

- [原生上下文执行装配](D:/deeptutor/deeptutor/services/session/turns/executor.py:67)：UnifiedContext 在此从验证后的请求、存储与资源服务装配。
- [原生 system prompt 与快照分离](D:/deeptutor/deeptutor/agents/loop/pipeline.py:436)，以及 [原生模型消息与快照重放](D:/deeptutor/deeptutor/agents/loop/pipeline.py:466)。
- [原生运行中窗口保护](D:/deeptutor/deeptutor/agents/loop/pipeline.py:1623)。
- [宿主部分字段装配](E:/项目/heart/project/integration/discrete-math-tutor/agents/turn_context.py:11)、[宿主模型历史处理](E:/项目/heart/project/integration/discrete-math-tutor/agents/agent_loop.py:335)。
- [宿主整个集合的工具过滤](E:/项目/heart/project/integration/discrete-math-tutor/agents/agent_loop.py:32)，对照 [原生分层工具挂载](D:/deeptutor/deeptutor/agents/_shared/tool_composition.py:174)。
- [当前主入口](E:/项目/heart/project/integration/discrete-math-tutor/main.py:210)，以及 [现有受限原生启动入口](E:/项目/heart/project/integration/discrete-math-tutor/integrations/deeptutor/native_bridge.py:171)。

## 图谱与架构说明中的滞后

- 图中可选工具写 7 个，源码 `USER_TOGGLEABLE_TOOL_NAMES` 为 8 个，包括 zotero_search。
- 源码实际登记 11 个回合能力、14 个循环扩展和 100 个内置工具；不能把图谱的 37 个 UnifiedContext 关联文件当作全部依赖集合。
- 架构说明写 `capabilities/_shared.py` 归一化结果，当前没有这个文件；实际实现为 `agents/_shared/capability_result.py`。
- AGENTS 文档提到的 SDK `deeptutor/app.py` 是旧位置；实际为 `deeptutor/app/`，入口类在 facade.py，由 __init__.py 导出。

## 收尾方式

不再先把本地简化循环补成另一个上游实现再删除。保留已验证的模块与底层适配，把缺失的上下文原生行为与第二部分的运行内核一起接通，作为第二部分 B0 的强制前置验收。**B0 未通过，不能宣称第一部分完整闭环。**

本轮仅审计和编写方案，未修改业务代码、未启用新的工具或能力、未重启现有服务。
