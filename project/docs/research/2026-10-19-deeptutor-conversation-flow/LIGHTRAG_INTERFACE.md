# LightRAG 独立后端接口

本窗口基线 `9c746e28173f7dcfeef34e8d6134dab7e58c5286`；历史上核对过 Q3/Q4 提交 `f886144`（只作契约参考，当前稳定集成基线仍待集成窗口确认），未提交的 agent_loop_service/task_service/test_q3_q4_integration 不纳入。本后端不要求从其他工作区复制未提交代码。

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
- `graph_context`：实体/关系摘要，仅背景，`evidence_eligible=False`。不能按这些摘要生成精确引文。original_source_ids 关联本次返回的真实原文 source_id，空列表表示本次没有返回对应原文；该关联不核验摘要整句语义。
- `references` 与 `metadata`：独立元信息，不能产生证据卡。
- `input_signature/usage/rerank_status`：版本与实测运行信息。原文重排复用 Q2 的 BGE 模型与 0.15 门槛；该门槛未经概率校准。

返回的 SDK chunk ID 只存在 `location.sdk_chunk_ids`，不冒充 Q2 的教材 block ID。

## Q2 引用发布

```python
bundle = backend.prepare_evidence(question, result, host_llm)
# Q3 使用 bundle.sources 生成正式文本，再用同一 bundle 发布：
body, published_sources, references = bundle.publish(generated_text)
```

`prepare_evidence` 调用现有 `choose_evidence/settings`；定位、引句校验、PDF 版本、编号去重、高亮与裁图继续由 Q2 EvidenceBundle 处理。`source_verified` 只证明原文存在，不代表教师审核或回答语义已通过。

历史 Q3 契约参考中的卡片生成代码会自行拼装 section/page evidence，不能直接把本后端原始候选当已核验证据。集成窗口应接上述 bundle，并让正文和引用卡统一发布；本窗口不改公共生成/页面流程。

## Q3 可选接线

`knowledge.lightrag.q3_adapter.LightRagNavigator(base_navigator, backend, course_id=...)` 只包装既有导航器；`resolve` 完全委托 Q2。精确 `ch...` 目标或带 block_start 的目标继续调用 Q2 search/read_target，不用图谱推断教学顺序。一般概念检索走本后端。该适配当前仅为本工作树 .runtime/drafts/q3_adapter.py 未提交草稿，待稳定集成基线确认后再适配、验证并独立提交；未注册、未开启正式入口。

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

Q2固定交付 `95b956a` 已接纳。规范输入snapshot_id为 `0a6096dc43a8829d48776cbcd0c583b6dc779bd6b450614b4bd20bd1d7f0e5ce`，325文件；原服务候选目录2331025f…只是历史SDK工作区身份，新服务候选位置见下文。实际来源为本窗口 `.runtime/q2-delivery-95b956a/snapshot/course`，不再读取可变主目录教材。44项确认装饰按disposition排除；未解决知识图缺口0，179项pending不变。

`search(..., cancellation=...)` 接受Q3 `is_cancelled()` 对象，查询中取消会等待SDK worker清理；Q3适配将async取消映射回现有Tool CancelledError。外层取消awaiting task同样透传。

表格与图片额外使用SDK原生chunk.sidecar.refs→sidecar.self_ref→冻结blocks.json→Q2 block/asset身份映射。表格恢复原始单元格，不把摘要当原文；原图单列visuals并保留pending，不把图像分析文字冒充精确引句。


## 实测服务与索引策略

原服务余额不足，原候选保留为partial_failed。用户明确选择新服务后，使用https://cn.chatapi.app/v1的deepseek-flash建立独立候选。凭据仅由当前测试进程环境注入，原项目.env未改，不把测试配置当正式服务切换。

有效候选由build-10启动并在build-11使用CUDA同权重恢复，位置`.runtime/lightrag-proxy-nothinking/0a6096dc43a8829d48776cbcd0c583b6dc779bd6b450614b4bd20bd1d7f0e5ce`，SDK workspace `deeptutor_426733019d24d665`。API支持JSON/真实原图输入/SDK长文本抽取请求，已实测thinking=disabled；该参数连同8192输出上限、0.1温度、endpoint和模型名构成模型身份。旧候选或不同策略不能被偷偷恢复为同一索引。

同一进程的OPENAI_BASE_URL、DEEPSEEK_API_KEY/OPENAI_API_KEY、DEEPSEEK_MODEL、OPENAI_VISION_MODEL必须与候选策略一致，凭据不得写入Git或报告。`--env-file`仅补充缺失配置，不覆盖进程已注入的测试配置。集成窗口需要通过自己的安全配置接入；本窗口不交付或复制密钥。

`check_lightrag_completion.py`从原生GraphML、KV及向量存储核对实数，区分计划块、实际文本块、向量块和正文/表格/图片块族；partial_failed也能输出核查报告，但whole_book_complete=false。失败块清单不能算已摄取原文，重复出现的同一原图不能算新的唯一资源。

当前专用.venv-lightrag安装独立SDK和适配依赖，基础包只读借用现有宿主site-packages；没有向其他窗口环境安装或改包。这是本机执行环境，不是完全自包含的部署环境。实际版本在依赖快照记录，部署应重新创建环境并复核。


本机运行配置使用 RAG_EMBED_DEVICE=cuda、RAG_RERANK_DEVICE=cuda，复用宿主设备校验；CUDA 不可用会明确失败。CPU/CUDA 同一权重的少量输入数值兼容检查已通过，设备不改变教材版本或模型权重签名。远程模型抽取与摘要仍为 API 调用，不使用本机 GPU。


## 真实查询已知限制

SDK检索预算显式设为实体2,000、关系2,000、总计10,000 tokens，保留教材原文空间；top_k=20、chunk_top_k=12，SDK内重排关闭，宿主BGE重排保持启用。五种模式已真实运行，结构化调用不生成答案。

当前章/节限制在图谱全局召回后过滤，不保证覆盖所有指定范围。真实跨第一、二章问题漏检第一章，第二章概述缺第1、3、5节；这两项未通过。集成窗口须让Q3按已有Q2精确章/节导航分解并读取全部目标，不能把有限检索结果当全章材料。当前未交付该公共流程，不新增另一套导航或AgentLoop。

Q2发布函数实际返回三项：正文、发布来源、引用。真实原文测试已验证同版本、页码、高亮、编号和裁图；这只是原文发布断言，不是Q3正式答案或页面验收。
