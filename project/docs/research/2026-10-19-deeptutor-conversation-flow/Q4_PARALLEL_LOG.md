# Q4 工具底座并行执行记录

日期：2026-10-19。分支：`codex/q4-tool-foundation`。Worktree：`E:\项目\heart-worktrees\q4-tool-foundation`。基线：`2d4b4d0`。主工作区 `E:\项目\heart` 的全部未提交改动未复制、未覆盖、未提交。

## 1. 源码与边界

- 上游固定源码：`D:\deeptutor`，提交 `6cf793bd868ba5ecbe64722936d4be8fab5a01df`。
- 逐项来源、类名、行号、阶段和依赖见 [Q4_TOOL_LEDGER.md](Q4_TOOL_LEDGER.md) 与 [Q4_TOOL_LEDGER.json](Q4_TOOL_LEDGER.json)。
- 本轮只做 Q4 工具注册/授权/校验/加载/调度桥接和四个只读工具；没有修改 Q2 教材解析/检索内部实现，没有实现另一套 AgentLoop，没有接管 Q5 学习业务或 Q6 多媒体。
- 没有执行外发、发布、第三方写入、定时任务或代码执行来证明功能。

## 2. Q3 接口依赖

开始本轮时 `Q3_INTERFACE_CONTRACT.md` 尚不存在；完成独立模块后，Q3 worktree 已生成：

- `E:\项目\heart-q3\project\docs\research\2026-10-19-deeptutor-conversation-flow\Q3_INTERFACE_CONTRACT.md`
- `agents/tool_protocol.py`、`agents/tool_dispatch.py` 等实现仍在 Q3 worktree 未提交状态。

本轮读取了该契约和实际实现，并按契约把 Q4 调整为**单一工具协议**：

- `BaseTool.run(arguments, context) -> ToolResult`（同步）；
- `ToolContext` 带 `student_id/session_id/task_id/request_id/knowledge_point/cancellation/emit/state`；
- `ToolDefinition`/`ToolParameter`/`ToolResult` 使用 Q3 形状；
- `ToolRegistry.register/get/names/definitions/schemas/canonical_arguments` 与 Q3 兼容；
- 去重、并发、超时、暂停排序、失败 result 由 Q3 `agents/tool_dispatch.py` 负责，Q4 不再实现第二套调度器；`agents/tools/dispatch.py` 只是薄桥接，Q3 缺失时明确抛 `Q3DispatchUnavailable`。

没有把 Q3 未提交文件复制进本分支，也没有修改 Q3 worktree。

## 3. 本轮迁入/新增文件

| 文件 | 来源/职责 | 适配说明 |
| --- | --- | --- |
| `agents/tools/protocol.py` | 上游 `core/tool_protocol.py` + Q3 契约 | 优先导入 Q3 `agents.tool_protocol`；Q3 未合并时使用同形状 fallback 仅供独立测试，`PROTOCOL_SOURCE` 明确标记来源 |
| `agents/tools/registry.py` | 上游 `runtime/registry/tool_registry.py`、`scoped_registry.py` | 惰性 built-in、别名、entry point、进程注册表；`ScopedToolRegistry`/`AuthorizationProxy` 在 `run` 再次校验工具名和资源 scope |
| `agents/tools/scope.py` | 上游 `runtime/providers/allowlist.py`、`multi_user/tool_access.py` | `Allowlist`、`ToolGrant`、`ToolScope`；空 scope 表示不授予，不把“未限制”误写成默认全开 |
| `agents/tools/validation.py` | 上游 `runtime/agentic/tool_arg_guard.py` | 必填/空白/类型/枚举/未知参数；仅对明确的数字/布尔字符串做有限归一 |
| `agents/tools/loader.py` | 上游 `runtime/registry/deferred_tools.py` | deferred manifest、按需加载、同轮 live schema 追加、可选会话持久化回调 |
| `agents/tools/mounting.py` | 上游 `agents/_shared/tool_composition.py` | 场景 baseline + 用户开关 + 上下文条件 + 扩展 owned tools；不把全部工具强开给通用循环 |
| `agents/tools/extensions.py` | 上游 14 个 loop capability/extension | 14 个激活条件、owned tools、hooks、阶段和迁移状态；不执行循环钩子 |
| `agents/tools/dispatch.py` | Q3 `agents/tool_dispatch.py` | 薄桥接；Q4 不复制 Q3 的并发/去重/超时实现 |
| `agents/tools/workspace_tools.py` | 上游 `tools/workspace.py` | `workspace_list/read/search` 只读；根来自 `ToolContext.state`，路径逃逸/绝对路径/二进制拒绝 |
| `agents/tools/skill_tools.py` | 上游 `ReadSkillTool`/`LoadToolsTool` | `read_skill` 从任务技能根读取；`load_tools` 使用 `DeferredToolLoader`，写入同轮 schema |
| `agents/tools/local_specs.py` | 上游 `tools/builtin_specs.py` 的 Q4 子集 | 当前只登记 5 个实际可加载工具，不把 100 个名称伪装成可调用 |
| `agents/tools/README.md` | 本地新增 | Q3 每轮挂载示例、`ToolContext.state` 注入点与边界说明 |
| `tests/test_q4_tool_foundation.py` | 本地新增 | 38 项隔离测试；含真实项目技能库只读测试、Q3 桥接测试 |
| `scripts/audit_q4_tools.py` | 本地新增 | 从 SOURCE_AUDIT/LOCAL_MIGRATION_MAP 生成 100/14 台账并校验来源类名/行号 |

## 4. 100 工具 / 14 扩展台账

台账状态口径与结果：

| 状态 | 工具 | 扩展 |
| --- | ---: | ---: |
| 已可运行（隔离验证） | 4 | 0 |
| 缺配置 | 27 | 3 |
| 待接业务 | 53 | 7 |
| 不适用 | 16 | 4 |
| **合计** | **100** | **14** |

- 已可运行：`workspace_list`、`workspace_read`、`workspace_search`、`read_skill`。
- `load_tools` 的加载器已实现并用替身验证，但没有真实 MCP/CLI provider，按“待接业务”记录，不标为动态外部工具可用。
- 缺配置项包括搜索/Zotero/arXiv/GitHub/Obsidian/IMA/外部 Agent/媒体生成/视觉/沙箱；逐项依赖见台账。
- 不适用项：MarginNote 4（当前 Windows 部署无本地库）、上游 setup 设置 UI（与项目 .env/管理员配置权威冲突）、伙伴/IM 账户与伙伴记忆（项目无对应产品面）。保留台账，不用空实现冒充。
- 上游工具描述、类名和行号已由脚本在固定源码中重新核对；注册名/文件存在/模拟返回均没有被当作能力验收。

## 5. 验证

### 5.1 Q4 独立测试

```powershell
$env:PYTHONPATH=(Get-Location).Path
& 'E:\项目\heart\project\integration\discrete-math-tutor\.venv\Scripts\python.exe' -B -m unittest tests.test_q4_tool_foundation -v
```

结果：**38 项通过，0 失败**。覆盖 schema、惰性注册、别名、插件去重、必填/类型/枚举、deferred manifest/加载、scope/授权代理、14 扩展激活、场景挂载、工作区路径逃逸/二进制拒绝、真实 `visualization/skills` 读取、Q3 调度桥接。

### 5.2 用 Q3 实际协议复跑

将 Q3 worktree 的 `agents/tool_protocol.py` 以 `agents.tool_protocol` 注入后复跑同一测试集：

- `PROTOCOL_SOURCE = q3`
- `BaseTool.__module__ = agents.tool_protocol`
- 结果：**38 项通过，0 失败**。

这证明 Q4 不是只匹配 fallback 形状，而是与 Q3 实际协议兼容。

### 5.3 用 Q3 实际调度联调

加载 Q3 实际 `agents/tool_dispatch.py`，使用 Q4 `ScopedToolRegistry` + `workspace_read`：

- 已授权调用：返回 `role=tool` 内容 `hello q3`，`success=True`；
- 未挂载的 `workspace_list`：返回“不在本轮工具列表中，未执行”，没有执行未授权工具；
- 动态加载：先调 `load_tools` 装载替身 deferred tool，`view.mount_tool` 将其加入本轮 registry；下一批调用成功返回 `deferred:same-turn`，证明同轮 schema 与可调用性同时生效（仍无真实 MCP/CLI provider）；
- 去重/超时：同一批重复 `workspace_read` 由 Q3 去重；慢工具在 0.05 秒超时返回失败，未继续生成。Q4 没有重复实现这两项。

该联调使用临时目录，不读取正式教材/学生数据库。

### 5.4 台账生成

```powershell
$env:PYTHONPATH=(Get-Location).Path
& 'E:\项目\heart\project\integration\discrete-math-tutor\.venv\Scripts\python.exe' -X utf8 -B scripts/audit_q4_tools.py
```

结果：100 工具、14 扩展；状态计数与上表一致；所有来源类名/行号检查通过。

## 6. 未完成与剩余事项

1. **Q3 合并/提交**：Q3 契约与实现目前在另一 worktree 未提交。Q3 提交后，应由 Q3 的 `build_default_registry`/任务链路调用 Q4 的 `ScopedToolRegistry`，并在 `ToolContext.state` 注入 `workspace_root`、`skills_root`、`deferred_loader`。本轮没有修改 Q3 代码或合并其未提交状态。
2. **Q4.2 余量**：27 个缺配置工具和 53 个待接业务工具尚未迁入；逐项按台账推进，不以统一注册表冒充完成。
3. **Q4.3 动作工具**：`workspace_export`、`cron`、`github`、`exec`、IMA/Obsidian 写入等需要一次性授权/幂等/撤销；当前没有执行这些动作。
4. **Q4.4 扩展**：14 个扩展的元数据和激活门已建立，但 Q3/Q5/Q6 的状态/UI/专属工具尚未接通；本分支没有执行任何扩展钩子。
5. **Q4.5 验收**：未授权资源不可达、缺配置如实反馈、动态加载同轮可用、写入幂等和真实失败仍需在真实调用点逐项验证。当前只完成隔离模块验证。
6. **真实 MCP/CLI provider**：`load_tools` 仍缺真实 provider；未配置项保持待配置。
7. **生产工作区/技能根**：Q4 只读工具需要 Q3 注入 per-task 根；未绑定即失败关闭，不使用项目根目录兜底。

## 7. 决策记录

- **Ruling：以 Q3 契约为唯一工具协议。** Q3 契约出现后，Q4 从 async `execute(**kwargs)` 改为同步 `run(arguments, context)`，并删除自建调度器实现，改为 Q3 dispatch 桥接。代价：若 Q3 后续修改协议，Q4 需同步适配。
- **Ruling：`load_tools` 不标为已可运行。** 加载器/同轮 schema 已用替身验证，但没有真实 MCP/CLI provider；标为待接业务，避免把模拟返回当能力验收。
- **Ruling：工作区/技能工具标为“已可运行（隔离验证）”。** 使用隔离目录和项目真实 `visualization/skills` 验证；生产任务根绑定仍待 Q3，未宣称页面级通过。
- **Ruling：MarginNote/setup/partner 标为不适用。** 当前 Windows 部署无 MarginNote 本地库；项目已有自己的配置权威；项目无伙伴/IM 产品面。保留 100/14 台账，不缩减计数。
- **Ruling：不修改主工作区。** 主工作区有 4,462 项已跟踪改动和未跟踪资料；仅创建独立 worktree，未复制/覆盖/提交这些改动。

## 8. 提交范围

仅提交本 worktree 的 Q4 文件：

- `agents/tools/` 新包；
- `tests/test_q4_tool_foundation.py`；
- `scripts/audit_q4_tools.py`；
- 本目录 `Q4_PARALLEL_LOG.md`、`Q4_TOOL_LEDGER.md`、`Q4_TOOL_LEDGER.json`。

不提交教材、数据库、密钥、运行产物；不合并主分支；不覆盖主工作区。
