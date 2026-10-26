# 教学卡片首批实现与验收

日期：2026-10-26。对应TA3展示能力，承接TA1教法与TA2辅助证据改动。基线仍为`3a0b0fbcfec54a05102898b1c65660955ee5cb39`，本轮未提交、未推送、未切换正式服务。

## 1. 本批范围与现有能力复用

核对后确认：误解更正、按知识点删除以及更正后的检索过滤已有实现，分别位于`memory_api.py`、`database/memory_management.py`、`memory/retrieval.py`及现有记忆管理页面。本轮没有重复建立误解表或撤销服务；正式题目到误解假设的联动仍待原生NT3。

本批实现三类有限展示：

| 类型 | 数据与交互 | 不代表什么 |
| --- | --- | --- |
| `learning_progress` | 服务端从当前辅导状态投影已讲解、待答和辅助反馈；无模型额外调用 | 不把已讲解、自报理解或辅助答对画成掌握率 |
| `step_reveal` | 学生明确要求分步展开/逐步展示时，生成2—6个可展开步骤 | 展开是阅读行为，不记评分或完成目标 |
| `concept_comparison` | 明确要求对比卡/比较卡时，生成两个对象和1—6个比较维度 | 对比关系不自动成为先修关系或考试重点 |

复用现有`teaching_step`工具和Q3/Q4协议，未新增工具调度器；复用`LocalAgentLoop`已经存在的`structured_response`发布分支，未建立第二轮自由回答生成。卡片与正文从同一份有界数据生成，再经原发布核验，不通过另一次改写重新分配引用。

## 2. 代码与调用链

应用目录相对路径：

- `agents/learning_cards.py`：Pydantic闭集输入、正文投影、来源编号映射及服务端进度投影。
- `agents/adaptive_tutoring.py`：现有工具增加可选展示字段；新检查题与解释卡片不得同时登记。
- `agents/agent_loop_service.py`：明确卡片需求才要求工具调用；结构化正文执行同一来源门禁；只在发布成功后投影卡片并保存。
- `agents/agent_loop.py`：沿用既有一次有界教学修订机制，补充卡片错误类别，没有提高循环预算。
- `frontend/learning-cards.js`、`learning-cards.css`：本地白名单渲染、分步展开、比较表和只读进度。
- `frontend/app.js`、`index.html`：接实时结果与历史恢复，复用`ChatMessageRenderer`的稳定消息键、展开保护、正文公式处理和上标引用入口。新增文件直接作为静态资源加载，无新的前端依赖或构建系统。

调用链：明确卡片请求 → 现有工具循环取证/登记展示 → 同一份数据生成正文 → 既有发布核验 → 构建展示卡片 → 原`append_exchange`保存 → API及页面显示。普通讲解仍使用原正文流，不要求每条回答生成分步卡或比较卡。

## 3. 协议、来源及保存边界

展示协议为`learning-cards/v1`，包括`card_id`、`revision`、`objective_id`、`kind`及类型对应字段。身份由学生、会话、任务与类型共同生成；卡片revision沿用当前任务revision。

- 输入限定种类、行/步骤数量和文本长度；未知嵌套字段拒绝。模型不能提供可执行动作、脚本或任意组件。
- 来源编号必须属于本轮实际证据并在正文使用。若正文发布发生编号投影，按相同`evidence_id`映射卡片编号，避免指向另一条原文。
- 卡片与引用保存在现有`PDFCitationRow.reference.learning_cards`（历史API以`selection_ref`暴露），只作为展示快照。没有新增学习表、双写掌握状态或执行正式数据库迁移。
- 客户端只渲染已知类型，文本转义；卡片不包含答案键。点击上标走原引用定位与版本失效检查。
- 展开位置仅在sessionStorage保存布尔状态，不保存新的教材或学生答案。重绘和刷新可恢复，键按卡片身份与revision隔离。
- 显式卡片目前每轮支持一种解释展示加一张进度投影；题目作答仍沿用原对话/练习入口，没有另建评分按钮。

卡片同源保证的是展示与正文一致，不等于已经人工验证所有教学结论。正式掌握、教师审核和知识关系证据仍按原计划单独验收。

## 4. 测试与保留失败

最终相关组合：**150项通过，0失败**。

```powershell
& .venv-runtime/Scripts/python.exe -B -m unittest tests.test_learning_cards tests.test_teaching_evidence tests.test_teaching_modes tests.test_task_execution tests.test_adaptive_tutoring tests.test_q3_agent_loop tests.test_q3_task_loop tests.test_q3_entrypoint tests.test_q5_learning -q
node tests/learning-cards.cjs
node --check frontend/app.js
```

日志：`.runtime/teaching-modes/cards-final-tests.log`。新增测试覆盖有界闭集输入、题目/卡片隔离、正文内容范围、来源重映射、隐私、进度语义、身份隔离及原对话保存；前端测试覆盖转义、来源按钮、未知类型、展开恢复及不展示掌握百分比。

扩展组合加入`tests.test_memory_management`时，164项中有1失败、1错误：

- `test_pdf_selection_deleted_mid_generation_is_not_saved`：旧选区夹具缺`record`，抛`KeyError`。
- `test_real_turn_deleted_mid_generation_is_not_published`：既有发布门禁先返回`quality_rejected`，与旧断言期待的`memory_deleted`不一致。

通过加载HEAD中受改模块到临时目录，单独复验这两项，基线同样出现1失败、1错误。日志：`cards-regression.log`及`cards-memory-baseline.log`；没有改写这些失败，也没有把150项通过写成全库通过。此前实施记录的六项兼容失败仍保留。

## 5. 真实模型与浏览器

使用8026隔离服务、真实固定教材运行时、当前真实模型及隔离SQLite。正式8000和正式数据库未切换。

最终运行`e0b4e06745`：

| 请求 | 结果 | 本次耗时 |
| --- | --- | --- |
| 教材中自变量与因变量的区别，要求对比卡 | answered；concept_comparison + learning_progress；6条引用 | 18.59秒 |
| 识别实验变量，要求分步展开 | answered；step_reveal + learning_progress；5条引用 | 4.31秒 |

这是单次功能验收，不是性能对照。模型替身宿主测试证明：已有展示数据后复用结构化发布，不再额外调用一次自由改写模型。

证据位于`.runtime/teaching-modes/live/`：`e0b4e06745-cards-summary.json`、同前缀comparison/steps请求响应、`e0b4e06745-cards-browser.json`及桌面/手机截图。两个生成结果均保存到实际对话历史，浏览器没有用假卡片替换真实数据。

Playwright最终10项通过：三类型恢复、分步展开、重绘保持、刷新保持、对比表、来源绑定、手机导航收起、375px无文档横向溢出、查看操作零生成请求、无pageerror。窄屏对比表允许容器内部横向阅读。浏览器脚本存于`.runtime/teaching-modes/playwright-learning-cards.cjs`，输入摘要路径由`CARDS_SUMMARY`指定。

保留失败：

- `50bdba7738`整体失败：自由改写造成卡片/正文措辞漂移与组合引用`[5, 2]`；第二题未完成必需工具。后改用既有结构化发布，一份数据生成两种展示。
- 首次截图暴露对比表首列过窄，已固定合理列宽。手机首次截图拍到布局过渡，最终使用真实“对话”切换并等待过渡完成，增加导航隐藏检查；初始图片保留为`*-initial.png`。
- 一次浏览器复验时隔离服务已退出，发生connection refused；失败报告单独保留，重启同一隔离库后完成最终验证。

## 6. 当前交付边界

TA3展示首批已实现并完成上述真实验收，但未标记TA3整阶段或全计划完成：新模式的选区/视觉/ask_user跨入口联合验收、正式题卡动作、原生学习状态单写入及迁移仍未完成。

当前卡片接在`ADAPTIVE_TUTORING_ENABLED=1`的既有Q3教材入口；没有声称原生完整应用已经消费该协议，也没有更改默认开关。正式评分、掌握门槛、复习调度仍待原生NT3稳定接入；既有误解管理继续复用。本轮无新增依赖、数据库迁移或上游源码修改。

收尾已停止8026隔离验收进程，确认该端口无监听；测试数据、截图及失败日志保留，未停止或替换8000服务。
