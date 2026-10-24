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
