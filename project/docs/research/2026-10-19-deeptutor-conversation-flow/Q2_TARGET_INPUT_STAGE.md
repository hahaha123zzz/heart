# Q2 目标质量、教材输入与来源接口收尾

日期：2026-10-20。基线提交：`9c746e28173f7dcfeef34e8d6134dab7e58c5286`。本记录按用户最新范围执行，不重新宣布 Q2 整阶段完成，不建设第二套学习路径或 LightRAG 后端。

## 1. 目标质量

此前 `outline()` 把正则匹配到的短编号段落都当作标题，再直接选择叶子；原 `_group()` 在累计约 2,000 字后停止。这会把教材介绍、法律引用中的编号和实验操作句变成目标，也可能提前切断目标正文。

本轮新增 `knowledge/teaching_targets.py`，从原 DOCX 的实际 `outlineLvl`、样式继承和原段落位置核对解析块，不以编号本身作为标题证明。目标沿用真实标题和实际块序列；教材组织介绍及其子分支不作为专业知识点；编号正文、描述句、错位标题和无正文标题分别审计。段落范围以真实同级/上级标题为界，拓展阅读等附加材料单列，不吞入默认目标；读目标时按完整段落控制材料量，不截断半个段落。短泛称使用父标题限定，不把具体问题标题硬编码成另一个概念。

全 11 章检查结果见 [目标质量清单](Q2_TARGET_QUALITY_AUDIT.json)：

- 旧算法 512 个目标，当前 461 个；各章均有真实目标。
- 711 个编号候选：461 个目标、176 个组织层级标题、1 个教材介绍、3 个介绍子项、70 个编号正文。另查原件正式标题，无遗漏的未识别编号形式。
- 77 条需人工确认：74 条介绍/编号正文，另 3 条较长或含分句的正式标题需确认教学粒度与命名。它们不是 77 个已确认错误，也不表示其他目标已获教师审核。
- 第一章下一目标由 `ch1:s1:b20`“主要讲心理学实验方法的教材”改为 `ch1:s1:b81`“什么是科学”。原教材介绍仍保留在教材解析输入中，没有删除原文。
- `下一步推导 / 继续这个例子` 仍绑定当前目标；不把它们当成下一知识点。

`target_schema=word-heading-targets-v1` 纳入路径版本，防止算法改变范围后仍静默接受旧游标。`source_title`、`source_block_ids` 保留原标题和实际来源块。461 个是目录型候选教学目标，不是自动生成、已审核的先修关系或 Mastery 路径。

## 2. 未提交导航补丁对账

“3 失败 / 1 错误”缺少原命令及日志，现有 Q2 执行记录不能核实该固定数量，用户也已明确不要求复现数量。没有为凑数量修改实现。

`activity`、更严格的绑定与版本校验由本窗口在本次任务前半段加入，不属于 `9c746e2`，也不是原样迁入的 DeepTutor 代码：

| 改动 | 用途与调用方 | 本次处理 |
| --- | --- | --- |
| `previous_cursor()` 附加 `activity` | 从最新有效任务收据读取待答/点内状态；现有 TaskService 调用 | 作为已有补丁对账并保留；不新增状态库、评分或循环。 |
| `resolve(..., activity=None)` | 可选教学活动；缺省读游标字段；当前 TaskService 原调用不变 | 保留参数兼容和同点保护；Q3 负责统一活动状态、步骤和作答执行。 |
| `bind_result()` | 核对文档身份/PDF 版本、实际文件哈希及真实目录位置；不唯一澄清 | 保留返回形状；无版本的历史不伪升级。候选标题或章号可用于澄清，不要求再次圈选。 |
| 导航/课程版本 | 目录、解析块、原 DOCX、原图登记及字节、PDF 定位/版本变化使旧绑定失效 | 本次来源接口范围；没有迁移正式数据或重建索引。 |
| Orchestrator、reply_budget、扩展多轮运行器 | 前半段为区别继续与重述所写的候选联动 | 留作独立差异交集成窗口，不混入本次目标/来源代码提交；本轮不再扩展编排。 |

联动差异见 [集成候选补丁](Q2_CONTINUATION_INTEGRATION_CANDIDATE.patch)，SHA256：`dd924bb6738ed42ccef6c4872777d52ae2eaa3ab7d6d4b1fcc3157e279ad443b`。包含 `orchestrator.py`、`agents/reply_budget.py`、`scripts/check_course_navigation.py` 和一个独立预算测试；不包含 main.py、TaskService 或前端。该差异已存在于当前主工作树，`git apply --reverse --check` 核对通过，**不要在本工作树重复应用**。集成窗口在没有这些差异的检出上审阅、合入并统一验收；本次不代替它决定编排。

开始时已保存相关文件哈希。`main.py`、`agents/task_service.py`、`frontend/app.js`、`web_api.py` 与开始时一致，未接管 Q3/Q4/Q5 或公共前端。主工作区其他已有改动、教材删除与计划修改均保留。

## 3. 当前工作树验证及失败

所有以下测试均针对**当前混合工作树**；没有以 detached 提交树通过替代工作树通过。基线与本次代码的只读算法对比不算测试通过证据。

```powershell
$env:TUTOR_COURSE='experimental-psychology-3'
$env:PYTHONIOENCODING='utf-8'
.venv/Scripts/python.exe -m unittest tests.test_teaching_targets tests.test_course_inputs tests.test_q2_closeout tests.test_course_navigation tests.test_citation_publication tests.test_course_release tests.test_source_visuals tests.test_grounded_citations tests.test_conversation_context tests.test_quality_guard tests.test_task_execution -v
```

结果：**132 项通过，154.632 秒**。原始日志：`project/integration/discrete-math-tutor/.runtime/q2-target-input/worktree-regressions.log`。覆盖目标提取与段落范围、11 章冻结/校验、导航及绑定、来源换版、原图缓存失效、引用发布、Q1 追问、任务执行及质检。

这是包含上述未采用编排候选的工作树结果，不冒称本次代码提交的干净检出结果；本次没有验证另一 worktree 或 detached 树。独立候选预算测试不纳入这 132 项。

真实模型、本地 TaskService、独立 SQLite 两轮：`.runtime/q2-target-input/target-live/report.json`，两轮均 `answered`、质量检查通过、有实际 PDF 证据，目标分别为 `b6` 和 `b81`。报告 SHA256：`53c1f748f53645d37383f2f6972d43bc7f804f203c900d4d65a2a978a9bff6a0`。索引前后 SHA 均为 `2a052d6d90624119c7bb10d445bcfb7c0a82306021f2af55ed29c71d23b0e7ef`。这只是新目标的实际生成验证，不是完整教学循环验收。

本轮实际失败均保留：

- `navigation-first.log`：增加原件标题校验后，旧版本测试夹具用普通字节冒充 DOCX，触发 `BadZipFile`。版本测试改用显式标题解析替身，真实 DOCX 样式另用 ZIP/XML 夹具验证；换版原件不再暴露有效目标。
- `targets-input-tests.log`、`target-fixtures.log`：同一版本夹具把“真实教材目标”写成标题，被教材介绍分类正确排除，出现空列表。改用专业标题“实验变量”，没有放松分类器；`target-fixtures-fixed.log` 8 项通过，再运行完整 132 项回归。
- 范围收窄前的多轮与页面记录另存 `.runtime/q2-closeout-20261020`，不替代新目标的验收，不把前半段固定措辞通过宣布为 Q3/Q5 完成。

## 4. 全书固定输入及新 worktree 获取方式

已实际创建并验证本机冻结快照：

```text
E:/项目/heart/project/integration/discrete-math-tutor/.runtime/q2-target-input/full-book-v2
├── input_manifest.json
└── course/  # 全 11 章原件及解析输入，不含密钥或旧 RAG 索引
```

共 325 个文件、102,504,640 字节；最终清单使用 UTF-8/LF，v1 原始快照保留，v2 与 Git 中清单字节一致。原 DOCX、生成 PDF、document.json、chunks.jsonl、text.txt、资产登记、原图、公式与位置 sidecar 均逐项列出路径、长度和 SHA256。每个原图均核对与 DOCX package part 字节一致。没有单章试点前置条件。

- `snapshot_id`：`0a6096dc43a8829d48776cbcd0c583b6dc779bd6b450614b4bd20bd1d7f0e5ce`
- [完整全书输入清单](Q2_FULL_BOOK_INPUT_MANIFEST.json)，清单 SHA256：`02b3a221c1d795d5894b1810332d0762f2ce7276b03cd73ba7bb49362cf2fc9d`
- 正式旧索引只记录现有哈希，`included=false`；它不是 LightRAG 的新图谱输入。

冻结与复核命令（再次冻结须使用新输出目录，拒绝覆盖）：

```powershell
.venv/Scripts/python.exe scripts/freeze_course_inputs.py --output .runtime/q2-target-input/full-book-v3
.venv/Scripts/python.exe scripts/freeze_course_inputs.py --verify .runtime/q2-target-input/full-book-v2
```

教材目录未跟踪，`git checkout` 不会带来教材。集成窗口可从上述**实际存在**的快照复制到新 worktree，或将整个快照目录传至另一台机器；本窗口没有替其他 worktree 执行复制。示例由接收方在其环境执行，目的地须不存在：

```powershell
$snapshot = 'E:/项目/heart/project/integration/discrete-math-tutor/.runtime/q2-target-input/full-book-v2'
$targetCourse = '<接收方新 worktree>/project/integration/discrete-math-tutor/knowledge/courses/experimental-psychology-3'
if (Test-Path -LiteralPath $targetCourse) { throw '目的地已存在，先由该窗口核对，不覆盖' }
if ((Get-FileHash -LiteralPath "$snapshot/input_manifest.json" -Algorithm SHA256).Hash.ToLower() -ne '02b3a221c1d795d5894b1810332d0762f2ce7276b03cd73ba7bb49362cf2fc9d') { throw '清单不匹配' }
Copy-Item -LiteralPath "$snapshot/course" -Destination $targetCourse -Recurse
$manifest = Get-Content -LiteralPath "$snapshot/input_manifest.json" -Raw | ConvertFrom-Json
foreach ($file in $manifest.files) {
  $actual = Get-FileHash -LiteralPath (Join-Path $targetCourse $file.path) -Algorithm SHA256
  if ($actual.Hash.ToLower() -ne $file.sha256) { throw "输入不一致：$($file.path)" }
}
```

仅把脚本、清单和说明提交 Git；教材原件、快照文件、测试库、运行产物和凭据不提交。LightRAG 窗口可立刻以全 11 章文本、表格、公式开始独立候选建图，读取资产的 disposition，不把构图范围退回单章。

## 5. 179 个 pending 与 44 项过滤记录的逐项结论

179 个可用原图均为 `pending`，这表示字节和源映射可核对、但**尚未教师审核**，不等于已批准的知识证据。允许作为全书候选处理输入，不能直接发布为已审核图像知识。

历史记录中的 44 个“缺图/占位缺口”实为四种装饰各重复 11 次。已查看四种原图，并对每个资产核对 DOCX 嵌入字节；逐项信息在全书清单的 `assets` 中：

| 分类 | 数量 | 恢复结论 |
| --- | ---: | --- |
| 拓展阅读装饰横条 | 11 | 原字节齐全；非知识图，不需要恢复成实验图 |
| 概念术语栏头 | 11 | 同上，不能用临近“表1-1”标签冒充表格原图 |
| 本章重点栏头 | 11 | 同上 |
| 推荐阅读栏头 | 11 | 同上 |

这不是把缺口抹去：`source_visuals.gaps()` 仍保留 44 项，并增加 `classification=decoration`；`stats()` 保留 `gaps=44`，新增 `filtered_decorations=44 / unresolved_gaps=0`。无法识别的尺寸异常仍标 unresolved，不拿占位图补证据。目前这 44 项中没有证据支持“丢失了 44 张实验图”的说法；也没有生成、重画或编造替代图。

当前 `course_release` 仍为 `status=staging / ready=false`，实际阻塞项是 179 图待教师审核及清单尚未发布。44 个确认的装饰排除项另行统计，不再错误写成 44 个丢失实验图。文件齐全与候选建图成功都不构成发布就绪。

## 6. 稳定接口与职责

| 接口 | 保持/增加 | 责任边界 |
| --- | --- | --- |
| `bind_result(result)` | 仍返回 `None/ready/clarify`；严格核对来源版本；并列不猜选 | 当前 TaskService 回答提交后调用；历史缺版本只澄清，不升级。 |
| `TaskContext.course_navigation` | 类型仍为 `dict | None`，不修改模型；原 ID/章/节/位置/模式字段保留 | 学生/会话/任务隔离仍归 TaskService；Q3 消费当前状态，不创建第二套路径库。 |
| `outline / validate / read_target` | 增加 `source_title/source_block_ids/target_schema/source_version`；返回 TextbookChunk/source_spans 保持 | 明确目录目标由 Q2 提供；旧游标失效后重新确认，不按位置静默升级。 |
| `source_visuals` | 原 load/get/section/block/stats/gaps 接口保留；新增分类统计、发送前缓存换版核验 | LightRAG 排除 decoration/unresolved，pending 保持审核语义；原图入口调用方仍用现有 Figure 接口。 |
| `course_release.snapshot/validate/binding` | 保留返回主字段；增加源文件与清单身份；validate/binding 刷新 | `snapshot` 是可缓存读数，换版门禁用 validate；staging 不发布。 |
| 引用发布/历史投影 | 共用来源身份；版本失效只作展示投影，不改原历史 | 前端、历史、主入口接线仍归集成窗口；本轮不改公共接线。 |

全章概述需要覆盖该章所有节和实际来源范围，不能用首个目标或目标列表假装概述。长期路径身份、插问恢复、并发/租约与下一动作编排由 Q3/集成窗口统一；目标驱动规划、正式评分、复习和掌握资格由 Q5 负责。LightRAG 关系图不自动成为教学顺序。

未完成：77 项人工确认、原图教师审核、全章概述、长期路径与 Q5 正式评分、LightRAG 实际建图/检索/发布及全书教学质量人工验收。没有切换正式服务或替换正式索引。
