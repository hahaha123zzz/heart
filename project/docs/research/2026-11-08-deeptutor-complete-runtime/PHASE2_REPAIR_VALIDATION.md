# 第二部分：四处接线缺口修复与验证

> 最新复测：[PHASE2_MIXED_CHAIN_REPAIR.md](PHASE2_MIXED_CHAIN_REPAIR.md)。出题后翻第 2 页、applied 回执及刷新恢复题卡已通过真实模型验证；其余能力仍未全部验收。

> 2026-11-09 真实模型补验：[PHASE2_LIVE_VALIDATION.md](PHASE2_LIVE_VALIDATION.md)。教材引用、题卡和独立阅读通过；出题后切换阅读仍出现错误页码，尚未全部通过。

日期：2026-11-08。对应修复前记录：[PHASE2_SOURCE_AUDIT.md](PHASE2_SOURCE_AUDIT.md)。

结论：本轮已修复并验证该复核提出的四处缺口。**这不等于研究、掌握学习、音频、动画等其余能力已全部验收。** 已隐藏的 31 个无关工具继续隐藏。

## 1. 阅读缓存与材料归属

- 删除 course_reading 中按 course_id 共享的进程缓存。
- 每次在真实用户/工作区作用域内使用原版 ReadingStore；按实际文件内容哈希幂等导入，不按 filename 判断版本。
- 核验 PDF 实际 SHA256 与宿主正式文档版本；换版后生成新材料 ID。
- 已有材料按 content_id 复用，保留用户修改的阅读标题与原生批注存储；不删除旧版本批注。
- 阅读请求采用宿主当前章节选择材料，chapter_id/document_id 由桥接层消费，原生 viewport 只接收原生契约字段。

验证：真实临时 PDF + 原版 ReadingCatalogStore/ReadingStore，覆盖跨用户、同名换版、重复导入、保留标题与版本篡改拒绝。

## 2. RAG 正式引用及历史保存

- rag 的原始教材块经过已有 choose_evidence、原文存在性和坐标核验，返回正式 SourceRef 与 evidence。
- 来源带稳定文档 ID/版本与证据 ID；同一原生回合内引用编号稳定，多次检索不会把同一编号分配给不同证据。选区已有编号作为检索起始偏移。
- 保留原始完整块供原版 read_source 补读，不把短摘录冒充完整材料。
- 宿主将原生正式来源接入原有 _publish_gate/EvidenceBundle，不放宽来源检查；换版或编号冲突会拒绝。
- pdf_references/textbook_sources 与正式回复一起保存到历史引用记录，刷新后仍可恢复来源。

验证：读取本机正式教材 SQLite 的真实块，通过当前 PDF 引句与坐标发布，得到非空 PDF 引用；另测编号稳定、换版/冲突拒绝和历史保存交接。

测试范围说明：该 PDF 发布测试隔离了全课程媒体清单元数据，避免重复扫描全部媒体；PDF、引句与坐标核验使用真实实现。生产代码的全课程发布检查保持原有行为，本轮不计为全媒体发布重新验收。

## 3. 出题结构与完成状态

- 保留原生 summary.results 中的题目、类型与选项，接入实际聊天展示组件；复用上游 extractQuizQuestions。
- 正确答案、解析、内部题目元数据不进入公开题卡，也不把可能包含答案的原生 response 当作公开题目正文。
- summary.success/completed/failed 与题目数量不一致时返回 incomplete_answer，不再仅因 native turn completed 就宣称出题完成。
- 题卡与公开结构随对话保存，可在历史恢复。正式测评评分仍属于现有受控流程，本次没有新增客户端评分或放宽答案权限。

验证：真实宿主 → 原版 DeepQuestionCapability → 原版 QuestionPipeline 的探索/规划/逐题阶段 → 安全投影 → 题卡。模型仅为本机受控 OpenAI 协议服务，能力与流水线为真实实现。

## 4. 阅读跳转与页面回执

- 从持久原生 tool_result 中提取 reader_goto 的真实指令，在原生用户作用域内映射到当前教材文档/版本。
- 宿主复用既有 ReaderGotoTool 的文档、页码、引文与任务绑定核验，指令随正式结果保存。
- 通过既有 reader_action SSE 与 TutorReaderActions 执行跳转；沿用既有 applied/rejected 回执接口。
- 重放结果标记 reader_action_replay，历史/网络恢复不会重复移动阅读器；正式保存失败不会提前执行页面动作。

验证：Playwright 在实际聊天表单中提交阅读请求，PDF 实际到达第 2 页；/reader-receipt 返回 applied，文档 ID/版本/页码与浏览器位置一致，无脚本错误。

## 5. 验证结果

| 检查 | 结果 |
| --- | --- |
| 相关完整回归 | 36 项通过；随后新增的 PDF 版本边界随 5 项阅读测试再次通过，合计 37 个不同用例 |
| 真实 HTTP 链路 | 22 项通过，报告 .runtime/native-chat-chain/20261108-232449/report.json |
| 实际浏览器 | 题卡渲染/私有答案过滤、真实 PDF 跳转与回执两项通过，errors=[] |
| 阅读动作前端守卫 | node tests/reader-actions.cjs 通过 |
| 前端构建 | 19 个固定上游源文件，53 个构建资源，构建成功 |
| 静态检查 | 改动 Python/JS 语法与 git diff --check 通过 |

浏览器证据：.runtime/native-delivery-browser/20261108-232706/browser.json 与 delivery.png。

## 6. 当前边界

本轮使用隔离数据库、隔离原生 home 与本机受控模型，没有修改正式学生数据或原始教材。没有调用外部真实模型，也没有重验收不需要的 31 个工具。

其余保留能力、动态 MCP/CLI/plugin、媒体产物以及学习状态迁移的完整性，仍按原台账的未完成项推进；不能用本轮四处修复替代整个第二部分的完成结论。
