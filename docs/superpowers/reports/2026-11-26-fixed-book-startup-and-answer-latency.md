# 固定教材启动与回答延迟执行报告

日期 2026-11-26
工作树 student-frontend-reuse-20261117
计划 [2026-11-26 固定教材启动与回答延迟](../plans/2026-11-26-fixed-book-startup-and-answer-latency.md)
基线资料 [2026-11-25 固定教材启动分段计时](2026-11-25-fixed-book-startup-timing.md)

## 状态

本轮完成阶段 1 第 1、2 项和阶段 2 第 1 项，并在本机测试部署做了三次受控重启与一次首问采样。
阶段 1 第 3 项按计划交给旧索引退役计划；第 4–7 项、阶段 2 第 2–4 项和阶段 3 记录为未执行及理由。

## 1. 改动

| 提交 | 改动 |
| --- | --- |
| 7108f9ff | `manage_student_local.py`：worker 先启动并独立探测 `/health/ready`，随后才启动宿主与 Web。 |
| 3dd607ac | `student_release.py` 新增 `inspect()`（清单、文件集合、路径与文件存在性）；启动和选版改用 `inspect()`，逐文件 SHA-256 只保留在显式 `verify` 命令与打包产物核对。`run_student_release.plan()`、`select()` 随之调整。 |
| c4d64f4b | `setup_student_local.py` 新增 `rerank_device()`：仅在目标解释器具备 `CUDAExecutionProvider` 时把新本机安装写成 `RAG_RERANK_DEVICE=cuda`。 |

宿主代码无需改动即可走 CUDA 重排：`retrieval.rank_sources` 已按 `RAG_RERANK_DEVICE` 取设备，
`_reranker_on_device` 的 lru_cache 复用同一个 GPU 会话。

部署侧还做了两项可回退配置（在 `.runtime` 内，不属于代码发行）：

- `private/runtime.env` 备份为 `runtime.env.bak-20261126` 后，设 `RAG_RERANK_DEVICE=cuda`、
  `CUDA_CACHE_PATH=<deploy>/private/cuda-cache`（放在发行目录外，先预热一次 JIT 缓存）。
- `active-release.json` 保持 `progressive-context-20261125d`；从干净 HEAD 打包的
  `fixed-book-startup-20261126` 因下述上游快照不一致无法启动，未启用。

## 2. 启动

三次受控重启，同一教材与发行，宿主重排 CUDA、Embedding CPU：

| 启动 | 缓存 | 控制总计 | 固定教材初始化 | health 首次 | worker 就绪 |
| --- | --- | --- | --- | --- | --- |
| 20261126T171953-40224 | process-cold | 38.82 | 14.35 | 18.95 | 15.86 |
| 20261126T172043-14152 | os-warm | 30.90 | 8.70 | 12.76 | 13.93 |
| 20261126T172114-13176 | os-warm | 34.97 | 8.58 | 13.42 | 16.76 |

对照：11 月 25 日默认编排三次都在宿主 60 秒等待内失败；worker 单独冷启动 `warm_retrieval`
49.21–60.46 秒；唯一成功样本固定教材 33.48 秒；旧基线 98.72 秒。

控制脚本发行核对合计从 25.35–36.96 秒降到 4.44–5.86 秒（三个服务各一次 `inspect()`，
单次 1.38 秒、4924 个文件；一次全量 `verify()` 实测 140.92 秒）。

固定教材阶段中位数（成功样本 11.52 秒）：

| 阶段 | 中位数 | 说明 |
| --- | --- | --- |
| `worker.warm_retrieval` | 3.69 | 相对旧 49.21–60.46 秒 |
| `lightrag.manifest.host_textbook` | 1.96 | 正式教材仍有两次目录扫描 |
| `lightrag.manifest.frozen_input` | 1.58 | 冻结输入逐文件哈希 |
| `warmup.local_index` | 1.42 | 旧索引预热，随退役计划移除 |
| `warmup.sample_query` | 0.35 | 旧 11.88 秒，GPU 重排后下降 |
| `fixed_book.hashes` | 0.53 | 与 host_textbook 同根重复扫描 |

受控失败也留了轨迹：`20261126T171821-15144`，worker `app_import` 4.82 秒后在
`install_learning_binding_adapter` 退出，`control.failed` 记 `target=worker`、`RuntimeError`、13.83 秒。

## 3. 重排设备对照

24 条正式教材候选原文，同一模型与快照：

| 设备 | providers | 初始化 | 单次重排 | 最高分 |
| --- | --- | --- | --- | --- |
| CPU | CPUExecutionProvider | 2.85 s | 11.36 / 11.15 / 11.43 s | -3.585 |
| CUDA | CUDAExecutionProvider, CPU | 2.90 s（JIT 已缓存） | 0.68 / 0.084 / 0.086 s | -3.5833 |

- 首次使用 CUDA 且 JIT 缓存为空时，首轮重排 45.39 秒（另一次 215.89 秒），因此把
  `CUDA_CACHE_PATH` 放在发行目录外并预热。
- `nvidia-smi` 显示重排会话约占 1.7 GiB 显存（2105 → 3812/4067 MiB）。
- `/health` 显示 `configured.reranker=cuda`，会话 providers 含 `CUDAExecutionProvider`；
  正式教材 LightRAG 原文重排路径由现有 `verify_device` 明确报错，不会静默按 CPU 使用。旧本地检索路径
  （`knowledge/local_rag/rerank.py`）另有捕获异常后关闭重排的旧行为，不在本次范围内。

## 4. 首问

复核账号 `heart-review-01`，题「自变量是什么」：

| 里程碑 | 本次（CUDA） | 11-26 CPU 样本 |
| --- | --- | --- |
| 首个正文 | 9.06 s | 17.48 s |
| 首个工具 | 9.49 s | 17.48 s |
| 来源 | 14.07 s（4 条） | 50.69 s（4 条） |
| 完成 | 14.31 s（4291 字符） | 50.77 s |

本次采样的第一问命中了上一回合的 0.124 秒回放，第二问才是真实回答；同一会话在完成约 0.5 秒后
再次提交被接受，没有再出现 11 月 25 日的 `protocol_error`。输出长度不同，不能把 50.77→14.31 秒
全部归因于重排；设备对照和 `warmup.sample_query` 是更直接的证据。

## 5. 未执行项与理由

| 计划项 | 状态 | 理由 |
| --- | --- | --- |
| 阶段 1 第 3 项 旧索引退役 | 交给独立计划 | 计划原文即指向 [旧索引退役计划](../plans/2026-11-25-retire-legacy-textbook-index.md)。 |
| 阶段 1 第 4–5 项 安装时哈希表、冻结输入扫描 | 未执行 | 需要计划未定义的教材发布/安装入口；必须用真实候选重建快照验证。按本轮轨迹剩余约 3.5 秒/次。 |
| 阶段 1 第 6–7 项 预生成图表/词表、页码映射 | 未执行 | 同上，需要发布管线；当前启动成本小（图表 0.00、图表目录 0.14、目录 0.76 秒）。 |
| 阶段 2 第 2–4 项 连接复用、SQLite 摘要定位、异步摘要 | 未触发 | 轨迹没有占主导的重复校验或连接阶段；合成历史读取 10–30 ms。 |
| 阶段 3 统一后端 | 未执行 | 宿主与 worker 的结构性合并，超出本轮可分步验收的范围。 |

## 6. 已知阻塞与注意

- 干净 HEAD 目前无法打包成可启动发行：`project/vendor/DeepTutor/UPSTREAM_SNAPSHOT.json` 的
  `local_changes` 与 HEAD 源码不一致（148 项仅换行差异、17 项内容差异），
  `install_learning_binding_adapter` 会拒绝。本轮验收因此只在已验证发行上替换控制脚本与运行配置。
  阶段 3 移除上游匹配检查后，这项阻塞才会消失；在那之前做整包计时需先核对或更新快照。
- `inspect()` 不再核对文件内容，同名篡改文件会通过启动检查；显式 `verify` 仍能发现。
- 发行清单沿用旧口径：`node_modules`、`.next`、`__pycache__`、`.cache` 不参与清单核对。发行现在是唯一入口门禁，
  这些目录里的注入文件不会被发现；`.cache` 是按本次 CUDA JIT 缓存需要新增的排除项。
- 已登记且仍存活的旧服务只按进程身份判断；若进程卡死但端口仍开，`start` 不会重新探测它。
- 首问采样器不保证新会话：第一问可能回放上一回合，报告时须区分回放与真实回答。

## 7. 回退

- 启动顺序与发行核对：恢复上一版 `control/*.py`，或回退 7108f9ff、3dd607ac。
- GPU 重排：恢复 `private/runtime.env.bak-20261126` 后重启，`/health` 应回到 CPU providers。
