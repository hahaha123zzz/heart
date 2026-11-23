# 保留上下文压缩与启动预热设计

日期：2026-11-09
状态：已批准（待实现计划）
范围：保留上一轮的性能修复，不改变回答链路业务行为，不修改 `vendor/DeepTutor`，不做混合提交。

## 1. 背景与证据

新版 native 链路的长会话暴露了一个真实问题：上游 `SQLiteSessionStore` 把完整 `model_turn` 写进 `messages.metadata_json`，其中包含超长工具结果；下一轮 `ContextBuilder` 又把它读回来、解析并发送给模型。

实测（`turn_1794205441230_649fa3af70` 等新链路回合）：

| 指标 | 数值 |
|---|---:|
| 单条 assistant `metadata_json` | 616KB |
| 其中 `model_turn.messages` | 588KB |
| 单条 `role=tool` 内容 | 497,438 字符 |
| 最大 prompt tokens | 270,693 |
| worker `start_turn` | 8.14s |
| 宿主 `native_start` | 16.02s |
| 原生首个事件 | 17.54s |
| 浏览器点击→完成 | 68.9–77.5s |

上一轮已实施三项修复：

1. `native_history.py`：读写和启动时压缩超长工具结果；
2. `warmup.py`：宿主/worker 启动预热；
3. `native_executor.py` / `native_bridge.py`：分段计时日志。

修复后同一长会话：

| 指标 | 数值 |
|---|---:|
| worker `start_turn` | 1.23s |
| 宿主 `native_start` | 1.56s |
| 原生首个事件 | 6.52s |
| 浏览器点击→完成 | 30.2s |
| 最大 prompt tokens | 62,834 |
| 单条 metadata | 62–95KB |

上表是压缩后原 5 轮会话、worker 已热时的测量；同一 session 继续增长后，`start_turn` 会随历史轮数回升，见 1.1。

### 1.1 真实服务检测（2026-11-09 20:36–20:44）

服务 8000 / worker 18001 启动成功，启动预热可见：

```
warmup host_llm_client 4.08s
warmup host_pdf_documents 0.02s
warmup host_inference_runtime 0.00s
启动阶段：宿主客户端预热完成（累计 15.6s）
warmup worker_llm_client 0.00s
warmup worker_tool_registry 0.75s
warmup worker_prompt_manager 0.00s
warmup worker_compact_history 0.03s
```

真实 SSE 提问结果（同一问题，`什么是自变量？`）：

| 场景 | 点击→完成 | worker `start_turn` | 首个阶段 |
|---|---:|---:|---:|
| 新 session（直接 SSE，未先走 catalog/bind） | 54.6s | 11.8s | 30.1s |
| 长 session 第 1 次 | 62.4s | 10.2s | 37.0s |
| 长 session 第 2 次（间隔 10s） | 78.1s | 7.0s | 49.7s |

结论：

- 压缩解决了 497KB 单条工具结果，但没有限制**历史轮数和 `model_turn` 条数**；长会话增长后 `start_turn` 仍会到 7–10s，`ContextBuilder` 首次阶段仍可能 30–50s。
- 新 session 直接走 SSE 时，`start_turn` 还包含首次 native session 创建/course 绑定成本；浏览器先走 catalog/bind 时这部分会提前发生。
- 本次真实服务里 host `heart.native_timing` 没有出现在日志中（logger 级别/处理器未生效）；worker `worker_native_start` 可见。实现时必须把 host 计时 logger 提到 INFO 或改用已有 INFO logger，否则“保留计时”只是代码在、日志看不到。
- 本计划只承诺“工具结果不再膨胀”和“启动预热可观测”，不承诺长会话固定耗时；历史轮数上限/摘要缓存不在本计划范围。

风险：`NATIVE_132_IMPLEMENTATION_PLAN.md` 的阶段 1-C/3-C/2 会继续改 `main._run_turn`、`native_executor.py`、`native_bridge.py`、`teaching_prompt_adapter.py` 等文件；如果没有文档约束和回归测试，这些修复可能在后续迁移中被静默删除。

## 2. 目标与非目标

### 目标

- 保留 `model_turn` 工具结果压缩（读、写、启动三个入口）。
- 保留宿主/worker 启动预热。
- 保留 host `heart.native_timing` 和 worker `worker_native_start` 计时日志。
- 用三份迁移文档和回归测试防止后续阶段移除上述能力。

### 非目标

- 不拆分 admit/execute（上游 `request_preparer.py` 已用 `asyncio.create_task(_run_turn)`）。
- 不调整 `explore_context.max_tokens`，不实现“简单题跳过 explorer”。
- 不新增 `UnifiedContext` 缓存，不做打开会话预热。
- 不解决历史轮数增长导致的 `start_turn` 变慢；不做 history cap / summary cache（后续单独评估）。
- 不修改 `project/vendor/DeepTutor`，不改数据库 schema。
- 不做混合文件提交。

## 3. 设计

### 3.1 上下文压缩层

文件：`project/integration/discrete-math-tutor/integrations/deeptutor/native_history.py`

- `compact_model_turn(metadata)`：
  - 只处理 `metadata["model_turn"]["messages"]` 中 `role == "tool"` 的消息；
  - 内容长度超过 `HEART_MODEL_TURN_TOOL_MAX_CHARS`（默认 8000）时截断，并追加 `[heart: 工具结果已截断，需要时重新读取原文]`；
  - 不修改 user/assistant 消息。
- `compact_history_home(home)`：
  - 递归扫描 `home` 下所有 `chat_history.db`；
  - 只处理 `length(metadata_json) > 200000` 的消息行；
  - 解析、压缩、仅在变小时写回；
  - 每个库 `sqlite3.connect(..., timeout=2)`；捕获 `OSError/sqlite3.Error` 后跳过；
  - 返回修改行数；幂等。
- `get_messages_for_context()` 包装：
  - 保留原有题卡历史恢复逻辑；
  - 对返回的每一行 metadata 调用 `compact_model_turn`，防止旧数据未压缩时再次膨胀。
- `add_message()` 包装：
  - 在调用原 `SQLiteSessionStore.add_message` 前压缩 `metadata`，保证新写入不再膨胀。

### 3.2 启动预热

文件：`project/integration/discrete-math-tutor/integrations/deeptutor/warmup.py`

- `warm_host()`：
  - `LLMClient()._client_lazy()`；
  - `knowledge.pdf_reader.documents()`；
  - `knowledge.inference_runtime.runtime_status()`。
- `warm_worker()`：
  - `deeptutor.services.llm.get_llm_client()`；
  - `deeptutor.runtime.registry.tool_registry.get_tool_registry()`；
  - `deeptutor.services.prompt.manager.get_prompt_manager()`；
  - 导入 `deeptutor.agents.chat.capability`、`deeptutor.agents.loop.pipeline`、`deeptutor.services.session.context_builder`；
  - 读取 `DEEPTUTOR_HOME`，调用 `compact_history_home(Path(home))`。
- 每个阶段用 `_run(name, fn)` 包裹：成功打印 `warmup <name> <seconds>s`，失败打印 `warmup <name> failed: <error>`，不阻断服务启动。

接线：

- `scripts/start_server.py`：模型预热完成后调用 `warm_host()`，并打印“宿主客户端预热完成（累计 ...s）”。
- `integrations/deeptutor/worker.py`：`install_native_bridge` / `warm_retrieval` 之后、`uvicorn.run` 之前调用 `warm_worker()`。

### 3.3 计时日志

- 宿主：`native_executor.py` 使用 `logging.getLogger("heart.native_timing")`，记录 `account_expire`、`resolve_resources`、`memory_epoch`、`claim`、`save_executing`、`prepare_selection`、`native_start`、`checkpoint_after_start`、`first_event`。
- worker：`native_bridge.py` 的 `start` 使用 `print(..., flush=True)` 记录 `worker_native_start` 的 `authorize`、`account`、`bind`、`start_turn`、`before_status`、`status`。
- 两边都保留，作为后续性能排查的固定诊断；不参与业务判断。
- host 计时必须可观测：实现时对 `heart.native_timing` 设置 `setLevel(logging.INFO)`，或在 `main.py` 的 logging 配置中显式启用；本次真实服务检测中发现它默认不可见。

### 3.4 迁移文档改动

1. `project/docs/research/2026-11-08-deeptutor-complete-runtime/NATIVE_132_IMPLEMENTATION_PLAN.md`
   - 新增“性能与上下文保留约束（不可回退）”一节；
   - 记录 497KB/616KB/270,693 prompt 与压缩后的 62KB/62,834 prompt；
   - 明确阶段 1-C/3-C/2/5 修改 `native_executor.py`、`native_bridge.py`、`teaching_prompt_adapter.py`、memory/context 来源时，不得删除压缩、预热、计时；
   - 若更换 context/memory 来源，必须保留 `model_turn` 压缩并重跑回归。
2. `project/docs/research/2026-11-08-deeptutor-complete-runtime/NATIVE_132_TODO.md`
   - 新增“0-G 保留上下文压缩、启动预热与计时”检查项。
3. `project/docs/research/2026-11-08-deeptutor-complete-runtime/NATIVE_IMPLEMENTATION_PROGRESS.md`
   - 记录“已实施/需保留”，附 before/after 指标、测试文件名、证据路径。

### 3.5 本 spec

文件：`docs/superpowers/specs/2026-11-09-preserve-context-compaction-and-startup-warmup-design.md`

## 4. 数据与迁移

- 启动压缩是单向操作：本地 `.runtime/deeptutor/**/chat_history.db` 中超长 `role=tool` 内容会被截到 8k 字符；截断后原文不可从该 DB 恢复。
- 只影响原生 SessionStore 的 assistant message metadata；不修改宿主 `ai_tutor*.db`、`learning_tasks`、`conversations`。
- 无 schema 变更；重复执行幂等。
- 阈值由 `HEART_MODEL_TURN_TOOL_MAX_CHARS` 控制，默认 8000。
- 启动成本：当前 demo 数据实测 `worker_compact_history 0.06s`；每个 DB 锁超时 2s，失败只告警。
- 如需回滚压缩行为：停止 worker 后恢复 `chat_history.db` 快照；本次不自动备份。

## 5. 回归测试

### 5.1 压缩测试

文件：`project/integration/discrete-math-tutor/tests/test_native_history_compaction.py`

保留现有：

- `test_compacts_oversized_tool_result`
- `test_leaves_small_metadata_untouched`

新增：

- `test_compact_history_home_rewrites_large_rows`：
  - 用 `tmp_path` 创建 `chat_history.db`，建 `messages(id, metadata_json)`；
  - 插入 >200KB 的 `model_turn`（含超长 tool 内容）和一条小 metadata；
  - 调用 `compact_history_home(tmp_path)`；
  - 断言大行变小、包含截断标记、小行不变、返回值 >= 1。
- `test_compact_history_home_ignores_bad_files`：
  - 目录中放一个非 SQLite 文件或损坏 DB；
  - 断言不抛异常并返回 0。

### 5.2 启动接线守卫

文件：`project/integration/discrete-math-tutor/tests/test_startup_warmup_wiring.py`

用 `ast` 解析源码，不启动服务：

- `scripts/start_server.py` 中存在 `warm_host()` 调用；
- `integrations/deeptutor/worker.py` 中存在 `warm_worker()` 调用；
- `integrations/deeptutor/warmup.py` 的 `warm_worker` 函数内存在 `compact_history_home` 调用；
- `native_history.py` 中存在 `compact_model_turn`、`compact_history_home` 定义。

### 5.3 运行方式

```powershell
cd E:\项目\heart\project\integration\discrete-math-tutor
.\.venv-deeptutor\Scripts\python.exe -m pytest -q tests\test_native_history_compaction.py tests\test_startup_warmup_wiring.py -p no:cacheprovider
.\.venv-deeptutor\Scripts\python.exe -m pytest -q tests\test_deeptutor_native_runtime.py tests\test_conversation_context.py tests\test_unified_context_chain.py -p no:cacheprovider
```

## 6. 验收标准

- 新增压缩/接线测试通过；现有 61 个相关测试通过。
- 三份迁移文档可 grep 到“不可回退”、`compact_model_turn`、`compact_history_home`、`warm_host`、`warm_worker`、`heart.native_timing`。
- 不修改 `project/vendor/DeepTutor`；不新增 schema；不做混合提交。
- 手工抽 1–2 个引用/归属类回答，确认截断后仍能引用教材原文。
- 真实服务冒烟（手工，不放进默认 pytest）：
  - 启动 8000 / 18001，确认 `warmup host_*`、`warmup worker_*`、`worker_compact_history` 日志存在；
  - 新 session 和长 session 各发一个真实问题，确认 `answer_status=answered`；
  - 确认 host `heart.native_timing` 和 worker `worker_native_start` 都能看到；
  - 只记录 `start_turn` / 首个阶段耗时，不设固定上限（历史轮数会增长）。
- 历史参考值（不作为硬断言）：原始 5 轮会话压缩后 `start_turn` 约 1.2s；长会话增长后实测 7–10s。

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 截断丢失细节 | 阈值可调；模型可重新 `read_source`；引用类抽样验收 |
| 启动压缩改本地历史 | 幂等、best-effort、2s 锁超时；文档注明单向；需要时先备份 DB |
| worker 父/子进程重复预热 | 当前只增加 1–5s 启动时间；后续可加进程级去重 |
| 代码仍未提交 | 文档+测试降低被删风险；后续需要时按 hunk 拆分提交 |
| AST 守卫在重构后失效 | 同步更新测试；守卫只检查接线，不替代运行时验收 |
| 阶段 3 更换 memory/context 来源 | 文档要求保留压缩并重跑回归；若 context 结构变化，更新 `compact_model_turn` 的字段路径 |
| 长会话历史轮数增长 | 压缩只限单条工具结果，`start_turn` 仍随轮数增长；本计划不承诺固定上限，后续单独做 history cap / summary cache |

## 8. 参考

- `project/docs/research/2026-11-08-deeptutor-complete-runtime/NATIVE_132_IMPLEMENTATION_PLAN.md`
- `project/docs/research/2026-11-08-deeptutor-complete-runtime/NATIVE_132_TODO.md`
- `project/docs/research/2026-11-08-deeptutor-complete-runtime/NATIVE_IMPLEMENTATION_PROGRESS.md`
- `D:\deeptutor\ARCHITECTURE.html`
- `D:\deeptutor\.ua\knowledge-graph.json`
- `D:\deeptutor\deeptutor\services\session\turns\request_preparer.py`（第 890 行 `asyncio.create_task`）
- `D:\deeptutor\deeptutor\services\session\turns\executor.py`（`ContextBuilder.build`）
- `D:\deeptutor\deeptutor\capabilities\explore_context\explorer.py`
- `D:\deeptutor\deeptutor\capabilities\mastery\loop.py`（mastery 不使用 explore_context 的设计说明）
