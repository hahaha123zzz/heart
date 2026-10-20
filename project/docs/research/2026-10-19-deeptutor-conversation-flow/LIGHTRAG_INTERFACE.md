# LightRAG 独立后端接口

本窗口基线 `9c746e28173f7dcfeef34e8d6134dab7e58c5286`；已核对 Q3/Q4 稳定集成提交 `f886144`，未提交的 agent_loop_service/task_service/test_q3_q4_integration 不纳入。本后端不要求从其他工作区复制未提交代码。

## 输入与权限

数据权威仍为 Q2。现有 `knowledge/courses/experimental-psychology-3` 尚未跟踪，课程状态 `staging`。独立快照保存在候选目录 `input/`，文件清单、SHA-256、来源路径与版本保存在 `input_manifest.json`。正文、PDF、DOCX、资产、公式和课程清单变化均拒绝混用。`crops/`、`sample/` 是派生产物，不参与教材输入版本。

服务端必须以实际账户权限提供 `authorized_course_ids`，不能采用模型传入的授权列表。候选只能显式 `allow_candidate=True` 用于验证；本窗口没有正式激活指针。

```python
from knowledge.lightrag.retrieval import LightRagBackend
backend = LightRagBackend(candidate_path,
    authorized_course_ids={course_id}, allow_candidate=True)
result = await backend.search(question, course_id=course_id,
    mode="hybrid", limit=6, chapter_id=None, section_id=None)
chunks, result = backend.retrieve(question, course_id=course_id)
```

检索模式：`naive/local/global/hybrid/mix`，默认 `hybrid`。固定 SDK 1.5.7 已实际检查 `LightRAG.aquery_data`，只取结构化检索结果；`answer` 恒为空。关键词抽取可能调用模型，正式答案由 Q3 生成。索引失败、未完整就绪、版本不符、无权限、配置缺失、SDK 错误均抛出明确异常；无检索结果返回 `status=no_evidence`，不回退其他检索器。

## 结构化结果

- `sources`：SDK chunk 与冻结 Q2 原文的连续交集；带 `source_id/document_id/version/chapter_id/section_id/text/quote/page/image_refs/location`。`page=None` 表示尚未做 Q2 PDF 精确定位，不编造页码。
- `location`：原文 block、字符范围、`source_spans`、原始素材 ID 与 `sdk_chunk_ids`；`evidence_status=candidate_requires_q2_pdf_verification`。
- `graph_context`：实体/关系摘要，仅背景，`evidence_eligible=False`。不能按这些摘要生成精确引文。
- `references` 与 `metadata`：独立元信息，不能产生证据卡。
- `input_signature/usage/rerank_status`：版本与实测运行信息。原文重排复用 Q2 的 BGE 模型与 0.15 门槛；该门槛未经概率校准。

返回的 SDK chunk ID 只存在 `location.sdk_chunk_ids`，不冒充 Q2 的教材 block ID。

## Q2 引用发布

```python
bundle = backend.prepare_evidence(question, result, host_llm)
# Q3 使用 bundle.sources 生成正式文本，再用同一 bundle 发布：
body, references = bundle.publish(generated_text)
```

`prepare_evidence` 调用现有 `choose_evidence/settings`；定位、引句校验、PDF 版本、编号去重、高亮与裁图继续由 Q2 EvidenceBundle 处理。`source_verified` 只证明原文存在，不代表教师审核或回答语义已通过。

当前 Q3 稳定分支的卡片生成代码会自行拼装 section/page evidence，不能直接把本后端原始候选当已核验证据。集成窗口应接上述 bundle，并让正文和引用卡统一发布；本窗口不改公共生成/页面流程。

## Q3 可选接线

`knowledge.lightrag.q3_adapter.LightRagNavigator(base_navigator, backend, course_id=...)` 只包装既有导航器；`resolve` 完全委托 Q2。精确 `ch...` 目标或带 block_start 的目标继续调用 Q2 search/read_target，不用图谱推断教学顺序。一般概念检索走本后端。该文件单独提交，集成窗口自行注入；未注册、未开启正式入口。

工具返回 SourceRef 仍是候选；正式发布必须遵循上面的 Q2 bundle 流程。检索与 Q3 工具调用测试不等于 AgentLoop 正式生成和页面验收。

## 全书构建与恢复

```powershell
& .venv-lightrag/Scripts/python.exe -X utf8 -B scripts/build_lightrag_book.py `
  --source <Q2教材目录> --env-file <原项目.env路径>
# 恢复指定的已接受候选，避免误建新版本：
& .venv-lightrag/Scripts/python.exe -X utf8 -B scripts/build_lightrag_book.py `
  --source <相同Q2目录> --env-file <同一配置路径> --resume-candidate <候选目录>
```

在该候选目录创建 `cancel.request` 触发取消；确认 `progress.json.state=cancelled` 且该构建进程退出后，移除该文件并使用 `--resume-candidate`。保留冻结输入、sidecar、SDK 状态与缓存。进程重启恢复和失败重试分别走 SDK 原协议，不手工将 FAILED 改成 PENDING。

文档级 `processed`、非空文本块及实体/关系统计均成立才标 `candidate_complete`；部分失败不产生完整标记，不更新正式索引。`candidate_complete` 也不代表教材已发布、图片审核完成或多模态完整。


## 最新数据依赖

Q2固定交付 `95b956a` 已接纳。规范输入snapshot_id为 `0a6096dc43a8829d48776cbcd0c583b6dc779bd6b450614b4bd20bd1d7f0e5ce`，325文件；候选目录ID保留2331025f…只是原SDK工作区身份。实际来源为本窗口 `.runtime/q2-delivery-95b956a/snapshot/course`，不再读取可变主目录教材。44项确认装饰按disposition排除；未解决知识图缺口0，179项pending不变。

`search(..., cancellation=...)` 接受Q3 `is_cancelled()` 对象，查询中取消会等待SDK worker清理；Q3适配将async取消映射回现有Tool CancelledError。外层取消awaiting task同样透传。

表格与图片额外使用SDK原生chunk.sidecar.refs→sidecar.self_ref→冻结blocks.json→Q2 block/asset身份映射。表格恢复原始单元格，不把摘要当原文；原图单列visuals并保留pending，不把图像分析文字冒充精确引句。
