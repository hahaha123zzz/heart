# LightRAG 并行执行记录

日期：2026-10-20。本窗口继续执行全书11章迁入和真实建图；以下状态随实际结果更新，当前仍在构建。

## 工作树、基线与边界

- 主工作树 `E:/项目/heart` 当前基线核对为 `9c746e28173f7dcfeef34e8d6134dab7e58c5286`，不是旧报告中的 SHA。
- 独立工作树 `E:/项目/heart-worktrees/lightrag-integration`，分支 `codex/lightrag-integration`。
- Q3/Q4 稳定集成提交已核对为 `f886144`；该工作树有尚未提交的公共入口修改，只作为已登记依赖，不复制、不修改。
- 项目根没有磁盘上的 AGENTS.md；遵循用户提供的全局 AGENTS 指令。未修改 vendor/DeepTutor，因此其内部 AGENTS 不在本次写入范围。
- 主工作树4,455项教材删除、未跟踪心理学课程、数据库、其他窗口代码均保留。
- 独立 `.venv-lightrag` 安装固定 SDK 与必要缺失依赖；只读借用既有 GPU/CPU 环境的已安装包，新包不写入共享环境。不复制 `.env` 和密钥。

## 源码与修改

来源：`D:/deeptutor` 当前 HEAD `6cf793bd868ba5ecbe64722936d4be8fab5a01df`。该仓库 llm/factory.py 有修改，与本次 lightrag 源文件无关；实际逐文件哈希另存 UPSTREAM.json，不仅依赖 HEAD。

现有 `project/vendor/DeepTutor` 已含原始来源副本，18项文件逐字节SHA256与D:/deeptutor一致，因此直接复用该固定副本，不重复提交第二套来源；`third_party/DeepTutor/lightrag-source/README.md` 指向来源台账。上游无根NOTICE，许可证保留。活动适配保存在 `knowledge/lightrag/`，不导入完整 DeepTutor 应用。

| 文件组 | 处理 |
| --- | --- |
| engine/parser/sidecar | 复用 SDK 校验、解析/IR 与结构化源校验；注册路径改为本项目；改用 aquery_data；修正 Windows URI 恢复 |
| ingress/block_policy | 保留冻结、摘要、路径/资源校验及块审计；补 Windows reparse point 拒绝 |
| worker/write_lock | 保留固定工作循环、回调/取消和跨进程写锁；补 Windows reparse point 拒绝 |
| storage/cache_reuse | 保留存储/状态读取和可用缓存算法；embedding 签名接宿主；候选状态独立，不调用全局发布器 |
| config/roles/indexing_policy | 保留上游重试分类/上限、模式与身份散列语义；替换全局账户、模型目录、配置入口 |
| pipeline | 保留上游引擎/冻结/工作循环/锁，宿主编排改为全书冻结、逐章状态、SDK 原生重试、全书完整性门禁；不引入 KB 管理应用 |
| course_input/retrieval/q3_adapter | 必要 Q2 结构转换、原文交集映射、宿主权限及可选 Q3 适配；不实现另一套学习状态或引用协议 |

依赖与许可证：DeepTutor Apache-2.0；lightrag-hku 1.5.7 MIT；langchain-text-splitters 0.3.11 MIT；psutil 7.2.2 BSD-3-Clause。实际依赖版本与目标文件哈希将在最终快照中登记。

## 输入与构建记录

全书Q2数据真实存在但未跟踪，课程 `staging`。固定输入含11章正文/原件/PDF/表格/公式/原图及清单；冻结副本和哈希均位于独立候选目录。原始 snapshot 包含 crops，但这些派生产物从教材版本核验中排除；正式教材字段变更仍拒绝混用。

当前真实候选：`.runtime/lightrag/2331025f52c8061dbee866dde4330b04fb075f7dfba9203f738be34173f342e0/`。`input_signature` 为该目录名；实际物质输入哈希另见最终输入清单。之前候选保留失败/取消记录，不冒充全书完成。

`input_validation.json` 已验证11章、4,602块、163表格、81个OMML对象；179项有效视觉资源全部映射，44项异常资源全部排除。179项仍 `pending` 审核，OMML仍待PDF逐式核验，不标多模态完整。

资源策略：CPU embedding，模型共享并发2、文件处理1、嵌入1；EXTRACT/VLM/KEYWORD 使用已有 deepseek-flash 配置。SDK 原生 Sidecar/paragraph_semantic 分块，1200 tokens，gleaning=0。角色限额和共享限额均有限；不占用本地GPU进行建图。

## 失败、取消、恢复与验证记录

- build 首次：Q2 load_visuals 实际返回 `(visuals,gaps)`，首次适配按数组访问失败；修正，原日志保留。
- build-02/03：独立环境未自动继承原 venv 的 CPU依赖链，随后只读补齐；资源记录缺 psutil 后在独立环境安装。
- build-04：真实模型调用47次后，主动取消验证完成，状态 `cancelled`，进程退出，冻结输入与SDK缓存保留。取消后的SDK子任务关闭错误完整保留，不算建图成功。
- build-05：恢复正确识别11个中断文档；暴露 SDK 1.5.7 Windows sidecar URI 写入/解析不对称，使 blocks_path 丢失，备用R分块又缺 langchain-text-splitters。适配层修复URI，新增实际SDK往返测试；安装必要分块依赖。
- build-06：固定SDK对FAILED文档需要原生 manual-retry 意图，仅驱动 process_enqueue 不会重试；已按SDK协议接入 commit_manual_retry_request，不手改状态。
- 两次旧签名变化来自其他页面新增 crops，非教材变化；修正物质输入范围，新增裁图不污染版本测试。
- build-07：正在真实处理全部11章，实际图像/表格分析及实体关系抽取已发生，未完成。
- 专项：19项通过（`.runtime-lightrag-tests-03.log`）；Windows sidecar往返、结构化API不生成答案、版本/返回形状、失败、无结果、路径、锁、权限、来源隔离、嵌入身份、重试和取消。
- 全书结构检查通过（`.runtime-lightrag-input-check-03.log`）；最初相对路径检查失败，已明确转绝对路径后独立复验。

模型调用和可得 token 用量见每个候选 usage.json；不估算费用，不把聚合用量伪装成逐章精确分账。资源占用记录在 progress.json 的 runs/resource 与采样峰值；首次启动尚未进入记录器的失败只保留日志，不能补造耗时。

## 接口与后续交付

稳定接口、Q2证据发布和Q3调用边界见 LIGHTRAG_INTERFACE.md。公共入口/工具注册/AgentLoop/页面由集成窗口负责。

最终将补充逐章状态、实体/关系/文本块实数、真实检索与Q3工具调用、版本/失败/恢复检查、实际耗时/用量、未运行项和提交顺序。未自动合入 main、未开启正式服务、未切换教材或索引。


## Q2 固定交付补充（95b956a）

已阅读 `Q2_TARGET_INPUT_STAGE.md`，用该提交中的原 `freeze_course_inputs.py --verify` 实际复核 v2：11章/325文件/102,504,640字节，snapshot_id `0a6096dc43a8829d48776cbcd0c583b6dc779bd6b450614b4bd20bd1d7f0e5ce`，清单SHA256 `02b3a221c1d795d5894b1810332d0762f2ce7276b03cd73ba7bb49362cf2fc9d`；清单字节与Git提交一致。

逐项比较325个固定交付文件与现有候选输入，325/325哈希完全相同、0差异；已有抽取没有混入另一教材版本。为停止后续读取可变主目录，先写本候选取消标记、确认进程退出并取得原跨进程写锁，然后在本候选内保留 `input-before-q2/` 和 `input_manifest.before-q2.json`，复制Q2冻结输入，绑定到本窗口只读副本 `.runtime/q2-delivery-95b956a/snapshot/course`。原图谱/SDK已接受文档/缓存不删除。该暂停用于固定数据权威，不用于更新Git基线；分支基线仍为9c746e2。

候选目录ID继续保留原2331025f…以维持SDK工作区名；规范输入身份已改为Q2的0a6096dc…，不再把候选目录名当教材snapshot_id。`q2_adoption` 保存等价证明。build-08正在同一候选中续跑，后续只读本窗口Q2固定副本。

更正视觉结论：44项由Q2确认是装饰栏头（不是44张丢失的知识图），按 `exclude_decoration` 排除，未生成替代图；179项保持pending。全书input_manifest.json保持staging，ready=false。Q2交付没有单独OMML XML文件；81个对象的解析身份和原DOCX仍在快照中，公式视觉/逐式语义核验未完成，不冒称多模态完整。

真实SDK替身模型专项通过：一次部分失败（1 processed/1 failed）、原生manual-retry后两文档完成、实际2实体/1关系、重启后0重新生成；这是隔离SDK/恢复验证，不是教材真实模型通过。首次验证脚本把调度记录当完整记录，暴露 `get_docs_by_ids` 不含chunks_list；已改用严格完整点读，避免把已处理文档错误统计为0块。实际全书后续采样和最终门禁使用完整记录。

当前21项专项通过（tests-04），真实全书尚未结束，真实查询/Q3工具脚本尚未运行；不将其记为全书或Q3联调通过。接口接线保持后续独立批次，等待集成窗口给出稳定基线。


## 首批独立后端提交及Q2规范身份补充

- `06a5571`：独立后端、源文件/许可证记录、依赖版本、21项专项与SDK恢复脚本。正式Q3适配和真实查询脚本留在后续批次，未提交教材、模型、索引、凭据和运行产物。
- 随后补齐Q2固定快照的规范snapshot_id/文件长度/唯一清单/完整11章校验、DOCX和原生索引的路径边界；实际325文件声明复核通过。22项专项通过，日志 `.runtime-lightrag-tests-07-boundaries.log`。
- 构建中未更改Git基线，未为提交停止/重启模型任务；build-08仍在运行。逐章失败除SDK日志外，追加观察在 `document_observations.jsonl`；观察时间不冒充实际失败发生时间。
- 模型可得用量按API真实返回保存；逐章缓存键可核对，历史并发调用缺少完整逐章token归属时保持未知，不估算为实测。


## build-08 实测结束与用户授权新服务候选

build-08以 `partial_failed` 结束：第2章先API连接失败，后两次原生manual retry实际返回HTTP402 Insufficient Balance；其余10章processed。未写全书候选就绪签名，未运行真实全书查询，未切正式索引。原候选及所有缓存保留。

独立读盘核对（completion-02）：全局6,688实体、13,962关系、1,149实际文本块、1,149实际文本向量。SDK状态清单合计1,237仅为计划块数；第2章88个块未实际保存，不能把1,237宣称为已摄取文本块。逐章如下，实体/关系存在跨章共享，不能简单相加当全局总数。

|章|状态|实际块/向量|实体|关系|
|---|---|---:|---:|---:|
|1|processed|107|859|1127|
|2|failed|0（计划88）|0|0|
|3|processed|131|727|1502|
|4|processed|130|561|1458|
|5|processed|131|687|1706|
|6|processed|116|663|1361|
|7|processed|156|759|1801|
|8|processed|102|763|1345|
|9|processed|84|575|1123|
|10|processed|65|409|706|
|11|processed|127|1568|2018|

素材sidecar为219次原图出现、163张表格分析成功；179个唯一有效原图仍pending，44项装饰排除，不能把模型分析成功当审核。81个OMML仍未逐式PDF/语义核验。逐章精确token归属未知，未反推。

build-07和08记录耗时分别935.361s、3392.019s；均为实际运行记录，不含早期未进入记录器的失败启动。模型可得用量与资源快照见保留候选的usage.json/progress.json/completion_validation.json；金额未返回。

关闭错误根因：SDK1.5.7的nano_vector_db.finalize仍需嵌入pending upsert；上游适配先关闭所有队列，导致chunks_vdb关闭失败。宿主修复为失败/取消时先停止模型队列，SDK落盘后再关闭嵌入队列；正常情况先SDK落盘再关闭队列。23项专项通过；真实SDK替身模型验证部分失败后finalize、重启、原生retry及再次重启通过（sdk-check-04），不等于全书成功。

用户随后提供新测试服务，并明确选择用新服务建立独立全书候选、保留原10章候选与缓存。新endpoint为https://cn.chatapi.app/v1，模型列表及返回模型名均包含deepseek-flash；JSON/真实原图输入契约预检通过，2次调用、717个API返回token。凭据只在测试进程环境使用，没有写入配置、Git或报告。

build-09候选：`.runtime/lightrag-proxy/0a6096dc43a8829d48776cbcd0c583b6dc779bd6b450614b4bd20bd1d7f0e5ce/`；SDK workspace `deeptutor_afca9240c7d2bdfd`。同一Q2冻结输入，独立模型策略和SDK缓存（启动日志0条cache），不把不同endpoint冒充相同指纹，不复制原候选图谱到新策略。全部11章已直接入队，有限并发不变。原候选未修改，正式服务与ready=false均不变。真实查询/证据发布待新候选全书完整后执行；Q3稳定基线/公共接线/页面仍未验收。


## 新代理长文本兼容与build-10

第三批提交 `4c1da2d` 已交付：失败收尾保留嵌入队列、真实存储数量核验、模型预检及23项专项。build-09随后暴露长文本抽取 `finish_reason=length`；适配未接受截断内容，第8章明确失败。小JSON和图像请求通过不能替代SDK长文本契约。主动取消build-09，状态cancelled、进程退出，候选/SDK缓存全部保留。

原宿主只在api.deepseek.com端点发送thinking=disabled，新代理默认开启thinking（初次预检返回reasoning_tokens>0）。现对已使用的deepseek-flash明确发送disabled，并将thinking/max_output_tokens/temperature写入模型身份。没有通过增加输出上限或忽略截断来制造成功。为不把生成策略变化混入同一索引，build-10使用全新独立候选，build-09不复用为已验收图谱。

实测兼容预检通过：结构化JSON、真实Q2原图输入、从build-09缓存重放的一条真实SDK长文本抽取请求，三次响应finish_reason=stop、reasoning_tokens=0，实际API返回总计3,607 tokens；长文本抽取返回entity协议及COMPLETE结束标记。图像仍pending，这只是请求契约检查。报告 `.runtime/lightrag-proxy-compatible-preflight.json`，不含凭据。

补齐截断失败的usage记录：原实现在检查finish_reason后才取usage，build-09截断调用的可得token未捕获，不能事后估算为实测；新实现收到响应即记录返回模型、finish_reason和usage，再执行严格非空/截断校验。新增回归首次因测试替身缺mock属性失败，补齐替身后24项专项通过（tests-11），原截断保护保留。

build-10：`.runtime/lightrag-proxy-nothinking/0a6096dc43a8829d48776cbcd0c583b6dc779bd6b450614b4bd20bd1d7f0e5ce/`，日志 `.runtime-lightrag-build-10-proxy-nothinking.log`。全部11章直接排队，同一95b956a冻结输入，CPU embedding、模型共享并发2、文件1；服务凭据只存在进程环境，原.env未修改。所有旧候选保留，未切正式服务。build-10结束后再独立核查实际块/向量/实体/关系及真实查询；全书/Q3/页面仍未标通过。
