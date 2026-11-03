# 教学可视化 T2/T3 实施与验收记录

日期：2026-11-03。范围：`project/integration/discrete-math-tutor` 当前工作区；8000 进程已加载当前代码。没有修改正式学生数据、课程发布状态或教材索引。

## 1. 当前服务

- 监听：`127.0.0.1:8000`，PID `24808`。
- 启动器：`.runtime/latest-8000-20261102/start-current.py`，使用 `.venv-runtime`。
- `/health`：HTTP 200，`mock_mode=false`，`fixed_book.ready=true`，embedding/reranker 为 CUDA。
- `VISUALIZATION_ON_DEMAND=1`（启动器显式设置；服务内实际出图已验证）。

## 2. 本轮修改

### 2.1 普通问答自动图解

当前主链路已经接通并验证：

- `main.py::_execute_task_turn` 把 `visualization_jobs` 传给普通 AgentLoop。
- `agents/agent_loop_service.py` 在文字核验完成后，对 `tool_purpose=textbook` 且 `visualization_jobs` 存在的普通问答调用 `build_guide`。
- `TaskService` 先保存文字，再处理延迟图解；成功 `attach_guide`，失败保留文字并标记 `unavailable`。

本轮没有重写这条链路，只做了 T3 覆盖修复。

### 2.2 预制主题匹配

文件：`visualization/psychology_presets.py`。

原实现要求问题去掉 `GENERAL` 词表后必须为空，导致自然问法漏配：

- V02 “容易混淆的地方” → 残留“容易混淆地方” → 不匹配；
- V03 “它们分别受什么影响” → 残留“它们” → 不匹配；
- V04 “注意是怎样分配的” → 残留“注意分配” → 不匹配，回退到按需变量图。

改为“主题词 + 教材证据位置 + 明确边界守卫”：

- 不再要求每个填充词都在白名单；
- 保留 `LOCATIONS` 教材章节/小节检查；
- 新增简单定义、用户自定义实验、页码/图号、明确“不要图解/不要可视化”、SOA/毫秒参数的拦截；
- 保留自定义例子/“我的实验”不被预制图替换。

新增回归：`tests/test_psychology_preset_natural_questions.py`（5 tests / 5 subtests）。

### 2.3 知识关系模板

文件：`visualization/templates.py`、`visualization/on_demand.py`。

- 心理学 CATALOG 增加 `knowledge_map`（章节/概念关系框架；箭头仅表示教学关系，不等同因果）。
- `render_plan` 复用现有 `structure` 流程渲染，不新增前端组件。
- 选择器提示增加“方法选择/研究设计判定流程”和“章节/知识关系框架”的适用说明。

## 3. 8000 真实模型验收

### 3.1 正向用例

| ID | 问题 | 文字 | 图解 | 结果 |
| --- | --- | --- | --- | --- |
| V01 | 解释自变量、因变量和额外变量，并说明关系 | 650 字 | `ready`，5 帧 | 变量关系图，自动触发 |
| V02 | 比较被试内与被试间设计，说明适用条件和易混点 | 1462 字 | `ready`，5 帧 | `psychology:between-within-mixed` 预制图 |
| V03 | 信号检测论中的辨别力和判准受什么影响 | 950 字 | `ready`，6 帧 | `psychology:signal-detection` 预制图 |
| V04 | 空间线索有效/无效条件下注意如何分配 | 668 字 | `ready`，5 帧 | `psychology:spatial-cue` 预制图 |

V02/V03/V04 的 `generation` 均为 `textbook-preset`，`validation=pinned-text-and-pdf-anchors`，不是模型随手画图。

### 3.2 负向/简单事实

| 用例 | 结果 |
| --- | --- |
| 费希纳是谁 | `answered` 898 字，`visualization_status=unavailable`，无图 |
| 教材有几本 | `answered` catalog，255 字，无图 |
| 只给提示，不要直接告诉答案 | `answered` 432 字，无图 |
| 什么是自变量？ | `answered` 516 字，`unavailable`，无图 |
| 总结刚才讲的实验控制方法（新会话） | `awaiting_clarification`：“刚才”没有可承接内容；不是图解失败 |

### 3.3 仍未稳定的扩展场景

| 场景 | 结果 | 日志/原因 |
| --- | --- | --- |
| 观察法/相关研究/实验法怎么选择 | `answered` 821 字，`unavailable` | 选择器选中 1 个模板，但生成/审计失败（`LLMJSONError` 两次或 `visual-check` ValueError） |
| 梳理第一章各节知识关系 | `answered` 1339 字，`unavailable` | 同上；`knowledge_map` 已可渲染，但模型生成/审计未稳定通过 |

结论：**V01–V04 的核心自动图解已可用**；方法选择流程与知识关系梳理仍是“模板可选择、生成/审计不稳定”，不能宣称 T3 全部完成。

## 4. 测试

```text
python -m pytest tests/test_psychology_visualization.py tests/test_psychology_presets.py \
  tests/test_visualization_request_regressions.py tests/test_psychology_preset_natural_questions.py -q
```

结果：**23 passed，7 subtests passed**。

另有既有失败未归因于本轮：
`tests/test_visualization.py`、`tests/test_on_demand_visualization.py` 的 27 个用例依赖旧教材 fixture（如 `KeyError: '定理9.5'`）或运行库状态；本轮未修改这些路径。

## 5. 下一步

1. 方法选择流程：把“观察法/相关研究/实验法”的判定做成确定性流程预设，或强化 `experiment_flow` 的生成/审计。
2. 知识关系梳理：优先用 `outline()` 生成确定性的章节关系图，避免依赖模型自由生成。
3. 前端/浏览器：用真实页面验证 `guided_visualization` 挂载、上一步/下一步、历史刷新和窄屏。
4. 计划 T4/T5：V01–V12 完整验收、失败/取消/版本失效、8000 配置与提交记录。

## 6. 边界

- 本轮没有跑完整测试矩阵。
- 没有做浏览器页面验收。
- 方法选择/知识关系两场景仍 `unavailable`，属于生成/审计稳定性问题，不是“没有模板”。
- 所有代码改动仍在工作区，未提交。

## 7. 两个按需出图阻塞的定向修复

本节记录随后开始的修复；与上文“仍不可用”的首次验收结果区分。

- `visualization/psychology_presets.py` 新增方法选择固定图：依据第1章方法比较表、第3章相关设计中的相关边界、伦理限制和实验结果构建4步高亮表格。教材PDF版本和正文块SHA不匹配时拒绝使用；每步定位到核验段落，无法精确定位时只退到核验过的小节标题。
- 新增章节目录结构图：从已发布目录读取章/节，并为每节绑定PDF中已核验的小节标题。图只说明“章节包含小节”，明确声明不代表先修或因果关系；它不声称知识点之间存在教材未给出的关系。
- `visualization/on_demand.py` 对这两类明确请求先走确定性图解，不再要求模型输出计划JSON或通过模型审计。一般按需生成仍保留原门禁。
- 按需失败日志新增`no_template`、`no_plan`、`json_invalid`、`schema_invalid`、`source_unlocated`、`audit_rejected`等类别，并给空计划日志关联trace，便于下一轮定位。
- 本轮仅完成Python语法编译和`git diff --check`；没有运行测试、没有重启8000、没有做真实模型或浏览器验收。因此这两个路径目前是**已实现、尚未实测**，不能标记为验收通过。

## 8. 随后在8000端口的隔离重放

2026-11-03重新启动当前工作区后，`/health`返回`status=ok`、教材索引`ready=true`、`mock_mode=false`，embedding与reranker使用CUDA。使用独立`account_type=test`身份重放上面两个原问题；只发送测试问题及当前教材检索材料，没有读取或外发已有学生聊天记录。

| 场景 | 回答 | 图解 | 教材锚点 | 耗时 |
| --- | --- | --- | --- | ---: |
| 观察法/相关研究/实验法怎么选 | `answered` | `ready`，`textbook-method-selection`，4步 | 4/4帧有PDF页内矩形锚点 | 8.53秒 |
| 梳理第一章各节关系 | `answered` | `ready`，`textbook-outline-map`，4步 | 4/4帧有PDF页内矩形锚点 | 10.23秒 |

两条固定图解路径不再调用模型生成plans或内容审计；自然语言回答仍由原问答链路生成。验收只覆盖这两个固定问题各一次，尚未做重复稳定率统计、浏览器按钮/刷新交互验收，也未运行全测试矩阵。
