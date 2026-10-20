# Q5 首批最小接线说明

日期：2026-10-20。适用于本分支 `90db1d5` 之后的首批 Q5 实现。本文是给集成窗口的接线说明，不是对 `main.py`/`TaskService`/前端的修改。

## 1. 数据库初始化

Q5 新增 6 张表：`q5_learning_paths`、`q5_learning_modules`、`q5_learning_objectives`、`q5_learning_progress`、`q5_learning_bindings`、`q5_learning_commands`。

- 项目正常启动：`database.database.init_db()` 已 import `database.q5_learning`，`Base.metadata.create_all` 会创建 Q5 表。
- 单独初始化/测试：
  ```python
  from database.database import init_db
  init_db()
  # 或：from database.q5_learning import ensure_q5_schema
  # ensure_q5_schema()
  ```
- 测试/预演必须使用独立 SQLite（例如 `.runtime/q5-...`），不要指向正式 `ai_tutor.db`。
- `q5_learning_paths.student_id` 有 `students` 外键；调用前确保该学生存在（测试账户用 `AccountManager` 或直接 `students` 行）。
- 路径/模块/目标/进度/绑定/命令表均带学生删除级联；不要复制 DeepTutor 的 JSON 学习库。

## 2. 创建服务与适配器

```python
from agents.q5_learning import LearningScope, Q5LearningService
from agents.q5_plan_generator import LLMPlanGenerator
from agents.q5_turn_adapter import Q5TurnAdapter

scope = LearningScope(
    student_id="student-1",
    session_id="session-1",
    course_id="experimental-psychology-3",
)
service = Q5LearningService(
    # 可选：把 Q2 发布版本作为来源校验的一部分
    source_validator=lambda ref: bool(ref.get("version")),
)
adapter = Q5TurnAdapter(service, scope)
```

## 3. 首次需求了解（只问缺失字段）

```python
profile = {
    "prior_knowledge": "学过一点实验设计",
    # target_level/time_budget/preferences 缺失
}
questions = adapter.intake_questions(profile)
# 返回缺失字段的 [{id,prompt,allow_free_text}]
# 集成窗口把它包装成 Q3 ask_user 问题卡；已有字段不会重复问。
```

用户回答后合并画像；不要用模型猜测替代回答。用户拒绝回答时按保守估计开始，并在后续 `mastery_profile`/服务中允许修正。

## 4. 生成计划 → 确认 → 开始

```python
materials = [
    {
        "document_id": "doc-1",
        "version": "v1",
        "unit_id": "ch1:s1:b6",
        "chapter_id": 1,
        "section_id": 1,
        "page": 3,
        "title": "实验心理学的含义",
        "text": "...",
        "release_id": "...",          # 来自 Q2 course_release
        "source_version": "...",
    }
]
made = adapter.generate_plan(
    goal="掌握实验设计基础",
    materials=materials,
    profile=profile,
    llm=llm,                         # 项目 LLMClient
    command_id=request.request_id,   # 任务/命令幂等键
    path_name="实验设计入门",
)
# made: status=draft, path_id, path_revision, plan_confirmed=false

# 展示 made 对应的 status/modules 给用户；用户调整/认可后：
started = adapter.confirm_and_start(
    made["path_id"], made["path_revision"], command_id=request.request_id
)
# started["mode"] == "study"; path status active
```

未确认不能进入 `study`。已有路径每轮只 `service.status(scope)`，不要重复 `generate_plan` 或 `mastery_build`。

## 5. 接入 Q3 LoopRequest

```python
binding = adapter.loop_binding()
# binding["target"]: Q3 LearningTarget
# binding["tools"]: Q4 ScopedToolRegistry
# binding["tool_state"]: Q5 path/objective/mode/revision

loop_result = LocalAgentLoop(llm).run(
    LoopRequest(
        student_id=scope.student_id,
        session_id=scope.session_id,
        task_id=request.task_id,
        request_id=request.request_id,
        message=request.message,
        system_prompt=system_prompt,
        tools=binding["tools"],
        target=binding["target"],
        navigation=Q5Navigator(service, scope, search_fn=q2_search),
        tool_state=binding["tool_state"],
        # 预算/取消/质量门禁仍由 Q3/TaskService 提供
    )
)
```

Q3 仍是唯一循环/工具协议；Q5 没有第二套 AgentLoop。检索必须通过 `Q5Navigator.search` 注入的 Q2 接口（当前检索或未来 LightRAG），Q5 不解析目录、不建索引、不用图谱替代学习状态。

## 6. 保存讲解位置与“我懂了”

- 模型在完成讲解后调用 Q5 工具 `mastery_note_explained`；服务只写 `explained`，不写 `mastered`。
- 用户明确说“我懂了/下一部分”时，模型调用 `mastery_understood`：
  - `mastery_goal`：推进到下一教学目标；
  - `textbook_navigation`：返回 `requires_navigation=true`，Q2 负责下一目录项；
  - 两条路径都不产生掌握分。
- 每次工具写操作使用 `command_id`（可由 `request_id + tool` 组成）；重复命令返回首次结果。
- 教学位置推进带 `base_revision`；旧 revision 返回 `path_conflict`，不会重复推进。
- 插问/无关单轮不调用 Q5 写工具，当前目标/位置保持不变；Q3 正常回答插问后回到原任务。

## 7. Q2 教材目标 / 圈选绑定

### 7.1 Q2 当前目标

```python
from knowledge.course_navigation import resolve

cursor = resolve("我想要学习教材第一章的内容")
# cursor: id/title/chapter_id/section_id/version/source_version/path_kind
adapter.bind_textbook_cursor(cursor, command_id=request.request_id)
```

`bind_textbook_target` 只保存当前目标投影，不计算下一目录项。`mastery_understood` 在教材路径返回 `requires_navigation`，下一步仍由 Q2 `resolve` 产生。

### 7.2 圈选来源

```python
selection = {
    "document_id": selection_ref["document_id"],
    "version": selection_ref["version"],
    "chapter_id": selection_ref["chapter_id"],
    "section_id": selection_ref["section_id"],
    "page": selection_ref.get("page"),
    "title": selection_ref.get("section_title", ""),
    "text": resolved_text,
    "release_id": release_id,
    "source_version": source_version,
}
# 新建单目标路径：
made = adapter.bind_selection(
    selection, goal="学习圈选内容", command_id=request.request_id
)
# 或绑定已有路径（按 document/version/unit/page 匹配）：
# adapter.bind_selection(..., path_id=existing_path_id)
```

绑定后 `service.status(scope)` 已保存目标/来源；后续继续学习不需要重新圈选。Q2 选区入口自动调用 `bind_selection` 仍需集成窗口接线，本批未改 TaskService/前端。

## 8. 刷新/重启恢复

```python
# 新进程/新服务实例
service = Q5LearningService()
status = service.status(scope)
# 读 q5_learning_bindings -> path_id -> current_objective_id/progress
# 页面重新展示 status["current"]、status["next"]、status["modules"]、status["mode"]
```

不得从上一轮模型文本猜当前位置；只读绑定/路径/进度。

## 9. Q2 版本校验

最新 Q2 `course_release.validate(expected)` 返回当前 release，版本变化时抛错。集成时建议：

```python
from knowledge.course_release import validate as validate_release

release = validate_release({"release_id": saved_release_id})  # 变化时失败
# 再把 release_id/source_version 放进 materials/selection source refs
```

Q5 source ref 已保留 `release_id`/`source_version` 字段；来源版本失效时 `status` 返回 `source_unavailable`，`mastery_understood` 不推进。

## 10. 接线边界

- **不改** `main.py`、`TaskService`、前端公共入口；由集成窗口在任务前后调用 `Q5TurnAdapter`。
- 不复制其他窗口未提交的 `task_service.py`/`agent_loop_service.py`/Q2 代码。
- 正式题卡、评分、掌握门槛、复习、教师审核不在本批。
- 本批已验证：隔离 SQLite 31 项；Q3/Q4/Q5 联合 132 项通过；Q2 相关 34 项通过。真实模型/页面/正式 TaskService 接线尚未完成。
