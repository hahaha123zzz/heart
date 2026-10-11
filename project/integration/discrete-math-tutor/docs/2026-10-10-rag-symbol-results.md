# 公式结构与教材术语召回改进（2026-10-10）

## 实现与来源依据

教材第一章定义 1.9 使用“二元有序组／序偶（ordered pairs）”，第四章合取定义与真值表使用 p∧q。此前有序对术语不匹配、A∧B 无法按完整符号找到 p∧q；即使加入结构召回，reranker 仍会因变量不同拒绝正确表格。

本轮实现：

1. knowledge/concept_aliases.py：加入经原文核对的有序对／序偶／二元有序组／ordered pairs、笛卡尔积／笛卡儿积对应。扩展完整概念，不把“序关系”当作有序对。
2. knowledge/logic_formula.py：受限命题逻辑 parser，支持否定、合取、析取、蕴涵、双向蕴涵、括号、变量与 0/1，统一相应 LaTeX 与教材 ┐ 符号；保留 AST 和重复变量关系。
3. 给 SQLite 添加 logic_formulas 表。第四章 263 条去重记录、62 个片段；记录 body/header 来源，原 chunks 和 vectors 均保持 2478 条。单独运行 scripts.build_formula_index 即可构建；常规索引构建也会生成该表。
4. 公式模板与完整术语各提供一条 RRF 候选信号，并将候选保留到 GPU 重排阶段。真值问题可限定到结构匹配表头，仍经过相关性门槛，不享受结构匹配豁免。
5. 只在检索模型输入中统一变量占位符，整段共享绑定；A→B 与 B→A 会变为 p→q 与 q→p。原始教材、返回摘录、资源 ID 和给回答模型的用户问题不修改。
6. trace 增加 search_query、formula_templates、formula_ids、concept_ids、structural_table_match、reranker_query，便于定位每一路的作用。

模板相同仅表示召回同一种结构，不代表数学等价。例如 A→B 与 B→A 单独抽象时形状相同，但在同一问题里变量绑定不同。p∧p 与 p∧q 不匹配，¬(p∧q) 与 ¬p∧q 不匹配。谓词绑定、一般代数、矩阵、缺失图像公式尚未纳入这个 parser。

## 测试与评估口径

32 项测试通过，包括运算优先级、否定作用域、重复变量、非法表达式、共享变量绑定、结构表格召回与门槛拒绝，及原有 RAG/GPU 设备回归。

新建 18 道问句（14 教材内、4 教材外），在实现之前核对标签并固定。s12 的初始小节标签在首个正式评分前按原文修正为“外延性公理与子集合”，问句未变。该题集随后揭示了变量名重排失败，因而最终成绩属于开发结果。

| 阶段 | 教材内 Hit@2 | 教材外仍返回出处 |
| --- | ---: | ---: |
| 修改前 | 7/14 | 3/4 |
| 术语与结构召回，尚无模型输入变量规范化 | 9/14 | 3/4 |
| 加入模型输入变量规范化 | 14/14 | 3/4 |

原先 16 道题的回归：12 道教材内题 Hit@2 为 12/12，4 道教材外题均无出处。此旧集含已修复的 c01 和 c11，不是独立验收。

Hit@2 核对章节、小节与指定资源类型，不表示回答准确率。本轮固定原 GPU reranker 和 0.15 阈值，没有按教材外问句调阈值或添加题目专用黑名单。运行包含首次 GPU 初始化，不作为新的严格性能基准。

原始记录：artifacts/symbol-before.json、symbol-after.json、symbol-normalized.json、symbol-normalized-regression.json。新问句检查另见 artifacts/symbol-followup.json；它由同一开发助手生成，且仍包含相同概念与公式模板，不能代替独立人员的跨概念评估。

## 剩余问题

- 新开发题的教材外误引用仍为 3/4，包括薛定谔方程、Python 按位运算和订单数据库设计。它们在修改前也失败；这说明相关性阈值会把数学上或词面上相关的材料当成回答依据。
- 第一章有序组定义中的多个数学对象仍仅有资源 ID 或缺失文本。现在找到正确小节，不代表完整定义已恢复；后续需局部公式识别与人工核验。
- 本轮只处理可提取的命题逻辑结构，并未完成全书数学表达式检索，更未将模板匹配解释为公式等价。

下一阶段应建立必要证据与回答范围标签，增加“证据是否充分”的判断，检查教材外误引用与教材内误拒，再做关键公式资源的识别修复。不能仅靠调低/调高 reranker 阈值宣布解决。

## 复现

~~~powershell
.\.venv-gpu\Scripts\python.exe -m scripts.build_formula_index
.\.venv-gpu\Scripts\python.exe -m unittest tests.test_logic_formula tests.test_rag_upgrade tests.test_inference_runtime -v
$env:RAG_RERANK_DEVICE='cuda'
.\.venv-gpu\Scripts\python.exe -m scripts.eval_rag_holdout --cases tests/data/rag_symbol_followup_2026_10_10.json --output artifacts/symbol-followup.json --reranker BAAI/bge-reranker-base --trace
~~~

项目已重启以加载新代码。用户看到的教材与变量名保持原样；检索内部增加术语与公式结构处理。

## 后续新问句与真实回答抽查

冻结的 12 道后续问句中，8 道教材内题 Hit@2 为 8/8；4 道教材外题仍有 2 道返回出处。没有据此继续修改规则、标签或门槛。此结果仍是同一开发助手生成问句的检查，不证明整体泛化。

真实 /api/chat 抽查“A∧B 在什么条件下取真？请结合教材真值表解释”：AI 正确回答 A、B 同真才为真，列出四种赋值并引用第四章 4.1.2 的表 4.2。人工检查确认该条结论及真值解释正确；单次抽查不代表全部答案正确率。完整回复见 artifacts/symbol-real-api.json。临时测试账户已清理，未使用真实用户记忆。
