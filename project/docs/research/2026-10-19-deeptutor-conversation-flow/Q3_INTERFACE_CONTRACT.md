# Q3 本地 AgentLoop 与教材工具接口契约

日期：2026-10-19。分支：`codex/q3-agent-loop`。适用范围：Q3 的对话执行循环、工具协议、ask_user 接续、取消/恢复。Q2 负责教材解析、索引与检索内部实现；Q4 负责完整工具注册与能力扩展；Q5 负责学习状态与评分。

本契约只定义**本项目内部接口**。任何实现都不得把整轮请求交给 `DeepTutorApp`、`TurnApplicationService` 或独立 DeepTutor 服务编排。

## 1. 模块边界

| 模块 | 责任 | 不负责 |
| --- | --- | --- |
| `agents/agent_loop.py` | 单轮探索→工具→继续→收尾；预算、失败收尾、暂停信号 | 教材解析、章节顺序、评分 |
| `agents/tool_protocol.py` | ToolDefinition / ToolParameter / ToolResult / BaseTool / ToolRegistry | 具体业务工具实现 |
| `agents/tool_dispatch.py` | 单条 assistant 消息内工具调用校验、去重、并发、超时、结果协议 | 跨请求幂等 |
| `agents/ask_user_contract.py` | 问题卡结构、参数校验、答复格式、答复替换 | 页面渲染 |
| `agents/loop_events.py` | 事件协议与 SSE/任务结果适配 | 前端样式 |
| `knowledge/local_rag/*`（Q2） | 教材检索、重排、来源版本 | 多轮对话、工具循环 |
| `LearningTaskRepository` | 任务状态、revision、幂等收据、取消/恢复 | 模型与工具执行 |

## 2. 工具协议

```python
@dataclass(frozen=True)
class ToolParameter:
    name: str
    type: str                  # string|integer|number|boolean|array|object
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[str] | None = None
    items: dict[str, Any] | None = None
    sensitive: bool = False

@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: tuple[ToolParameter, ...] = ()
    raw_parameters: dict[str, Any] | None = None

@dataclass
class ToolResult:
    content: str
    sources: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    success: bool = True
    pause_for_user: dict | None = None   # AskUserPayload.to_dict()
    model_message: dict | None = None    # request-only, never persisted/displayed

class BaseTool(ABC):
    definition: ToolDefinition
    async def run(self, arguments: dict, context: ToolContext) -> ToolResult: ...
```

`ToolContext` 至少包含：

```python
student_id, session_id, task_id, request_id,
knowledge_point, cancellation, emit(event_type, message, metadata),
navigation: LearningNavigator | None
```

工具只能从 `ToolRegistry` 取已挂载的 schema；模型请求未挂载工具时返回失败 tool message，不执行、不自动补权。

## 3. 教材检索与学习导航接口（Q2 必接）

Q3 **先确定目标，再检索**，不自行解析章节或用“下一知识点”原句直接检索。

```python
@dataclass(frozen=True)
class LearningTarget:
    target_id: str                 # 稳定目标 ID；可等于 section/知识点 ID
    name: str                      # 用于讲解和检索的目标名称
    chapter_id: int | None = None
    section_id: int | None = None
    source_scope: dict = field(default_factory=dict)
    reason: str = ""               # 来自课程状态/用户显式目标
    version: str = ""              # 课程/路径版本

class LearningNavigator(Protocol):
    def resolve(
        self, *, message: str, student_id: str, session_id: str,
        current_target: LearningTarget | None,
        context: Any,
    ) -> "NavigationDecision": ...

    def search(
        self, *, target: LearningTarget, query: str, limit: int,
        preferred_types: tuple[str, ...] = (),
    ) -> list["SourceRef"]: ...
```

`NavigationDecision` 至少包含：

```python
action: Literal["teach", "next", "previous", "clarify", "out_of_scope"]
target: LearningTarget | None
missing: tuple[str, ...]       # 需要澄清的槽位
reason: str
version: str
```

`SourceRef` 必须带本项目权威来源字段，Q3 只透传，不把上游 `node_id` 冒充旧 `chunk_id`：

```python
source_id, document_id, version, chapter_id, section_id,
page, text, quote, image_refs, location
```

Q2 未就绪时，Q3 使用 `StubLearningNavigator`：

- 只返回显式传入的 `current_target`；
- `search` 返回替身来源，并在结果中标记 `stub=True`；
- 测试报告必须写明“替身检索”，不得写成真实教材验收。

## 4. 循环请求与结果

```python
@dataclass
class LoopRequest:
    student_id: str
    session_id: str
    task_id: str
    request_id: str
    message: str
    system_prompt: str
    seed_messages: list[dict]       # 不含当前用户消息
    tools: list[ToolDefinition]
    max_exploration_rounds: int = 8
    max_settlement_rounds: int = 3
    max_parallel_calls: int = 15
    max_tool_retries: int = 0
    tool_timeout_seconds: float | None = 30
    deadline_monotonic: float | None = None
    cancellation: "Cancellation" | None = None
    context: Any = None

@dataclass
class LoopResult:
    final_text: str = ""
    completed: bool = False
    paused: bool = False
    pending_question: dict | None = None   # ask_user payload
    messages: list[dict] = field(default_factory=list)
    rounds: int = 0
    settlement_rounds: int = 0
    tool_steps: int = 0
    sources: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    error: str = ""
    protocol_version: int = 1
```

约束：

- 探索预算用尽后进入最多 `max_settlement_rounds` 轮收尾；仍不收敛则做一次禁用工具的强制回答。
- 第一轮模型失败直接失败；已有工具结果的后续失败做有界收尾，不无界重跑。
- 工具异常返回 `success=False` 的 role=tool 消息，模型可换策略；相同失败调用不原样无限重试。
- 最终无工具调用的有效文本才发布；空文本/仅有内部推理按有界提示重试。
- `LoopResult.messages` 保存完整 assistant/tool 配对，供恢复与审计；不得保存 provider 私密思考或密钥。

## 5. ask_user 暂停与接续

问题结构沿用上游字段名，前端可复用：

```python
AskUserOption {label, description?}
AskUserQuestion {id, prompt, options[], header?, multi_select?, allow_free_text?, placeholder?}
AskUserPayload {intro?, questions[]}
```

暂停流程：

1. `ask_user` 工具返回 `pause_for_user=payload`；
2. 循环在 `LoopResult.paused=True` 停止，不发布空回答；
3. `TaskService` 保存任务为 `awaiting_clarification`（为兼容现有页面），`result.clarification = {"mode":"ask_user", "ask_user": payload, "loop": serialized_loop_state}`；
4. 下一请求带 `task_id`、`task_revision` 和答复；TaskService 校验 revision/epoch，把答复写入对应 `tool_call_id` 的 role=tool 消息；
5. 从保存的 `messages` 继续循环，不重新执行已完成的工具；
6. 重复请求由 `TaskRequestRow` 收据/revision 拒绝，不重复生成或记分。

禁止：

- 把答复当成新的用户问题重新开始一轮；
- 未保存的 ask_user 卡片刷新后丢失原任务；
- 同一 revision 的答复执行两次。

## 6. 取消与恢复

- `Cancellation` 提供 `is_cancelled()`；循环在每轮模型调用前、工具执行前、收尾前检查。
- 取消端点调用 `TaskCancellationRegistry.cancel(task_id, revision)` 并更新任务状态；跨进程场景以数据库 `cancelled` 状态为兜底。
- 已开始的实际工具调用允许返回失败 result，但不再生成新回答、不推进学习状态。
- 刷新只重放已保存的 `LoopResult`/事件；恢复只从保存的完整消息继续，未保存的执行明确失败，不静默重跑。
- 删除/记忆 epoch 变化在恢复、保存和工具结果回填时重新校验；失效任务返回 `memory_deleted`。

## 7. 事件契约

Q3 事件最小集合：

```text
stage_start, progress, tool_call, tool_result, sources,
wait_for_input, answer, done, error
```

- `tool_call` 只暴露工具名和脱敏参数；`sensitive` 参数不进入事件。
- `tool_result` 包含 `success`、简短摘要和来源数量，不包含学生私有草稿或完整 provider 思考。
- `wait_for_input` 携带 `ask_user` payload 与 `task_id`/`task_revision`。
- 事件先写任务结果/事件列表，再发布 `done`；SSE 断开不等于取消执行。
- 页面现有 SSE 仅识别 progress/done/error；Q3 适配层把工具事件映射为带 `metadata.trace_kind` 的 progress，后续前端再升级。

## 8. 与 Q2/Q4/Q5 的依赖

| 依赖 | Q3 调用点 | Q3 不做什么 |
| --- | --- | --- |
| Q2 学习导航 | 每轮开始前 `navigator.resolve`，再 `navigator.search` | 不解析 DOCX/PDF、不建索引、不猜章节顺序 |
| Q2 来源 | 工具结果 `SourceRef` 映射到 `sources` | 不伪造 chunk_id/页码/版本 |
| Q4 工具注册 | `ToolRegistry.register`/`schemas` | 不一次开放全部工具；按角色/课程/资源挂载 |
| Q5 学习状态 | 保存 `LearningTarget`、讲解/暂停状态 | 不把“讲过”写成“掌握”，不重复记分 |
| 页面 | `TaskService`/SSE 适配 | 不替换整个网页或另建账户/会话库 |

## 9. 验收分层

| 层级 | 允许声明 | 不允许声明 |
| --- | --- | --- |
| 替身循环测试 | 循环、工具配对、预算、暂停、取消、幂等通过 | 真实教材/真实模型/页面通过 |
| Q2 检索接口联调 | 目标先于检索、来源版本透传 | 全教材召回率/答案质量通过 |
| 真实页面联调 | 本项目任务内完成检索/澄清/继续/取消/恢复 | 11/14/100 全量能力完成 |
