# RAG GPU 接入与同模型对照（2026-10-10）

## 完成内容

- CUDA Driver API 成功初始化，识别 RTX 5060 Laptop GPU，总显存 8,546,484,224 bytes（约 8 GB）。NVML 管理查询仍报错，未据此判断 CUDA 不可用。
- 建立 .venv-gpu：自身安装 ONNX Runtime GPU 1.26.0 与固定的 CUDA 12.9/cuDNN 9 运行库，通过 .pth 复用原 .venv 应用依赖；原 CPU 环境保留。此 GPU 环境依赖原 .venv，重建原环境后需再检查兼容性。
- 为 embedding/reranker 增加显式 cpu/cuda 配置，缓存按模型和设备区分。要求 CUDA 时检查真实会话，拒绝静默 CPU 回退；检索异常仍按原有机制降级并记录 trace。
- 启动入口优先使用经过本机验证的 GPU 环境，预热 reranker 后启动服务。/health 显示实际加载设备与会话 providers。

## 同模型对照

使用现有冻结题集 tests/data/rag_blind_reranker_2026_10_10.json：12 教材内题、4 教材外题。固定 bge-reranker-base、索引、候选池、batch_size=4、0.15 门槛与输入格式，顺序运行。embedding 均为 CPU。先初始化并预热，以下只统计热启动检索，不包含网络大模型生成。

| 方法 | Hit@2 | 教材外仍返回出处 | 中位耗时 | p95 耗时 |
| --- | ---: | ---: | ---: | ---: |
| CPU，ORT 1.31.0 | 10/12 | 0/4 | 7753.1 ms | 12152.7 ms |
| GPU，ORT 1.26.0 | 10/12 | 0/4 | 454.0 ms | 575.2 ms |

中位耗时约改善 17.1 倍。16 题逐题返回的出处、顺序及摘录一致；对应候选原始重排分数最大绝对差约 0.00890。ORT 版本和执行后端不同，不应声称浮点评分完全一致。没有重排失败降级。

CPU 冷探针约 2.76 秒，GPU 首次成功冷探针约 46.54 秒，包含初始化及两条短文本推理；更早的一次探针因 40 秒超时终止。启动预热用于把这项开销提前处理。首次运行耗时与系统缓存相关，不能保证每次固定为 47 秒。

p95 为 16 个观测的 nearest-rank 统计，样本少；不代表生产并发性能。已知有序对与 A∧B 两题仍未命中目标，GPU 加速没有修复这些质量问题。

原始记录：artifacts/rag-cpu-benchmark.json、artifacts/rag-gpu-benchmark.json。测试：CPU 环境 19 项通过；GPU 环境同样 19 项通过。ONNX profile 记录 361 个 CUDA 算子事件（包含 MatMul、LayerNormalization、Softmax），8 个 CPU 事件。实际算子证据见 artifacts/reranker-cuda-proof.json。

## 启动与复现

正常使用 3-start-api.bat。启用条件是 .venv-gpu 中存在本机验证标记且 Python 可用；模型预热失败会明确退出，避免以为 GPU 生效。

建立 GPU 环境：

~~~powershell
.\.venv\Scripts\python.exe -m scripts.setup_gpu_environment
~~~

复现对照（顺序运行）：

~~~powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_rag_device --device cpu --output artifacts/rag-cpu-benchmark.json
.\.venv-gpu\Scripts\python.exe -m scripts.benchmark_rag_device --device cuda --output artifacts/rag-gpu-benchmark.json
.\.venv-gpu\Scripts\python.exe -m scripts.profile_rag_cuda
~~~

环境变量：RAG_RERANK_DEVICE=cpu/cuda；RAG_EMBED_DEVICE=cpu/cuda。本阶段只把 reranker 切至 GPU，embedding 保持 CPU，以便隔离效果。GPU 环境安装不涉及系统驱动升级；固定依赖见 requirements-gpu-runtime.txt。

## 下一步

基于当前速度基线，建立证据级人工题集并做公式结构索引/完整术语召回；更强 reranker 和 embedding 作为独立实验，不与此次设备迁移混在一起。参见 [深度调研报告](2026-10-10-textbook-rag-deep-research.md)。

## 服务验证

项目已通过 GPU 环境启动，首页与 /health 返回 HTTP 200，mock_mode=false。/health 的 reranker 会话包含 CUDAExecutionProvider，embedding 会话为 CPUExecutionProvider。启动脚本改为等待健康检查成功再打开浏览器，避免预热时提前打开导致无法访问。
