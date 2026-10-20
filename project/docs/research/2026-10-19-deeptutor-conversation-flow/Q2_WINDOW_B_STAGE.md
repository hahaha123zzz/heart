# Q2 窗口 B：路径绑定、引用去重、原图与发布验收

日期：2026-10-19/20。分支：`main`。范围：Q2.10、Q2.9、Q2.4、Q2.5、Q2.6。没有修改 Q3 文件 `agents/agent_loop*.py`、`agents/q3_tools.py`、`agents/quality_checker.py`、`agents/reply_budget.py`。

## 1. Q2.10 普通问答/选区学习绑定真实路径

### 实现

- `knowledge.course_navigation.bind_result(result)`：从真实 `selection_ref`/`pdf_references` 的章、节、原文范围绑定目录游标；位置唯一时返回 `status=ready`，跨小节或无法唯一匹配时返回 `status=clarify` 和候选，不猜下一目标。
- `TaskService` 在回答 `answered` 且学习记录 `committed` 后绑定游标；绑定只读目录，放在写事务之外。普通概念问答和 PDF 选区都走同一绑定。
- 自然表达进入导航：`下一部分`、`下一步`、`继续`、`接下来`、`继续学习`、`好的，继续`。保留原对象：`下一步推导`、`下一步证明`、`继续这个例子`、`继续刚才的证明`、`继续讲刚才的` 不当作教材推进。
- 无路径时返回澄清；路径末尾明确结束；`course_navigation` 仍不增加 `covered` 或掌握分。
- `pdf_selection_tutor` 成功保存后补 `memory_commit`，使选区回答与普通回答使用同一提交/绑定条件。

### 验证

离线 `tests.test_course_navigation` 25 项通过，新增覆盖自然下一部分、真实目录绑定、跨节澄清、普通问答接续。

真实模型/本地任务链路：`.runtime/course-navigation/20261019T152950Z-399552/report.json`，三组 8 轮全部通过：

| 场景 | 轮次 | 实际目标/模式 | 结果 |
| --- | --- | --- | --- |
| 显式章节 | 学习第一章 | `ch1:s1:b6` / start | answered，质检通过，2 个 PDF 引用 |
|  | 继续下一个知识点 | `ch1:s1:b20` / topic | answered，质检通过 |
|  | 没听懂，请换个说法 | `ch1:s1:b20` / repeat | answered，质检通过 |
| 普通问答 | 请解释教材里的自变量 | `ch2:s2:b34` / bind | answered，3 个 PDF 引用，绑定真实小节 |
|  | 我懂了，下一部分 | `ch2:s2:b42` / next | answered，目标“操作性自变量” |
|  | 继续 | `ch2:s2:b44` / next | answered，目标“选择性自变量” |
| 选区 | 解释选中的自变量 | `ch2:s2:b34` / bind | answered，2 个 PDF 引用 |
|  | 我懂了，下一部分 | `ch2:s2:b42` / next | answered，未再次圈选 |

三轮 `mastery=0.5`、`covered=false`、`explained=true`；正式索引 SHA 未变。

真实页面（隔离端口 8010、隔离库 `.runtime/q2-windowb-page2`）：

- 第一问“请解释教材里的自变量，不要出题。”：3 条引用，全部 `source_verified`，编号紧凑，实际范围唯一，正文编号无悬空。
- 第二问“我懂了，下一部分”：页面回答切到“操作性自变量”，1 条 `source_verified` 引用；服务端随后加载 `chapter=2, section=2` 阅读页。
- 页面无 `pageerror`；截图 `.runtime/q2-windowb-page2/page.png`，会话库 4 条消息。
- 第一次长页面脚本在刷新阶段浏览器被关闭，保留为失败；随后拆成两段完成上述流程。没有把失败运行改写成成功。

## 2. Q2.9 引用协议、去重与旧历史

### 实现

- `EvidenceBundle.publish` 的去重身份改为：教材文档、版本、原文块、实际起止范围、媒体类型；图像保留证据 ID。相同版本+相同实际范围只展示一份，正文编号、来源数组和结论绑定同步重映射；同一小节不同范围仍保留。
- 新引用记录增加 `textbook_release`/`release_status`/`release_ready`，与 Q2.5 发布身份同源。
- 既有 `references_for_display` 继续只对展示结果投影失效状态，不覆盖旧历史、不把旧记录伪升级。
- `web_api` 历史读取继续走同一投影；前端点击失效证据禁用跳转，保留旧协议标记。

### 验证

`tests.test_citation_publication` 16 项、`tests.test_grounded_citations` 14 项通过。新增“同版本同范围不同引句去重”和“新引用携带发布身份”测试。

真实页面：点击引用打开 `citation-grounding-v1`，版本 `840d14...`，页码 3；刷新后回答、来源和引用记录保持一致，页面无“旧引用”标记。点击的证据 ID 属于页面第二条回答的引用集合；没有伪造新版状态。

## 3. Q2.4 视觉资产/原图映射

### 实现

- 新增 `knowledge/source_visuals.py`，只读加载心理学课程 11 章 `assets.json`，校验文件 SHA、原教材源哈希、路径、章节/小节/块、引文标签和审核状态。
- `knowledge/figures.py` 在心理学课程下把合格原图/公式对象接入既有 `load_figures/get_figure/section_figures/retrieve_figures`；保留 `review_status`，PDF 接口按真实 MIME 返回；视觉请求使用真实 JPEG/PNG MIME。
- 过滤缺图占位条：44 个固定扁图（如 1688×58、809×50）标为缺口，不作为教材原图送出。
- 普通文本问题不再因为来源块带有 `asset_ids` 就附无关图片；明确图号/图/表/公式/示意问题才检索视觉对象。
- 明确图号但无可用原图时，`orchestrator` 返回 `visual_unavailable`，不以纯文字回答冒充看过图。

### 验证

- 当前真实资产：179 个可用原图（全部 `pending` 教师审核），44 个占位/缺图缺口，0 个文件缺失或哈希不一致。
- `tests.test_source_visuals` 3 项通过：章节/图号绑定、占位/缺失/源哈希缺口、JPEG MIME。
- 真实模型图 1-1 问题：`.runtime/q2-visual-live/report.json`，38.0 秒，`answered`，质检通过，`image_refs` 为 `image-01-0003`（图 1-1），回答描述液体守恒实验并引用 PDF；同时绑定 `ch1:s1:b92`。
- 页面第一版曾把占位图 `image-01-0001` 当作“表 1-1”附给普通文本问题，质检正确拒绝；该失败保留在 `.runtime/q2-windowb-page`。过滤后同一页面流程通过。

## 4. Q2.5 发布/索引/换版绑定

新增 `knowledge/course_release.py` 与 `scripts/check_course_release.py`：

- 绑定 11 章 `document.json`、PDF 版本、`assets.json`、检索索引 SHA 和原图统计，生成稳定 `release_id`。
- `validate(expected)` 在换版/索引变化时拒绝旧绑定。
- 当前报告 `.runtime/course-release/20261020T011725Z.json`：`status=staging`、`ready=false`、`release_id=8d3d6350...`、索引 SHA `2a052d6d...`。
- 明确缺口：179 个原图待教师审核、44 个原图缺失/占位/哈希异常、教材清单仍为 `staging`。没有把文件齐全冒充已发布。

## 5. Q2.6 检索验收

`scripts/check_local_rag.py` 扩展为 8 个真实检索案例，全部 `hybrid` 且 `rerank_status=applied`：

| 类型 | 查询 | 结果 |
| --- | --- | --- |
| 概念 | 什么是自变量 | 通过 |
| 比较 | 被试内设计和被试间设计有什么区别 | 通过 |
| 同义 | 随机化如何帮助控制无关变量 | 通过（随机化/额外变量） |
| 同义 | 操作定义是什么意思 | 通过（操作性定义） |
| 跨章 | 第一章的实验程序和第二章的自变量控制 | 通过（第 1、2 章均覆盖） |
| 图表/公式 | 差别感觉阈限DL公式中PSE是什么 | 通过（第 7 章 6 条来源） |
| 未命名 | 这个怎么理解 | 通过（不编造来源，明确空结果） |
| 教材外 | 火星表面玄武岩的晶体结构 | 通过（拒绝） |

报告：`.runtime/local-rag-checks/20261019T153313Z-ed820a/report.json`；索引前后 SHA 均为 `2a052d6d90624119c7bb10d445bcfb7c0a82306021f2af55ed29c71d23b0e7ef`。`tests.test_local_rag` 14 项通过，含索引换版、查询中变更、WAL、维度/向量错误和重排降级。

## 6. 回归与边界

- 最终相关回归 **129 项通过，227.133 秒**，包含导航、引用/证据、发布、原图、任务执行、检索、心理学预设/QA、任务上下文和质检。
- `node --check frontend/app.js` 通过；变更 Python 文件 `compileall` 通过。
- 未修改正式教材、正式索引、实际 `.env` 或 8000 服务；页面验收使用隔离 8010/隔离库，验收后已停止。
- 主工作区仍有 4,455 个教材删除、未跟踪 `knowledge/courses/`、数据库/运行产物；这些未提交。

未完成/仍需集成：

- Q2.1 的原 DOCX/PDF 解析、新摄取/切块、FAISS 持久化、全量发布仍未完成。
- Q2.3 的完整模型权重/文档签名绑定仍需补齐；当前只验证索引/PDF/资产哈希。
- Q2.7/Q2.8 的完整章导览、全章概述、覆盖状态与长路径恢复仍不完整；本轮只验证首章/下一目标/自然接续。
- Q2.9 原用户截图的实际请求/响应仍未取得；baseline 只复现相同配置分支。
- Q2.4 的 179 个原图均为 `pending` 教师审核；quality_checker 的提示词仍写“经审核 PNG”，该文件属于 Q3 范围，未在本窗口修改；集成时需统一审核状态文案。
- Q2.10 的选区页面重选/刷新恢复、Q3.7 循环接续和 Q5 长路径仍需联验。
- Q2.6 是 8 个案例的功能验收，不是人工标注的召回率/精度基准。

## 7. 需要集成窗口配合的接口

| 接口 | 用途 |
| --- | --- |
| `knowledge.course_navigation.bind_result(result)` | 从真实回答引用绑定 `ready`/`clarify` 目录游标；`TaskService` 已调用，Q3 循环可直接复用。 |
| `TaskContext.course_navigation` | 当前目标/模式/位置；Q3 需在循环前读取有效状态，不用旧轮快照。 |
| `knowledge.source_visuals.load_visuals/get_visual/visuals_for_section/stats/gaps` | 原图映射、审核状态和缺口。 |
| `knowledge.course_release.snapshot/validate/binding` | 发布身份、索引 SHA、换版拒绝；引用记录已带 `textbook_release`。 |
| `Figures` 心理分支 | `load_figures` 现在包含合格 `image-*`/`formula-*`；PDF 接口按真实 MIME。 |
| 共享文件 | `agents/task_service.py`、`orchestrator.py`、`main.py`、`llm/client.py`、`knowledge/grounded_citations.py` 有 Q2 改动，集成窗口合入前需按最新 `main` 复核。 |

未触碰 Q3 文件：`agents/agent_loop*.py`、`agents/q3_tools.py`、`agents/quality_checker.py`、`agents/reply_budget.py`。
