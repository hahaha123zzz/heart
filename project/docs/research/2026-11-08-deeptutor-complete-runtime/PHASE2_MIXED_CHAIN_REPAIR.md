# 出题后切换阅读：历史交接与教学计划修复

日期：2026-11-09。接续 [真实模型初验](PHASE2_LIVE_VALIDATION.md)。

**结论：本次真实混合链路通过。此前“出题后要求翻第 2 页却跳到第 28 页”的问题，在补齐题卡历史并停止给页面操作附加讲解计划后，按原请求、原顺序复测通过。第二部分其余能力仍未全部验收。**

## 修改及实际接线

1. `integrations/deeptutor/native_history.py` 在宿主授权会话范围内适配原生 SQLite `get_messages_for_context`。从与 assistant 消息关联的已完成原生回合事件恢复题卡，复用 `public_quiz` 过滤正确答案、解析及未知字段，再交给原版 ContextBuilder。通过 `NativeTurnBridge` 初始化实际安装；不新增上下文构造器、不修改固定上游源码、不删除历史或覆盖原始消息。
2. `teaching_prompt_adapter.teaching_snapshot` 复用现有 `agents.input_understanding.route.reader_requested`。页面操作继续由原生阅读能力处理，宿主不再强加 `read_material → explain` 默认教学计划。否定跳转的正常讲解和普通提示仍使用原教学策略。
3. 浏览器验收在出题已明确失败时立即报告，避免无意义等待；完整结果继续写入文件，终端只输出精简摘要。

## 定位证据与逐步复测

- 只补题卡历史后，真实运行 `20261109-082611` 仍在相同请求下跳到第 28 页，因此没有把历史修复单独宣称为根因解决。
- 继续核对该回合实际系统提示：宿主向“只需翻页、不需要解释”注入了强制讲解 moves。新增回归先复现该错误计划，再通过既有页面操作判定排除它。
- `20261109-082234` 曾在出题阶段出现 `httpx.ConnectTimeout/openai.APITimeoutError`，停止该轮后重试；该次不计为修复通过。
- 最终运行 `20261109-083118` 保留原始测试问题、同一会话先出题再翻页的顺序和原页码断言，未更换模型或放宽引用/页面权限。

## 验证结果

| 项目 | 结果 |
| --- | --- |
| 相关原生回归 | 第一阶段 42 项通过，104.524 秒 |
| 最终专项 | 历史/页面操作边界、共享策略原生快照、原生提示隔离等 11 项通过，101.615 秒；两阶段合计 49 个不同相关用例 |
| 正式 RAG 引用 | 真实模型 rag → read_source → answered，2 条 PDF 引用、2 条教材来源；历史接口恢复引用 |
| 真实出题 | 实际聊天表单生成一道四选项变量题；公开结构过滤正确答案和解析 |
| 同会话出题后翻页 | 原生事件明确为 reader_goto(locator=2)，未调用旧题目的内容检索/讲解；页面实际第 2 页，回执 applied |
| 文档与版本 | 回执和 actualReaderPosition 的 document_id/version/page 一致 |
| 刷新恢复 | 页面刷新后重新显示原题卡；无浏览器脚本错误 |
| 静态检查 | Python AST、JS 语法及 git diff --check 通过 |

实际原生阅读工具序列为 `notebook_lookup → reader_goto(locator=2)`。该回合保存的系统提示中已没有“统一教学决策”默认讲解计划，证据位于 `mixed-chain-audit.json`。

证据目录：宿主 `.runtime/native-delivery-live/20261109-083118/`，含 `rag.json`、`rag-history.json`、`browser.json`、`mixed-chain-audit.json`、`delivery.png`。截图在刷新后拍摄，展示恢复的题卡与翻页回复；实际 PDF 页码及执行回执以 browser.json 中刷新前保存的 position/receipt 为准。

## 尚未覆盖

扩展运行旧链路 `tests.test_shared_teaching_strategy` 共 22 项时有 5 项错误；将页面操作判定恢复为本轮改动前的行为后仍复现相同错误：4 项旧测试 Mock.tool_calls 不支持 len，1 项导入已不存在的 requests_supplementary_proof。该组不能宣称全绿；本轮没有改动这些旧测试或旧链路业务。

没有验收其余研究、媒体和掌握学习能力；没有做真实模型的大样本稳定性测试。历史投影补齐原生尚可读取的完整回合，已经进入旧压缩摘要的内容不在本轮迁移范围。一次混合样本通过不能作为所有后续意图切换的可靠性保证。
