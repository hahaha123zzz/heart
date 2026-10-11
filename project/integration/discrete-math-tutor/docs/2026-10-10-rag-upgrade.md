# 教材检索升级说明

## 数据流

1. `knowledge/structured_index.py` 从十章 Word 提取 JSON 生成结构单元。题库 catalog 中的章后练习块不进入教材索引；交互题仍由练习系统处理。
2. `knowledge/semantic_chunks.py` 在构建语义向量时，只对较长的普通讲解段落比较相邻句的 embedding；定理、例题及带公式资源的单元保持结构边界。
3. `scripts/build_rag_index.py` 写入 SQLite FTS5/BM25、块元数据及可选的 FastEmbed 中文向量。原 Word 块号、章节、小节和 PDF 小节起始页随块保存。
4. `knowledge/hybrid_retrieval.py` 做关键词与向量召回、倒数排名融合、精确编号匹配，并可按环境变量调用交叉编码器重排。命中子片段时补齐同一父单元上下文。
5. `orchestrator.py` 使用新的检索入口；服务端选区问答仍以 PDF 裁图和坐标为直接证据。

## 运行与限制

停止 API 服务后，在项目目录执行 `python -m scripts.build_rag_index --embed` 生成完整索引；Windows 下运行中的 SQLite 文件可能阻止原位替换。没有 FastEmbed 模型时，可不带 `--embed` 构建结构与 BM25 索引。索引文件缺失时，首次问答会自动构建无向量版本。重排模型默认关闭；设置 `RAG_RERANK_MODEL=BAAI/bge-reranker-base` 可调用 FastEmbed，设置 `BAAI/bge-reranker-v2-m3` 则需安装 FlagEmbedding。

PDF 页码目前只表示命中小节的起始页。由于 Word 块与 PDF 逐块坐标尚无可靠映射，不能把这个页码当成命中句子的精确页码。公式依赖原资源图片与邻近正文；没有自动识别成可核对的 LaTeX。未核定图号的绘图仍保留“未核定”状态。

## 评测

`python -m scripts.eval_rag_retrieval` 对 13 个人工标注的教材问题计算出处 Hit@2，并列出未命中的问题。该小样本用于回归，不代表整体教学质量。正式调参应扩充到跨章节、同义改写、图表公式、证明、无答案问题，并检查回答准确性、出处定位和延迟。

2026-10-10 本机结果：旧检索 8/13，新结构与语义索引 13/13；新检索整组约 3.2 秒（包含首次加载中文模型）。部分排序规则根据这组问题调整过，因此这个结果只说明回归样本通过，不能当作独立泛化评估。额外抽查的 10 个问题中，9 个能返回对应章节；教材没有提及的“对称差”返回空证据。相近表述“欧拉通路”仍可通过语义检索命中欧拉路径相关内容。

## 参考实现

- Docling 结构与 token 切片：https://github.com/docling-project/docling/blob/main/docs/concepts/chunking.md
- LlamaIndex 语义切片：https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/node_parser/text/semantic_splitter.py
- LangChain 父子文档检索：https://github.com/langchain-ai/langchain/blob/master/libs/langchain/langchain_classic/retrievers/parent_document_retriever.py
- SQLite FTS5：https://www.sqlite.org/fts5.html
- FastEmbed：https://github.com/qdrant/fastembed
