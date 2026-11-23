# 保留上下文压缩与启动预热 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把上一轮已落地的 `model_turn` 压缩、宿主/worker 启动预热和计时日志固化为“不可回退”的迁移约束，并补上回归测试与真实服务冒烟。

**Architecture:** 不重写回答链路。压缩层继续留在 `native_history.py` 的读/写/启动三个入口；预热继续由 `warmup.py` 在 `start_server.py` / `worker.py` 启动时调用；计时继续留在 `native_executor.py` / `native_bridge.py`。本计划只补测试、让 host 计时可见、更新三份迁移文档，并增加一个真实服务冒烟脚本。

**Tech Stack:** Python 3.11、pytest、SQLite、FastAPI/uvicorn、stdlib `ast`/`urllib`。

**Spec:** `docs/superpowers/specs/2026-11-09-preserve-context-compaction-and-startup-warmup-design.md`

## Global Constraints

- 不修改 `project/vendor/DeepTutor`，不新增数据库 schema。
- 不做混合提交：`native_history.py`、`native_executor.py`、`native_bridge.py`、`worker.py`、`start_server.py` 和测试文件继续留在工作区；只允许提交三份迁移文档、本计划、spec 和新增冒烟脚本。
- 压缩阈值默认 `8000` 字符，环境变量 `HEART_MODEL_TURN_TOOL_MAX_CHARS` 可覆盖；非法值必须回退到 8000，不能让模块导入失败。
- 启动压缩是单向数据操作，只扫描 `.runtime/deeptutor/**/chat_history.db`；不触碰宿主 `ai_tutor*.db`、`learning_tasks`、`conversations`。
- 真实服务使用 8000 / 18001；本机探测必须禁用代理（`ProxyHandler({})`）。
- 不设固定耗时上限；长会话历史轮数增长会让 `start_turn` 回升，冒烟只记录、不硬断言。

## Review Focus

- 非法 `HEART_MODEL_TURN_TOOL_MAX_CHARS`（空串、字母、0）：模块仍可导入，阈值回退 8000；由 Task 1 的 `test_invalid_tool_max_chars_falls_back` 覆盖。
- 损坏或锁住的 `chat_history.db`：`compact_history_home` 跳过，不阻断 worker 启动；由 Task 1 的 `test_compact_history_home_ignores_bad_files` 覆盖。
- 未来重构把 `warm_host()` / `warm_worker()` 从启动文件删掉：AST 守卫立即失败；由 Task 2 覆盖。
- host `heart.native_timing` 在真实服务里不可见：logger 必须有 level 和 handler；由 Task 3 覆盖。
- 长会话继续增长被误判为“压缩失效”：文档和冒烟记录 `start_turn`，但不设固定上限；由 Task 4 / Task 5 覆盖。

---

### Task 1: 加固压缩阈值并补 SQLite 回归测试

**Files:**
- Modify: `project/integration/discrete-math-tutor/integrations/deeptutor/native_history.py`
- Test: `project/integration/discrete-math-tutor/tests/test_native_history_compaction.py`

**Interfaces:**
- Produces: `_tool_max_chars() -> int`，读取 `HEART_MODEL_TURN_TOOL_MAX_CHARS`，非法值返回 8000。
- Produces: `MODEL_TURN_TOOL_MAX_CHARS: int`，模块导入时由 `_tool_max_chars()` 赋值。
- Keeps: `compact_model_turn(metadata: dict) -> dict`、`compact_history_home(home: Path) -> int`。

- [ ] **Step 1: 写失败测试**

在 `tests/test_native_history_compaction.py` 追加：

```python
import json
import sqlite3

from integrations.deeptutor.native_history import (
    _tool_max_chars,
    compact_history_home,
    compact_model_turn,
)


def test_invalid_tool_max_chars_falls_back(monkeypatch):
    monkeypatch.setenv("HEART_MODEL_TURN_TOOL_MAX_CHARS", "not-a-number")
    assert _tool_max_chars() == 8000
    monkeypatch.setenv("HEART_MODEL_TURN_TOOL_MAX_CHARS", "0")
    assert _tool_max_chars() == 8000


def test_compact_history_home_rewrites_large_rows(tmp_path):
    db = tmp_path / "chat_history.db"
    large = {"model_turn": {"messages": [{"role": "tool", "content": "x" * 300000}]}}
    small = {"model_turn": {"messages": [{"role": "assistant", "content": "短回答"}]}}
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, metadata_json TEXT)")
        conn.execute("INSERT INTO messages VALUES (1, ?)", (json.dumps(large),))
        conn.execute("INSERT INTO messages VALUES (2, ?)", (json.dumps(small),))
    changed = compact_history_home(tmp_path)
    assert changed == 1
    with sqlite3.connect(db) as conn:
        rows = dict(conn.execute("SELECT id, length(metadata_json) FROM messages"))
    assert rows[1] < len(json.dumps(large))
    assert rows[2] == len(json.dumps(small))
    assert compact_history_home(tmp_path) == 0


def test_compact_history_home_ignores_bad_files(tmp_path):
    (tmp_path / "chat_history.db").write_text("not sqlite", encoding="utf-8")
    assert compact_history_home(tmp_path) == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
cd E:\项目\heart\project\integration\discrete-math-tutor
.\.venv-deeptutor\Scripts\python.exe -m pytest -q tests\test_native_history_compaction.py -p no:cacheprovider
```

Expected: FAIL，`cannot import name '_tool_max_chars'`。

- [ ] **Step 3: 实现 `_tool_max_chars` 并替换模块级阈值**

在 `native_history.py` 顶部把：

```python
MODEL_TURN_TOOL_MAX_CHARS = int(os.getenv("HEART_MODEL_TURN_TOOL_MAX_CHARS", "8000"))
```

替换为：

```python
def _tool_max_chars() -> int:
    try:
        value = int(os.getenv("HEART_MODEL_TURN_TOOL_MAX_CHARS", "8000"))
    except (TypeError, ValueError):
        return 8000
    return value if value > 0 else 8000


MODEL_TURN_TOOL_MAX_CHARS = _tool_max_chars()
```

- [ ] **Step 4: 运行测试确认通过**

Run: 同 Step 2。Expected: 5 passed（原有 2 个 + 新增 3 个）。

- [ ] **Step 5: 不提交**

Run: `git status --short -- project/integration/discrete-math-tutor/integrations/deeptutor/native_history.py project/integration/discrete-math-tutor/tests/test_native_history_compaction.py`

Expected: 两个文件仍为 `M`，不执行 `git add`。

---

### Task 2: 启动接线 AST 守卫

**Files:**
- Create: `project/integration/discrete-math-tutor/tests/test_startup_warmup_wiring.py`

**Interfaces:**
- Consumes: `scripts/start_server.py` 中的 `warm_host()` 调用。
- Consumes: `integrations/deeptutor/worker.py` 中的 `warm_worker()` 调用。
- Consumes: `integrations/deeptutor/warmup.py` 的 `warm_worker` 函数体调用 `compact_history_home`。
- Consumes: `integrations/deeptutor/native_history.py` 定义 `compact_model_turn`、`compact_history_home`。

- [ ] **Step 1: 写守卫测试**

创建 `tests/test_startup_warmup_wiring.py`：

```python
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _called_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            names.add(node.func.id)
    return names


def _function_calls(path: Path, function_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            names = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                    names.add(child.func.id)
            return names
    return set()


def test_start_server_calls_warm_host():
    assert "warm_host" in _called_names(ROOT / "scripts" / "start_server.py")


def test_worker_calls_warm_worker():
    assert "warm_worker" in _called_names(ROOT / "integrations" / "deeptutor" / "worker.py")


def test_warm_worker_compacts_history():
    calls = _function_calls(ROOT / "integrations" / "deeptutor" / "warmup.py", "warm_worker")
    assert "compact_history_home" in calls


def test_native_history_exposes_compaction():
    source = (ROOT / "integrations" / "deeptutor" / "native_history.py").read_text(encoding="utf-8")
    assert "def compact_model_turn" in source
    assert "def compact_history_home" in source
```

- [ ] **Step 2: 运行守卫**

Run:

```powershell
cd E:\项目\heart\project\integration\discrete-math-tutor
.\.venv-deeptutor\Scripts\python.exe -m pytest -q tests\test_startup_warmup_wiring.py -p no:cacheprovider
```

Expected: 4 passed。若任一失败，说明上一轮的接线被删除，修 `start_server.py` / `worker.py` / `warmup.py`，不要改测试断言。

- [ ] **Step 3: 不提交**

Run: `git status --short -- project/integration/discrete-math-tutor/tests/test_startup_warmup_wiring.py`

Expected: `??`，不执行 `git add`。

---

### Task 3: 让 host 计时 logger 在真实服务可见

**Files:**
- Modify: `project/integration/discrete-math-tutor/integrations/deeptutor/native_executor.py`
- Test: `project/integration/discrete-math-tutor/tests/test_native_history_compaction.py`（追加一个 logger 测试）

**Interfaces:**
- Produces: 模块级 `TIMING_LOGGER = logging.getLogger("heart.native_timing")`，level 为 `INFO`，至少一个 `StreamHandler`，`propagate=False`。
- `run()` 和 `_consume()` 使用 `TIMING_LOGGER`，不再每次 `getLogger`。

- [ ] **Step 1: 写失败测试**

在 `tests/test_native_history_compaction.py` 追加：

```python
import logging


def test_native_timing_logger_is_visible():
    import integrations.deeptutor.native_executor  # noqa: F401
    logger = logging.getLogger("heart.native_timing")
    assert logger.level == logging.INFO
    assert logger.handlers
    assert logger.propagate is False
```

- [ ] **Step 2: 运行确认失败**

Run:

```powershell
cd E:\项目\heart\project\integration\discrete-math-tutor
.\.venv-deeptutor\Scripts\python.exe -m pytest -q tests\test_native_history_compaction.py::test_native_timing_logger_is_visible -p no:cacheprovider
```

Expected: FAIL（level 不是 INFO 或没有 handler）。

- [ ] **Step 3: 在 `native_executor.py` 配置 logger**

在 import 之后、`_pending` 之前加入：

```python
TIMING_LOGGER = logging.getLogger("heart.native_timing")
TIMING_LOGGER.setLevel(logging.INFO)
if not TIMING_LOGGER.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
    TIMING_LOGGER.addHandler(handler)
TIMING_LOGGER.propagate = False
```

把 `run()` 里的 `timing = logging.getLogger("heart.native_timing")` 改为 `timing = TIMING_LOGGER`；把 `_consume()` 里的 `logging.getLogger("heart.native_timing").info(...)` 改为 `TIMING_LOGGER.info(...)`。

- [ ] **Step 4: 运行确认通过**

Run: 同 Step 2。Expected: PASS。再跑整个文件：5 + 1 = 6 passed。

- [ ] **Step 5: 不提交**

Run: `git status --short -- project/integration/discrete-math-tutor/integrations/deeptutor/native_executor.py`

Expected: `M`，不执行 `git add`。

---

### Task 4: 写进三份迁移文档

**Files:**
- Modify: `project/docs/research/2026-11-08-deeptutor-complete-runtime/NATIVE_132_IMPLEMENTATION_PLAN.md`
- Modify: `project/docs/research/2026-11-08-deeptutor-complete-runtime/NATIVE_132_TODO.md`
- Modify: `project/docs/research/2026-11-08-deeptutor-complete-runtime/NATIVE_IMPLEMENTATION_PROGRESS.md`

**Interfaces:**
- 主计划新增一节 `## 十二、性能与上下文保留约束（不可回退）`。
- TODO 新增 `- [ ] 0-G 保留上下文压缩、启动预热与计时（回归测试/文档约束）`。
- 进度文档新增 `### 性能保留项（2026-11-09）`。

- [ ] **Step 1: 主计划追加一节**

在 `NATIVE_132_IMPLEMENTATION_PLAN.md` 末尾追加：

```markdown
## 十二、性能与上下文保留约束（不可回退）

2026-11-09 实测长会话暴露：上游 `SQLiteSessionStore` 会把完整 `model_turn` 写进 `messages.metadata_json`，其中单条 `role=tool` 内容可达 497,438 字符，单条 metadata 616KB，下一轮 `ContextBuilder` 重新解析并发送 270,693 prompt tokens。

已实施且必须保留：

- `integrations/deeptutor/native_history.py`：`compact_model_turn`（读/写时截断 `role=tool` 到 `HEART_MODEL_TURN_TOOL_MAX_CHARS`，默认 8000）、`compact_history_home`（worker 启动时压缩已有 `chat_history.db`）。
- `integrations/deeptutor/warmup.py`：`warm_host` / `warm_worker`，由 `scripts/start_server.py` 与 `integrations/deeptutor/worker.py` 在启动时调用。
- 计时：宿主 `heart.native_timing`（必须 level=INFO 且有 handler）、worker `worker_native_start`。

修复后原 5 轮会话：`start_turn` 8.14s→1.23s，首个事件 17.54s→6.52s，浏览器 68.9–77.5s→30.2s，最大 prompt 270,693→62,834。会话继续增长后 `start_turn` 会回升到 7–10s；本约束只保证工具结果不膨胀，不承诺固定耗时上限。

阶段 1-C/3-C/2/5 修改 `main._run_turn`、`native_executor.py`、`native_bridge.py`、`teaching_prompt_adapter.py`、memory/context 来源时：

- 不得删除上述三个入口；
- 若 `model_turn` 结构变化，同步更新 `compact_model_turn` 的字段路径；
- 每次相关改动后运行 `tests/test_native_history_compaction.py` 与 `tests/test_startup_warmup_wiring.py`；
- 不得以“原生已接管上下文”为由移除压缩或预热，除非有新的等价机制和回归证据。
```

- [ ] **Step 2: TODO 加检查项**

在 `NATIVE_132_TODO.md` 的“已完成的计划准备”小节末尾追加：

```markdown
- [ ] 0-G 保留上下文压缩、启动预热与计时（回归测试/文档约束）
```

- [ ] **Step 3: 进度文档记录证据**

在 `NATIVE_IMPLEMENTATION_PROGRESS.md` 的“已实施”末尾追加：

```markdown
7. 上下文压缩/启动预热/计时已落地，作为后续阶段不可回退项。长会话 `start_turn` 8.14s→1.23s、首个事件 17.54s→6.52s；会话增长后 `start_turn` 回升到 7–10s，属于历史轮数增长，不是压缩失效。回归：`tests/test_native_history_compaction.py`、`tests/test_startup_warmup_wiring.py`。证据：`.runtime/pw-test-20261109/`、`worker.log` 的 `warmup worker_*` 与 `worker_native_start`。
```

- [ ] **Step 4: 校验文档**

Run:

```powershell
cd E:\项目\heart
Select-String -Path "project\docs\research\2026-11-08-deeptutor-complete-runtime\NATIVE_132_IMPLEMENTATION_PLAN.md","project\docs\research\2026-11-08-deeptutor-complete-runtime\NATIVE_132_TODO.md","project\docs\research\2026-11-08-deeptutor-complete-runtime\NATIVE_IMPLEMENTATION_PROGRESS.md" -Pattern '不可回退|compact_model_turn|compact_history_home|warm_host|warm_worker|heart.native_timing'
```

Expected: 三份文件都能匹配到对应关键词。

- [ ] **Step 5: 只提交三份文档**

```powershell
cd E:\项目\heart
git add -- project/docs/research/2026-11-08-deeptutor-complete-runtime/NATIVE_132_IMPLEMENTATION_PLAN.md project/docs/research/2026-11-08-deeptutor-complete-runtime/NATIVE_132_TODO.md project/docs/research/2026-11-08-deeptutor-complete-runtime/NATIVE_IMPLEMENTATION_PROGRESS.md
git commit -m "docs: 固化上下文压缩与启动预热保留约束"
```

---

### Task 5: 真实服务冒烟脚本

**Files:**
- Create: `project/integration/discrete-math-tutor/scripts/check_preservation_smoke.py`

**Interfaces:**
- CLI：`--base-url`、`--student-id`、`--session-id`、`--message`。
- 输出：每个阶段首行耗时 + `answer`/`done` 的状态；退出码 0 仅当 `done` 且 `answer_status=answered`。
- 使用 stdlib；`build_opener(ProxyHandler({}))` 禁用代理；不引入新依赖。

- [ ] **Step 1: 创建脚本**

```python
"""对已启动的 8000 服务做真实 SSE 冒烟；只读事件，不启动服务。"""
import argparse
import json
import time
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--student-id", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--message", required=True)
    args = parser.parse_args()

    payload = {
        "student_id": args.student_id,
        "session_id": args.session_id,
        "message": args.message,
        "account_type": "test",
        "request_id": "smoke-" + str(int(time.time())),
    }
    request = urllib.request.Request(
        args.base_url.rstrip("/") + "/api/chat/stream",
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    started = time.perf_counter()
    event = data = None
    last_stage = None
    answer_status = None
    done = False
    with opener.open(request, timeout=300) as response:
        for raw in response:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
            elif not line:
                if not event:
                    continue
                elapsed = round(time.perf_counter() - started, 2)
                try:
                    body = json.loads(data or "{}")
                except ValueError:
                    body = {}
                if event == "progress" and body.get("stage") and body["stage"] != last_stage:
                    last_stage = body["stage"]
                    print(f"{elapsed:7.2f}s stage={last_stage}")
                elif event in ("answer", "done", "error"):
                    answer_status = body.get("answer_status") or answer_status
                    print(f"{elapsed:7.2f}s {event} status={answer_status}")
                    done = event == "done"
                    if event in ("done", "error"):
                        break
                event = data = None
    return 0 if done and answer_status == "answered" else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 用新 session 跑**

```powershell
cd E:\项目\heart\project\integration\discrete-math-tutor
$sid = "smoke-" + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
.\.venv-runtime\Scripts\python.exe -B -X utf8 scripts\check_preservation_smoke.py `
  --student-id demo-b6ba6eba-8370-4657-9010-e9c1b59dd916 `
  --session-id $sid `
  --message "什么是自变量？请结合教材举一个例子。"
```

Expected: 输出 `stage=...`、`done status=answered`，退出码 0。

- [ ] **Step 3: 用已有长 session 跑**

```powershell
.\.venv-runtime\Scripts\python.exe -B -X utf8 scripts\check_preservation_smoke.py `
  --student-id demo-b6ba6eba-8370-4657-9010-e9c1b59dd916 `
  --session-id f6c21aad-8882-44e5-9ccb-e4f52b96f093 `
  --message "什么是自变量？请结合教材举一个例子。"
```

Expected: `done status=answered`，退出码 0；记录 `stage` 时间，不设上限。

- [ ] **Step 4: 检查日志**

```powershell
Select-String -Path "E:\项目\heart\.runtime\pw-test-20261109\server.err.log","E:\项目\heart\project\integration\discrete-math-tutor\.runtime\deeptutor\worker.log" -Pattern 'heart.native_timing|worker_native_start|warmup worker_|warmup host_'
```

Expected: host `heart.native_timing` 出现（Task 3 后）；worker `worker_native_start` 与 `warmup worker_*` 出现。

- [ ] **Step 5: 提交脚本**

```powershell
cd E:\项目\heart
git add -- project/integration/discrete-math-tutor/scripts/check_preservation_smoke.py
git commit -m "test: add real-service preservation smoke probe"
```

---

### Task 6: 最终验证与交付说明

**Files:**
- No code changes.

- [ ] **Step 1: 跑新增与相关测试**

```powershell
cd E:\项目\heart\project\integration\discrete-math-tutor
.\.venv-deeptutor\Scripts\python.exe -m pytest -q tests\test_native_history_compaction.py tests\test_startup_warmup_wiring.py -p no:cacheprovider
.\.venv-deeptutor\Scripts\python.exe -m pytest -q tests\test_deeptutor_native_runtime.py tests\test_conversation_context.py tests\test_unified_context_chain.py -p no:cacheprovider
```

Expected: 新增测试全过；既有 61 个相关测试全过。

- [ ] **Step 2: 确认工作区没有混合提交**

```powershell
cd E:\项目\heart
git status --short -- project/integration/discrete-math-tutor/integrations/deeptutor/native_history.py project/integration/discrete-math-tutor/integrations/deeptutor/native_executor.py project/integration/discrete-math-tutor/integrations/deeptutor/native_bridge.py project/integration/discrete-math-tutor/integrations/deeptutor/worker.py project/integration/discrete-math-tutor/scripts/start_server.py project/integration/discrete-math-tutor/tests/test_native_history_compaction.py project/integration/discrete-math-tutor/tests/test_startup_warmup_wiring.py
```

Expected: 代码/测试仍为 `M` / `??`；只有三份迁移文档和冒烟脚本被提交。

- [ ] **Step 3: 记录结果**

在最终回复里报告：

- 新增测试通过数量；
- 真实服务新/长 session 的 `stage=...`、`done status=answered`；
- host/worker 计时日志是否可见；
- 明确说明代码/测试仍未提交，后续需要时按 hunk 拆分。

---

## Self-Review

- Spec coverage：压缩（Task 1）、预热/接线守卫（Task 2）、host 计时可见（Task 3）、三份迁移文档（Task 4）、真实服务冒烟（Task 5）、验收（Task 6）均有任务。
- 类型/命名一致性：`_tool_max_chars`、`MODEL_TURN_TOOL_MAX_CHARS`、`compact_model_turn`、`compact_history_home`、`TIMING_LOGGER` 在任务间一致。
- Review Focus 的五项分别落在 Task 1（非法 env、坏 DB）、Task 2（接线被删）、Task 3（host 计时不可见）、Task 4/5（长会话增长不设上限）。
- 比例：计划只给测试断言、签名和文档要点，不复制实现体。
