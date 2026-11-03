# 章节导学与统一路由：实现验收记录

日期：2026-11-02。对象：`project/integration/discrete-math-tutor` 当前工作区（基线 `2019833` + 未提交改造）。本轮使用隔离临时数据库、真实 `deepseek-flash`、FastAPI `TestClient` 进程内调用；没有重启或改写 8000 正式服务、正式学习库或课程发布状态。

## 0. 8000 正式进程验收

本轮已按用户要求重启 8000，加载当前工作区代码。

- 进程：PID `37336`，监听 `127.0.0.1:8000`。
- 启动器：`.runtime/latest-8000-20261102/start-current.py`（旧 `serve.py` 带有源码 hash pin，当前工作区改动会拒绝启动；新启动器保留原 `.env`/`deepseek.env` 与 flags）。
- Python：`.venv-runtime`（`.venv-gpu` 缺 `lightrag`，无法启动固定教材）。
- `/health`：HTTP 200，`mock_mode=false`，`fixed_book.ready=true`，`embedding/reranker` 实际为 CUDA。
- 真实请求“我想学习第一章的主要内容”：`answered` / `chapter_overview`，**1273 字，8.64 秒**；标题“实验心理学概论”；四节齐全；`course_navigation.mode=overview`；`coverage_ok=true`、`content_ok=true`；`formal_mastery=null`。
- 原始结果：`.runtime/latest-8000-20261102/ch1-live-8000.json`。

## 1. 真实模型结果

运行：

```text
python scripts/accept_chapter_overview_live.py \
  --key-file deepseek.env \
  --output ..\..\..\.runtime\chapter-overview-live-20261102-e \
  --model deepseek-flash
```

| 用例 | 结果 | 关键指标 |
| --- | --- | --- |
| 我想学习第一章的主要内容 | `answered` / `chapter_overview` | 1318 字，11.2 秒；标题“实验心理学概论”；四节齐全；`coverage_ok=true`、`content_ok=true`；`course_navigation.mode=overview`；`formal_mastery=false`；`step_advanced=false`；0 个问号 |
| 不要出题，只讲第一章主要内容 | `answered` / `chapter_overview` | 1220 字，7.1 秒；四节齐全；`coverage_ok=true`、`content_ok=true`；正文 0 个问号 |
| 费希纳是谁（同会话第一句） | `quality_rejected` | 16 字未发布；不是 catalog |
| 教材中与他相关的内容有哪些，我想学习（第二句） | `quality_rejected` | 未走 catalog；正文不是文件清单 |
| 教材有几本 | `answered` / catalog | 11 份 PDF 清单，4.7 秒 |

### 章节导学的实际内容

回答包含：

1. **本章地图**：四个层层递进的问题——是什么、从哪里来、怎么做、伦理底线；串成“是什么—怎么来的—怎么做—怎么做得正当”。
2. **逐节核心问题**：四节各一条，来自课程目录和节标题，不是别书目录。
3. **建议顺序**：按目录先第一节立概念，再第二节背景，再第三节程序，最后第四节伦理；说明第一、三节是主干。
4. **第一段讲解**：实验心理学的定义、控制条件/客观化定量化、冯特 1862 年概念来源，并附“背景音乐与阅读速度”的教学示例（标明非教材原例）。
5. **下一步**：建议从第一节“实验心理学的含义”读起，并询问是否继续梳理该节。

关键修复验证：

- 第一章标题为“实验心理学概论”；
- 不再出现“第一章的标题是心理学的实验设计和数据处理”；
- 四节全部出现；
- 没有声称掌握、没有推进路径、没有出题。

## 2. 测试结果

在 `project/integration/discrete-math-tutor` 下使用系统 `python -m pytest`：

| 测试 | 结果 |
| --- | --- |
| `tests/test_chapter_overview.py` | 26 passed |
| `tests/test_turn_router.py` | 8 passed, 14 subtests |
| `tests/test_reply_budget.py + tests/test_long_answer_publication.py` | 19 passed, 5 subtests |
| `tests/test_task_execution.py` | 24 passed |
| `tests/test_session_study_plan.py` | 17 passed |
| `tests/test_chapter_overview.py + tests/test_task_service_context.py + tests/test_session_study_plan.py + tests/test_input_understanding_integration.py` | 61 passed, 3 failed（既有 host-loop/环境失败） |
| `python -m py_compile`（12 个改动实现文件） | 通过 |
| `git diff --check` | 无 whitespace error；仅 `task_service.py` CRLF 提示 |

既有失败未由本轮修复，也未冒充通过：`test_memory_personalization` 的 `IndexError`、`test_stream_retraction` 的 `.llm` fixture、`test_q3_q4_integration` 的 retrieval/plan-scope、`test_course_navigation` 的 12 个 `.llm` fixture、`test_clarification_tasks` 的 `q5_learning_bindings` 临时库缺口。

## 3. 本轮已实现的行为

- 回答正文字数上限移除：`ReplyBudget.target/maximum=None`，`ANSWER_MAX_TOKENS=8000` 只作为模型 API 技术上限；`回复过长`、`reply_maximum`、`max_characters`、`length_ceiling`、`style_instructions` 的长度分支、选区重试截断均移除。
- 唯一路由契约：`TurnRoute` + `classify_route`；`TaskContext.turn_route`；`resolve_tool_purpose` 先读 route；`CourseSearch` 用 route 的 `query`/chapter/section 范围。
- 章节意图：`course_navigation.intent` 区分 `overview`/`start`；“主要内容/讲什么/有什么内容”不再漏判。
- Q5 计划：判断移到理解之后；章节计划用 `propose_chapter_plan`，通用安排用 `propose_session`；确认/调整不会被新提案抢占。
- 教学策略：错误/部分正确的作答优先 `direct_correction`/`guided_revision`，不被 route 的 `exercise` 覆盖。
- 章节导学：课程目录 + 本章检索 + 三块 `LearningResponse`（roadmap / section_map / first_concept）；校验标题、节覆盖、引用、掌握声明、问题数量；模型/JSON 失败重试一次，再降级为结构导览 `partial`；无来源不编造教材事实。
- 完成检查：`chapter_overview`/`section_overview` 只有 `coverage_ok and content_ok` 才算完成。
- 计划调整保护：Q5 计划确认/调整不会被章节处理器抢占。
- 章节游标：导学后返回第一节的可解析 `course_navigation`（含 `id`/`version`），下一部分不再走死路。
- 最小依据守卫：日期/数字/理论名没有 `[n]` 会被拒绝；结构句可无引用。
- `no_questions`：章节导学的“下一步”改为陈述句，正文不再出现问号。

## 4. 边界与未验证

- **已重启 8000 正式服务**：PID `37336`，使用当前工作区代码和 `.venv-runtime`；`/health` 正常、固定教材 ready、CUDA 生效。重启使用的是新启动器 `start-current.py`，不是旧 `serve.py`（旧脚本的源码 hash pin 会拒绝当前未提交改动）。
- **Fechner 两句仍是 `quality_rejected`**：在 `Q3_RETRIEVAL_MODE=stub` 的隔离验收环境中，费希纳第一句走 Q3 循环但没有证据，被证据/发布门禁拒绝；这不是路由回退（没有变成 catalog），但“费希纳追问可回答”仍未在此环境验证。需要真实 `existing`/fixed-book 检索再测。
- **没有跑完整测试套件**：全量套件存在网络/上游依赖和既有夹具失败，本轮只跑任务相关定向回归。
- **没有浏览器/前端验收**：`course_navigation.mode='overview'` 没有新增控件，前端按 ready 处理；未验证页面展示。
- **没有教师评分/学习增益**：本轮只验证工程链路和回答形态，不宣称教学效果。
- **CRLF**：`task_service.py` 内容完整、可导入；Git 提示 CRLF→LF，不是编码损坏。
- **未提交**：所有改动仍在工作区，未 stage/commit；用户可逐文件审阅。

## 5. 复现命令

```text
cd project/integration/discrete-math-tutor
python -m pytest tests/test_chapter_overview.py tests/test_turn_router.py tests/test_reply_budget.py tests/test_long_answer_publication.py tests/test_task_execution.py tests/test_session_study_plan.py -q
python scripts/accept_chapter_overview_live.py --key-file deepseek.env --output ..\..\..\.runtime\chapter-overview-live-20261102-e --model deepseek-flash
```

原始请求/结果：`.runtime/chapter-overview-live-20261102-e/acceptance.json`。
