# 构建、试验与切换

以下命令在 `E:/项目/heart/project/integration/discrete-math-tutor` 中运行。默认引用链路尚未切换。

## 独立构建

```powershell
.\.venv-gpu\Scripts\python.exe -m scripts.build_citation_index --output artifacts/citation-grounding/new-build/positions.sqlite3
```

目标文件必须不存在；构建不会覆盖当前服务索引。报告同目录 `.report.json` 包含文档哈希与对齐计数。更新 PDF 后必须先更新教材清单，再重建位置索引；旧版本坐标不能直接复用。

当前可用构建：`artifacts/citation-grounding/build-v2/positions.sqlite3`。早期 `build-v1` 缺少新规范化标识，已被明确拒绝加载，保留作探索记录。

## 隔离验收

```powershell
.\.venv-gpu\Scripts\python.exe -m scripts.evaluate_citation_locations --split development --index artifacts/citation-grounding/build-v2/positions.sqlite3 --output artifacts/citation-grounding/new-development.json
.\.venv-gpu\Scripts\python.exe -m scripts.check_double_blind_citations --index artifacts/citation-grounding/build-v2/positions.sqlite3 --output artifacts/citation-grounding/new-double-blind.json
.\.venv-gpu\Scripts\python.exe -m scripts.accept_citation_grounding --mode candidate --repeat-high-risk --index artifacts/citation-grounding/build-v2/positions.sqlite3 --output artifacts/citation-grounding/new-160.json
```

每个输出名必须全新；保留被中断的试验。真实模型入口使用独立临时课程库及合成账户，写入逐次模型原始响应、请求次数、终止原因、检索范围、任务结果和耗时。错误版本负例实际提交错误版本选区，不能只把错误哈希留在测试标签里。

留出集只在代码冻结后的正式验收中检查，不用于反复调参。语义、来源存在性、几何、最终图片、检索召回分别报告，教师审核单独注明。

## 门槛通过后启用

```powershell
.\.venv-gpu\Scripts\python.exe -m scripts.switch_citation_index --enable artifacts/citation-grounding/build-v2/positions.sqlite3 --acceptance 发布验收报告.json
```

切换入口校验索引哈希、全部教材版本及8项门槛；未达标报告会拒绝启用。合格索引复制到课程内以哈希命名的独立文件，再原子替换指针，同时保存上一指针。验收报告应包含 `schema`、`index_sha256`、`gates`、`metrics`、`real_model_runs`、`reviewed_holdout_cases`；未经逐项复核不得手工填写“passed”。

切换或教材版本更新后重启服务，清除已有教材、检索和 PDF 清单缓存。服务每轮创建索引只读连接，不持有旧位置缓存。测试用显式环境变量只在隔离进程设置，不能据此绕过正式切换验收。

## 回退

```powershell
.\.venv-gpu\Scripts\python.exe -m scripts.switch_citation_index --rollback
# 或禁用新链路：
.\.venv-gpu\Scripts\python.exe -m scripts.switch_citation_index --disable
```

回退同样校验上一版的文件哈希及教材版本；已失效的旧教材索引不能回启。也可设置 `CITATION_GROUNDING_MODE=off` 并重启服务。现有历史保留已保存证据，不从新教材重新猜测旧答案的精确位置。
