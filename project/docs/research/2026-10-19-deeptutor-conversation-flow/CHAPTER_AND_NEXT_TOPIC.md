# 章节学习与“下一个知识点”专项源码调研

日期：2026-10-19。范围：D:/deeptutor 源码与当前项目。用户报告的两个场景一起核查；本轮不表示线上已修复。

## 1. 结论及原计划的覆盖情况

两个问题涉及共同链路：**学习导航意图 → 课程范围与当前位置 → 明确目标 → 检索原文 → 讲解 → 更新覆盖/位置并接续**。

原计划并非没有涉及：Q2 包含教材检索，Q5.2 包含阅读/课程编排，Q5.3 包含 Mastery 路径，Q5.1 包含学习接续。但没有将“按章启动”和“进入下一知识点”列为早期必过场景，而且路径接线安排偏后。前一轮已补 Q2.7 章节入口；本轮补 Q2.8 和 Q3.7，让基本导航提前接通，正式 Mastery/复习仍按 Q5 实施。

共同缺口不是教材不存在，也不只是重排阈值。需要把已有目录、当前目标和下一目标选择接入检索之前。只提高相似度召回、拼接历史或迁入 Agent 循环，都不能代替这一层。

## 2. 第一章和变量知识确实存在

只读检查：第一章为《实验心理学概论》，四节分别是研究对象、产生与发展、实验程序、伦理问题；SQLite 索引中第一章有 191 条记录。第一章第三节 block 322、323、324 分别有自变量、因变量、额外变量的定义。

这证明教材已有相关内容，不表示所有学习路径都应把因变量无条件作为自变量的下一点；具体顺序需来自所选课程范围和学习路径。

## 3. “我想学习第一章”的处理差异

### 当前项目

- `_chapter_hint` 用 `\d+` 提取显式章号。独立执行该函数，“第一章”得到 None，“第1章”得到 1；这是已确认的中文章号缺口。
- 章号线索只是通用召回的提示，不负责启动章节学习、读取大纲或选择首节。
- `knowledge/course.py::chapters()` 已可提供真实章/节和内容，但普通对话没有统一地先将章节学习要求解析为这个结构化范围。
- Orchestrator 在检索为空时提前返回 evidence_rejected；LessonPlanner 在此之后才执行，无法再选择本章首个教学目标。

依据：[章节线索](E:/项目/heart/project/integration/discrete-math-tutor/knowledge/hybrid_retrieval.py:41)、[目录](E:/项目/heart/project/integration/discrete-math-tutor/knowledge/course.py:45)、[检索入口](E:/项目/heart/project/integration/discrete-math-tutor/orchestrator.py:214)。

### DeepTutor

| 机制 | 实际职责 | 源码 |
| --- | --- | --- |
| material_outline / read_material | 先读取材料目录和 locator，再读取指定单元，不必只依赖一句宏观请求的向量命中 | [目录](D:/deeptutor/deeptutor/capabilities/reading/tools.py:171)、[读取](D:/deeptutor/deeptutor/capabilities/reading/tools.py:311) |
| SyllabusUnit / set_syllabus | 保存稳定 ID、position、title、topics、covered 的有序课程单元 | [数据结构](D:/deeptutor/deeptutor/services/courses.py:84)、[保存](D:/deeptutor/deeptutor/services/courses.py:507) |
| build_course_state | 整理课程实际状态，取首个未 covered 的单元作为 syllabus.next | [课程状态](D:/deeptutor/deeptutor/services/courses_state.py:343) |
| course_study pre_loop / handoff | 模型开始前读取真实状态，再建议学习入口并交接；该模式本身明确不直接教授内容 | [状态预读](D:/deeptutor/deeptutor/capabilities/course_study/capability.py:483) |
| mastery_build | 依据材料设计并保存有序模块和知识目标，而非凭空获得下一目标 | [路径构建](D:/deeptutor/deeptutor/capabilities/mastery/tools.py:1761) |

这些机制要求材料、课程/大纲或目标路径已经绑定。普通 chat 加一个未初始化大纲的知识库，不保证自动变成完整的章节导学。

## 4. “自变量学完了，继续下一知识点”的处理差异

### 当前项目已有状态，但不足以跨知识点导航

TaskContext 有当前 knowledge_point、历史、已知点及资源对象，但没有完整接入“当前路径的有序目标、当前目标 ID、下一目标及覆盖状态”。LessonPlan 的步骤通常围绕一个 point 生成，如自变量的解释、检查和应用；推进这些步骤，不等于进入教材的下一知识点。

独立探测 `_retrieval_query` 的结果：

| 合成路由条件 | 实际查询 |
| --- | --- |
| intent=continue，student_move=question，needs_context=False | `继续下一个知识点` |
| 同上，但 needs_context=True，当前点为自变量 | `自变量 继续下一个知识点`，再附最近历史 |

这两条路径都没有先确定新的真实目标。历史拼接能表达刚讲过自变量，但不会自动得到下一目标的 ID、名称和来源范围。它可能查不到，也可能又找回旧对象。

这是函数分支探测，不是用户在线请求的重放；不能据此认定用户当时实际路由字段一定是哪一组。

依据：[TaskContext](E:/项目/heart/project/integration/discrete-math-tutor/models/task_context.py:30)、[单点计划](E:/项目/heart/project/integration/discrete-math-tutor/models/lesson_plan.py:30)、[查询构造](E:/项目/heart/project/integration/discrete-math-tutor/orchestrator.py:781)、[检索后规划](E:/项目/heart/project/integration/discrete-math-tutor/orchestrator.py:366)。

### DeepTutor 先提供真实下一目标

`mastery_status` 返回权威目标与 next；`learning/policy.py::next_objective` 是无模型、无 I/O 的确定性策略：

1. 有待答题目，返回该题所属目标的待答状态。
2. 有到期复习，优先给出复习目标（排除暂缓项）。
3. 按 module.order 和模块内知识点顺序选择未过门槛、未暂缓的目标。
4. 必要时回到暂缓目标；全部过关且无到期复习才 complete。

结果包含 action、module_id、knowledge_point_id/name/type、状态、门槛、原因等。模型据此读取实际目标的材料，不是只搜索“下一个”。

依据：[下一目标策略](D:/deeptutor/deeptutor/learning/policy.py:255)、[状态工具](D:/deeptutor/deeptutor/capabilities/mastery/tools.py:704)。

### 讲过、掌握、暂时往后学是三回事

- `mastery_note_explained` 只记录讲过，不授予掌握分，也不自动让下一目标策略越过未达标目标。
- 满足掌握评估门槛后，策略跳过该已掌握目标。
- 用户明确要求先往后学，可以 `mastery_defer_objective` 暂缓当前目标，再读取 next；不谎称已经掌握。
- syllabus.covered 是学习者选择的覆盖标记，不是模型推断的掌握分。

因此，直接照搬严格 Mastery 门槛，也不能保证用户听过讲解后就自动跳到下一点。普通章节浏览、解释覆盖、暂缓和正式评估必须明确区分。

依据：[讲解覆盖](D:/deeptutor/deeptutor/capabilities/mastery/tools.py:826)、[显式暂缓](D:/deeptutor/deeptutor/capabilities/mastery/tools.py:1693)、[教学协议](D:/deeptutor/deeptutor/capabilities/mastery/prompts/zh/mastery_loop.yaml:86)。

## 5. 本项目需要补齐的连接

| 环节 | 当前情况 | 需要连接的内容 |
| --- | --- | --- |
| 章/节目录与原文 | 已有 | 作为导航和范围解析入口 |
| 有序知识目标与来源 | 单点计划不等于跨点路径 | 课程/模块/目标顺序、稳定 ID、原文范围 |
| 当前学习位置 | 有当前点和单点步骤 | 绑定所选路径、当前目标、已讲/暂缓等状态 |
| 下一目标选择 | 查询构造没有先完成 | 根据范围和状态取得真实 next |
| 原文检索 | 可能收到导航原句或旧点 | 使用已解析目标名/ID和章/节范围 |
| 接续与学习事实 | 已有评分保护 | 导航位置变化与掌握评分分开，幂等提交 |

建议顺序是：识别导航动作 → 读取课程范围和当前位置 → 确定真实目标 → 检索/读取该目标原文 → 讲解与核验 → 保存学习位置。缺少必要路径信息才澄清，不把必要状态缺失笼统表述成教材无相关内容。

这是本项目的代码集成建议，不要求将请求交给完整 DeepTutor 应用。基本章/节/知识点导航应先做，正式 Mastery/复习按 Q5 接续。

## 6. 联合验收用例

1. 第一章/第1章/实验心理学概论定位同一章，按真实目录启动。
2. 在明确路径中讲解自变量后，“继续下一知识点”先取新目标再检索；不能只搜原句，也不能继续讲旧点。
3. 若路径已定义自变量→因变量→额外变量，则依次推进；没有定义或有跨章歧义时不编造全局唯一顺序。
4. “再解释一次”保持当前目标；“继续这个例子/下一步推导”保持同一知识点；“下一节/下一章”按相应层级处理。
5. 仅听讲后要求先往后，不自动记为掌握。正式过关、暂缓和跳题分别保留真实状态。
6. 明确章/目标不被页面当前位置覆盖；刷新、重复提交、切换会话、取消、删除及换版不重复推进或恢复失效目标。
7. 路径末尾明确结束或提出下一范围，不回复教材检索不到内容。

每例记录原消息、导航动作、路径/教材版本、当前与下一目标、查询、来源、输出及状态变化。

## 7. 本轮验证与限制

使用 D 盘原源码和独立环境，在新建的隔离 DEEPTUTOR_HOME 内运行：`deeptutor/learning/tests/test_policy.py`、`tests/capabilities/test_course_study.py`、`tests/services/test_courses.py`。结果 **60 passed，3.63 秒**。覆盖目标策略、课程状态/编排及课程服务，不等于模型已在我们的页面正确调用相应工具。

本项目只读探测确认第一章数据存在、中文章号缺口、查询缺少下一目标解析，以及空检索早于教学规划。未重放用户的两次在线请求或修改业务代码，实施时仍需关联路由、检索和门禁记录，确认每次失败的具体分支。
