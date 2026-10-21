# LightRAG 隔离验收与集成交付（2026-10-21）

## 结论与边界

后端、全书候选、现有 SourceRef 适配及隔离工具调用可交付；**未达到正式切换条件**。11/11 建图完成不代表检索质量通过。本轮没有合并 main、切换正式索引/服务、修改正式学生库或教材发布状态；没有修改 main.py、TaskService、agent_loop、agent_loop_service、公共前端。已阅读 RESPONSE_EXPERIENCE_IMPLEMENTATION_PLAN.md，流式正文、上标引用、Markdown、公共视觉接线归集成/回答体验窗口。

## 代码与输入身份

- worktree：`E:\项目\heart-worktrees\lightrag-integration`；分支 `codex/lightrag-integration`。本轮开始 HEAD `9f8f52d8eb75f6d7c5c1eccef1c4bec582adc9fc`，原始分叉基线 `9c746e28173f7dcfeef34e8d6134dab7e58c5286`。本轮代码提交 `22ac81d0b0c8d0791cd153bc41101dfe2e599b35`，故障判据补充 `effd694fb256fa0940f05b66aa1794a3179dcd9b`；文档提交见执行日志和 Git 历史。
- 主工作树当时实际已提交验收宿主：`a2be38741c2c08162efd2335e7249db3353f9812`。仅从该提交提取 Python/agents JSON 到隔离 host；未合并、未复制主工作树未提交接口。该提交是固定验收宿主，不等于集成窗口批准的正式切换基线。
- Q2 交付 `95b956a515d1868341c8f18b29fc2d23e3a7ebb6`：11章、325文件、102,504,640字节；冻结清单 SHA256 `02b3a221c1d795d5894b1810332d0762f2ce7276b03cd73ba7bb49362cf2fc9d`。来源 `.runtime/q2-delivery-95b956a/snapshot/course`；最终完整性检查再次逐文件核验冻结源与候选 input，未从可变主教材目录取材。
- 候选绝对路径：`E:\项目\heart-worktrees\lightrag-integration\project\integration\discrete-math-tutor\.runtime\lightrag-proxy-nothinking\0a6096dc43a8829d48776cbcd0c583b6dc779bd6b450614b4bd20bd1d7f0e5ce`。
- 输入/候选签名 `0a6096dc43a8829d48776cbcd0c583b6dc779bd6b450614b4bd20bd1d7f0e5ce`；SDK workspace `deeptutor_426733019d24d665`。教材仍 staging / ready=false。
- `LIGHTRAG_DELIVERY_LOCK.json` 固定核心图谱、向量、KV、来源映射、输入清单、模型策略和实测依赖；锁自身 SHA256 `9453b0d7c11d8447464f92f59052286de9e78a498e1a12f6b0aa0a473581aa89`。查询及最终重启后全部封存哈希仍一致。

## 构建、依赖与交付方式

固定 SDK `lightrag-hku==1.5.7`；上游 `D:/deeptutor` SHA `6cf793bd868ba5ecbe64722936d4be8fab5a01df`，Apache-2.0，SDK MIT。原始文件保留于 vendor，逐文件来源及适配哈希在 knowledge/lightrag/UPSTREAM.json；本轮只增加宿主 q3_adapter，不重写上游算法。依赖入口 requirements-lightrag.txt 已在前序提交。

embedding BAAI/bge-small-zh-v1.5，512维/512输入tokens，权重签名 `76ea289a945b5bba118930654cffe3c5841570dba3b405148bd310910f841b6c`；BGE reranker-base，阈值0.15（未校准）。构图/关键词模型 deepseek-flash，https://cn.chatapi.app/v1，thinking=disabled，输出8192、温度0.1；并发模型2/embedding1/文件1，chunk1200/overlap100/gleaning0。结构化 aquery_data，模式及预算见接口文档；内层不生成正式答案。实体/关系各2000、总10000tokens，top_k20/chunk_top_k12，宿主BGE重排。CUDA用于本地embedding/rerank；远程图谱模型仍调用API。

专用 .venv-lightrag 为 Python3.12.14，SDK单独安装，基础包只读借用宿主 site-packages，**不是自包含部署包或完整锁文件**。实测 openai3.26.1 / fastembed0.8.1 / loaded ONNX Runtime1.26.0 / numpy2.5.3 / pydantic2.14.0 / networkx3.7 / psutil7.2.2 / langchain-text-splitters0.3.11；ORT分发元数据存在CPU1.31.0与实际GPU模块差异，base requirements networkx3.5也与本机实测不同。新部署环境须重新校准，不能将这些观察值当已完成干净安装验收。

代码/测试/文档入 Git；教材、模型、学生库、索引、缓存和原始验收运行产物不入 Git。本机交付采用上述固定目录及冻结源路径，保留 sidecar、SDK缓存、锁/版本元数据。SDK sidecar及source_root含绝对路径，**异机或任意改目录搬迁尚未验证**，不能只复制GraphML就宣称可加载。保留整个候选与冻结源；正式服务账号必须有读取及必要SDK缓存/锁写入权限。

## 实际接通的调用点

隔离 HTTP /turn → 固定宿主现有 LocalAgentLoop / build_registry → 现有 RetrieveCourseTool → LightRagNavigator → 原生 aquery_data → Q2 choose_evidence / EvidenceBundle.publish → 现有 QualityChecker → 隔离 MemoryManager。没有新增对话循环、学习路径或引用协议；尚未接通正式 TaskService/public HTTP/浏览器页面。

SourceRef 保留原教材块、document_id/version、chapter/section、原文字符范围与 source_spans；release身份/status/ready置于 location，符合现有字段。实体、关系摘要单列 graph_context，非教材精确引文；metadata/reference不直接生成证据卡。无可映射来源不发布答案。原图通过Q2 get_visual/is_valid/sha256核对后附 image_refs；179项 pending 如实保留，44装饰排除。正文、编号、版本、页码、高亮、裁图使用Q2发布流程。返回图题/图片候选不表示模型看过像素，实测工具链 image_inputs=0，不能宣称视觉解释通过。81个OMML身份保留，未逐式完成PDF/语义复验。

resolve 完全委托原导航；明确 block/ch/section 精确目标走 Q2 read_target，不走图谱。一般边只表示关联，不形成先修、教学顺序、重点或掌握状态。正式宿主若启用 q5.loop_binding，会用 Q5Navigator(search_fn=q5.search) 覆盖传入 navigator；集成必须保留 Q5 resolve/计划，仅在其 search 边界接适配，不能仅传 navigator 就宣称启用。

## 验收方法与结果

独立端口 127.0.0.1:18977、隔离 students.sqlite3、每次 lr-test-UUID 学生；代码宿主固定为上述提交，旧检索使用只读复制且与Q2交付 existing_index相同的基线索引（1465块/512维），SHA256 `2a052d6d90624119c7bb10d445bcfb7c0a82306021f2af55ed29c71d23b0e7ef`。两后端同模型、同冻结教材、同问题、同BGE重排和同CUDA设备设置。

首轮22项记录保留，但错误使用 RAG_RERANKER_MODEL，基线重排未启用；不作为公平对照。第二轮改用 RAG_RERANK_MODEL，两边相同配置：22项18通过/4失败。下表列出全部第二轮尝试；导航和故障检查单列，不算语义质量提升。质量通过含现有模型门禁判断，并非独立人工逐句证明。

|问题|旧检索|LightRAG|检索秒（旧/LR）|整轮秒（旧/LR）|说明|
|---|---|---|---|---|---|
|concept|通过|通过|4.892/6.828|38.157/17.422|原文命中、映射、回答门禁通过|
|synonym|通过|失败|0.719/4.313|13.344/16.140|LR原文可映射，但回答超过宿主260字门禁|
|comparison|通过|通过|0.610/6.204|13.469/17.797|原文命中、映射、回答门禁通过|
|cross_chapter|失败|失败|0.703/6.109|21.188/18.594|均仅命中第2章，缺第1章，保留失败|
|previous_relation|通过|通过|0.718/6.844|21.860/20.281|关联解释；不推导先修|
|first_chapter|通过|失败|0.000/0.000|13.391/10.968|Q2精确导航；LR分支回答长度门禁失败|
|next_target|通过|通过|0.000/0.000|9.391/12.015|Q2 b6→b81；LR前一轮未发布，完整两轮流程失败|
|figure|通过|通过|0.672/4.969|9.937/15.282|LR绑定图1-1有效原图；未看像素|
|no_hit|通过|通过|0.704/5.391|4.657/10.078|均无依据并阻止发布|
|source_stale|通过|通过|0.000/0.000|0.016/0.015|真实Q2版本失效拒绝，0模型调用|
|backend_unavailable|通过|通过|0.000/0.000|0.015/0.016|构造隔离缺失索引；未回退|

跨章两后端都漏第1章，不能宣称 LightRAG 改善覆盖。首章→下一点：两边目标确为 ch1:s1:b6→ch1:s1:b81；旧检索分支两轮发布成功，LR分支首轮被拒绝，所以仅下一点解析/发布成功，完整流程仍失败。导航由Q2确定，并非LR检索贡献。

最新服务04禁用模型客户端隐藏 transport retries（0），超时90秒。补测保留3项：正常概念首次模型 Connection error（未执行工具，9.250秒）；两个真实 RetrieveCourseTool 内缺索引故障，旧检索1次工具/10.656秒，LR2次工具/14.703秒，工具错误保留、外层 quality_rejected，均0历史行、无fallback。显式正常概念重试 `2f380735-861d-470f-8341-86f8989ac7d5` 成功：实际backend=lightrag、1次工具、84.625秒、发布引用并保存2行隔离历史。重试不抹去首次连接失败。缺索引是故障注入，不等于真实公网停机验收。

34项专项（后端26+SourceRef/验收适配8）全部通过；最终原生SDK重启实际加载7138实体/14741关系/11个processed文档及全套KV/VDB，封存锁和全书完整性检查通过。测试不替代页面验收。

### 时间、调用、费用与资源

有效第二轮旧检索返回70,376tokens /40次模型create调用，LR返回64,797tokens /40次（含关键词调用）。旧检索1次调用无usage，LR该轮无缺失；早期客户端底层默认网络重试未逐次观测，create调用数不等于精确HTTP尝试数。总时长旧145.425秒/LR138.608秒，包含导航/故障、冷启动、缓存和质量重试，**不可据此宣称性能优势**。金额API未返回，cost=null，不估算为实付费用；失败未返回usage的部分未知。全部49次HTTP验收尝试（smoke、两轮矩阵、最终补测及显式重试）保留。

最后单时点：服务PID60572 RSS1,699,086,336字节，累计CPU user71.390625秒/system33.015625秒；宿主GPU总占用4287/8151MiB、利用率10%。这是单点快照，非本进程GPU峰值/全程采样。构建阶段逐次耗时、资源、调用和未归属逐章token见全书报告及completion_validation；未将推算写成实测。

## 全书最终读盘复核

|章|状态|实体关联数|关系关联数|实际块/向量|
|---|---|---:|---:|---:|
|1|processed|858|1127|107/107|
|2|processed|609|954|88/88|
|3|processed|711|1407|131/131|
|4|processed|560|1468|130/130|
|5|processed|680|1642|132/132|
|6|processed|646|1332|116/116|
|7|processed|749|1816|156/156|
|8|processed|772|1346|103/103|
|9|processed|585|1102|84/84|
|10|processed|429|737|65/65|
|11|processed|1548|2032|127/127|

全局去重7138实体、14741关系、1239块/同ID向量；章内关联统计不可相加当全局去重。所有章缺块/缺向量清单为空。854正文、219图片出现块、166表格块（163唯一表格）；179唯一有效原图pending，不将重复出现或图题当已审核多模态完成。

## 证据路径（本机保留，不入Git）

应用绝对根目录：`E:\项目\heart-worktrees\lightrag-integration\project\integration\discrete-math-tutor`。以下均相对此根：

- `.runtime/lightrag-acceptance-01/isolation.json`：宿主/隔离库/旧索引身份；`deployment.json`：最后服务实际配置、脚本哈希。
- `.runtime/lightrag-acceptance-01/comparisons/comparison-1792509372488080100.json`：首轮全部尝试（配置差异已说明）。
- `.runtime/lightrag-acceptance-01/comparisons/comparison-1792509814393061200.json`：有效第二轮22项；对应health文件为同名运行ID。
- `.runtime/lightrag-acceptance-01/attempts.jsonl` 和 `attempts/<uuid>.json`：49次全部请求的实际模型/工具事件、来源、质量门禁、引用、用量及失败。
- `.runtime/lightrag-acceptance-01/acceptance-summary.json`：从原始尝试重算的调用/用量；`final-targeted.json`、`final-retry.json`、`health-final.json`、`resource-final.json`：最终补测、真实重启与资源快照。
- `.runtime-lightrag-q3-adapter-tests-final.log`、`.runtime-lightrag-backend-tests-final.log`：8+26项结果；`.runtime-lightrag-delivery-final.log`、`.runtime-lightrag-completion-final.log`：最终锁/全书复核。
- `.runtime-lightrag-comparison-01.log`、`-02.log`、`.runtime-lightrag-final-targeted.log`：保留非零退出与失败，未以删样本方式改成全绿。

## 剩余问题与采用顺序

1. 按 LIGHTRAG_PARALLEL_LOG.md 的前序提交顺序采用后端，再采用本轮独立接口/隔离验收提交，最后采用文档提交；先在集成窗口自己的worktree确认稳定宿主契约，不在本窗口合并主工作树。
2. 采用 `LightRagNavigator` 或其search边界接Q3/Q5现有注册点，保留精确Q2导航、SourceRef、Q2发布门禁；公共入口接线另批。配置和可复验命令见 LIGHTRAG_SWITCH_RUNBOOK.md。
3. 解决跨章/概述覆盖不足（优先在已有Q2目标分解与精确读取流程处理）；回答长度门禁失败须由公共回答窗口整合，不通过放宽/删除现有门禁掩盖。
4. 原图pending、公式逐式复验、真实像素送模、正式TaskService/Q5完整链路、浏览器页面和干净独立部署环境未通过；不可宣称这些已完成。
5. 本轮仅交付候选，不改staging/ready=false；发布审批、正式切换和公共fallback开关均归集成窗口。

隔离服务最终已核对命令行后停止PID60572，18977无本窗口监听；候选/缓存/测试库/证据全部保留。后续驱动要求backend_unavailable必须包含所选后端的真实retrieve_course FileNotFoundError，已用留存两个实际工具故障复核通过，并新增专项防止模型连接失败被误记为后端故障成功。
