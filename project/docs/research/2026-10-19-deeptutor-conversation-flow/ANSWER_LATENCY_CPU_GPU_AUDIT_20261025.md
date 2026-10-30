# 回答速度第一轮排查：实际运行、CPU/GPU 与 DeepTutor

核对日期：2026-10-25。只读调研，未切换服务、安装依赖、迁移数据库或修改模型配置。主线 `8d62c30`；上游 `D:\deeptutor` 为 `6cf793bd868ba5ecbe64722936d4be8fab5a01df`。

## 1. 当前页面实际运行情况

8000 的 `/`、`/health` 返回200。监听进程cwd为 `.runtime/q4-switch-20261024/release`，发布记录为 `e8edcf4`，不是当前main。

健康接口和指定环境字段共同证实：

- Q3_RETRIEVAL_MODE=lightrag，LOCAL_AGENT_LOOP_ENABLED=1，Q5_LEARNING_ENABLED=1。
- RAG_EMBED_DEVICE=cpu、RAG_RERANK_DEVICE=cpu。
- 已加载的embedding和reranker会话均为CPUExecutionProvider，不只是配置写了cpu。
- 实际使用的发布虚拟环境只有onnxruntime 1.31.0，没有onnxruntime-gpu及对应NVIDIA wheel；可用provider为AzureExecutionProvider/CPUExecutionProvider。不能只将环境变量改为cuda后原样启动。

硬件只读探测：RTX 5060 Laptop GPU，约7.96GiB独立显存，当时空闲约6.21GiB；系统内存约15.61GiB，当时可用约1.58GiB。这只是当时快照，不能由低可用内存直接断言已发生换页瓶颈，也不能为释放资源停止其他窗口。

项目既有 `.venv-gpu` 存在，导入ONNX Runtime可列出CUDAExecutionProvider/TensorrtExecutionProvider；安装元数据同时能查到onnxruntime 1.31.0和onnxruntime-gpu 1.26.0，以及cuDNN/cuBLAS wheel。provider枚举不等于实际模型会话能成功运行；CPU/GPU包元数据共存还需确认导入文件和实际二进制版本，不能当成兼容验证通过。未加载新模型或进行GPU推理。

## 2. 哪些适合GPU

| 工作 | 当前方式 | GPU判断 |
| --- | --- | --- |
| BAAI/bge-reranker-base候选原文重排 | 本地CPU，retrieval.py::rank_sources，batch_size=4 | 优先做GPU对照；候选数量/长度决定收益，不能预告倍数 |
| BAAI/bge-small-zh-v1.5查询向量 | 本地CPU | 可测GPU；单条短查询可能受调度/拷贝开销影响，未必明显更快 |
| DeepSeek关键词、选证、正文、质检 | 远端API | 本机GPU不能加速远端生成，需减少无效调用/上下文/重试 |
| SHA校验、JSON/原文映射、PDF字符定位、SQLite | CPU/文件I/O | 优化重复工作和算法；不适合直接改成CUDA |
| LightRAG图查询、候选装载/队列 | 现有图/向量存储与宿主生命周期 | 不能由embedding切GPU推断整个LightRAG已GPU化 |

CUDA本身是GPU计算后端，不是“在CPU上运行的服务”；本项目当前明确选了CPU会话。`knowledge/inference_runtime.py` 已支持显式选设备并核查实际provider，无需新造一套GPU管理层。

## 3. 冗余与必要开销

| 项目 | 8000实际发布 | main现状 | 结论 |
| --- | --- | --- | --- |
| 同查询完整校验 | validate三次，额外宿主目录再遍历 | 查询前后两次并复用部分结果 | 旧发布重复开销可减少；前后完整性保护不能直接删除 |
| 引用并发锁 | q3_tools进程级RLock包整个检索 | 每轮状态原子提交与迟到结果保护 | 应部署已验证改造；主要改善跨会话排队，不保证单问提速 |
| 模型取证、选证和覆盖 | 旧循环可能多次模型决策、独立覆盖判断 | 有界预取、每对象合并选证/覆盖、本请求结果复用 | 先联合集成；不能把最终事实质检当重复选证直接删除 |
| SDK传输连接 | 发布未含提速连接池链 | main已有有界传输复用、生命周期关闭 | 采用现有改造，不再复制第二个池 |
| PDF定位 | 逐字符访问页面元数据的旧热点 | main已有每页复用尺寸/旋转矩阵 | 历史局部64.531→13.125秒是局部剖析，不是总回答收益 |
| 全书来源/权重身份 | 冻结文件和模型身份核对 | 仍有内容核验、权重签名和全书映射遍历 | 有成本，但不能仅为速度弱化防换版；先从阶段数据量化 |
| 原生引擎初始化/释放 | 每查询执行 | main同样执行 | DeepTutor也如此，不是本项目独有错误；历史热初始化耗时很小，未证实值得常驻改造 |
| 正文后语义/视觉质检 | 额外模型调用，失败可修订 | 仍保留，main明确预算 | 是可见延迟成本；与选证职责不同，不能无条件删掉 |

## 4. DeepTutor的实际做法

1. `deeptutor/agents/loop/pipeline.py:1481`：对传统RAG知识库有界预取，独立知识库asyncio.gather，减少模型先决定“要不要检索”的回合。不是所有任务都预取，也不是一个原生候选可无限并发。
2. `deeptutor/runtime/agentic/client.py:234`：事件循环内有界SDK连接池；稳定系统提示见loop/pipeline约477行。main已适配相关做法，8000尚未统一部署。
3. `deeptutor/services/embedding/client.py`及adapters：统一provider请求，支持远端OpenAI兼容服务、Ollama等；Ollama适配器有keep_alive=5m。GPU在哪由对应模型服务决定，不是上游自动将本机所有计算改CUDA。
4. `deeptutor/services/rag/pipelines/lightrag/pipeline.py:609`：逐次build/initialize/query/finalize；其engine使用aquery_llm，宿主使用aquery_data避免内层再次生成答案。照搬上游整条查询链可能反增一次生成。

主要可借鉴优势是更少无效模型回合、资源复用和有界工具编排，而不是未经验证的“DeepTutor天然更快”。宿主额外Q2原文/版本核验属于本项目发布职责，上游不是可直接替换的同等质量基准。

## 5. 已有速度证据的正确解读

`OUTPUT_SPEED_ACCEPTANCE.md`的80次成对记录来自优化前后旧基线，不是最终教学整合版本，也不是当前8000：跨章31.469→23.547秒；普通定义17.875→18.891秒；图1-4为8.937→10.547秒。说明优化不是所有问题都达标，不能继续统一宣称20%提速。

本次还只读聚合了evidence-final的stage-observations，但它混有不同提交、不同问题和故障尝试，父阶段也包含子模型调用；这些阶段中位数不能相加、不能代替同题当前运行剖析。未将其作为“主瓶颈百分比”。

## 6. 建议顺序

1. 先完成已有主线集成计划，对齐main与现有Q4服务功能；固定一个统一宿主，避免重复开发已写好的提速代码。
2. 对该宿主做CPU基线，分别统计重排、embedding、文件/PDF、模型调用、最终质检；首进度、有效正文、正式完成分开。
3. 使用既有GPU环境先检查实际二进制/provider兼容，再用同一权重/教材/问题隔离验证reranker GPU；随后测embedding GPU。比较CPU/CPU、CPU/GPU、GPU/GPU三个组合，预热和冷启动分别记录；同来源质量、输出和成功率前提下选择。
4. GPU会话必须实际包含CUDAExecutionProvider，完成真实向量/重排推理；失败不能静默称GPU成功。切设备不改模型身份、向量维度、权重或候选，不以此重建图谱。
5. 只对证实耗时高的剩余阶段继续改造。小查询embedding若GPU无益则保留CPU；远端选证/质检等待用减少重复回合处理，文件校验保留版本保护。

当前未执行真实模型同题CPU/GPU对照、显存/算子实测或服务切换。GPU环境仅通过provider枚举，实际推理、数值/来源一致性和资源占用仍需验收。
