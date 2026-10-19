# Q2-A：本地混合检索与重排模块

日期：2026-10-19。状态：本检查点完成，Q2整阶段未完成。保留整套11/14/100目标，本轮落实Q2.2的混合检索/重排子部分和Q2.3/Q2.6的部分验证。

## 实际迁入与项目调用

从固定提交6cf793bd868ba5ecbe64722936d4be8fab5a01df成组迁入LlamaIndex检索模块：

| 固定来源 | 本项目文件 | 适配 |
| --- | --- | --- |
| services/rag/pipelines/llamaindex/config.py | knowledge/local_rag/config.py | 配置从本项目RAG环境变量读取，移除DeepTutor设置服务 |
| services/rag/pipelines/llamaindex/retrievers.py | knowledge/local_rag/retrievers.py | 保留向量/BM25组合、RRF、候选预算、小库top_k限制及缺依赖降级 |
| services/rag/pipelines/llamaindex/rerank.py | knowledge/local_rag/rerank.py | 保留重排/缓存/分数转换；接现有FastEmbed/FlagEmbedding，按设备缓存，严格验证分数数量与有限值，显式记录降级 |

来源与迁入文件的SHA-256见knowledge/local_rag/UPSTREAM.json；Apache-2.0许可证及修改说明保存在third_party/DeepTutor。

本地新增course_retrieval.py、tokenization.py，连接本项目只读SQLite、已有512维BGE向量和模型、TextbookChunk及来源身份。psychology_retrieval.retrieve在选择local_llamaindex时调用本地模块，后续概念标题补召回、父块展开、证据核验和阅读定位继续走本项目链路。没有启动、导入或路由到DeepTutorApp/TurnApplicationService。

本次使用现有1,465个教材片段及全部对应向量，在内存中建立LlamaIndex索引；没有重新解析或覆盖教材、重算整库向量，也没有新建DeepTutor账户或会话。向量存储使用LlamaIndex默认内存存储，FAISS摄取/持久化尚未迁入，不冒称完成。

## 关键行为

- 中文BM25使用项目已有terms_for词项，避免英文默认分词把整段中文当一个词；模型查询和语料使用一致处理。融合前恢复原始节点，保证两路的节点hash、来源ID和文字一致。
- 查询向量必须与教材声明的模型及512维索引相符；空/非有限/零向量、缺失向量和混合维度拒绝执行，预置向量不被隐式重新生成。
- SQLite只读打开；索引全文件SHA作为缓存版本，拒绝WAL写入状态，并在读取/检索后重新核对版本。完整模型权重签名和原件发布版本绑定仍属于后续Q2.3/Q2.5。
- RRF分数只表示排序，不作为相关性。真实重排成功时沿用现有sigmoid后0.15门槛（未经概率校准）；重排不可用/失败时明确标记，使用余弦0.58门槛，不能以降级冒充重排已执行。
- trace记录配置/实际检索profile、模型、维度、索引身份、设备、候选、重排状态和最终来源；当前在检查报告中可查，尚未新增页面状态展示。
- 修复表格来源映射：原心理学检索只为text计算source_spans，table未映射。现在使用原单元格数据计算范围，保留表格序列化文字和顺序，不转换为普通段落。

## 安装与复现

本项目实际运行环境需安装requirements-local-rag.txt。此次在.venv-gpu（Windows Python3.12）新增41个缺失依赖，未卸载/升级原有包；增量锁见requirements-local-rag-win32-py312.lock.txt，基础依赖另按原项目方式安装。未安装完整DeepTutor应用、FAISS或SentenceTransformers，重排使用原环境已有的本地BGE模型。

默认RAG_RETRIEVAL_ENGINE=legacy；试点值local_llamaindex。实际.env未修改，未发起当前服务重启。新模式报错不自动跳回旧检索或调用DeepTutor后端来伪装成功。

在宿主目录执行：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONPATH=(Get-Location).Path
& '.venv-gpu/Scripts/python.exe' -B -m unittest discover -s tests -p test_local_rag.py -v
& '.venv-gpu/Scripts/python.exe' -B scripts/check_local_rag.py --require-rerank
```

检查脚本使用已缓存的CPU embedding/重排模型，不下载权重、不调用聊天模型、不访问学生学习数据库。每个案例包含底层检索和心理学入口两次执行，耗时不能当作单次检索延迟。

## 验证结果与失败记录

专项14项通过。覆盖真实LlamaIndex/BM25/RRF、中文分词和原始hash恢复、小库限制、配置hybrid实际vector降级、向量错误、索引换版/检索中变化/WAL、低相关拒绝、重排失败及表格原文范围。测试只替换embedding/重排模型传输，不模拟检索器和融合算法。

最终相关回归81项全部通过，37.369秒，包含心理学课程/导入/检索/记忆等已有测试、Q1上下文/质检及新增检索测试。日志.runtime/q2-regressions-final.log。没有重跑此前199项完整集合，原有数据漂移记录不据此消失。

真实模型配置：embedding BAAI/bge-small-zh-v1.5、512维；重排BAAI/bge-reranker-base；CPU。最终同一次运行4项均通过，全部实际profile=hybrid、rerank_status=applied：

| 案例 | 底层/投影来源数 | 案例耗时 | 核对 |
| --- | --- | --- | --- |
| 自变量 | 6 / 6 | 16.593秒 | 有真实自变量来源、原文范围与PDF版本 |
| 被试内/被试间设计 | 6 / 6 | 15.328秒 | 两个对象均有来源 |
| 内部/外部效度 | 6 / 6 | 22.266秒 | 两个对象及表格范围均可定位 |
| 火星玄武岩结构（教材外） | 0 / 0 | 26.609秒 | 拒绝把排序候选当教材依据 |

报告：.runtime/local-rag-checks/20261019T122806Z-c3650a/report.json。

报告SHA-256：fb8c0f548ad6534179236db3560f166e6bf4bae9bda7130c82492cacd8379700。

教材索引前后SHA-256相同：2a052d6d90624119c7bb10d445bcfb7c0a82306021f2af55ed29c71d23b0e7ef。固定来源副本3,764文件再次校验，保留原有已登记factory.py补丁，本轮没有修改vendor。

首次真实运行20261019T122336Z-f3b257保留失败：内部/外部效度召回了表3-9，但table缺少source_spans。修复后另起上述完整4项运行，不拼接成一次绿色报告。新增离线表格回归同时通过。

## 本检查点不代表的完成项

未完成原DOCX/PDF解析迁入、新摄取/切块、FAISS持久化、全量索引发布、完整模型/文档签名绑定、查询改写、视觉资产/选区输入和页面真实问答验收。当前4组主要验证召回执行、概念覆盖及来源范围，不是完整人工标注召回率/正确率基准，也不能据此宣称学生回答质量已提高。

后续继续Q2.1/Q2.4/Q2.5及标注集/图像验收，再联动Q3本地循环；Q4—Q6完整能力范围不变。
