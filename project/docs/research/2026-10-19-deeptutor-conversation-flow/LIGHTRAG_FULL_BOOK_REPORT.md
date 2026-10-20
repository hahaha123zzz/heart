# LightRAG 全书候选实测报告

日期：2026-10-20。全书候选建图完成；检索质量专项仍有2项失败，Q3正式接线和页面未验收。未合入main，未切换正式索引。

## 输入、源码与候选

- 工作树：`E:/项目/heart-worktrees/lightrag-integration`，分支 `codex/lightrag-integration`。
- 起始提交：`9c746e28173f7dcfeef34e8d6134dab7e58c5286`。本批源码提交：`bd93051ca7db483c160fca9886dfb693d0bef652`。
- Q2交付：`95b956a515d1868341c8f18b29fc2d23e3a7ebb6`；325/325文件哈希等价，0差异；原冻结脚本和本窗口实际复核均通过。
- snapshot_id：`0a6096dc43a8829d48776cbcd0c583b6dc779bd6b450614b4bd20bd1d7f0e5ce`；清单SHA256：`02b3a221c1d795d5894b1810332d0762f2ce7276b03cd73ba7bb49362cf2fc9d`。
- 上游来源：`D:/deeptutor`，SHA `6cf793bd868ba5ecbe64722936d4be8fab5a01df`；逐文件原始及活动实现哈希、改动和许可见 `knowledge/lightrag/UPSTREAM.json`。原始18项文件复用现有vendor副本。
- DeepTutor Apache-2.0、LightRAG MIT，SDK固定且实际模块为1.5.7；依赖/许可记录已提交。未引入完整DeepTutor应用。
- 固定来源：本窗口应用下 `.runtime/q2-delivery-95b956a/snapshot/course`，不从主工作树的可变教材继续取材。
- 候选绝对路径：`E:/项目/heart-worktrees/lightrag-integration/project/integration/discrete-math-tutor/.runtime/lightrag-proxy-nothinking/0a6096dc43a8829d48776cbcd0c583b6dc779bd6b450614b4bd20bd1d7f0e5ce`；SDK workspace `deeptutor_426733019d24d665`。
- 仅 `candidate_complete`，教材仍为 `staging/ready=false`。旧10章候选、默认thinking候选及全部SDK缓存均保留。

## 逐章实际存储核验

独立读取GraphML、KV、向量文件核对。每章实体/关系可能共享，不可相加当全局唯一数。正文块是SDK文本分块，图片和表格块含模型分析，不能当精确引文。

|章|状态|正文块|图片块|表格块|实际块/向量|实体|关系|
|---|---|---:|---:|---:|---:|---:|---:|
|1|processed|90|10|7|107 / 107|858|1127|
|2|processed|72|8|8|88 / 88|609|954|
|3|processed|82|33|16|131 / 131|711|1407|
|4|processed|77|24|29|130 / 130|560|1468|
|5|processed|89|17|26|132 / 132|680|1642|
|6|processed|70|39|7|116 / 116|646|1332|
|7|processed|101|19|36|156 / 156|749|1816|
|8|processed|69|21|13|103 / 103|772|1346|
|9|processed|49|27|8|84 / 84|585|1102|
|10|processed|50|9|6|65 / 65|429|737|
|11|processed|105|12|10|127 / 127|1548|2032|

全局唯一实数：**7,138实体、14,741关系、1,239实际存储块与1,239对应向量**；分为854正文块、219图片出现块、166表格块。计划块、实际块、向量身份全部一致，无缺块/缺向量/未归属块。原163张表格中长表可拆成多块；219图片出现对应179个唯一原图。11章均非空图，最终失败文档0。

转换前输入为4,602原文block、163表格、81个OMML对象；保留章、节、block、原文、表格、素材和PDF版本身份。179个唯一原图仍pending；44个装饰栏头按Q2排除记录排除，未解决知识图缺口0。219次图像与163次表格分析成功只是模型分析状态，不是人工审核。81个OMML保留解析身份和原DOCX/PDF，冻结交付没有单独XML；尚未逐式PDF/语义核验，也没有81个已核验独立公式块，不宣称多模态完整。

## 失败、重试、取消与重启

- 原服务候选build-08：10章成功，第2章HTTP402余额不足，最终partial_failed；保留原图谱与缓存，未覆盖。
- 用户授权新服务独立候选；build-09长抽取发生截断并明确失败。保留候选及缓存，未接受截断为成功。
- 对deepseek-flash显式thinking=disabled，记录endpoint/模型/8192输出上限/0.1温度身份；用新策略候选build-10直接排队11章。
- build-10经历实际Windows睡眠27,654.605秒及连接/队列超时，第2和第10章失败；未将历史失败观察次数冒充请求失败次数。
- 第2章原生manual retry成功；受控取消build-10用于CUDA同权重恢复，保留已完成章及抽取缓存；build-11从6章成功继续，完成其余章及第10章原生重试。
- 未手改FAILED为PENDING。全书记录见progress.json的runs/chapters/attempts/failures与document_observations.jsonl；失败观察时间不是实际发生时间，跨运行重复观察不算新失败。
- 真实固定SDK隔离验证覆盖部分失败落盘、重启、原生retry、再次重启0重新生成；替身模型不冒称真实教材模型测试。
- 构建进程已退出，临时SYSTEM_REQUIRED电源请求已释放。

## 真实查询和证据

固定SDK真实aquery_data，answer恒空，没有aquery_llm内层答案；正式生成由Q3负责。默认hybrid，naive/local/global/mix也实际调用并返回原文。SDK实体/关系分别限2,000 tokens，总10,000，top_k=20、chunk_top_k=12；SDK重排关闭，宿主BGE重排启用。

|检查|结果|实际来源章|说明|
|---|---|---|---|
|concept|通过|2,9|自变量原文|
|synonym|通过|2,9|操作定义→操作性定义原文|
|comparison|通过|4,5|返回被试内/间相关原文；不等于正式比较答案验收|
|cross_chapter|失败|2,3,9|要求第1、2章，但漏检第1章|
|chapter_overview|失败|2|仅覆盖第2、4节；缺第1、3、5节|
|figure|通过|1|有效图1-1身份；pending不变|
|formula|通过|7|PSE相关第7章原文；不是81个公式逐式核验|
|no_basis|通过||无教材证据，sources为空|

- 五模式原生调用通过；8项内容检查6通过、2失败，query_validation.passed=false保持真实，不将其改成全绿。
- 章/节过滤当前在全局召回之后；跨章和完整章节概述须由集成窗口让Q3结合已有Q2精确导航分解并读取，不能把有限召回当完整教材覆盖。该公共流程尚未接线。
- 图谱摘要evidence_eligible=false；original_source_ids只关联本次返回的真实原文ID，空列表表示本次缺相应原文。metadata/reference不生成证据卡。
- Q2真实模型选择证据ID后，使用同一EvidenceBundle发布确切原文以核对编号/引用协议，没有生成正式答案。发布函数实际返回正文、来源、引用三项。
- 实际证据：experimental-psychology-3:chapter-02，版本 `840d14cbc821fe3ea5b3735da78c76c51ad021abed9c57bcf8d5a18d945fa0e7`，block 35、字符0–68、第2页；verification=source_verified、location_status=exact。
- 引句存在性、版本、正文[1]与卡片编号、页码、高亮矩形、裁图文件身份全部通过；已人工查看实际裁图，与自变量原文一致。source_verified不是教师审核或答案语义验收。
- 来源链：原生chunk.full_doc_id/sidecar refs→冻结blocks.json→Q2 block/asset/PDF版本→source_map.json→Q2证据定位与裁图。查询后再次复核325输入哈希、核心图谱签名与数量通过。
- Q3正式工具/AgentLoop/页面：未运行。历史f886144仅作契约参考，最新稳定集成基线待集成窗口提供；Q3适配草稿保留在.runtime/drafts，不交付正式接线。

## 实测耗时、调用及资源

|运行|实际墙钟秒|进程CPU增量秒|说明|
|---|---:|---:|---|
|build-10|32049.706|4189.047|含已证实27,654.605秒宿主睡眠、失败和缓存|
|build-11|1980.551|447.609|CUDA同候选恢复，复用缓存|

- 本候选累计模型尝试1981次，成功1925、失败56；API返回可得prompt 4,346,700、completion 1,441,786、total 5,788,486 tokens。包含本候选启动预检；失败请求未返回usage的56次未知，不按0估算完整账单。
- extract：1,749次尝试、1,705成功/44失败、4,889,774个返回token；vlm：232次、220成功/12失败、898,712个返回token。历史并发调用缺少逐章精确token归属，不反推。
- 远程模型共享并发2，本地embedding并发1，文档/解析/分析并发均有限；2,517个embedding batch、25,011条文本（含重试/重复运行），不是唯一教材块数。
- 采样进程RSS峰值980,926,464 bytes；不是整机/显存峰值。GPU为RTX5060 Laptop、8151MiB；CUDA功能已验证，没有速度基准或任务显存峰值实测，不报加速倍数。
- build-10+11墙钟共34,030.257秒；已证实睡眠单列，不能将墙钟或API seconds当纯模型服务性能。金额未返回，不估算费用。
- 查询首轮：11个关键词真实请求、7,672返回token；后两轮使用SDK关键词缓存，0新增关键词调用。两次Q2选择分别1次/1,432 token，共2,864；三轮合计13次/10,536个返回token，不把缓存命中算新增调用。
- 最后查询进程采样RSS起点62,537,728、终点1,646,342,144 bytes；CPU增量60.500秒，墙钟采样间隔56.137秒。它们是该次独立验证的边界采样，非峰值或性能基准。
- 专用venv只读借用宿主基础包，不是完全自包含部署锁；实际ORT模块1.26.0而CPU发行版metadata1.31.0，快照分别记录。部署环境需单独重建核验。

## 验证与运行证据

- 26项专项通过：.runtime-lightrag-tests-14-links.log；覆盖SDK版本、结构化结果、路径/锁/权限、输入漂移、取消/失败/重试、保留向量、截断用量、设备选择、图谱与原文分离。
- 真实SDK替身模型隔离验证通过：.runtime-lightrag-sdk-check-06-budget.log（2实体/1关系）；不得当成教材真实模型通过。
- 全书转换检查通过：.runtime-lightrag-input-check-06-nothinking.log。
- CPU/CUDA同权重功能数值检查通过：device_validation.json；最小余弦0.9999998211860657，最大绝对差0.00009504519402980804，非速度测试。
- 全书实数和查询后封存复核：.runtime-lightrag-completion-03-full.log、.runtime-lightrag-completion-04-after-query.log。
- 真实检索三轮日志：queries-01-full、queries-02-budget、queries-03-source-links；首轮预算耗尽0原文是实际失败，第二轮暴露验证脚本二元解包错误。原失败JSON保留validation_runs/01-budget-failure和02-budget-fixed，未抹除。
- 版本失效/权限拒绝/无来源/SDK不兼容/有限重试/查询取消在专项覆盖；真实构图取消与恢复已实测。正式页面上的失效呈现、Q3取消传播和正式工具接线尚未运行。
- 所有运行证据、图谱、输入、原图、缓存和模型均留本机未跟踪运行目录，Git只提交源码/测试/许可/说明。

## 关键文件签名

|文件（相对候选）|SHA256|
|---|---|
|input_manifest.json|`ca81fddc5c4c970569d1feebba208ffe147e75b3611b0f4e33d720754f289c77`|
|source_map.json|`986fd9bf9785588b023a6ca1c19036e0a936c94f4ab0ae00a1b43c852a1988a3`|
|policy.json|`63e2e2c0747a250a9d5c8706ee64506e40975ebcd543ebbe9820f6d4022b630f`|
|index_files.json|`28317ae34f66f4cf0365555f58b71cccb0932672ce2d3f7500d7fd1f754f26ed`|
|completion_validation.json|`7c70416bfb26d6af7f15f885b6df24c727eed6fbb72a208504e62d505b94474b`|
|query_validation.json|`61ee90e6233b9594585c335cab17e7798716c32d35754b46f3b52904f296e93d`|

## 集成提交顺序及剩余项

按原起始基线依次接纳本窗口六个源码批次；最终执行报告为随后文档批次。Q2 95b956a固定交付是数据依赖，不将教材快照放进Git。公共接线待集成窗口确认稳定基线，再以独立提交接入；本窗口没有自动merge main。

- `06a55710a6315f4cc31ad33b2ed6be9d92a389f9` feat: 迁入原生LightRAG独立后端与全书候选验证
- `f92c20041d806a6cc1eb6ffb6fdcc954b57697db` fix: 固定Q2快照身份并加强来源路径校验
- `4c1da2de5ae2fd5fd904b3fc2db68f81246a9d7a` fix: 保留SDK待写向量并核实部分失败候选实数
- `5ff9f6b2b30a4ed6e8d36b482d756ffbfac9554b` fix: 固定代理thinking策略并保留截断调用实测用量
- `8fe824484ca3d381ad11adefac41822eec724e77` feat: 复用宿主CUDA配置并验证同权重索引兼容
- `bd93051ca7db483c160fca9886dfb693d0bef652` fix: 保留结构化检索原文预算并交付真实来源验证

剩余问题：跨章召回漏检、完整章节概述缺节、179原图pending、81公式逐式核验、独立可重建部署环境、Q3正式工具与页面验收。不得以全书图谱完成为由提升staging/ready=false。
