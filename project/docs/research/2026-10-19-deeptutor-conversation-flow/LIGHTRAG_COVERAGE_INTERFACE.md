# 跨章覆盖与关系上下文接口

日期：2026-10-21。实现提交：`2b79ddc434824510a6d296d5f6201bc3858b3e81`。供集成窗口采用，未改公共入口；没有切换正式服务。

## 1. 实际可调用接口

```python
from knowledge.lightrag.coverage import (
    CoverageNavigator, Requirement, requirements_for, semantic_selection,
)
from knowledge.lightrag.q3_adapter import (
    LightRagNavigator, ContextualRetrieveCourseTool,
)
from knowledge.lightrag.relationships import relationship_context, append_tool_context
```

`CoverageNavigator(navigator, *, question, select, judge, requirements=None, cancellation=None)`：

- `navigator` 是现有同步 search/resolve 边界，通常为 `LightRagNavigator(existing_q2_navigator, backend, course_id=COURSE, cancellation=token)`；后端仍固定 SDK/aquery_data、课程授权与候选签名。
- `question` 必须是本轮完整用户问题，不能只传模型改写后的工具query；原题保留“第一章的实验程序和第二章的自变量控制有哪些联系？”。
- `requirements_for(question)` 零模型解析显式章与和/与等比较表达，得到不可变 `Requirement(id, query, chapter_id=None, section_id=None)`。复杂指代/更多句法由现有Q3规划层传明确requirements；不支持的语句不会冒称已有完整覆盖。最多3对象，每对象描述最多300字符。
- `select(requirement, raw_source_refs) -> list[SourceRef]`：必须在各对象内调用项目已有Q2 `choose_evidence`，返回其真实精确引句，保留本轮Q2证据单元以供后续发布。不要在合并后再做一次不检查覆盖的全局选择，否则会重现丢失。
- `judge(requirement, selected_source_refs) -> {"source_ids": [...], "reason": str}`：可绑定 `lambda req, refs: semantic_selection(existing_llm, req, refs)`。允许空数组；必须都是提供的ID，重复/伪造/无效响应明确失败。核查实际引句是否直接提供对象内容，不以章节数量、关键词出现或模型常识算覆盖。
- `search(target=existing_target, query=tool_query, limit=N, preferred_types=()) -> list[SourceRef]`：与原导航器相同同步协议。多对象只临时替换检索范围，不修改传入target或Q2/Q5状态。单点保留原target、单次检索、沿用Q2选择，不增加规划/覆盖模型调用。
- `resolve(**kwargs)` 仍委托原导航；`report` 是只读用途的覆盖结果，`trace` 保留各阶段，`tool_context(final_tool_sources)` 返回有界覆盖/关联区块。covered仅表示对象原文可用，不是已教会、先修、重点或掌握状态。

失败和取消透传，不fallback。每对象初查一次，只对未覆盖对象最多补一次；最多6次后端检索，SDK同候选并发1。后端原生重试另按原SDK协议记录，不能把后端调用数当HTTP/模型次数。

## 2. Q2选择回调的接入点

完整工作示例已经在交付的 `scripts/serve_lightrag_acceptance.py` 的 `select_for_query` 与 `gate` 中真实运行，不是模拟协议：

1. 将 raw SourceRef 转成现有 `as_textbook_chunk` / 原项目TextbookChunk。
2. 对 `requirement.query` 调用 `knowledge.grounded_citations.choose_evidence(llm, query, chunks, settings())`。
3. 使用bundle.evidence的retrieval_source_index对应原Ref，SourceRef.source_id用Q2给出的evidence_id，document_id/version/quote/range仍取Q2证据单元。
4. location保留原SDK `sdk_chunk_ids` 和 `retrieval_source_id`，并更新到实际被选的source_spans、block/char范围；release身份/status/ready取既有Q2 binding。
5. 按evidence_id保留现有bundle单元；正式发布只用最终工具SourceRef集合重组现有EvidenceBundle并调用publish，不能把所有暂存候选都当正式证据。

接口没有新引入引用模型或编号算法。图谱不能补造页码、范围、引用或版本。示例服务的students.sqlite3只用于隔离验收；正式学生库不应由此服务打开。

## 3. 现有工具注册方式

```python
raw_navigator = LightRagNavigator(
    existing_q2_navigator, backend, course_id=COURSE, cancellation=token,
)
covered_navigator = CoverageNavigator(
    raw_navigator, question=original_user_message,
    select=existing_q2_select_to_source_refs,  # 集成窗口的上述Q2选择回调
    judge=lambda req, refs: semantic_selection(existing_llm, req, refs),
    cancellation=token,
)
registry = build_registry(
    # 保留调用方现有授权/作用域参数及其他extra_tools
    extra_tools=(*existing_extra_tools, ContextualRetrieveCourseTool()),
)
```

`existing_q2_select_to_source_refs` 是必须由集成窗口绑定的现有Q2选择回调，不是声称项目已导出的新函数；本窗口交付其完整实际实现与调用样例于隔离服务，未越界替换公共发布门禁。

`ContextualRetrieveCourseTool` 保留名称/definition、原父类检索/去重/来源预算/引用编号，持有同一RLock后附加独立区块，保持授权注册路径；未另建工具协议。通过既有extra_tools挂载，不修改全局main/TaskService/AgentLoop。不应仅将关系塞到last_result而不装载此后处理。

如果集成窗口选择直接在现有RetrieveCourseTool返回前加hook，则使用：

```python
result = append_tool_context(result, context.navigation.tool_context(result.sources))
```

同时保持原检索锁覆盖search与context读取，避免并行工具交换last_result。此共享调用者改动由集成窗口单独提交，本窗口未改该文件。

Q5 loop_binding存在时，宿主会构建 `Q5Navigator(search_fn=q5.search)` 覆盖传入navigator。因此需在Q3/Q5共用search边界绑定本协调器，保留Q5.resolve/当前路径；单传navigator不代表Q5已启用。显式插问只属于检索：不得根据report.covered触发record_explained、mark_understood或更新游标。完整回合的教学/插问判定须在集成窗口按现有Q5协议复验。

## 4. SourceRef与关系数据

原文仍在原工具 `sources` 字段。关联只在附加正文区块及 `metadata.retrieval_context` 中，schema为 `lightrag-associations/v1`：

- `associations[].kind` 区分entity/relationship；id保持SDK实体/关系身份，entity_ids保留端点。
- description是图谱生成摘要，永远evidence_eligible=false；不是教材精确引句。
- sdk_chunk_ids链接原始SDK块；source_links包含本轮实际Q2 source_id、document_id、version、chapter_id、source_spans、release身份/status以及对应SDK块。
- `linked_candidate_requires_claim_check` 仅表示有当前原文链接，不能据此断言整个关系描述已被原文支持；仍由外层现有事实/引用门禁核查。
- `requires_original_lookup` 只能提示补查；没有原文的关系不能生成引用卡、教材结论、先修关系或重点。
- 最多12项，关联JSON最多6000字符；描述320字符，每项最多3来源链接/12SDK块。omitted/description_truncated/各链接计数明确展示裁剪，不能将有界上下文称为全图导出。
- 覆盖与关联总附加JSON超过12000字符明确失败，不改变原文sources或分配引用号。SDK reference、metadata仍不生成证据卡。

有效链接也不能说明模型看过教材原图；沿用source_visuals/PDF既有校验及真实review状态。本轮不修改179项pending、44装饰排除与UX4像素消息链路。

## 5. 观测与故障

后端result.trace与导航器calls记录native_recall、original_mapping_input、original_mapping、scope_filter、rerank_threshold、limit；协调器trace记录object_scope、object_dedupe、semantic_coverage、balanced_limit、merged_dedupe和tool_output。

每条包含源/SDK块ID、章、document/version、原文范围、子问题、得分、接受与排除原因。Q2未返回理由时只标not_selected_by_q2，不能编造根因。保留原query与原问题，不能混用改写查询和完整句子做同一对照。

backend异常带lightrag_audit供适配器保存可得trace/Metrics，原异常类型/取消语义不变。模型错误cause链仅保留去凭据的类型/短消息；HTTP/usage缺失必须记未知，不估算费用。无来源/版本失效/SDK不兼容/后端故障不得静默改后端。

## 6. 本机复验命令

在 `E:\项目\heart-worktrees\lightrag-integration\project\integration\discrete-math-tutor`，先按LIGHTRAG_SWITCH_RUNBOOK.md安全注入相同模型与CUDA配置；不要复制密钥或打印.env。

```powershell
$py = '.venv-lightrag/Scripts/python.exe'
& $py -X utf8 -B scripts/serve_lightrag_acceptance.py --isolation .runtime/lightrag-acceptance-01 --port 18978
# 另一个终端，同一目录与$py：
& $py -X utf8 -B scripts/check_lightrag_coverage.py --output .runtime/lightrag-gap-coverage-20261021/matrix
# 有界专项：每次仍保留全部记录，不覆盖旧matrix
& $py -X utf8 -B scripts/check_lightrag_coverage.py --output .runtime/lightrag-gap-coverage-20261021/matrix --case cross_chapter --case missing_object --case q5_interjection
& $py -X utf8 -B scripts/check_lightrag_coverage.py --output .runtime/lightrag-gap-coverage-20261021/matrix --case overlapping_sources
$env:LIGHTRAG_ACCEPTANCE_HOST = (Resolve-Path .runtime/lightrag-acceptance-01/host).Path
& $py -X utf8 -B -m unittest discover -s tests -p test_lightrag_coverage.py -v
& $py -X utf8 -B -m unittest discover -s tests -p test_lightrag_q3_adapter.py -v
Remove-Item Env:LIGHTRAG_ACCEPTANCE_HOST
& $py -X utf8 -B -m unittest discover -s tests -p test_lightrag_backend.py -v
& $py -X utf8 -B scripts/check_lightrag_delivery.py --candidate .runtime/lightrag-proxy-nothinking/0a6096dc43a8829d48776cbcd0c583b6dc779bd6b450614b4bd20bd1d7f0e5ce --lock ../../docs/research/2026-10-19-deeptutor-conversation-flow/LIGHTRAG_DELIVERY_LOCK.json
```

真实矩阵调用模型，TLS失败会如实非零退出。它调用实际Q2选择/语义模型/现有RetrieveCourseTool，不生成正式回答；不使用旧宿主260字预算判断本轮检索质量。正式回答与页面必须在集成窗口最新稳定宿主另验，保留本文原题和旧失败UUID。

本轮不需要、也没有运行全书重建命令。保留已封存候选、原冻结输入及SDK缓存，正式激活和回退仍按原操作预案由集成窗口执行。

## 7. 已提交宿主兼容检查

a3b653e3ba968242755c01781117d13203ca964c已包含前批LightRAG包；隔离测试明确把本分支knowledge.lightrag包放在该包路径首位，仍使用a3b653e的SourceRef/ToolContext/工具协议和Q2。兼容修正31adf968cfbc9a5490905867fc18eef194524d90，15+8项通过；这只检查接口，不代表新宿主真实回答或页面。正式集成按Git提交更新同一后端包；路径优先规则仅用于隔离验收。
