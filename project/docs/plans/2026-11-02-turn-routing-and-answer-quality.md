# 取消回答字数限制与统一回合分类实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 先彻底移除回答正文的长度门禁，再把“章节导学/文件清单/学习计划/概念提问/提示/练习/指代”等回合类型收拢到一个分类契约，修复“分类错误导致回答错误”，并让“我想学习第一章的主要内容”得到有章节地图、节级问题和第一段讲解的回答。

**Architecture:** 复用现有 `GroundedTurn`、`TaskFrame`、Q5 章节导学、`course_navigation.outline()`、`CourseSearch`/`retrieve`、`ResponseComposer`/`LearningResponse`、引用门禁和任务收据。新增一个 `TurnRoute` 作为唯一分流结果，由 `classify_route()` 一次计算，`TaskService`、工具路由、教学策略、内容组合和完成检查只消费它；不再让 `first_wave_runtime.purpose()`、`course_navigation.intent()`、`Q5Runtime.is_plan_request()`、`reply_budget()` 各自用正则解释同一句原话。章节导学走一个薄的专用处理器，复用课程目录和现有检索/引用校验，不新建第二套教学状态机。

**Tech Stack:** Python 3.12、FastAPI、Pydantic v2、SQLite、现有 DeepTutor 桥接、unittest/pytest、DeepSeek Flash（仅隔离测试配置）。

**Spec:** [章节导学调研报告](../research/2026-11-02-chapter-overview-answer-quality/README.md)

## Global Constraints

- 取消所有**回答正文**的字符上限：`ReplyBudget.target/maximum`、`reply_maximum`、`max_characters`、`回复过长`、`length_ceiling` 全部移除；不得用“压缩重写”处理长度问题。
- 保留模型 API 的 `max_tokens` 技术上限，默认 `ANSWER_MAX_TOKENS=8000`。这不是字数门禁，只是防止无界生成；`round_tokens` 不得再被 `3200` 截断。
- 不删除输入/查询/工具/数据库字段的安全上限（如 4000 字问题、工具参数、卡片标题、检索 query）；本计划只处理回答正文。
- 唯一分类权威是 `GroundedTurn.route`（`TurnRoute`）。`purpose(message)`、`course_navigation.intent()`、`Q5Runtime.is_plan_request()` 只允许作为规则来源被 `classify_route()` 调用，或在输入理解关闭时兜底；下游不得再用原话重新分类。
- 复用而不是重写：Q5 章节导学、`outline()`、`chapters()`、`retrieve()`/`CourseSearch`、`ResponseComposer`、`citation_issues()`、`repo.save()` 收据。
- 章节导学不写掌握度、不推进路径、不创建正式评价；`answer_status=answered` 必须同时满足覆盖校验。
- 不新增第三方依赖；不迁移数据库；不改生产配置；不调用真实学生数据。
- 测试使用隔离 SQLite、固定时钟/假 LLM；真实模型只走隔离测试账户。
- 只暂存本计划列出的文件；工作区已有其他未提交改动，不得整体 `git add .`；未获用户授权不提交。

## Review Focus

1. **内容问题被误判为文件清单**：`教材中与他相关的内容有哪些，我想学习` 必须走教材讲解，不能走 `catalog/kb_files`；`教材有几本` 仍要能列文件。
2. **章节标题张冠李戴**：第一章标题必须等于 `chapters()` 的“实验心理学概论”，不能把教材里另一本书的目录标题当本章标题。
3. **长回答被残留门禁拒绝**：任何 6000 字以上的合法回答不得因“回复过长”被拒绝或压缩。
4. **指代/歧义被猜**：`这个呢`、`他` 等未绑定指代必须澄清，不能默认解析。
5. **章节导学假完成**：缺少节、标题不符、引用不支持时不能标记 `answered`，更不能写掌握度或推进路径。

---

## Part I — 取消回答字数限制

### Task 1: 让 `ReplyBudget` 不再有字符上限

**Files:**
- Modify: `integration/discrete-math-tutor/agents/reply_budget.py`
- Modify: `integration/discrete-math-tutor/agents/quality_checker.py`
- Modify: `integration/discrete-math-tutor/agents/pdf_selection_tutor.py`
- Modify: `integration/discrete-math-tutor/agents/agent_loop_service.py`
- Modify: `integration/discrete-math-tutor/agents/composition_execution.py`
- Modify: `integration/discrete-math-tutor/models/interaction_preferences.py`
- Test: `integration/discrete-math-tutor/tests/test_reply_budget.py`
- Test: `integration/discrete-math-tutor/tests/test_memory_personalization.py`

**Interfaces:**
- Produces: `ReplyBudget(target: int | None = None, maximum: int | None = None)`；属性 `max_tokens: int`；方法 `instructions() -> str`
- Produces: `reply_budget(text="", *, preferences=None, execution=None, action="explain", question_options=False, feedback_mode="", proof_overview=False, supplementary_proof=False, comparison=False, proof=False) -> ReplyBudget`，签名保持不变，所有参数忽略长度计算。

- [ ] **Step 1: 写失败测试**

```python
def test_budget_has_no_character_cap(self):
    budget = reply_budget("我想学习第一章的主要内容")
    self.assertIsNone(budget.target)
    self.assertIsNone(budget.maximum)
    self.assertEqual(budget.max_tokens, 8000)
    self.assertNotIn("不超过", budget.instructions())
    self.assertIn("不设字数上限", budget.instructions())

def test_detailed_and_hint_budgets_are_also_uncapped(self):
    self.assertIsNone(reply_budget("请完整解释并比较", action="give_hint").maximum)
    self.assertIsNone(reply_budget("请给出全书详细学习计划").maximum)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_reply_budget.py::ReplyBudgetTests::test_budget_has_no_character_cap -q`
Expected: FAIL，`target` 仍是 200 或 `instructions()` 含“不超过”。

- [ ] **Step 3: 实现无上限预算**

`ReplyBudget` 改为两个可选字段；`max_tokens` 从 `os.getenv("ANSWER_MAX_TOKENS", "8000")` 读取并 `int()`，非法值回退 8000；`instructions()` 返回：

```text
不设字数上限。按问题需要完整回答，优先保证结构、覆盖、依据和可执行性；
避免重复铺垫；不得为缩短而漏答对象、条件、结论或引用。
```

`reply_budget()` 直接返回 `ReplyBudget()`，删除所有正则分支和 `target/maximum` 计算。保留参数只为兼容现有调用。

同时在同一个任务里给宿主消费者加 `None` 守卫，避免中间态把 `len(text) > None` 变成 TypeError：`quality_checker` 的 `limit is not None and len(response) > limit`，并让 `reply_maximum_override` 在 `budget.maximum is None` 时直接忽略；`pdf_selection_tutor` 在 `maximum is None` 时不计算 `length_ceiling`；`agent_loop_service`/`composition_execution` 在 `maximum is None` 时不传 `max_characters`、不比较长度。Task 2 再删除这些死分支。

同时删除 `models/interaction_preferences.py::style_instructions` 里的 `answer_length` 分支，避免“回答简短/详细解释”作为另一条长度指令重新进入系统提示；`InteractionPreferences.answer_length` 字段保留以兼容旧画像，但不再影响生成长度。反馈/提示场景里的“简短”是教学范围约束，不是回答字数上限，保留。

- [ ] **Step 4: 更新旧断言**

把 `tests/test_reply_budget.py` 中 `(1800, 2400, 4800)`、`(480, 500)`、`(200, 260)`、`(140/240)` 等断言改为 `None` / `8000`，把“只给提示仍然 260 字”改为“提示也不设字符上限，但策略仍只允许提示范围”。同时更新 `tests/test_memory_personalization.py` 中断言“回复不超过140/240/200字”的用例，改为断言提示词包含“不设字数上限”且仍尊重偏好/提示约束；增加断言 `style_instructions({'answer_length': 0})` 不再包含“回答简短”。

- [ ] **Step 5: 运行本文件测试并提交**

Run: `python -m pytest tests/test_reply_budget.py tests/test_memory_personalization.py -q`
Expected: PASS。

```bash
git add integration/discrete-math-tutor/agents/reply_budget.py integration/discrete-math-tutor/agents/quality_checker.py integration/discrete-math-tutor/agents/pdf_selection_tutor.py integration/discrete-math-tutor/agents/agent_loop_service.py integration/discrete-math-tutor/agents/composition_execution.py integration/discrete-math-tutor/models/interaction_preferences.py integration/discrete-math-tutor/tests/test_reply_budget.py integration/discrete-math-tutor/tests/test_memory_personalization.py
git commit -m "refactor: remove answer character budgets"
```

### Task 2: 删除宿主侧长度门禁和压缩重写

**Files:**
- Modify: `integration/discrete-math-tutor/agents/quality_checker.py`
- Modify: `integration/discrete-math-tutor/agents/agent_loop_service.py`
- Modify: `integration/discrete-math-tutor/agents/composition_execution.py`
- Modify: `integration/discrete-math-tutor/agents/response_composition.py`
- Test: `integration/discrete-math-tutor/tests/test_q3_agent_loop.py`
- Test: `integration/discrete-math-tutor/tests/test_composition_execution.py`
- Test: `integration/discrete-math-tutor/tests/test_response_composition.py`
- Test: `integration/discrete-math-tutor/tests/test_stream_retraction.py`
- Test: `integration/discrete-math-tutor/tests/test_q3_q4_integration.py`

**Interfaces:**
- `QualityChecker._rule_check(response, plan, context)` 不再读取 `reply_maximum`，不再产生 `回复过长` issue。
- `execute_batches(..., max_characters: int | None = None)`；`None` 表示不按字符数分配/拒绝。
- `ResponseComposer.instructions()` 不再出现“字数预算”。

- [ ] **Step 1: 写失败测试**

```python
def test_quality_checker_accepts_long_answer(self):
    issues = QualityChecker._rule_check("字" * 5000, self.plan(), {"reply_maximum": 260})
    self.assertFalse(any("回复过长" in issue for issue in issues))

def test_composer_instructions_have_no_budget(self):
    composer = ResponseComposer(plan_response("kp:x", strategy="direct"))
    self.assertNotIn("字数预算", composer.instructions())
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_q3_agent_loop.py tests/test_response_composition.py -q -k "long_answer or no_budget"`
Expected: FAIL，出现“回复过长”或“字数预算”。

- [ ] **Step 3: 删除门禁**

- `quality_checker.py`：删除 `reply_maximum_override`、`rule_context["reply_maximum"]`、`limit` 和 `len(response) > limit` 分支；保留引用、覆盖、事实、题目等其他检查。
- `agent_loop_service.py`：`round_tokens = max(1200, budget.max_tokens)`；删除 `min(round_tokens + 600, 3200)`；`batch_gate` 删除 `len(text) > budget.maximum`；`execute_batches` 不传 `max_characters`。
- `composition_execution.py`：`max_characters` 默认 `None`；分配逻辑只在非 `None` 时生效；提示词删除“全部内容累计仍遵守原字数预算”。
- `response_composition.py`：删除“全部段落总长遵守本轮原有字数预算”。

- [ ] **Step 4: 更新相关旧测试**

`test_q3_agent_loop.py` 中“回复过长 → 压缩修复”的用例改为“引用/格式错误仍修复，长度错误不存在”；`test_stream_retraction.py`、`test_q3_q4_integration.py` 删除 `reply_maximum_override` 断言。

- [ ] **Step 5: 运行并提交**

Run: `python -m pytest tests/test_q3_agent_loop.py tests/test_composition_execution.py tests/test_response_composition.py tests/test_stream_retraction.py -q`
Expected: PASS。

```bash
git add integration/discrete-math-tutor/agents/quality_checker.py integration/discrete-math-tutor/agents/agent_loop_service.py integration/discrete-math-tutor/agents/composition_execution.py integration/discrete-math-tutor/agents/response_composition.py integration/discrete-math-tutor/tests/test_q3_agent_loop.py integration/discrete-math-tutor/tests/test_composition_execution.py integration/discrete-math-tutor/tests/test_response_composition.py integration/discrete-math-tutor/tests/test_stream_retraction.py integration/discrete-math-tutor/tests/test_q3_q4_integration.py
git commit -m "refactor: remove host answer length gates"
```

### Task 3: 删除选区路径和原生桥接的长度门禁

**Files:**
- Modify: `integration/discrete-math-tutor/agents/pdf_selection_tutor.py`
- Modify: `integration/discrete-math-tutor/agents/response_generator.py`
- Modify: `integration/discrete-math-tutor/integrations/deeptutor/agentic_bridge.py`
- Modify: `integration/discrete-math-tutor/llm/client.py`
- Modify: `integration/discrete-math-tutor/agents/agent_loop.py`
- Test: `integration/discrete-math-tutor/tests/test_deeptutor_agentic.py`
- Test: `integration/discrete-math-tutor/tests/test_reply_budget.py`

**Interfaces:**
- `AgenticRequest.max_characters: int | None = None`，不再 `Field(ge=1, le=10000)` 强制。
- `LLMClient.chat(..., agentic_max_characters: int | None = None)` 原样传递；`None` 不写 `max_characters`。
- `agent_loop.py` 的修订分支不再匹配“过长/压缩/字数”；只保留引用、格式、工具协议等修订。

- [ ] **Step 1: 写失败测试**

```python
def test_native_accepts_unbounded_draft(self):
    request = AgenticRequest(model="m", messages=[], evidence="[1] 原文", max_characters=None)
    self.assertIsNone(request.max_characters)

def test_selection_publishes_long_reply_without_length_metadata(self):
    # 复用 tests/test_reply_budget.py 的 self._selection 夹具
    reply = "说明。" * 1200  # 约 3600 字
    tutor, context, resolved, selection = self._selection([reply], [QualityResult(passed=True)])
    with patch("knowledge.grounded_citations.settings", return_value=None), \
         patch("agents.pdf_selection_tutor.selection_memory", return_value={"preferences": {}, "summary": ""}), \
         patch.dict("os.environ", {"VISUALIZATION_ON_DEMAND": "0"}):
        result = explain_selection(tutor, "s", context.message, selection, "production",
                                   task_context=context, resolved_selection=resolved)
    self.assertEqual(result["answer_status"], "answered")
    self.assertGreaterEqual(len(result["reply"]), 3600)
    self.assertNotIn("length_overrun_chars", result)
    self.assertEqual(tutor.llm.chat.call_count, 1)

def test_selection_still_rejects_factual_issue(self):
    tutor, context, resolved, selection = self._selection(
        ["说明。" * 10], [QualityResult(passed=False, issues=["引用编号不支持结论"])])
    with patch("knowledge.grounded_citations.settings", return_value=None), \
         patch("agents.pdf_selection_tutor.selection_memory", return_value={"preferences": {}, "summary": ""}), \
         patch.dict("os.environ", {"VISUALIZATION_ON_DEMAND": "0"}):
        with self.assertRaisesRegex(LLMError, "引用编号不支持结论"):
            explain_selection(tutor, "s", context.message, selection, "production",
                              task_context=context, resolved_selection=resolved)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_deeptutor_agentic.py -q`
Expected: FAIL，`max_characters` 仍被强制或桥接返回“草稿超过”。

- [ ] **Step 3: 删除原生/选区门禁**

- `agentic_bridge.py`：删除 `if len(final_text) > request.max_characters` 分支和“压缩到 3/4”提示；`max_characters` 可选。
- `pdf_selection_tutor.py`：删除 `length_ceiling`、`length_only` 和“超长 10% 放行”逻辑；质量检查只处理非长度 issue。
- `response_generator.py`：不传 `agentic_max_characters`（或传 `None`）。
- `llm/client.py`：`agentic_max_characters: int | None = None`，只在非 `None` 时放入载荷。
- `agent_loop.py`：删除 `("过长", "压缩", "字数")` 分支；`"超过"` 不再单独作为长度信号。
- `agentic_bridge.py` / `llm/client.py`：`max_tokens` 未提供时使用 `ANSWER_MAX_TOKENS`（默认 8000），不要回落到 1200；这是 API 技术上限，不是字符门禁。

- [ ] **Step 4: 运行并提交**

Run: `python -m pytest tests/test_deeptutor_agentic.py tests/test_reply_budget.py -q`
Expected: PASS。

```bash
git add integration/discrete-math-tutor/agents/pdf_selection_tutor.py integration/discrete-math-tutor/agents/response_generator.py integration/discrete-math-tutor/integrations/deeptutor/agentic_bridge.py integration/discrete-math-tutor/llm/client.py integration/discrete-math-tutor/agents/agent_loop.py integration/discrete-math-tutor/tests/test_deeptutor_agentic.py integration/discrete-math-tutor/tests/test_reply_budget.py
git commit -m "refactor: remove selection and native answer length gates"
```

### Task 4: 用长回答回归固定“无字数限制”

**Files:**
- Create: `integration/discrete-math-tutor/tests/test_long_answer_publication.py`
- Modify: `integration/discrete-math-tutor/agents/agent_loop_service.py`

**Interfaces:**
- 失败测试使用假 LLM 返回 6000 字 + 一个已核验来源；结果必须 `answer_status=answered`，`len(reply) >= 6000`，不得出现 `回复过长`。

- [ ] **Step 1: 写失败测试**

```python
def test_long_answer_is_published_without_length_rejection(self):
    reply = "这是完整讲解。" * 1000  # 约 7000 字
    llm = Mock()
    llm.chat.return_value = reply
    # 复用 tests/test_q3_agent_loop.py 的 request()/registry() 夹具
    result = LocalAgentLoop(llm).run(
        request(llm, self.registry(), publish_gate=lambda text, outcome: (True, ""))
    )
    self.assertTrue(result.completed)
    self.assertGreaterEqual(len(result.final_text), 6000)
    self.assertNotIn("回复过长", result.final_text)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_long_answer_publication.py -q`
Expected: FAIL，出现长度拒绝或返回被截断。

- [ ] **Step 3: 修正 `round_tokens` 与发布路径**

确保 `round_tokens = max(1200, budget.max_tokens)` 且 `budget.max_tokens=8000`；内容组合/门禁没有字符上限；只在 `llm` API 层使用 `max_tokens`。

- [ ] **Step 4: 运行并提交**

Run: `python -m pytest tests/test_long_answer_publication.py -q`
Expected: PASS。

```bash
git add integration/discrete-math-tutor/tests/test_long_answer_publication.py integration/discrete-math-tutor/agents/agent_loop_service.py
git commit -m "test: pin uncapped long-answer publication"
```

---

## Part II — 统一回合分类

### Task 5: 修复 `course_navigation.intent` 的章节识别

**Files:**
- Modify: `integration/discrete-math-tutor/knowledge/course_navigation.py:81-112`
- Test: `integration/discrete-math-tutor/tests/test_course_navigation.py`

**Interfaces:**
- `intent(message: str) -> Literal["start", "overview"] | None`
- `start`：明确“学习第一章/带我学第一章/从第一章开始”，其余无“主要内容”修饰。
- `overview`：明确“第一章主要内容/第一章讲什么/第一章重点/第一章框架/第一章有什么内容”。

- [ ] **Step 1: 写失败测试**

```python
def test_chapter_main_content_is_overview(self):
    self.assertEqual(course_navigation.intent("我想学习第一章的主要内容"), "overview")
    self.assertEqual(course_navigation.intent("第一章主要内容是什么"), "overview")
    self.assertEqual(course_navigation.intent("第一章讲什么"), "overview")
    self.assertEqual(course_navigation.intent("第一章有什么内容"), "overview")

def test_chapter_start_stays_start(self):
    self.assertEqual(course_navigation.intent("我想学习第一章"), "start")
    self.assertEqual(course_navigation.intent("从第一章开始"), "start")

def test_specific_concept_is_not_chapter_overview(self):
    self.assertIsNone(course_navigation.intent("第一章的实验设计是什么"))
    self.assertIsNone(course_navigation.intent("第一章第三节的实验程序是什么"))
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_course_navigation.py -q -k "main_content or chapter_start or specific_concept"`
Expected: FAIL，“主要内容”返回 None。

- [ ] **Step 3: 修后缀白名单与触发词**

在 `intent()` 中：
- 触发词增加 `内容|讲什么|学什么|重点|要点|框架|脉络|概览|简介`；
- 后缀允许集合增加 `主要|重点|核心|基本|大致|整体|概要|简介|框架|脉络|讲什么|学什么|有什么|有哪些|是什么|内容`；
- 先判断 `overview` 修饰词，再判断 `start`；`第一章的实验设计是什么` 不因“内容”误判，保持 None；
- 不把“第一章第三节的内容是什么”误判为整章。

- [ ] **Step 4: 运行并提交**

Run: `python -m pytest tests/test_course_navigation.py -q`
Expected: PASS。

```bash
git add integration/discrete-math-tutor/knowledge/course_navigation.py integration/discrete-math-tutor/tests/test_course_navigation.py
git commit -m "fix: recognize chapter overview requests"
```

### Task 6: 新增 `TurnRoute` 和唯一分类器

**Files:**
- Modify: `integration/discrete-math-tutor/models/input_understanding.py`
- Create: `integration/discrete-math-tutor/agents/input_understanding/route.py`
- Create: `integration/discrete-math-tutor/tests/test_turn_router.py`

**Interfaces:**
- `RouteKind = Literal['concept_answer','comparison','chapter_overview','section_overview','learning_plan','exercise','hint','navigation','catalog','personal_state','reader_action','clarify','reject']`
- `RouteScope = Literal['course','chapter','section','kp','selection','figure','pending','none']`
- `ToolPurpose = Literal['textbook','outline','catalog','personal_state','reader_action']`
- `class TurnRoute(StrictModel)` 字段：`kind`, `scope`, `chapter_id: int | None`, `section_id: int | None`, `target_id: str | None`, `name: str`, `query: str`, `tool_purpose`, `navigation_mode: Literal['start','overview','guide','next','repeat','bind'] | None`, `constraints: list[Constraint]`, `source: Literal['rule','model','fallback']`, `reason: str`
- `GroundedTurn.route: TurnRoute | None = None`（默认 None，旧快照可加载）。
- `classify_route(turn: GroundedTurn, context: TaskContext) -> TurnRoute`

- [ ] **Step 1: 写失败测试（表驱动）**

```python
CASES = [
    ("我想学习第一章的主要内容", "chapter_overview", "chapter", 1, "textbook"),
    ("第一章讲什么", "chapter_overview", "chapter", 1, "textbook"),
    ("第一章第一节讲什么", "section_overview", "section", 1, "textbook"),
    ("什么是实验心理学", "concept_answer", "kp", None, "textbook"),
    ("比较观察法和实验法", "comparison", "kp", None, "textbook"),
    ("教材有几本", "catalog", "course", None, "catalog"),
    ("列出教材文件清单", "catalog", "course", None, "catalog"),
    ("教材中与他相关的内容有哪些，我想学习", "clarify", "none", None, "textbook"),  # 无历史时“他”未绑定
    ("帮我制定第一章的学习计划", "learning_plan", "chapter", 1, "textbook"),
    ("今天怎么安排", "learning_plan", "none", None, "textbook"),
    ("我选 B", "exercise", "pending", None, "textbook"),
    ("不要出题，只讲第一章主要内容", "chapter_overview", "chapter", 1, "textbook"),
    ("刚才那个图", "reader_action", "figure", None, "reader_action"),
    ("这个呢", "clarify", "none", None, "textbook"),
]
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_turn_router.py -q`
Expected: FAIL，`route` 模块不存在。

- [ ] **Step 3: 实现 `TurnRoute` 与规则分类**

`classify_route` 顺序：
0. 先看已校验的歧义/拒绝状态：`turn.resolution_status in ('ambiguous','missing')` 或 `context.input_decision.status in ('clarify','reject')` → `kind='clarify'`/`'reject'`，不要再用正则猜目标。
1. 从 `turn.tasks` 读取动作：`propose_learning_plan → learning_plan`；`compare_content → comparison`；`provide_hint → hint`；`request_practice/submit_student_answer → exercise`；`resume_learning_activity/switch_learning_target → navigation`；`chapter_overview → chapter_overview`；`section_overview → section_overview`。
2. 单条 `explain_content`：调用 `course_navigation.intent(message)`；`overview → chapter_overview`；`start → chapter_overview + navigation_mode='start'`；否则 `concept_answer`。若 `intent` 为 None 但消息显式包含“第 X 章第 Y 节”或“第 Y 节”且有“讲什么/内容/重点/要点”，用 `outline()` 解析节标题 → `section_overview`。`Q5Runtime.is_plan_request` 在函数内局部导入，避免 `route.py` 与 `q5_runtime.py` 的循环依赖。
3. 显式文件清单：只匹配“几本/数量/清单/列表 + 教材/文档/资料”或反向组合；`教材中……内容有哪些` 不匹配。
4. 显式“目录/章节结构/有哪些小节” → `tool_purpose='outline'`，kind 仍为 `concept_answer`/`chapter_overview`，由调用方决定是否用结构化工具。
5. 显式“记得我/偏好/画像” → `personal_state`；显式“跳转/打开第 X 页/带我到” → `reader_action`。
6. 无任务或指代未解决 → `clarify`；混合写入/越权 → `reject`。
7. 用 `chapters()` 解析章标题，用 `outline()` 解析节标题；`target_id` 分别为 `chapter:{id}`、`section:{chapter}:{section}`、`kp:{context.knowledge_point}`。
8. `query` 取已解析任务的 `turn.tasks[0].query`（指代绑定后的目标）；章节导学时用 `chapter_title + 全部节标题` 组成结构查询，绝不再把“他/这个/主要内容”这类原句直接送进检索。

- [ ] **Step 4: 运行并提交**

Run: `python -m pytest tests/test_turn_router.py -q`
Expected: PASS。

```bash
git add integration/discrete-math-tutor/models/input_understanding.py integration/discrete-math-tutor/agents/input_understanding/route.py integration/discrete-math-tutor/tests/test_turn_router.py
git commit -m "feat: add unified turn route classifier"
```

### Task 7: 把 `chapter_overview` 接入输入理解和六维视图

**Files:**
- Modify: `integration/discrete-math-tutor/models/input_understanding.py`
- Modify: `integration/discrete-math-tutor/agents/input_understanding/service.py`
- Modify: `integration/discrete-math-tutor/agents/input_understanding/ontology.py`
- Modify: `integration/discrete-math-tutor/knowledge/semantic_labels.v1.json`
- Test: `integration/discrete-math-tutor/tests/test_input_understanding_contracts.py`
- Test: `integration/discrete-math-tutor/tests/test_input_understanding_integration.py`

**Interfaces:**
- `Action` 增加 `'chapter_overview'` 和 `'section_overview'`。
- `READ_ACTIONS` 包含两者。
- `ontology.ACTION_INTENT` 两者映射到 `'learning_management'`；`semantic_labels.v1.json` 的 `learning_management` 描述增加“章节导览/学习路径”。
- `understand()` 末尾：`route = classify_route(understood, context)`；若 `route.kind in ('chapter_overview','section_overview')` 且只有一条 `explain_content`，把 task action 改为对应 kind；`understood.route = route`。

- [ ] **Step 1: 写失败测试**

```python
def test_chapter_overview_action_and_route(self):
    turn = understand(context, request("我想学习第一章的主要内容"), llm=None)
    self.assertEqual(turn.tasks[0].action, "chapter_overview")
    self.assertEqual(turn.route.kind, "chapter_overview")
    self.assertEqual(turn.route.chapter_id, 1)
    self.assertEqual(ontology.intent_for("chapter_overview"), "learning_management")

def test_saved_old_turn_without_route_still_validates(self):
    data = turn("什么是实验心理学").model_dump()  # 本文件已有的 turn() 夹具
    data.pop("route", None)
    self.assertIsNone(GroundedTurn.model_validate(data).route)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_input_understanding_contracts.py -q -k "chapter_overview or old_turn"`
Expected: FAIL，`Action` 不接受 `chapter_overview`。

- [ ] **Step 3: 实现**

- `Action`/`READ_ACTIONS` 增加两个值；
- `service.py` 末尾调用 `classify_route` 并改写单条 `explain_content`；
- `ontology.intent_for` 与 registry 更新；
- `GroundedTurn.instructions()` 增加 `route` 摘要（kind/scope/chapter/section），让模型知道本轮是章节导览而不是单点解释。

- [ ] **Step 4: 运行并提交**

Run: `python -m pytest tests/test_input_understanding_contracts.py tests/test_input_understanding_integration.py -q`
Expected: PASS。

```bash
git add integration/discrete-math-tutor/models/input_understanding.py integration/discrete-math-tutor/agents/input_understanding/service.py integration/discrete-math-tutor/agents/input_understanding/ontology.py integration/discrete-math-tutor/knowledge/semantic_labels.v1.json integration/discrete-math-tutor/tests/test_input_understanding_contracts.py integration/discrete-math-tutor/tests/test_input_understanding_integration.py
git commit -m "feat: add chapter overview action to input understanding"
```

### Task 8: 应用 route，移除工具路由的二次判断

**Files:**
- Modify: `integration/discrete-math-tutor/models/task_context.py`
- Modify: `integration/discrete-math-tutor/agents/task_service.py`
- Modify: `integration/discrete-math-tutor/agents/agent_loop_service.py:394-395`
- Modify: `integration/discrete-math-tutor/agents/tools/first_wave_runtime.py`
- Modify: `integration/discrete-math-tutor/agents/course_search.py`
- Test: `integration/discrete-math-tutor/tests/test_turn_router.py`
- Test: `integration/discrete-math-tutor/tests/test_q3_agent_loop.py`
- Test: `integration/discrete-math-tutor/tests/test_course_search_bridge.py`

**Interfaces:**
- `TaskContext.turn_route: dict | None = None`，从 `prompt_payload()` 排除。
- `apply_route(context: TaskContext, route: TurnRoute) -> None`：设置 `context.turn_route = route.model_dump()`；章节/节范围同时设置 `context.activity_target = {'target_id','name','chapter_id','section_id','reason'}`，并清空旧的 `context.course_navigation`，避免 clarify 与正文冲突。
- `agent_loop_service`：新增 `resolve_tool_purpose(context: TaskContext, message: str) -> str`，返回 `context.turn_route['tool_purpose']`；没有 route 时回退 `purpose(message)`。两者不一致时 `log.warning("purpose_mismatch", extra={...})`，但以 route 为准。
- `shared_search(base, *, message, llm, navigator=None, cancellation=None, route: TurnRoute | None = None)`；`CourseSearch.__init__(..., route=None)`；`CourseSearch.message_for_retrieval() -> str` 返回 `route.query or message`。检索优先使用 `route.query` 和 `route.chapter_id/section_id`；只有 `route` 为空时才用 `explicit_chapters(message)`/`question_interjection(message, target)` 兜底。真正的跨章比较（`len(explicit_chapters) > 1`）仍按侧问题处理。

- [ ] **Step 1: 写失败测试**

```python
def test_content_question_is_not_catalog(self):
    route = classify_route(turn("教材中与他相关的内容有哪些，我想学习"), context)
    self.assertNotEqual(route.tool_purpose, "catalog")
    self.assertIn(route.kind, ("concept_answer", "chapter_overview", "clarify"))

def test_explicit_file_count_stays_catalog(self):
    self.assertEqual(classify_route(turn("教材有几本"), context).tool_purpose, "catalog")

def test_active_mode_does_not_call_legacy_purpose(self):
    context = context_with_route("教材中与他相关的内容有哪些，我想学习", "textbook")
    with patch("agents.tools.first_wave_runtime.purpose", side_effect=AssertionError("legacy")):
        self.assertEqual(resolve_tool_purpose(context, context.message), "textbook")

def test_retrieval_uses_resolved_route_query(self):
    route = TurnRoute(kind="concept_answer", scope="kp", target_id="kp:费希纳",
                      name="费希纳", query="费希纳 心理物理学 韦伯定律 对数定律",
                      tool_purpose="textbook", source="rule", reason="test")
    search = CourseSearch(fake_base, message="与他相关的内容有哪些", llm=None, route=route)
    self.assertEqual(search.message_for_retrieval(), route.query)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_turn_router.py tests/test_q3_agent_loop.py -q -k "catalog or legacy_purpose"`
Expected: FAIL，内容问题仍走 catalog，或 `purpose()` 被调用。

- [ ] **Step 3: 实现**

- 增加 `turn_route` 字段和 `apply_route`；
- 在 `TaskService` 的 `input_decision` clarify/reject 分支之后、Q5/教学分支之前调用 `apply_route`；被拒绝或需澄清的回合不应用章节范围；
- `agent_loop_service` 只读 route；`purpose()` 保留给 input_mode=off/shadow 的兜底；`shared_search` 传入 route；
- `CourseSearch.search()` 内部所有 `self.message` 作为检索 query 的位置改用 `self.message_for_retrieval()`；`explicit_chapters` 只用于“本轮是否跨章/侧问题”，不再覆盖已解析的章范围；
- `first_wave_runtime.purpose` 删除宽泛的 `(?:教材|资料|文档).*有哪些` 分支，改成与 Task 6 相同的“数量/清单”条件；即使被兜底调用也不能再把内容问题判成 catalog。

- [ ] **Step 4: 运行并提交**

Run: `python -m pytest tests/test_turn_router.py tests/test_q3_agent_loop.py -q`
Expected: PASS。

```bash
git add integration/discrete-math-tutor/models/task_context.py integration/discrete-math-tutor/agents/task_service.py integration/discrete-math-tutor/agents/agent_loop_service.py integration/discrete-math-tutor/agents/tools/first_wave_runtime.py integration/discrete-math-tutor/agents/course_search.py integration/discrete-math-tutor/tests/test_turn_router.py integration/discrete-math-tutor/tests/test_q3_agent_loop.py integration/discrete-math-tutor/tests/test_course_search_bridge.py
git commit -m "refactor: consume turn route instead of reparsing message"
```

### Task 9: 把 Q5 计划路由移到理解之后，复用章节计划

**Files:**
- Modify: `integration/discrete-math-tutor/agents/task_service.py:359-381`
- Modify: `integration/discrete-math-tutor/agents/q5_runtime.py`
- Test: `integration/discrete-math-tutor/tests/test_session_study_plan.py`
- Test: `integration/discrete-math-tutor/tests/test_q3_task_loop.py`

**Interfaces:**
- `q5_propose = route.kind == 'learning_plan'`（替换 `q5.is_plan_request(request.message)`）。
- `route.kind == 'learning_plan' and route.scope == 'chapter'` → `q5.propose_chapter_plan(...)`。
- `route.kind == 'learning_plan' and route.scope != 'chapter'` → `q5.propose_session(...)`（保留“本次安排，不代表全书”）。
- 显式“第一章章节导学”仍走 `q5.is_chapter_guide` 分支；但只在理解之后判断。

- [ ] **Step 1: 写失败测试**

```python
def test_chapter_plan_uses_chapter_guide(self):
    result = run("帮我制定第一章的学习计划")
    self.assertEqual(result["result_type"], "session_plan")  # 或 q5_plan
    self.assertIn("第一节", result["reply"])
    self.assertIn("第四节", result["reply"])

def test_generic_session_plan_still_works(self):
    result = run("今天怎么安排")
    self.assertEqual(result["result_type"], "session_plan")
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_session_study_plan.py -q -k "chapter_plan or generic_session"`
Expected: FAIL，“第一章学习计划”仍返回“45 分钟/3 个单元/未纳入第一章”。

- [ ] **Step 3: 实现**

- 把 `q5_plan/q5_previous_mode/q5_propose/session_*` 计算块从 `understand()` 之前移动到之后；
- 用 `route.kind`/`route.scope` 决定 `propose_chapter_plan` 或 `propose_session`；
- 不改变 Q5 的计划确认、修订、幂等收据语义；
- 若 `route.kind == 'chapter_overview'`，不进入 Q5 计划分支，交给 Part III 的处理器。

- [ ] **Step 4: 运行并提交**

Run: `python -m pytest tests/test_session_study_plan.py tests/test_q3_task_loop.py -q`
Expected: PASS。

```bash
git add integration/discrete-math-tutor/agents/task_service.py integration/discrete-math-tutor/agents/q5_runtime.py integration/discrete-math-tutor/tests/test_session_study_plan.py integration/discrete-math-tutor/tests/test_q3_task_loop.py
git commit -m "refactor: route chapter plans after turn understanding"
```

### Task 10: 让教学策略消费 route，而不是再次正则分类

**Files:**
- Modify: `integration/discrete-math-tutor/agents/adaptive_tutoring.py:282-305`
- Modify: `integration/discrete-math-tutor/agents/teaching_strategy.py:221-305`
- Test: `integration/discrete-math-tutor/tests/test_shared_teaching_strategy.py`
- Test: `integration/discrete-math-tutor/tests/test_adaptive_tutoring.py`

**Interfaces:**
- `TeachingTurn` 的 `changed_target` 使用 `route.scope in ('chapter','section')` 或 `explicit_switch()`，不再只靠 `CHANGE_TOPIC` 正则。
- `_decide(inputs)` 的 `inputs` 增加 `route_kind: str = ''`、`scope: str = ''`；若 `route_kind` 是 `comparison/hint/exercise`，优先对应策略；只有 `route_kind` 为空时才走现有正则。
- 章节导学不构造 `TeachingTurn`（由 Part III 处理器接管），避免把章节目标当成 KP 做掌握度。

- [ ] **Step 1: 写失败测试**

```python
def test_comparison_route_selects_comparison_strategy(self):
    plan = decide_for_context(context_with_route("比较观察法和实验法", "comparison"), execution)
    self.assertEqual(plan.primary_strategy, "conceptual_comparison")

def test_chapter_scope_target_is_chapter_not_section(self):
    context = context_with_route("我想学习第一章", "chapter_overview")
    target = _target_from_context(context)
    self.assertEqual(target.target_id, "chapter:1")
    self.assertIsNone(target.section_id)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_shared_teaching_strategy.py -q -k "route"`
Expected: FAIL，`route_kind` 参数不存在。

- [ ] **Step 3: 实现**

- `TeachingTurn` 读取 `context.turn_route`；`changed_target` 使用 route scope；
- `teaching_strategy._decide` 先看 `route_kind`，再走正则；
- 不改变 13 种策略库；只改变“怎么选”的输入来源。

- [ ] **Step 4: 运行并提交**

Run: `python -m pytest tests/test_shared_teaching_strategy.py tests/test_adaptive_tutoring.py -q`
Expected: PASS。

```bash
git add integration/discrete-math-tutor/agents/adaptive_tutoring.py integration/discrete-math-tutor/agents/teaching_strategy.py integration/discrete-math-tutor/tests/test_shared_teaching_strategy.py integration/discrete-math-tutor/tests/test_adaptive_tutoring.py
git commit -m "refactor: teaching strategy consumes turn route"
```

---

## Part III — 章节导学回答

### Task 11: 用课程目录构建章节包

**Files:**
- Create: `integration/discrete-math-tutor/agents/chapter_overview.py`
- Test: `integration/discrete-math-tutor/tests/test_chapter_overview.py`

**Interfaces:**
- `@dataclass(frozen=True) class ChapterSection`: `section_id: int`, `title: str`, `first_target: str`, `source_id: str | None`
- `@dataclass(frozen=True) class ChapterPackage`: `chapter_id: int`, `chapter_title: str`, `sections: tuple[ChapterSection, ...]`, `sources: tuple[dict, ...]`, `query: str`
- `build_chapter_package(chapter_id: int, *, limit: int = 6) -> ChapterPackage`
- 复用 `knowledge.course.chapters()`、`knowledge.course_navigation.outline()`、`knowledge.psychology_retrieval.retrieve()`、`agents.q3_navigation.source_from_chunk()`。

- [ ] **Step 1: 写失败测试**

```python
def test_package_uses_course_outline(self):
    package = build_chapter_package(1)
    self.assertEqual(package.chapter_title, "实验心理学概论")
    self.assertEqual([s.title for s in package.sections], [
        "第一节 实验心理学的研究对象",
        "第二节 实验心理学的产生与发展",
        "第三节 心理学实验的程序",
        "第四节 心理学实验中的伦理问题",
    ])
    self.assertTrue(all(s.first_target for s in package.sections))

def test_package_sources_stay_in_chapter(self):
    package = build_chapter_package(1)
    self.assertTrue(all(s["chapter_id"] == 1 for s in package.sources))
    self.assertIn("实验心理学概论", package.query)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_chapter_overview.py -q`
Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现**

- `chapters()` 找到章标题；找不到抛 `ValueError('unknown_chapter')`。
- `outline()` 过滤 `chapter_id`，按 `section_id` 分组，取每组第一个目标作为 `first_target`。
- `query = " ".join([chapter_title] + [section.title for section in sections])`。
- `retrieve(query, [], limit=limit)`；过滤 `chunk.chapter_id == chapter_id`；用 `source_from_chunk(chunk).to_dict()` 转成 source dict，并补 `index=i`、`source_id`、`text`、`location`、`page`（`SourceRef.to_dict()` 已提供后四项中的大部分）。
- 不把别章 chunk 混入；没有来源时允许 `sources=()`，但处理器必须降级为“结构导览 + 明确说明无正文依据”。

- [ ] **Step 4: 运行并提交**

Run: `python -m pytest tests/test_chapter_overview.py -q`
Expected: PASS。

```bash
git add integration/discrete-math-tutor/agents/chapter_overview.py integration/discrete-math-tutor/tests/test_chapter_overview.py
git commit -m "feat: build chapter package from course outline"
```

### Task 12: 章节导学提示词、输出协议和校验

**Files:**
- Modify: `integration/discrete-math-tutor/agents/course_prompts.py`
- Modify: `integration/discrete-math-tutor/models/learning_response.py`
- Modify: `integration/discrete-math-tutor/agents/chapter_overview.py`
- Test: `integration/discrete-math-tutor/tests/test_chapter_overview.py`

**Interfaces:**
- `CHAPTER_OVERVIEW` 系统提示词，要求输出严格 JSON：
  ```json
  {"roadmap":"...","sections":[{"section_id":1,"question":"..."}],
   "order":"...","first_concept":"...","next_action":"..."}
  ```
- `SemanticType` 增加 `'roadmap'`、`'section_map'`。
- `ContentClaim.text` 的 `max_length` 从 2000 提高到 12000（单条 claim 的结构上限，不是回答总长）。
- `validate_overview(payload: dict, package: ChapterPackage, *, require_citations: bool = True) -> tuple[bool, list[str]]`：章节标题、节覆盖、引用绑定、掌握声明、问题数量。
- 没有可取正文时 `require_citations=False`：允许只由节标题构成的 `roadmap/sections/order`，但 `first_concept` 必须为空，且不得出现任何教材事实 `[n]`；处理器返回 `partial`，不冒充完整讲解。

- [ ] **Step 1: 写失败测试**

```python
def valid_payload(package):
    return {
        "roadmap": "本章是实验心理学概论[1]。",
        "sections": [{"section_id": s.section_id, "question": f"{s.title}的核心问题[1]"}
                     for s in package.sections],
        "order": "先研究对象，再发展史，再实验程序，最后伦理[1]。",
        "first_concept": "实验心理学用实验方法研究心理现象[1]。",
        "next_action": "先从第一节开始。",
    }

def test_validator_rejects_wrong_chapter_title(self):
    payload = valid_payload(package)
    payload["roadmap"] = "第一章的标题是心理学的实验设计和数据处理[1]"
    ok, errors = validate_overview(payload, package)
    self.assertFalse(ok)
    self.assertTrue(any("chapter_title" in e for e in errors))

def test_validator_rejects_missing_section(self):
    payload = valid_payload(package)
    payload["sections"] = payload["sections"][:1]
    ok, errors = validate_overview(payload, package)
    self.assertFalse(ok)
    self.assertTrue(any("section_coverage" in e for e in errors))

def test_validator_rejects_mastery_claim(self):
    payload = valid_payload(package)
    payload["first_concept"] = "你已经掌握了本章内容[1]"
    ok, errors = validate_overview(payload, package)
    self.assertFalse(ok)

def test_validator_rejects_unbound_citation(self):
    payload = valid_payload(package)
    payload["roadmap"] = "这一章讲实验设计[9]"
    ok, errors = validate_overview(payload, package)
    self.assertFalse(ok)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_chapter_overview.py -q -k validator`
Expected: FAIL，`validate_overview` 不存在。

- [ ] **Step 3: 实现**

- 提示词明确：先本章地图，再逐节核心问题，再学习顺序，再第一段概念讲解+例子，最后一句下一步；不得把别书目录当本章；不得声称掌握；教材事实必须 `[n]`，例子标“教学示例（非教材原例）”。
- `validate_overview` 使用 `package.sections` 的 `section_id` 集合，要求完全覆盖或显式 `omitted_sections`；标题必须包含 `package.chapter_title`；引用编号必须在 `package.sources` 的 `index` 集合内；拒绝 `已掌握|学会了|你已经掌握|formal_mastery`；问号最多 1 个且只能在 `next_action`。
- 失败时返回具体错误码，供处理器做一次修复重试；不得静默发布。

- [ ] **Step 4: 运行并提交**

Run: `python -m pytest tests/test_chapter_overview.py -q`
Expected: PASS。

```bash
git add integration/discrete-math-tutor/agents/course_prompts.py integration/discrete-math-tutor/models/learning_response.py integration/discrete-math-tutor/agents/chapter_overview.py integration/discrete-math-tutor/tests/test_chapter_overview.py
git commit -m "feat: add chapter overview protocol and validator"
```

### Task 13: 接入章节导学处理器和完成检查

**Files:**
- Modify: `integration/discrete-math-tutor/agents/chapter_overview.py`
- Modify: `integration/discrete-math-tutor/agents/task_service.py:420-455`
- Modify: `integration/discrete-math-tutor/agents/input_understanding/adapters.py:104-132`
- Test: `integration/discrete-math-tutor/tests/test_chapter_overview.py`
- Test: `integration/discrete-math-tutor/tests/test_input_understanding_integration.py`

**Interfaces:**
- `run_chapter_overview(context: TaskContext, request: ChatRequest, llm, *, package: ChapterPackage | None = None) -> dict`
- 返回至少：`reply`, `answer_status`, `learning_response`, `chapter_overview`（`coverage_ok`, `content_ok`, `chapter_id`, `section_ids`）, `course_navigation`（`status='ready'`, `mode='overview'`, `chapter_id`, `chapter_title`）, `pdf_references`, `textbook_sources`, `sources`, `step_advanced=False`。
- `coverage_ok` 表示四节都出现或显式声明省略；`content_ok` 表示 `first_concept` 有已核验来源。`answered` 要求两者都为 true；无来源时 `answer_status='partial'`、`coverage_ok=true`、`content_ok=false`。
- 前端仍只读 `course_navigation.status/mode`；`mode='overview'` 是新增值，未知 mode 按 `ready` 处理，不新增控件或改导航布局。
- `final_summary` 对 `chapter_overview`/`section_overview`：只有 `coverage_ok and content_ok` 才把 task 标 `completed`；否则 `paused`/`pending`。

- [ ] **Step 1: 写失败测试**

```python
def test_exact_phrase_returns_grounded_chapter_overview(self):
    result = run("我想学习第一章的主要内容", fake_llm)
    self.assertEqual(result["answer_status"], "answered")
    self.assertIn("实验心理学概论", result["reply"])
    for title in ("第一节", "第二节", "第三节", "第四节"):
        self.assertIn(title, result["reply"])
    self.assertTrue(result["chapter_overview"]["coverage_ok"])
    self.assertTrue(result["chapter_overview"]["content_ok"])
    self.assertEqual(result["course_navigation"]["status"], "ready")
    self.assertEqual(result["course_navigation"]["mode"], "overview")
    self.assertFalse(result.get("teaching", {}).get("formal_mastery", False))

def test_missing_section_is_not_answered(self):
    result = run("我想学习第一章的主要内容", fake_llm_without_section_4)
    self.assertNotEqual(result["answer_status"], "answered")
    self.assertFalse(result.get("chapter_overview", {}).get("coverage_ok", False))
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_chapter_overview.py -q -k "exact_phrase or missing_section"`
Expected: FAIL，仍走 `direct_explanation` 或返回 235 字。

- [ ] **Step 3: 实现处理器**

`run_chapter_overview`：
1. `package = package or build_chapter_package(route.chapter_id)`；没有章 → 返回 `clarify`。
2. 用 `package.query` + 教材摘录调用 `llm.chat_json`，只调用一次；失败按 `validate_overview` 的错误重试一次（复用一次修复预算，不新建循环）。
3. 校验通过后，把 `roadmap/section_map/first_concept` 转成 `LearningResponse` 三块；`claims` 的 `source_ids` 使用 package sources；`content_origin='generated'`。
4. 生成 `reply`：本章标题 + 地图 + 节级问题 + 顺序 + 第一段讲解 + 下一步；引用编号由服务端统一映射。
5. 返回 `answer_status='answered'`；若 `omitted_sections` 非空，返回 `partial` 并把 `coverage_ok=False`。
6. 不写 `formal_mastery`、不建 pending question、不推进路径。

`TaskService` 在 `apply_route` 之后、Q5 计划分支之前插入：
```python
if context.turn_route and context.turn_route["kind"] in ("chapter_overview", "section_overview"):
    result = run_chapter_overview(context, request, self.tutor.llm)
    return save_answer(result)
```
把现有 `save_q5` 闭包（`task_service.py:439-455`）提取成同级的 `save_answer(result, *, status=None)`，保留原来的 `final_summary`、`repo.save`、`status` 判断（`loop_paused → awaiting_clarification`，否则 `completed`）和 payload/context 参数；Q5 分支改为调用 `save_answer`，不得改变收据、幂等或状态语义。

- [ ] **Step 4: 运行并提交**

Run: `python -m pytest tests/test_chapter_overview.py tests/test_input_understanding_integration.py -q`
Expected: PASS。

```bash
git add integration/discrete-math-tutor/agents/chapter_overview.py integration/discrete-math-tutor/agents/task_service.py integration/discrete-math-tutor/agents/input_understanding/adapters.py integration/discrete-math-tutor/tests/test_chapter_overview.py integration/discrete-math-tutor/tests/test_input_understanding_integration.py
git commit -m "feat: serve chapter overview from course outline"
```

---

## Part IV — 回归与验收

### Task 14: 建立分类黄金用例，防止再次分叉

**Files:**
- Create: `integration/discrete-math-tutor/tests/data/routing_golden.json`
- Create: `integration/discrete-math-tutor/tests/test_turn_routing_golden.py`

**Interfaces:**
- 每条用例字段：`message`, `kind`, `scope`, `chapter_id`, `tool_purpose`, `expect_clarify`, `expect_catalog`, `note`。
- 测试遍历 JSON，调用 `classify_route`，断言所有字段；同时断言 `route.source` 不是 `fallback`（除显式歧义用例）。

- [ ] **Step 1: 写失败测试**

```python
def test_golden_routes(self):
    for case in load_cases():
        with self.subTest(case["message"]):
            route = classify_route(turn(case["message"]), context)
            self.assertEqual(route.kind, case["kind"])
            self.assertEqual(route.scope, case["scope"])
            self.assertEqual(route.chapter_id, case["chapter_id"])
            self.assertEqual(route.tool_purpose, case["tool_purpose"])
```

- [ ] **Step 2: 写入黄金用例**

至少覆盖：
- 章节导学 4 条（主要内容/讲什么/有什么内容/不要出题）；
- 章节开始 2 条（我想学习第一章/从第一章开始）；
- 概念 3 条（什么是实验心理学/解释自变量/第一章的实验设计是什么）；
- 比较 2 条（观察法与实验法/信度与效度）；
- 计划 2 条（第一章学习计划/今天怎么安排）；
- 文件 2 条（教材有几本/列出文件清单）；
- Fechner 2 条（无历史“他” → clarify 且非 catalog；先“费希纳是谁”再“与他相关的内容有哪些，我想学习” → concept_answer 且非 catalog）；
- 指代 2 条（这个呢 → clarify；刚才那个图 → reader_action）；
- 练习/提示 2 条（我选 B/只给提示）；
- 选区/图 1 条（刚才那个图 → reader_action）。

- [ ] **Step 3: 运行并提交**

Run: `python -m pytest tests/test_turn_routing_golden.py -q`
Expected: PASS。

```bash
git add integration/discrete-math-tutor/tests/data/routing_golden.json integration/discrete-math-tutor/tests/test_turn_routing_golden.py
git commit -m "test: add golden turn-routing cases"
```

### Task 15: 8000 真实服务验收并记录

**Files:**
- Create: `integration/discrete-math-tutor/scripts/accept_turn_routing_live.py`
- Create: `project/docs/research/2026-11-02-chapter-overview-answer-quality/ACCEPTANCE.md`
- No production code changes.

**Interfaces:**
- 脚本用隔离测试账户调用 `POST /api/chat`，保存完整 JSON 到 `.runtime/latest-8000-20261102/turn-routing-acceptance/`。
- 断言：
  - 原始问题 `reply` 长度 ≥ 600，含“实验心理学概论”，含四节标题，`chapter_overview.coverage_ok=true`、`content_ok=true`；
  - 不含“第一章的标题是心理学的实验设计和数据处理”；
  - `formal_mastery` 不为 true，`step_advanced` 为 false；
  - Fechner 两句会话：先“费希纳是谁”，再“教材中与他相关的内容有哪些，我想学习”；第二句的 `publication_kind`（若返回）不是 `catalog`，正文不是文件清单/PDF 列表，且 `answer_status=answered`（若指代仍未绑定，允许 `awaiting_clarification`，但不能是 catalog）；
  - 长回答用例（消息：“请完整、详细地讲解第一章的四节内容，不要省略、不要压缩。”）不被 `quality_rejected`，`len(reply) > 1000`；
  - `catalog` 用例（“教材有几本”）仍能列文件。
- 不读取其他学生历史；不修改正式库；不把密钥写进报告。

- [ ] **Step 1: 写验收脚本**

按 `tests/data/routing_golden.json` 的子集发送；每个用例独立 `student_id/session_id`；保存 `request`、`result`、`seconds`。

- [ ] **Step 2: 启动最新 8000 服务**

按现有 `serve.py`/`.runtime` 启动流程；确认 `health.mock_mode=false`、`fixed_book.ready=true`；只改测试账户，不改生产配置。

- [ ] **Step 3: 运行验收**

Run: `python scripts/accept_turn_routing_live.py`
Expected: 所有断言通过；输出 `acceptance-summary.json`。

- [ ] **Step 4: 写验收记录并提交文档**

`ACCEPTANCE.md` 记录：提交/工作区快照、用例表、字数、章节标题、节覆盖、引用数、失败项、未验证项（多轮、浏览器、教师评分、学习增益）。只提交文档，不提交 `.runtime`。

```bash
git add integration/discrete-math-tutor/scripts/accept_turn_routing_live.py docs/research/2026-11-02-chapter-overview-answer-quality/ACCEPTANCE.md
git commit -m "docs: record turn-routing and chapter-overview acceptance"
```

---

## 执行顺序与依赖

1. **Part I（Task 1–4）先独立完成并发布**：长度限制移除不依赖分类改造，可先验证“长回答能发布”。
2. **Part II（Task 5–10）再完成**：Task 5 → 6 → 7 → 8 → 9 → 10；Task 8 依赖 Task 6/7，Task 9 依赖 Task 8，Task 10 依赖 Task 6/8。
3. **Part III（Task 11–13）最后**：Task 11 → 12 → 13；Task 13 依赖 Task 8/9。
4. **Part IV（Task 14–15）收尾**：Task 14 可在 Part II 后先写；Task 15 在全部通过后跑真实服务。

## 明确不做

- 不新增 PostgreSQL/Redis/LangGraph/向量库；不迁移数据库。
- 不重写 13 种教学策略；只改“选择策略的输入来源”。
- 不关闭引用、证据、发布、幂等、取消、权限门禁。
- 不把“章节导学”写成掌握度、正式评价或路径推进。
- 不为“更长”而删除事实、条件、引用或题目完整性校验。
- 不一次性重构整个 `TaskService`；只移动 Q5 判断块并插入章节导学分支。
