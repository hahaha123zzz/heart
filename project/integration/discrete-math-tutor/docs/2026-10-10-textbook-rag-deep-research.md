# 中文离散数学教材 RAG 深度调研与升级决策

调研日期：2026-10-10。对象：现有离散数学助教 Demo。范围：核对本地实现、开源源码、官方运行文档及论文；本轮交付研究与实验设计。

用户补充：本机有 GPU，可以让小模型使用 GPU。本报告据此调整部署路线。

## 1. 结论与优先顺序

建议保留 FastAPI、SQLite FTS5、现有教材资源与 PDF 定位，逐步升级为：

```text
原始教材与可追溯资源
  → 结构完整的知识单元 + token 预算 + 可选语义细分
  → BM25/术语召回 + dense 召回 + 公式结构召回
  → RRF 合并、资源去重
  → GPU reranker
  → 有界扩展定义/证明/图表关联上下文
  → 检查证据充分性
  → AI 解释与逐条来源引用
```

优先实施：

1. **建立 GPU 同模型基线和独立证据评估集。** 先确定加速是否可用，再测吞吐、延迟及排名差异。
2. **补齐公式与术语表达。** 对丢失符号的资源补识别；先为命题逻辑建立范围明确的 AST 索引；补充有序对等完整术语匹配。
3. **完善知识单元及上下文组装。** 定义、定理、证明、表格等增加语义类型与显式关联，按 token 限制输入。
4. **重做证据评估。** 分开衡量相关性、可回答性和引用支持程度，再决定门槛。
5. **在固定题集上比较更大模型。** BGE-M3、bge-reranker-v2-m3、Qwen3-Reranker-0.6B 是实验候选；视觉检索作为后续补充路线。

以上是结合本地失败案例作出的工程判断，收益尚需实验确认。不能预先承诺换模型、加知识图谱或增加语义切片必然提高准确率。

## 2. 我们现在已经具备什么

本地依据：[检索代码](../knowledge/hybrid_retrieval.py)、[结构切片](../knowledge/structured_index.py)、[语义切片](../knowledge/semantic_chunks.py)、[索引构建](../scripts/build_rag_index.py)、[最新重排评估](2026-10-10-rag-reranker-results.md)。

| 环节 | 当前实现 | 仍需解决 |
| --- | --- | --- |
| 教材导入 | Word 块、图片、公式、表格与 PDF 章节定位 | 公式内容保真、图表解释与精确块坐标仍需核验 |
| 结构单元 | chapter、section、parent_id、资源关联、位置字段 | kind 偏向载体类型，尚缺统一 definition/theorem/proof/example 分类 |
| 混合切片 | 结构边界内，对长普通讲解做相邻句向量细分 | 350/760 等字符预算需要换成模型 token 预算；独立增益尚未证明 |
| 词面召回 | FTS5 BM25，中文字符片段与英文词 | 短术语、歧义词和数学符号需要专门处理 |
| 向量召回 | FastEmbed，bge-small-zh-v1.5 | 换变量名、符号残缺、跨章应用题存在失败 |
| 排序 | RRF、结构排序、bge-reranker-base、排序融合 | 章节启发式会错导；重排输入有截断；CPU 延迟数秒 |
| 证据门槛 | sigmoid 后相关性分数，开发值 0.15；精确资源匹配另处理 | 未校准为概率，也不等于摘录足以回答 |
| 诊断 | 各阶段候选、分数、过滤与降级 trace | 需加入必要证据覆盖、源文本质量、引用与回答级标签 |

特别注意：embedding 已输入“小节标题 + 正文”，reranker 也已输入小节标题。下一步有价值的改变是补上可靠的单元类型、标题、完整表头和公式内容，以及控制截断位置。

### 最新评估应怎样解释

最新未见题集：12 道教材内问题、4 道教材外问题。原混合检索 Hit@2 为 9/12，融合重排为 10/12；两者教材外返回出处均为 0/4。融合重排中位延迟约 7.6 秒，但两组评估同时运行，存在 CPU 竞争。题目由开发助手编写，样本很小，只能说明有限提升。详见[原始报告](2026-10-10-rag-reranker-results.md)。

仍失败的 c01“有序对”落到第九章序关系；c11“`A∧B` 真值”没有命中目标联结词小节。之前开发集 25/25 已被用于修复，不能视为独立验收成绩。Hit@2 检查的是章节、小节和指定载体，并不直接衡量答案正确性或证据充分性。

## 3. 初步调研中需要修正的判断

| 初步建议或判断 | 深度核验后的结论 | 对我们的影响 |
| --- | --- | --- |
| 给 embedding/reranker 补小节上下文 | 本项目已包含小节标题 | 增加语义类型、资源内容与 token 预算，并做输入消融 |
| 结构感知 + 语义切片一定更好 | 研究结果依任务而变，复杂切片的增益不稳定 | 保留结构优先，用固定预算对照评估语义切片 |
| BGE-M3 能解决数学符号变化 | 官方提供 dense/sparse/multi-vector；未证明教材公式的变量改名等价检索 | 加专用公式表达，BGE-M3 单独 A/B |
| semantic + structure + type_match 可当证据评分 | 加权相关性不能保证答案所需信息齐全 | 先标注充分性，避免章节偏置再次支配分数 |
| 增加知识图谱会明显提升排序 | 本地无实验证据 | 先增加可追溯局部关系；比较完整证据覆盖收益 |
| FlagEmbedding 是 Apache-2.0 | 当前代码 LICENSE 是 MIT | 模型权重仍需逐个查看 model card |
| ColPali Engine 可直接作为新生产依赖 | 当前 README 已标注 deprecated，并推荐 Sentence Transformers | 借鉴视觉检索方法，采用当前维护的集成入口 |
| MinerU 只能依赖大型 VLM/GPU | 当前 master 的 Basic 路线支持 CPU ONNX 小模型；高等级另用 VLM | 可试局部公式/表格识别，固定版本再比较 |

源码依据：[FlagEmbedding LICENSE](https://github.com/FlagOpen/FlagEmbedding/blob/master/LICENSE)、[ColPali 当前 README](https://github.com/illuin-tech/colpali/blob/97487f8871ff4d5d2284411fe61bdcd2cfe99894/README.md)、[MinerU tiers](https://github.com/opendatalab/MinerU/blob/31e4e3d0a54e5a82d169bdd81b2f3eddb652bb27/docs/en/usage/tiers.md)。

## 4. 切片：怎样落实你的混合方案

### 4.1 借鉴 Docling 的结构与预算控制

Docling-core 的 HybridChunker 从层级结构出发，再处理 tokenizer 长度、分割和同级合并，表格切片可以带重复表头。其“Hybrid”不能直接理解为我们当前的“相邻句 embedding 相似度断点”。值得借鉴的是 token 预算、结构来源保留，以及检索输入的上下文序列化。[HybridChunker 源码](https://github.com/docling-project/docling-core/blob/main/docling_core/transforms/chunker/hybrid_chunker.py)、[chunking 文档](https://github.com/docling-project/docling/blob/main/docs/concepts/chunking.md)。

本项目建议：

- 章节、小节、定义、定理、例题、证明作为结构边界；题号、图号和表号保留为资源定位字段。
- 短知识单元完整保留。超长证明按步骤拆成子块，仍指向同一证明与定理；避免为了满足长度只留下证明后半段。
- 公式保留表达式、变量说明和局部解释；表格保留表头、行名和单位；完整真值表优先保持原子性。
- 长普通讲解先按句子组织，再试语义细分。语义断点不跨结构边界，也不拆开公式与解释。
- embedding、reranker、生成各自有 token 预算，保留原始完整单元；不能简单共用“正文前 700 字”。

### 4.2 论文并不支持无条件扩大语义切片

Qu、Tu、Bao 的 *Is Semantic Chunking Worth the Computational Cost?*（2024）比较多种检索与生成任务，语义切片的优势不稳定，实验还存在句向量缺少上下文等限制。它支持做任务内对照，不能证明中文数学教材无需语义切片。[论文全文](https://arxiv.org/html/2410.13070v1)。

2026 年的 *A Systematic Analysis of Chunking Strategies for Reliable Question Answering* 在 Natural Questions、SPLADE 与 Mistral-8B 设置下也报告简单句切片的成本优势。这里仅核验摘要，不能将其上下文长度结论照搬到我们的教材。[预印本](https://arxiv.org/abs/2601.14123)。

2026 年 *When Is Complex Chunking Worth It?* 的摘要强调效果与吞吐、延迟、内存一起比较，最佳策略随模型和语料变化；它也是预印本，尚未据其全文复现。[预印本](https://arxiv.org/abs/2608.16586)。

**实验建议：固定解析结果、模型、总 token 预算与评估题集，比较结构切片、结构 + 句预算、结构 + 语义细分。** 当前 2440 → 2478 单元只说明少量单元被细分，无法证明改进来自语义切片。

## 5. 公式检索：第三路召回值得优先试验

### 5.1 两类开源实现的启发

Tangent-CFT/TangentS 使用公式树及节点、路径关系表示公式；Approach0 使用公式结构路径做检索。两者说明公式可以有独立于普通文本向量的结构表达。[Tangent-CFT 论文](https://www.cs.rit.edu/~rlaz/files/Mansouri_ICTIR2019.pdf)、[SymbolTree 源码](https://github.com/BehroozMansouri/TangentCFT/blob/7ff464a55582005c2b97f2ac6d120d9c1f66579f/TangentS/math_tan/symbol_tree.py)、[Approach0 论文](https://www.cs.rit.edu/~dprl/assets/files/Approach0_ECIR2019.pdf)、[路径索引源码](https://github.com/approach0/search-engine/blob/b99c50ce0eeee153247cc0628c8dd7963ccd28ad/math-index/subpath-set.c)。

复用方式：借鉴结构表示与评估方法。Approach0 README 明确称公开 master 不再活跃、最新实现闭源；TangentCFT 本轮未发现明确根许可证。二者均不建议直接作为本项目完整生产依赖。[Approach0 README](https://github.com/approach0/search-engine)。

### 5.2 第一版仅覆盖命题逻辑表达式

先支持 `¬、∧、∨、→、↔`、括号与原子命题。统一 Unicode 和相应 LaTeX 别名，按优先级解析，保留原始字符串及 AST；解析失败明确记录，不生成假结构。

| 输入 | 检索模板 | 注意事项 |
| --- | --- | --- |
| `A∧B` 与 `p∧q` | `AND(v1,v2)` | 用于召回相同形式，未证明两式真值相同 |
| `p∧p` | `AND(v1,v1)` | 重复变量关系不能丢失 |
| `¬(p∧q)` | `NOT(AND(v1,v2))` | 必须区别于 `¬p∧q` |
| `A→B` 与 `B→A` | 单独改名会产生相同抽象形状 | 保留原符号；比较两个式子要共享变量绑定 |

“模板相同”只表示结构召回信号。公式等价需额外验证，例如在受限命题逻辑范围内用真值表或逻辑工具；不能把 AST 哈希当作数学等价证明。集合、谓词量词绑定、矩阵与有序对需另扩语法。

有序对的失败还需要文本端完整术语匹配：`有序对`、`序关系`作为不同概念，短词片段不得强制推断第九章。“关系”作为普通问句词不宜直接成为章节硬条件。用户明确给出的章节和当前阅读选区则可成为可追溯范围约束。

### 5.3 先补原始内容，再建结构索引

建议顺序：可提取的原生数学对象 → 局部公式图像识别 → 人工核验关键资源。尚未完成全部 Word 数学对象类型与数量审计，不能假设全书都有可直接转 LaTeX 的 OMML。

- **Docling formula enrichment**：针对 FORMULA 类型生成 LaTeX，默认未启用；官方文档提示裁剪边界和重复生成问题，需要审计公式编号与邻接正文是否混入。[官方说明](https://docling-project.github.io/docling/usage/enrichments/)。
- **MinerU**：当前 Basic 的 ONNX 公式识别包装保留 bbox 并回填结果，可借鉴资源裁剪与结果对应管理；GPU/Torch 路线需按所选版本核实。[公式包装源码](https://github.com/opendatalab/MinerU/blob/31e4e3d0a54e5a82d169bdd81b2f3eddb652bb27/mineru/model/mfr/pp_formulanet_plus_m_onnx.py)。
- **pix2tex**：适合裁剪后的公式图像 → LaTeX，不能替代整个文档结构解析器。[代码](https://github.com/lukas-blecher/LaTeX-OCR/blob/5c1ac929bd19a7ecf86d5fb8d94771c8969fcb80/pix2tex/cli.py)。

先抽样 50–100 个公式、表格和图示比较，不必一开始重新解析全书。评估否定符、上下标、量词作用域、矩阵行列和资源页码；可编译 LaTeX 不代表识别正确。原图始终保留，OCR 结果另存并带版本与验证状态。

## 6. 知识关系与证据门槛

### 6.1 为现有单元添加少量可靠关系

可以先增加 `proved_by / has_formula / has_example / has_figure / has_table`，由同一小节、连续结构块及明确编号建立；前置知识关系须有教材依据或人工确认。先限制一跳扩展和 token 预算，观察是否补齐答案必要证据。

Docling-core 已有树与页面上下文扩展器，可借鉴显式来源和扩展入口；整页扩展也可能加入大量无关内容，仍需控制范围。[chunk_expander 源码](https://github.com/docling-project/docling-core/blob/0d5a7bdc6eec6138055714756277730f1520ca61/docling_core/transforms/chunker/chunk_expander.py)。

数据库可沿用 SQLite，添加类型、关联表和来源字段即可。收益先通过“证明步骤是否完整”“图与定义是否同时到达模型”验证；当前没有引入 Neo4j 或全书自动 GraphRAG 的必要证据。

### 6.2 判断证据能否支撑解释

*Sufficient Context*（ICLR 2025）区分相关上下文与足以作答的上下文，研究发现两种情况下模型都可能出错。因此必须分别测试检索、充分性判断与生成。[论文](https://arxiv.org/html/2411.06037v3)。

建议增加状态 `sufficient / partial / insufficient / conflicting`，并记录所需但缺失的证据及支持资源 ID。它是本项目的拟议接口，不是论文提供的现成生产 SDK；[官方仓库](https://github.com/hljoren/sufficientcontext)主要提供研究材料与提示模板。

门槛顺序建议：

1. 校验来源 ID、页码和精确图号是否存在。
2. 排除 OCR 严重残缺、仅有标题或未包含关键表行的资源。
3. 对问题需要的定义、条件、证明步骤和图表建立人工标签，再测试自动判断。
4. 部分证据时只解释能支持的部分；不足时明确缺口；冲突时展示来源差异。

reranker 分数用于相关性判断，不能当“答案正确概率”。保留相关性阈值作为工程过滤，另测它造成的教材内误拒和教材外漏拦。自动 judge 也要与人工标签对照，避免用同一模型自评作为唯一验收。

## 7. GPU 路线：已确认的硬件与当前障碍

### 7.1 2026-10-10 本机只读检查

- Windows CIM 识别到 **NVIDIA GeForce RTX 5060 Laptop GPU**，另有 Intel UHD Graphics。
- `nvidia-smi` 返回 `Failed to initialize NVML: Unknown Error`；因此实际总显存、空闲显存与 CUDA 可用性尚未确认。
- CIM 的 AdapterRAM 字段约 4 GB，不能据此认定该独显真实显存。NVIDIA 官方该型号标准配置为 8 GB，这只是型号规格，不能替代本机运行时测量。[官方规格](https://www.nvidia.com/en-us/geforce/laptops/50-series/)。
- 项目 Python 为 3.12；ONNX Runtime 1.31.0 仅提供 `AzureExecutionProvider` 与 `CPUExecutionProvider`；未安装 torch、sentence_transformers、FlagEmbedding。

所以：现有模型仍在 CPU 上。本轮尚未安装 CUDA 依赖或改变服务配置。NVML 报错的原因尚未定位，可能涉及运行会话或驱动状态，不能只凭这条错误判定显卡故障。

### 7.2 接入顺序

**阶段 G0：运行时兼容性。** 在独立 GPU 环境检查驱动、CUDA 构建、设备可用性和小规模实际推理。RTX 50 系列应选支持 Blackwell 的构建。PyTorch 官方 2.7 开始提供相关支持；当前新版本发布矩阵已改变，不能照抄几年前的默认安装命令。[Blackwell 支持说明](https://pytorch.org/blog/pytorch-2-7/)、[当前与历史安装矩阵](https://pytorch.org/get-started/previous-versions/)。

特别是官方 2.12 说明 CUDA 12.8 wheel 不再随标准矩阵发布，新 Blackwell 用户的 CUDA 13 路线有更高驱动要求。安装时以版本、Windows 驱动、CUDA/cuDNN 三者兼容为准；不为了“最新版”自动升级显卡驱动。[2.12 官方说明](https://pytorch.org/blog/pytorch-2-12-release-blog/)。

**阶段 G1：同模型迁移。** 固定 bge-reranker-base、候选池与序列化，比较 CPU ONNX 和 GPU 后端。优先试兼容 CUDA Execution Provider；若模型封装不可配置 GPU，采用显式设备的 PyTorch 接口。不同导出或精度会产生评分差异，门槛附近需检查排名和拒答变化。

ONNX Runtime 的 CUDA/cuDNN 版本必须匹配。当前官方文档说明 1.27 起默认 GPU 包为 CUDA 13，另有 CUDA 12.8 构建，不能直接把现有 `onnxruntime` 名称改成最新版 `onnxruntime-gpu` 就认定可用。[CUDA EP 依赖与 DLL 文档](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)。

**阶段 G2：更强模型 A/B。** embedding、reranker、OCR 分别测试，GPU 上先常驻在线 reranker；embedding 建索引和 OCR 可在离线任务中运行。不要让多个模型自动同时占满显存。进程数、batch 与最大长度通过实际负载确定。

| 模型/能力 | 用途 | 本机试验建议 |
| --- | --- | --- |
| 现有 bge-small / bge-reranker-base | 同模型 GPU 基线 | 最先测，保留现有结果作为质量对照 |
| BGE-M3 | dense，后续可试 sparse/multi-vector | 先只换 dense，重建独立索引；再单独测新增分支 |
| bge-reranker-v2-m3 | 更强重排候选 | 固定候选池，比较证据排序与显存/延迟 |
| Qwen3-Reranker-0.6B | 指令式重排候选 | 若前两者仍有质量瓶颈再测；不直接照搬原阈值 |
| 公式 OCR | 离线修复图像公式 | 优先局部批处理，记录识别质量与资源对应 |

BGE-M3 的论文与模型卡证明其三种检索表征能力，未验证本教材的符号问题。[论文](https://arxiv.org/abs/2402.03216)、[模型卡](https://huggingface.co/BAAI/bge-m3)。Qwen3 官方示例由最后 token 的 yes/no logits 计算分数，与 BGE 的评分入口不同；示例还使用 FlashAttention 2，Windows 实验要选择实际支持的 attention 后端。[源码](https://github.com/QwenLM/Qwen3-Embedding/blob/44548aa5f0a0aed1c76d64e19afe47727a325b8f/examples/qwen3_reranker_transformers.py)、[论文](https://arxiv.org/abs/2506.05176)。

GPU 性能试验同时记录 batch、最大 token 数、精度、峰值显存、冷启动和热启动 p50/p95。先进行长度分组与候选去重，必要时再试量化。[FlagEmbedding 批处理源码](https://github.com/FlagOpen/FlagEmbedding/blob/master/FlagEmbedding/inference/reranker/encoder_only/base.py)、[Sentence Transformers 推理优化](https://www.sbert.net/docs/cross_encoder/usage/efficiency.html)。

## 8. 视觉检索与阅读器选区的衔接

ColPali 用页面视觉多向量与文本查询匹配，可以补充图表和版面信息检索；命中页面不自动产生可靠公式转录或正确图解。[论文](https://arxiv.org/abs/2407.01449)。当前 `colpali-engine` README 已标注 deprecated，推荐 Sentence Transformers 的 MultiVectorEncoder；新实验采用维护中的入口。[迁移说明](https://github.com/illuin-tech/colpali/blob/97487f8871ff4d5d2284411fe61bdcd2cfe99894/README.md)、[官方 MultiVectorEncoder 文档](https://www.sbert.net/docs/multi_vector_encoder/usage/usage.html)。

建议先用一章做视觉检索实验，测页面命中、块定位、索引体积、显存与延迟。它可以作为第四路补充，当前没有必要替换全部文本检索。

选区提问优先使用用户给出的定位：document_id、版本、页码、bbox、选中文本/截图、邻接资源 ID。先找该位置的定义、变量说明、图注和关联证明，再针对缺少的信息全书检索。用户记忆另检索，只用于解释深浅、常见误区和学习进度；数学结论必须有教材来源或明确的推导依据。

答案引用绑定到实际使用的 unit_id/asset_id，而不是只引用整个章节。单独验证：文字引用是否支撑对应句子、图片是否确实送达回答模型、点击引用是否跳到正确页与选区。

## 9. 建议的数据增量

保留原有 chunks 与资源表；以下为新增字段/表的草案：

```text
unit_metadata:
  unit_id, semantic_type, title, concept_ids, source_version
unit_links:
  source_id, target_id, relation, evidence_blocks, verified
formula_records:
  asset_id, raw_latex, parsed_ast, template_key,
  parse_status, origin, verified, page, bbox, source_version
concept_aliases:
  alias, concept_id, namespace, verified
```

原始文本、检索规范化文本与展示原图分开保存。OCR、人工纠正和自动类型判定带版本；索引缓存键应包含模型版本、输入格式、内容摘要。改 embedding 后建立新索引，禁止新查询向量与旧模型文档向量混用。

## 10. 可以否定方案的实验与验收

先由独立人员标注 50–80 题作为试验，再扩至 150–300 题。按概念或公式模板分组拆训练/开发/测试，避免“同一题只换变量名”同时出现于调参与测试集。已用于修复的旧题保留为回归集。

| 实验 | 固定条件与改变因素 | 衡量什么 | 如何判定无收益 |
| --- | --- | --- | --- |
| GPU 同模型 | 固定模型、候选、输入；改变后端与精度 | 排名差异、门槛误差、p50/p95、显存 | 显著误拒/排序退化或无可观延迟改善 |
| 切片消融 | 固定模型及总上下文 token；三种切片 | 必要证据 Recall@K、MRR/nDCG、回答支持率 | 无独立收益且解析/索引成本上升 |
| 公式结构分支 | 逻辑模板、换变量、否定作用域及反例 | Recall、模板碰撞、解析失败率 | 错误绑定或碰撞导致误导回答 |
| 术语与章节信号 | 完整术语、歧义词、明确章节约束 | 有序对/序关系等跨章误导 | 新问题更依赖硬编码偏置 |
| 类型与关系扩展 | 固定候选，分别加类型和一跳关系 | 完整证明/表格证据覆盖、token 成本 | 只提高小节 Hit，必要证据仍缺失 |
| 新 reranker | 固定候选池与 token 预算 | 排名、证据充分性、时延 | 更大模型质量无稳定提升 |
| 充分性门槛 | 人工充分/部分/不足/冲突标签 | 误拒、无证据回答、风险—覆盖曲线 | 靠大量拒答制造表面准确率 |
| 选区真实回答 | 固定选区与记忆样本 | 答案正确、引用支持、跳转定位 | 相关页命中但图/表/公式解释错误 |

拟议性能目标：在线检索热启动 p95 先争取小于 2 秒；这是目标，不是 GPU 尚未运行时的承诺。模型候选数 16/24/40、token 上限 128/256/384 可作为小规模网格，最终选质量与延迟都可接受的点。标注题少时报告逐题变化，不用一两题提升宣称统计显著。

必须分别报告：检索出处命中、必要证据覆盖、证据充分性、答案正确性、引用支持率、教材内误拒和教材外伪引用。不能把任何一个指标直接称为“RAG 准确率”。

## 11. 开源维护与许可核验

GitHub API 快照日期为 2026-10-10。push 时间不等于发布质量，也不能单独证明成熟度；采用时固定 release/commit 并复核模型权重许可。

| 项目 | 本轮查询的最近 push | 许可/维护核验 | 建议 |
| --- | --- | --- | --- |
| Docling / docling-core | 2026-10-10 | MIT；模型分别核验 | 结构、token 切片、局部解析 |
| FlagEmbedding | 2026-08-24 | 代码 MIT；权重分别核验 | GPU embedding/reranker 实验 |
| MinerU | 2026-10-09 | 当前 Apache-2.0 加附加条款 | 固定版本，局部 OCR/公式/表格对照 |
| LaTeX-OCR | 2025-01-18 | 代码 MIT | 局部公式识别候选 |
| sufficientcontext | 2025-07-22 | 未发现明确根许可证；研究材料仓库 | 借鉴判定方法，自己设计接口 |
| ColPali | 2026-09-21 | 代码 MIT；Engine deprecated；权重依底座 | 采用维护中的 MultiVectorEncoder 路线 |
| Approach0 | 2023-11-16 | MIT；README 称 master 不活跃 | 借鉴公式路径检索设计 |
| TangentCFT | 2025-03-21 | 本轮未发现明确根许可证 | 研究参考，不直接复制模块 |
| Qwen3-Embedding | 2025-09-30 | README 声明模型 Apache-2.0；根许可需再查 | 0.6B 备选，验证成本与中文教材收益 |
| Sentence Transformers | 2026-10-08 | Apache-2.0；当前支持多向量集成 | 推理与视觉检索实验入口 |

MinerU 当前许可除 Apache-2.0 外，包含商业规模门槛与在线服务标识义务；不能简写为“纯 Apache-2.0”。[当前许可原文](https://github.com/opendatalab/MinerU/blob/master/LICENSE.md)。这是本次版本选型记录，采用其他版本时重查对应条款。

## 12. 下一步具体交付

第一阶段交付建议为：**独立 GPU 环境 + 现有 reranker 的 GPU 实测报告 + 冻结的证据级题集 + 逻辑公式/完整术语召回原型**。先解决运行后端与两类已知错误，再决定更大模型和更广泛的解析改造。

本轮完成了调研及只读环境检查；尚未完成 CUDA 可用性验证、GPU 推理实测、全书原生公式审计、解析器样本对照或新模型 A/B。所引用的初步对话只取得截断预览，未将不可见内容当成已核验事实。

## 调研后的实施更新

本机 GPU 已在后续实施中验证并接入现有 reranker，同模型检索中位耗时由 7.75 秒降至 0.45 秒；详见 [GPU 接入实测](2026-10-10-rag-gpu-results.md)。第 7 节的运行时未知状态记录的是调研当时的检查结果。
