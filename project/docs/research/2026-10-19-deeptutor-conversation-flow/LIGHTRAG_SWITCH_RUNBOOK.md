# LightRAG 候选加载、复验与切换预案

当前结论：后端可集成交付，正式切换条件未满足。本轮不执行正式接线或切换。

## 本机目录与安全配置

以下 PowerShell 命令在 `E:\项目\heart-worktrees\lightrag-integration\project\integration\discrete-math-tutor` 执行。使用现有独立环境；命令不安装/修改共享环境。

```powershell
$py = '.venv-lightrag/Scripts/python.exe'
$candidate = '.runtime/lightrag-proxy-nothinking/0a6096dc43a8829d48776cbcd0c583b6dc779bd6b450614b4bd20bd1d7f0e5ce'
$docs = '../../docs/research/2026-10-19-deeptutor-conversation-flow'
$env:OPENAI_BASE_URL = 'https://cn.chatapi.app/v1'
$env:DEEPSEEK_MODEL = 'deepseek-flash'
$env:OPENAI_MODEL = 'deepseek-flash'
$env:OPENAI_VISION_MODEL = 'deepseek-flash'
$env:LLM_MOCK = '0'
$env:RAG_EMBED_DEVICE = 'cuda'
$env:RAG_RERANK_DEVICE = 'cuda'
$env:RAG_RERANK_MODEL = 'BAAI/bge-reranker-base'
# 由宿主安全配置预先注入 DEEPSEEK_API_KEY / OPENAI_API_KEY；不要写入脚本、报告或Git。
# 不输出完整.env，也不在命令里打印环境变量。
```

模型传输自行校验候选策略；缺配置、SDK不兼容、输入/模型签名变化、CUDA不可用均须明确失败，不切回旧检索冒称成功。新进程不要沿用不同endpoint或thinking策略恢复旧候选。密钥不是交付材料。

## 检查与加载

```powershell
& $py -X utf8 -B scripts/check_lightrag_delivery.py --candidate $candidate --lock "$docs/LIGHTRAG_DELIVERY_LOCK.json"
& $py -X utf8 -B scripts/check_lightrag_completion.py $candidate
# 首次准备，或复核已有相同宿主；不得覆盖不同宿主目录。
& $py -X utf8 -B scripts/prepare_lightrag_acceptance.py `
  --candidate $candidate `
  --host-revision a2be38741c2c08162efd2335e7249db3353f9812 `
  --baseline-index 'E:\项目\heart\project\integration\discrete-math-tutor\knowledge\courses\experimental-psychology-3\rag_index.sqlite3' `
  --output .runtime/lightrag-acceptance-01
& $py -X utf8 -B scripts/serve_lightrag_acceptance.py --isolation .runtime/lightrag-acceptance-01 --port 18977
```

基线SQLite只读核验与复制；如主目录索引已变化，命令明确失败，请使用Q2交付签名一致的保留副本，不能放松哈希检查。冻结教材始终取候选input/固定Q2snapshot；不从上述主目录重新取教材。独立服务启动实际执行SDK initialize/finalize并读入GraphML/KV/VDB，失败不开放成功health。

另一个终端复验（同一应用目录）：

```powershell
Invoke-RestMethod http://127.0.0.1:18977/health
& $py -X utf8 -B scripts/check_lightrag_acceptance.py --url http://127.0.0.1:18977 --output .runtime/lightrag-acceptance-01/comparisons
$env:LIGHTRAG_ACCEPTANCE_HOST = (Resolve-Path .runtime/lightrag-acceptance-01/host).Path
& $py -X utf8 -B -m unittest discover -s tests -p test_lightrag_q3_adapter.py -v
Remove-Item Env:LIGHTRAG_ACCEPTANCE_HOST
& $py -X utf8 -B -m unittest discover -s tests -p test_lightrag_backend.py -v
```

完整模型矩阵会真实消费API，写入独立测试学生库和忽略的运行证据；当前已知失败应返回非零，不能期待全绿。每次都保留原始attempt，不能仅报告最好一次。新驱动会核验下一点ID确实变化，并单独报告首轮是否已发布；旧矩阵的目标ID已从原始响应复核。验收客户端最后版本关闭隐藏传输重试；早期矩阵的模型create调用数不能换算为全部HTTP次数。

停止时在运行此服务的终端按Ctrl+C，核对该端口和该脚本进程退出，释放GPU模型；不关闭其他窗口服务。

## 构建/恢复（已有完整候选无需重建）

```powershell
& $py -X utf8 -B scripts/build_lightrag_book.py `
  --source .runtime/q2-delivery-95b956a/snapshot/course `
  --env-file 'E:\项目\heart\project\integration\discrete-math-tutor\.env' `
  --output .runtime/lightrag-proxy-nothinking `
  --resume-candidate $candidate
```

.env仅补缺失项，进程安全配置优先；不复制或修改该文件。此命令会校验源文件、模型策略和SDK版本，保留同候选原生缓存/失败恢复。不修改运行中的输入。需要新模型/教材身份时另建独立候选，绝不能改旧候选签名硬接续。取消协议、锁和重试见 LIGHTRAG_INTERFACE.md。完整候选及冻结源保留原绝对位置；异机迁移不在已通过范围。

## 集成窗口采用接口

```python
from knowledge.lightrag.course_input import COURSE
from knowledge.lightrag.retrieval import LightRagBackend
from knowledge.lightrag.q3_adapter import LightRagNavigator

# 仅隔离候选验收允许此开关；正式发布要先完成宿主发布授权/就绪门禁。
backend = LightRagBackend(candidate_path, authorized_course_ids={COURSE}, allow_candidate=True)
backend.validate(COURSE)
navigator = LightRagNavigator(existing_q2_navigator, backend, course_id=COURSE,
                              cancellation=existing_cancellation)
# 接已有 RetrieveCourseTool 的导航/search边界；不另建AgentLoop。
```

若宿主 q5.loop_binding 启用，run_agent_loop_turn 会以 Q5Navigator(search_fn=q5.search) 覆盖 navigator。集成窗口必须在已有Q5 search注入上述一般检索，并保留原Q2/Q5 resolve、精确read_target、学习状态与计划契约。本窗口没有改公共入口，不能仅传入此对象就宣称真实页面启用。

不要设置 `RAG_RETRIEVAL_ENGINE=lightrag` 当作已经生效：当前公共后端枚举没有完成本轮接线。后续应由集成窗口实现明确的后端选择/工厂；所选后端、候选身份、实际backend、fallback及失败原因必须可观测。公开检索结果继续用现有SourceRef与Q2 EvidenceBundle.publish；不能把 graph_context 或元数据变成教材证据。与Q2精确目标并用时实际backend=q2_exact应单列。

## 就绪门禁与失败处理

需要同时成立：

1. 交付锁、固定输入、模型权重/维度/endpoint策略、SDK兼容检查通过，原生重启可加载，逐章非空且无未完成文档。
2. 课程授权、教材发布及版本门禁通过。当前staging/ready=false，**不通过修改状态来完成本轮验收**。
3. 跨章/章概述覆盖、正式回答门禁失败解决；同题保留所有尝试，无来源和后端不可用明确阻止正式发布。
4. 在集成窗口稳定宿主上采用现有Q3/Q5工具、引用协议，验证正式TaskService/页面及Q2导航；图像语义声明须实际送像素且审核状态如实显示。
5. 独立部署环境、资源限额、就绪检查、并发和取消满足正式服务要求；本机借用包环境不能视为部署完成。

检索异常直接返回失败；无可核验原文则返回no_evidence并阻止发布。宿主若希望提供旧后端服务，应通过明确的配置/路由切换记录 actual_backend=旧后端、fallback=true/原因，不得将该回答记为LightRAG成功。无需为了容错更改教材版本、引用协议或学生状态。

## 后续人工切换与回退顺序（本轮未执行）

1. 集成窗口确认稳定提交、发布授权与上述门禁；保留旧SQLite及哈希，不覆盖候选以外目录。
2. 将所需独立提交采用到集成worktree，安全注入同模型配置；先用独立端口/测试学生跑完整矩阵和页面检查。
3. 就绪全部通过后由集成窗口批准并显式切换公共检索工厂到已核验候选。仅改变检索路由，不移动教材、重置学习状态或删除会话。
4. 发生失效、错误或资源争用：停止向候选分配新请求，等待/取消已有worker并释放锁；显式恢复原工厂/旧索引路径与已固定模型配置，再做旧检索health/来源检查。记录切换时间、真实backend及失败原因；保留候选、缓存、运行证据用于复盘。
5. 不清理其他窗口worktree/数据库/索引，不以自动fallback掩盖未完成验收。
