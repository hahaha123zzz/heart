# 输出速度实施记录

日期：2026-10-24。独立 worktree：`E:\项目\heart\.worktrees\output-speed`，分支 `codex/output-speed`。

## OS0 基线

- 主线基线：`be7cc9c7b18530b2660d5df33cede4efbd76e10f`。8000 保持既有 `2ae1e5f` 固定导出，不用正式服务做压力测试。
- 已核对流式完整依赖链，采用 `4bf24d934dba605a27c1d1a3ddf42592b4797be9` 及全部祖先；合并基础 `0bd95c0`。唯一冲突为 app.js 错误状态列表，保留 Q5 和流式双方状态。
- 原 E 盘基线导出发生 WinError 112（磁盘已满），尚未启动或查询；只删除本次不完整导出，保留工具失败堆栈。改用 C 盘临时目录，完整教材和独立候选逐项复制，7 个核心文件哈希一致；未清理其他窗口。
- 隔离基线 8016：`C:\Users\free\AppData\Local\Temp\heart-output-speed-20261024\baseline`，`setup.json` 记录完整 SHA、路径、候选哈希。
- 冷启动定义请求：224.687 秒，失败（不计成功性能）。第一次工具120秒超时后，迟到结果仍分配来源号，第二次工具从4开始；最终未保存。原始收据 `baseline/cold-definition.json`，内部阶段 `baseline/stage-observations.jsonl`；仅观测包装，不改变任何检索/模型结果。该样本不代表热启动中位数。
- 基准运行器：应用 `scripts/benchmark_output_speed.py`；对每类按 A/B、B/A 交替，分别记录首进度、正文 delta、完成、原始收据和失败率。不把失败草稿首字当有效首字；无 p95 声明。

## 执行状态

代码改造与针对性回归进行中。OS01—OS16 真实模型、页面和20%性能目标尚未验收，不据代码存在标记完成。


## OS1—OS5 核心实现（待真实验收）

- 查询完整校验由3次降为2次；重复宿主遍历一并去除。前后仍逐文件内容哈希，控制文件（manifest/progress/index_files/policy/source_map）前后身份相同才返回。未启用不安全的跨请求哈希缓存；模型文件重叠路径去重后仍逐请求哈希，保留热换载检测。
- 传输池容量8，按端点、内存凭据和代理/TLS环境区分；只借用同步SDK传输，同步宿主和原生多角色共用。请求参数、metrics、取消和消息不共用；活跃引用结束才关闭淘汰资源，lifespan退出关闭池。
- 默认原生/已解析教材目标先用同一retrieve_course工具取证，不额外生成取证答案；ask_user恢复不重取已有来源。跨章对象选证+覆盖合并成一次JSON决策，ID/原文范围本地检查，缺口仍最多补查一次；最终事实质检不删除。
- 引用锁改为ToolContext私有，搜索在锁外；编号、source_offset和去重原子提交。超时工具持独立deadline，迟到结果不能写来源。相同候选保留跨进程锁，进程内每候选最多8个持有/等待、最多32个候选，等待默认最多180秒且服从活动剩余预算和取消。
- 固定规则/工具块前置，目标后置；记录可获取prompt_cache_hit_tokens，未返回则不推测缓存收益。沿用流式窗口唯一事件协议/活动预算；普通质检明确25秒、1200token、零JSON重试；keyword1200token，查询网络重试最多2次且占用同一预算。
- 132项针对性测试通过：`python -B -m unittest tests.test_output_speed tests.test_lightrag_backend tests.test_lightrag_relocation tests.test_lightrag_coverage tests.test_lightrag_q3_adapter tests.test_course_search_bridge tests.test_stream_retraction tests.test_q3_agent_loop tests.test_answer_stream -q`。证据：`E:\项目\heart\.runtime\output-speed-20261024\offline-third.log`。
- 首轮测试缺少未跟踪教材输入及旧fixture的注入SDK优先级，失败保留在offline-first.log。复制完整教材输入并修复显式注入兼容后，第二轮只剩新测试异常类型和Q5旧模型脚本不符合先取证契约，记录offline-second.log；修正契约测试后第三轮通过。未以隐藏测试或删除核验处理失败。


## 补充定位：PDF 每字符重复页面元数据

真实预热显示选证耗时明显超过模型调用后，暂停诊断测量，保留 `paired-45212b7` 和 `paired-70076b1` 全部已完成样本，不将不同时点/提交拼接成最终5对。

局部 cProfile（无网络、真实教材6片段、4次PDF解析）证据：`.runtime/output-speed-20261024/selection-profile-before.log` / `selection-profile-after.log`。前后 `_live_document` 均16命中、4未命中，解析文档数相同。总时间64.531→13.125秒；函数调用22,846,316→6,775,916。原实现133,950次读取rotation_matrix、536,066次读取page.bound等；将旋转矩阵、页面宽高移至每页读取一次即可消除重复跨语言访问。**该数据只是局部剖析，不是端到端20%通过证据**。

`pdf_characters` 的文本、glyph坐标与pages结构不变；新增0/90/180/270度PDF逐字符等值测试。未扩大跨请求缓存、未改变PDF哈希和来源版本检查、未建新索引。基准还发现16GB内存下旧8017副本额外占用约1GB，仅停止本窗口已被替代进程；其他服务不接管。


## 主线并行提交集成

验收期间 main 从 be7cc9c 前进到 2803d8d，包含完整教学引擎、会话隔离和选区共享循环。仅合入已提交祖先，不复制其他 worktree 未提交内容。保留 TeachingTurn/SelectionLoopInput/initial_sources、teaching_step、会话历史隔离和 Q5 语义；预取不重复读取 initial_sources，启用教学工具时不使用“已有证据关闭全部工具”的快捷分支。

发布策略存在实质冲突，已向用户说明，用户选择按 DeepTutor 处理。核对上游 pipeline.py:958—984、agent_loop.py:983—1031/1190—1210，普通教学实时流式，协议载荷缓冲，拒绝轮按身份撤回。保留本窗口已集成 SR 协议，并补齐教学修订分支撤回；主线 final-answer-publishing-design 追加此决策而不删除原记录。

合并首次85项测试1失败：新增 planning-failure fixture 的 Mock.is_chapter_guide 未显式设false，未进入被测 propose_session；与已记录插问fixture同类。只补齐两个fixture的真实boolean契约，不改Q5生产逻辑，重跑85项全过。另18项提速测试全过，含教学修订必须撤回且保留工具。原始日志 merge-main-focused.log / merge-main-focused-second.log / merge-final-speed.log 均保留。

79460d3 的8类×5对完整性能队列已结束，仅作为合并前优化版本测量；不把它算成并行主线合入后的最终宿主验收。后续固定合并提交重新导出真实页面与故障验证。


合并49cd0cc后固定导出跑256项：255通过，1失败（普通问答可发布性质检被新增blended分支的else附加结构化要求）。修复为elif not agent_loop，恢复原有普通问答与结构化计划的不同质检范围，blended补充知识说明仍独立保留。57项相关回归通过，日志offline-49cd0cc.log / merge-quality-scope.log；49cd0cc概念/图1-4/图5-2页面成功及刷新记录仅属修复前版本，后续最终提交重跑。
