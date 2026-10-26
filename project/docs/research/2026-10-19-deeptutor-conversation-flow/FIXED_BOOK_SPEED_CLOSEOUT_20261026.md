# 固定教材提速：实现与本机独立环境收尾

日期：2026-10-26。当前主流程已实现，本机独立环境、实际模型与页面复验通过。**严格前后交替对照及人工置信度校准未完成，不标记全部性能指标通过。** 初次交付与失败记录保留在 [实施记录](FIXED_BOOK_RETRIEVAL_SPEED_EXECUTION_20261026.md)。

后续已切换到 [8000 主入口并完成最终检查](DEPLOY_8000_FINAL_CHECK_20261026.md)，8137 已停止；下文 8137 相关数据作为切换前记录保留。

## 本轮新增收尾

- 复杂 LightRAG 查询直接匹配冻结图谱中的已存在实体，用 SDK 的 `hl_keywords/ll_keywords` 传入；优先完整实体，实例内有界缓存。不认识的对象保留 SDK 模型提取。已读固定 SDK 的缓存实现：缓存键包含查询、模式、语言及 keyword 模型身份，存储命名空间绑定候选版本，没有另建模型缓存。
- 真实跨章复验中，SDK 关键词模型调用为 0，两个独立对象仍分别有证据判断，最后一次回答生成。普通 B 路径一次查询 embedding（一个文本），无模型路由、关键词或选证调用，聊天模型仅最终回答一次。
- 修复工具入口残留 `course_release.validate(refresh=True)` 全书扫描：固定模式统一读取启动快照、返回副本；错误 release_id 仍拒绝。
- 取消端点、旧 SSE 回合现在统一为 task_cancelled；取消后其他学生与常驻图谱下一问正常。初始化失败释放已创建资源；关闭实例失败也保证关闭后台 worker 和模型连接池。
- 修复真实计划生成失败：需求提取提示词的“未提供均填空字符串”与列表契约冲突。仅在 LLM 输出入口归一化空数组/可缺字段，非空错误类型仍拒绝；未放宽时间、来源和权限约束。
- 三项旧断言已按实际契约修正：隔离测试不再意外挂载本机真实教材工具；重放单独检查 reader_action_replay；已删除二次模型审稿后，不再要求 checking 状态。取消相关测试改为明确检查 task_cancelled，保留取消不保存草稿和不推进位置的断言。

## 独立环境与来源

环境：`E:\项目\heart\.runtime\fixed-book-speed-20261025\standalone-venv`，Python 3.12.14；当前 8137 入口 `E:\项目\heart\.runtime\main-integration-20261025\serve_standalone.py`。

此入口不追加旧环境路径。LightRAG 1.5.7、FastEmbed GPU 0.8.1、ONNX Runtime GPU 1.26.0、LlamaIndex 0.14.25 与 BM25 0.7.1 均从该环境导入。pip check 通过，SDK 的 172 个 Python 文件与官方 1.5.7 wheel 逐字节一致；官方包 SHA256 见 `.runtime/fixed-book-speed-20261025/environment-seal.json`。没有修改旧的两个 Python 环境。

完整 140 包版本锁：[requirements-fixed-book-gpu-win32-py312.lock.txt](../../../integration/discrete-math-tutor/requirements-fixed-book-gpu-win32-py312.lock.txt)。这是本机独立运行验收，不等于跨机器驱动和全新联网安装也已通过。

普通启动脚本优先选择有实际 GPU 验证记录的 `.venv-runtime`；原启动方式仍可用。当前环境通过目录 junction 提供给主目录和集成目录，环境、模型与教材均不提交。主线代码身份以本批 Git 提交及 `.runtime/fixed-book-speed-20261025/main-sync.json` 为准。

## 验收结果

独立环境中：254 项联合回归、27 项设备/资产/发布/引用边界测试、16 项本次计划测试均通过。分别见 `tests-standalone2.log`、`tests-negative-matrix.log`、`tests-q5-empty2.log`，不把中途失败日志改写为成功。

此前独立环境并行复验期间，执行进程与服务异常退出，未记录 Python 回溯；该轮 `tests-standalone.log`、`page-standalone.log` 未计为通过。恢复后采用顺序复验。初次计划生成失败保留在 `q5-native/plan.json`；另一次测试脚本错误地要求插问响应包含 q5_status，已改为读取同一测试学生的持久化状态，原失败也保留。

### 20 次暖运行

每类 5 次，成功 20/20。原始记录：`warm-repeats/*.json`。这组是在独立环境整理前、同样 GPU 模型配置的组合环境中取得；不能伪装成独立环境的严格 A/B 对照。

| 场景 | 完成率 | 首字中位数/秒 | 完整中位数/秒 | 完整最大值/秒 |
|---|---:|---:|---:|---:|
| 自变量 | 5/5 | 5.578 | 7.359 | 13.438 |
| 因变量 | 5/5 | 2.937 | 4.781 | 8.719 |
| 遗忘曲线＋原图 | 5/5 | 7.187 | 8.047 | 10.563 |
| 科学方法与自变量跨章联系 | 5/5 | 7.312 | 9.062 | 11.922 |

### 独立环境最新浏览器

原始记录：`page-standalone2.log`、`page-results.json`、`page-final.json`。刷新恢复通过，页面错误数 0，带图答案显示 1 张教材原图。

| 场景 | 状态 | 完整秒数 |
|---|---|---:|
| text | answered | 3.186 |
| image | answered | 7.683 |
| chapter | answered | 4.774 |
| next | answered | 2.513 |
| cross | answered | 6.730 |
| ask-user | awaiting_clarification | 2.142 |
| ask-user-resume | answered | 3.520 |
| pdf | answered | 2.784 |
| pdf-followup | answered | 3.438 |

### 真实 Q5 学习接续

原始记录：`q5-native-final/*.json`。生成草稿、确认讲解、跨章插问、返回原目标、理解后推进均通过；插问前后持久化的 current_item_id 和 revision 一致。没有隐式创建长期掌握路径，也没有因“我懂了”产生掌握评分。

| 回合 | 状态 | 完整秒数 |
|---|---|---:|
| plan | awaiting_clarification | 8.250 |
| confirm | answered | 6.094 |
| interjection | answered | 9.890 |
| return | answered | 5.328 |
| next | answered | 5.094 |

### 启动、索引与限制

当前这次启动 `14.234` 秒；独立环境首次曾为 111.172 秒，后续还测得 82.516、84.953 秒，全部保留。不能把加载成本移到启动后隐藏。当前 embedding/reranker 均为真实 CUDA session；图处理与数据库仍在 CPU，聊天模型在远端。

封存的 7 项核心图谱/向量/文本存储哈希全部未变。SDK 查询缓存允许变化；未重建全书，未改 staging/ready=false。

原生图存储查询继续串行持锁，独立对象的选证与后续查询可重叠，不能声称 SDK 图查询已经完全并发。每次新加载完整图谱会占用较多 RAM，当前保持单实例。

## 重新部署与回退

在 Windows x64 / Python 3.12 的**新** `.venv-runtime` 中安装本批 lock，使用既有代理配置；不要向已有环境直接覆盖安装。驱动和 CUDA 可用性需本机实测。首次可直接用该 Python 运行 `-m scripts.start_server`，显式设置 RAG_EMBED_DEVICE/RAG_RERANK_DEVICE 为 cuda，读取 `/health` 确认两个真实 session 均有 CUDAExecutionProvider 后保存 gpu-verified.json，后续启动脚本才优先使用该环境。

教材、模型配置、PDF、图谱与资产登记更新必须停止服务、更新、重启。固定模式有意不检测运行中同路径内容替换；权限、资源缺失、路径边界和引用编号检查仍在。

回退只切换代码和启动配置；不覆盖已有学习数据库，不清空索引。可回退到 `8e58cca` 的独立代码副本并使用原 serve_gpu.py；不要用会强制开启固定模式的包装入口冒充已关闭。不得同时启动两个全书图谱实例。

剩余专项验收：同一对话快照、每类至少 5 对的前后交替性能实验；人工标注置信度/检索质量；OS 关闭时在途任务和全部故障组合；跨机器全新部署。当前数据不支持宣称 p95 或每次固定几秒完成。
