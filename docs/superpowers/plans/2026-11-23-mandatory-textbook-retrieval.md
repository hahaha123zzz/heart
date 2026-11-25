# 强制教材检索实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 课程类提问的第一轮必须先用阅读工具读教材原文；非课程提问不检索。回答依据、角标与高亮都走工具结果，不再创建笔记本。

**Architecture:** 复用上游已有的"首轮强制工具"机制（`AgenticLoopPipeline.initial_tool_choice`，`deeptutor/agents/loop/agent_loop.py:1097` 会把工具名转成 `tool_choice`，工具不在本轮清单时自动退回 `auto`）。宿主在自己的 `tool_policy.compose` 钩子里，对课程问题设置首轮工具：有阅读位置时用 `read_material`，否则用 `rag`。`rag` 已返回已核验原文和 `#dt-material-…-locator-<页>?quote=…` 链接，因此角标可点、可跳页、可高亮。

**Tech Stack:** Python / pytest；宿主集成层 `integrations/deeptutor/`；不改前端、不改原生契约字段。

**Spec:** 本计划即规格。上一条链路诊断见 `docs/superpowers/plans/2026-11-23-separate-textbook-reading-from-screenshot-intake.md` 的验收记录；旧链路"先检索后作答"证据见 `agents/agent_loop_service.py:117-148`。

## 问题与判据

日志证据：`自变量是什么` 一轮 414 个事件、`tool_call` 为 0，回答 247 字无角标；同账号几分钟前的概念题却调用了 `rag`。检索能力正常，是原生链路把检索变成可选工具。

验收判据：

1. 课程类提问（概念、教材内容、复习相关）在第一轮必然出现 `rag`（或阅读器打开时的 `read_material`）调用；非课程提问（时间、身份、界面操作、问候）不出现教材工具。
2. 回答引用教材时角标可点击，页码等于证据页，点击后能高亮原文（沿用现有 `citation-target` 链路）。
3. 工具返回"没有匹配原文"时，回答先说明本轮没有检索到教材依据，再用通用知识回答并标注为通识解释。
4. 首轮强制失败（工具不可用、供应商拒绝 `tool_choice`）不得阻断回合，退回模型自选工具。
5. 不创建任何笔记本，不改 `NativeTurnStart` 字段。

## Global Constraints

- 复用上游机制，不新增原生接口字段；仅改宿主侧钩子与提示词。
- 强制只在第一轮生效；后续轮次由模型自选。
- 若 `capability` 已经设置过首轮工具（如 `ask_questions` 的 `ask_user`），不得覆盖。
- 工具不在本轮 schema 时不得报错；上游会自动退回 `auto`。
- 中文与英文提示词同步改动，语义一致。
- 检索/工具异常不得阻断回合。

## Review Focus

- **闲聊与系统类提问**（"今天几号"、"你是谁"）：不强制工具、不出现教材依据提示，正常回答。
- **阅读器打开时提问**：首选 `read_material` 读当前页，而不是跨库 `rag`，避免答非当前页。
- **工具返回空结果**：回答要先声明"没有检索到教材依据"，再用通用知识兜底，不能拒答也不能假装引用。
- **供应商拒绝强制工具**：`openai_compat_provider` 会退回 `tool_choice=required`；再失败时回合仍要给答案。
- **一轮内模型重复检索**：第一轮已读过原文，后续重复调用只允许一次，不得死循环（循环自身有轮次上限，验收时观察）。
- **首轮延迟**：多一次模型往返与一次检索，预热后单轮额外耗时要可测量。

---

### Task 1: 抽出可复用的教材证据函数

**Files:**
- Modify: `project/integration/discrete-math-tutor/integrations/deeptutor/heart_rag.py`
- Test: `project/integration/discrete-math-tutor/tests/test_heart_rag_citations.py`

**Interfaces:**
- Produces: `course_evidence(query: str, limit: int = 3) -> list[dict]`（同步）。元素是 `prepare_retrieval` 的 source 字典，额外带 `reader_citation`；无法核验或无法生成角标的条目被丢弃；检索异常返回 `[]`。
- `HeartCourseRagTool.execute` 改为复用该函数。

- [ ] **Step 1: 写失败测试**

```python
def test_course_evidence_keeps_only_linked_sources_and_respects_limit(monkeypatch):
    from integrations.deeptutor import heart_rag
    monkeypatch.setattr(heart_rag, "_retrieve_rows", lambda query: [object(), object(), object()])
    monkeypatch.setattr(heart_rag, "_authorized_course_rows", lambda rows: rows)
    monkeypatch.setattr(heart_rag, "prepare_retrieval", lambda *_: [
        {"chapter_id": 1, "page": None, "section_id": 1, "document_id": "d", "version": "a" * 64,
         "text": "原文一", "quote": "原文一", "location": {"evidence": {"rects": [{"page": 7}]}}},
        {"chapter_id": 1, "page": None, "section_id": 1, "document_id": "d2", "version": "b" * 64,
         "text": "原文二", "quote": "原文二", "location": {"evidence": {"rects": []}}},
        {"chapter_id": 1, "page": None, "section_id": 1, "document_id": "d3", "version": "c" * 64,
         "text": "原文三", "quote": "原文三", "location": {"evidence": {"rects": [{"page": 9}]}}},
    ], raising=False)
    monkeypatch.setattr(heart_rag, "_reader_citation",
                        lambda source: "[教材](#dt-material-x-revision-1-locator-7)"
                        if source["text"] != "原文二" else "")
    assert [item["text"] for item in heart_rag.course_evidence("自变量是什么", limit=3)] == ["原文一", "原文三"]
    assert len(heart_rag.course_evidence("自变量是什么", limit=1)) == 1


def test_course_evidence_degrades_to_empty_on_retrieval_error(monkeypatch):
    from integrations.deeptutor import heart_rag
    def boom(query):
        raise RuntimeError("index down")
    monkeypatch.setattr(heart_rag, "_retrieve_rows", boom)
    assert heart_rag.course_evidence("自变量是什么") == []
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_heart_rag_citations.py -q`
Expected: FAIL，`course_evidence` / `_retrieve_rows` 不存在。

- [ ] **Step 3: 实现**

```python
def _retrieve_rows(query: str) -> list:
    from knowledge import psychology_retrieval
    return psychology_retrieval.retrieve(query, [], limit=40)


def course_evidence(query: str, limit: int = 3) -> list[dict]:
    """已授权、已核验、带精确角标的教材证据；失败返回空列表。"""
    try:
        rows = _retrieve_rows(query)
    except Exception:
        logger.warning("course evidence retrieval failed", exc_info=True)
        return []
    rows = _authorized_course_rows(rows)[:max(limit * 4, limit)]
    if not rows:
        return []
    try:
        from .native_grounding import prepare_retrieval
        sources = prepare_retrieval(query, rows, None, "实验心理学")
    except Exception:
        logger.warning("course evidence verification failed", exc_info=True)
        return []
    evidence = []
    for source in sources:
        citation = _reader_citation(source)
        if not citation:
            continue
        source["reader_citation"] = citation
        evidence.append(source)
    return evidence[:limit]
```

`HeartCourseRagTool.execute` 调 `await asyncio.to_thread(course_evidence, query, limit)`。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_heart_rag_citations.py -q`
Expected: PASS（含既有用例）。

- [ ] **Step 5: 提交**

```bash
git add project/integration/discrete-math-tutor/integrations/deeptutor/heart_rag.py project/integration/discrete-math-tutor/tests/test_heart_rag_citations.py
git commit -m "refactor: 抽出可复用的教材证据函数"
```

### Task 2: 课程问题判定

**Files:**
- Create: `project/integration/discrete-math-tutor/integrations/deeptutor/course_scope.py`
- Test: `project/integration/discrete-math-tutor/tests/test_course_scope.py`

**Interfaces:**
- Produces: `is_course_question(message: str) -> bool`。命中课程线索（教材/课本/第X章/定义/概念/实验/自变量…）返回 `True`；命中系统类负向类别（时间日期、身份与模型、界面与账号操作、纯问候）返回 `False`；其余默认 `True`。顺序固定：先课程线索，再负向类别。

- [ ] **Step 1: 写失败测试**

```python
import pytest

from integrations.deeptutor.course_scope import is_course_question


@pytest.mark.parametrize('message', [
    '今天几号', '现在几点', '你是谁', '你是什么模型', '怎么导出笔记', '登录密码忘了怎么办', '你好', 'hi',
])
def test_system_or_chitchat_messages_do_not_retrieve(message):
    assert is_course_question(message) is False


@pytest.mark.parametrize('message', [
    '自变量是什么', '什么是准实验设计', '第3章讲了什么', '教材里怎么定义信度', '为什么今天上课讲的那个实验要控制额外变量',
])
def test_course_messages_retrieve(message):
    assert is_course_question(message) is True
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_course_scope.py -q`
Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现**

正则表两段：`COURSE_HINTS`（命中即 True）与 `SYSTEM_PATTERNS`（命中即 False），函数按顺序判断后默认 True；纯空白返回 False。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_course_scope.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add project/integration/discrete-math-tutor/integrations/deeptutor/course_scope.py project/integration/discrete-math-tutor/tests/test_course_scope.py
git commit -m "feat: 判定课程问题"
```

### Task 3: 首轮强制教材工具

**Files:**
- Modify: `project/integration/discrete-math-tutor/integrations/deeptutor/tool_policy.py:96-112`
- Test: `project/integration/discrete-math-tutor/tests/test_tool_policy_course_first.py`（新建）

**Interfaces:**
- Produces: `preferred_first_tool(context) -> str | None`：
  - `context.reading_viewport` 有 `locator` 时返回 `"read_material"`；
  - 否则课程问题返回 `"rag"`；
  - 非课程问题返回 `None`。
- `tool_policy.compose` 在 `pipeline.initial_tool_choice` 为空且该工具在当前 `names` 里时设置它。

- [ ] **Step 1: 写失败测试**

```python
from types import SimpleNamespace

from integrations.deeptutor import tool_policy


def _context(message, locator=None):
    viewport = SimpleNamespace(locator=locator) if locator is not None else None
    return SimpleNamespace(user_message=message, reading_viewport=viewport)


def test_reading_viewport_uses_read_material_first():
    assert tool_policy.preferred_first_tool(_context('这段什么意思', locator=7)) == 'read_material'


def test_course_question_uses_rag_first():
    assert tool_policy.preferred_first_tool(_context('自变量是什么')) == 'rag'


def test_system_question_forces_nothing():
    assert tool_policy.preferred_first_tool(_context('今天几号')) is None
```

再加一条 compose 行为测试（用真实 `AgenticLoopPipeline` 实例较慢时，用 `SimpleNamespace` 模拟 `pipeline`）：

```python
def test_compose_sets_first_tool_only_when_unset(monkeypatch):
    import integrations.deeptutor.tool_policy as policy
    pipeline = SimpleNamespace(initial_tool_choice=None,
                               tool_lookup={'rag': object(), 'kb_files': object()},
                               _exclusive_capability_active=lambda context: False)
    names = policy.compose(pipeline, _context('自变量是什么'))
    assert 'rag' in names and pipeline.initial_tool_choice == 'rag'
    pipeline.initial_tool_choice = 'ask_user'
    policy.compose(pipeline, _context('自变量是什么'))
    assert pipeline.initial_tool_choice == 'ask_user'
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_tool_policy_course_first.py -q`
Expected: FAIL，`preferred_first_tool` 不存在。

- [ ] **Step 3: 实现**

```python
def preferred_first_tool(context):
    if getattr(context, 'reading_viewport', None) is not None:
        return 'read_material'
    message = str(getattr(context, 'user_message', '') or '')
    from .course_scope import is_course_question
    return 'rag' if is_course_question(message) else None
```

`compose` 末尾追加：

```python
if active_scope() and not pipeline.initial_tool_choice:
    choice = preferred_first_tool(context)
    if choice and choice in names:
        pipeline.initial_tool_choice = choice
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_tool_policy_course_first.py tests/test_course_scope.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add project/integration/discrete-math-tutor/integrations/deeptutor/tool_policy.py project/integration/discrete-math-tutor/tests/test_tool_policy_course_first.py
git commit -m "feat: 课程问题首轮强制读取教材"
```

### Task 4: 提示词与降级

**Files:**
- Modify: `project/vendor/DeepTutor/deeptutor/agents/chat/prompts/zh/agentic_chat.yaml`
- Modify: `project/vendor/DeepTutor/deeptutor/agents/chat/prompts/en/agentic_chat.yaml`
- Test: `project/integration/discrete-math-tutor/tests/test_course_grounding_prompt.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / 'vendor/DeepTutor/deeptutor/agents/chat/prompts'

def test_chat_prompts_require_textbook_first_and_disclose_missing_evidence():
    zh = (ROOT / 'zh/agentic_chat.yaml').read_text(encoding='utf-8')
    en = (ROOT / 'en/agentic_chat.yaml').read_text(encoding='utf-8')
    assert '先检索教材' in zh and '没有检索到教材依据' in zh and '通识解释' in zh
    assert 'search the textbook first' in en
    assert 'no textbook evidence was retrieved' in en and 'general-knowledge' in en
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_course_grounding_prompt.py -q`
Expected: FAIL。

- [ ] **Step 3: 实现**

中文 `runtime_policy` 追加：

```yaml
  课程问题必须先检索教材再作答：工具已给出已核验原文时据其作答，并原样保留来源里的教材角标链接。
  如果本轮没有检索到教材依据，先用一句话说明“本轮没有检索到教材依据”，再用你自己的知识回答并标为通识解释。
  不得声称教材说过你没读到的内容；同一轮已读过的原文不要反复检索。
```

英文写同义表达，含 `search the textbook first`、`no textbook evidence was retrieved`、`general-knowledge`。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_course_grounding_prompt.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add project/vendor/DeepTutor/deeptutor/agents/chat/prompts/zh/agentic_chat.yaml project/vendor/DeepTutor/deeptutor/agents/chat/prompts/en/agentic_chat.yaml project/integration/discrete-math-tutor/tests/test_course_grounding_prompt.py
git commit -m "feat: 提示词要求先检索教材并声明无依据"
```

### Task 5: 预热与端到端验收

**Files:**
- Modify: `project/integration/discrete-math-tutor/integrations/deeptutor/heart_rag.py`（新增 `warm_course_retrieval`）
- Modify: `project/integration/discrete-math-tutor/integrations/deeptutor/runtime_config.py:17-56`
- Test: `project/integration/discrete-math-tutor/tests/test_heart_rag_citations.py`

**Interfaces:**
- Produces: `warm_course_retrieval() -> None`，异常只记日志。
- `native_lifespan` 启动时用 `asyncio.create_task(asyncio.to_thread(warm_course_retrieval))` 后台预热，不 await。

- [ ] **Step 1: 写失败测试**

```python
def test_warm_course_retrieval_swallows_errors(monkeypatch):
    from integrations.deeptutor import heart_rag
    monkeypatch.setattr(heart_rag, "_retrieve_rows", lambda query: (_ for _ in ()).throw(RuntimeError('cold')))
    heart_rag.warm_course_retrieval()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_heart_rag_citations.py -q`
Expected: FAIL，函数不存在。

- [ ] **Step 3: 实现预热**

```python
def warm_course_retrieval() -> None:
    try:
        _retrieve_rows("自变量和因变量")
    except Exception:
        logger.warning("course retrieval warmup failed", exc_info=True)
```

在 `native_lifespan` 的 `yield` 前插入后台任务（异常吞掉）。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_heart_rag_citations.py tests/test_course_scope.py tests/test_tool_policy_course_first.py tests/test_course_grounding_prompt.py -q`
Expected: PASS。

- [ ] **Step 5: 端到端验收（本机 8000）**

按既有流程生成候选发行（bundle → 复制 `.next` → verify → select → restart，失败回退上一版），浏览器验证：

- 问 `自变量是什么`：`turn_events` 中出现 `rag` 调用；回答带 `dt-material` 角标；点击后 `citation-target` 返回 200、页码与角标一致、页内出现 `.Highlight__part`。
- 问 `今天几号`：无教材工具调用，正常回答。
- 问一个教材确实没讲的问题：首句说明"本轮没有检索到教材依据"，随后通识兜底。
- 记录首轮额外耗时（工具往返 + 检索），预热后应在可接受区间。

- [ ] **Step 6: 提交并记录**

```bash
git add project/integration/discrete-math-tutor/integrations/deeptutor/heart_rag.py project/integration/discrete-math-tutor/integrations/deeptutor/runtime_config.py project/integration/discrete-math-tutor/tests/test_heart_rag_citations.py
git commit -m "feat: 宿主启动预热教材检索"
```

把浏览器结果补进 `docs/superpowers/plans/2026-11-23-separate-textbook-reading-from-screenshot-intake.md` 的验收记录。

---

## 回退

任一关键验收失败：`deploy/student_release.py select` 切回上一版发行并重启本机服务；源码改动保留但不发布。

## 验收记录（2026-11-24）

- 发行：`textbook-first-v3-20261124`（上一版 `textbook-first-v2-20261124`，更早的 `textbook-rag-citations-20261123` 亦可回退）。
- 定向测试 34 项通过：教材证据、课程判定、首轮强制工具、提示词约束；`test_native_tool_policy` 的 rag→read_source 链路保持通过。
- 本机 8000 浏览器：
  - 问 `自变量是什么`（纯聊天页、未开阅读器）：本轮出现 `rag` 工具调用，回答带 1 个 `dt-material` 角标，点击后 `citation-target` 返回 200，跳到第 2 章第 9 页并出现原文高亮。
  - 问 `今天几号`：本轮 0 次工具调用、无教材依据提示，正常回答。
- 发现并修复：工作区缺少 7 个宿主模块（`course_rag_provider` 等），`native_bridge` 已引用它们但工作区没有；缺文件会让新会话的原生回合在 `_bind` 抛 `ModuleNotFoundError`。已从主仓库补齐后再打包发布。
- 已知残留：模型仍可能在正文里另写一句"教材第X章第Y页"纯文本；只要本轮至少有一个可核实角标，就能点开定位。`test_native_teaching_prompt` 中依赖已退休 `host_teaching_style` 的 5 条断言仍失败，属于历史遗留，与本次改动无关。

