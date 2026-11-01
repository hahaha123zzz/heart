# 教学策略决策器：第三轮闭环与原生阻塞修复

日期：2026-11-01。用户澄清继续第三层教学策略改造；本轮没有新增第二层六维分类功能。基于独立工作树 `feat/teaching-strategy-engine-20261031` / `94ba9ca` 的前两轮未提交改动继续，保留全部 13 种策略。

## 改造范围与选择

沿用现有 TeachingTurn、LocalAgentLoop 和 TaskService 的任务快照，补齐恢复、取消及教材来源缺口的边界。与新增通用工作流服务、整体更换编排框架相比，这条路径能继续使用现有题目身份、工具授权、引用发布和掌握度校验。没有安装新的运行依赖。

GitHub 对照采用原生 DeepTutor 的实际调用路径及 LangGraph 的有限重试与取消后停止写入思路；没有复制其整个调度器。LangGraph 的源码会按错误类型和最大次数限制重试，计时窗口关闭后阻止新的写入。这里的适配是把既有一次发布修订预算写入原任务快照，并在教学状态锁内重新检查取消/超时，而非引入另一套任务身份。

- [DeepTutor 工作区初始化](https://github.com/HKUDS/DeepTutor/blob/6cf793bd868ba5ecbe64722936d4be8fab5a01df/deeptutor/multi_user/paths.py)
- [LangGraph 重试和写入边界](https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/langgraph/pregel/_retry.py)，本轮读取 blob `4c695f59ee53ca134c8a26e3d249b36bb36ee41e`。
- [Python os.chmod 平台语义](https://docs.python.org/3.11/library/os.html#os.chmod)：Windows 只处理只读属性，不能将 0700 解读为 Windows ACL。

## 已实现的行为

1. **恢复不重置修订预算**：LoopResult/state 增加 repair_used，暂停恢复沿用；旧快照缺省兼容。教学修订、格式修订和来源补救共用一次预算，不因 ask_user 或进程恢复重新获得修订机会。
2. **来源不足时受限补救**：在需要教材、没有可核验来源且发布器给出明确缺来源原因时，经取消和任务版本检查，只用宿主原问题调用一次现有 retrieve_course。既有工具探索预算不重置。补取为空即拒绝；成功后仍由原发布器检查引用、内容和教学动作。不能让被拒绝草稿提供工具参数或扩大授权。
3. **局部计划修订**：TeachingTurn 将来源补救记录为 attempted，缩短本轮深度，确保 read_material 排在前面，保留 decision_id、已登记题目与教学收据。只有最终发布成功才写 recovered；失败标记 blocked，不新增发布收据、掌握或成绩。该修订只处理明确的来源缺口，不是任意教学语义重规划。
4. **已登记动作可重放**：相同 teaching_step 参数继续返回原结果，并返回与首次一致的成功元数据。已有成功动作可满足 required_tools，不会因为恢复后缺少工具标记而再次登记新题或重复计数。
5. **等待状态锁后仍检查取消**：TeachingStepTool 在拿到回合锁后再次检查取消和工具截止时间，防止排队中的工具在取消后登记题目。
6. **不提问修订路径一致**：最终发布门禁使用既有可修订原因前缀。学生明确不提问而首版仍有问号时，可使用已有一次预算改为陈述句，仍不能新增检查题。

动作的语义执行仍区分模型声明、工具收据和实际发布。讲解、类比等不能由规则证明已正确完成的动作继续为 not_observed；不把“计划中出现了动作”当执行成功。

## 原生超时：复现、根因证据与补丁

原有原生教学偏好收据用例在 15 秒事件等待条件下失败，保留 round3-native-before.xml。仅用于诊断的独立运行允许更长观察窗口，实际事件收集 30.24 秒后完成；这说明该样例并非死锁，也不能把诊断窗口当正式通过门槛。

进一步计时记录 round3-native-profile.json：单个隔离用例调用 ensure_all_directories 535 次，累计约 27.075 秒；该次事件收集约 15.609 秒。另有冷启动同步导入模型 SDK 等开销。各次负载不同，不据此计算严格的端到端提升比例。

在固定上游 utils/secret_files.py 做小范围本地补丁：已有目录先检查存在；Windows 每次仍读取实际文件属性，只有只读属性需要纠正时才调用 chmod，POSIX 原有 chmod 行为保留。没有请求级永久缓存，没有关闭权限校验，没有改学习服务、提示组装器或授权逻辑。

补丁保存于 vendor/DeepTutor/LOCAL_PATCHES/windows-private-mode.patch；UPSTREAM_SNAPSHOT.json 的 local_changes 同时记录原始/当前 SHA-256，files 记录实际本地版本。不能把修改后的文件冒充原始上游。

优化后，同一个原生用例在原先 15 秒事件等待条件下通过，报告 round3-native-after.xml；全用例总耗时约 86.72 秒，包含冷启动，不等于事件流耗时。

## 验收结果

最终分批测试、真实 deepseek-flash 及教材快照结果见下文。所有真实模型调用使用独立测试库及用户授权入口，密钥仅进程内读取。未改变生产配置、正式学习库或教材发布审核状态。

## 真实模型发现的后续边界

本轮 prepare 中直接讲解与困难调整均 answered，但开放题经历“缺引用”修订后仍被题干门禁拒绝，失败的 check.json 和 session.json 保留。进一步的确定性用例确认：在完全相同题干后附加 [1] 会被旧题干比较逻辑视为文字变化，与引用要求冲突。现题干核验仅允许末尾引用编号这类呈现装饰；题目身份、已保存题干不变，追加答案或改写题干仍拒绝，编号有效性仍经过原发布器。工具返回也明确要求原样呈现题干。不能据此宣称任意模型改题都能被自动修复。

HTTP 重放最初的验收断言还漏掉已有 reader_action_replay=true。该字段用于阻止页面重放阅读动作，是正确的接口契约。数据库收据与首版教学结果完全一致；现脚本明确核验重放标志后再比较其余结果，没有删除该标志或修改生产幂等协议。

原生完整回归在并发真实模型和宿主回归负载下仍发生 15 秒超时，保留 round3-native-suite.xml（1 passed、2 subtests passed、1 failed）。因此撤回把单例通过解释为已彻底解决超时的可能推论。继续复用 DeepTutor 已有、按用户 ID 和根目录绑定的 get_path_service_for_scope，避免每次重新构造 PathService；每次 ensure_all_directories、目录恢复和权限检查仍执行。新增测试验证调用两次仍检查两次，且相同用户不同根目录不复用对象。补丁及原始/当前哈希另记为 LOCAL_PATCHES/reuse-scoped-path-service.patch。

## 最终分批验收（2026-11-01）

各批存在重复覆盖，不相加为唯一测试数。

| 结果 | 实际结论 |
| --- | --- |
| round3-host-suite.xml | 138 passed、46 subtests passed；宿主策略、工具循环、提示生命周期及教学模式回归 |
| round3-recovery-final.xml | 40 passed；末尾引用装饰修复后的恢复、题目及提示专项 |
| round3-recovery-guards.xml | 10 passed；包含最终的空来源不可提交、取消、修订预算及重复收据边界 |
| round3-native-io.xml | 6 passed；目录/文件属性修复及按根目录隔离的服务复用 |
| round3-native-scoped-suite.xml | 17 passed、2 subtests passed，606.96 秒；完整原生提示和运行协议，原 10/15 秒等待条件未变 |
| round3-release-replay.json | 98 份历史快照通过，0 来源失效；integrity=ok，原数据库 SHA-256 不变，未调用模型 |

原生回归使用真实 DeepTutor 应用、协调器、SQLite 和提示组装器，模型能力为受控测试能力；不是原生真实模型端到端或吞吐压测。

真实官方 deepseek-flash 分段复验：

- live-round3：直接讲解 answered，原始新请求 119.25 秒；相同请求重放 5.14 秒（缓存，不作为生成速度）。困难后的 scaffolding answered，70.19 秒。HTTP 标志与其余发布结果一致。随后首次开放题仍失败，其记录保留。
- live-round3-practice：修复后以新隔离库重验，开放题 retrieval_practice answered，32.81 秒、2 回合；一级提示 hint answered，23.25 秒、2 回合。均有 4 条实际教材来源，待答题身份与题干保持不变。
- 同目录在另一个 Python 进程执行 resume：answered，7.95 秒、0 模型回合，同一待答题原样恢复。
- 上述场景 formal_mastery=false、step_advanced=false，没有把模型回答、自报理解或辅助题写成正式掌握。

教材仍为原 Release staging / release_ready=false。11 章、37 节、11 PDF / 376 页、1465 片段；本轮没有审核原图或激活 LightRAG 候选。

## 剩余验证边界

- 原生完整功能回归通过，但整组耗时约 10 分钟；早先并发负载超时报告保留。不能由隔离通过推断并发性能或生产延迟达标。
- 本轮没有运行浏览器页面验收，没有新教学增益或因果效果结论。
- 来源补救只处理明确的“无可核验教材来源”，不能替代跨章缺口调查、任意语义重规划或所有动作的自动判真。
- 没有提交、推送或部署，没有修改生产服务、密钥文件、正式库或全局 Git/代理配置。

## 固定源码完整性与工作树收尾

全量扫描发现本机 core.autocrlf=true 将 1377 个未显式指定 LF 的上游文本转成 CRLF；除换行外没有其他清单差异。仅在归一化后 SHA-256 恰好等于清单时恢复原字节，逐个复查文件身份、路径和哈希。最终 3764 个上游文件与当前明确记录本地补丁的清单全部一致，other_mismatches=0；结果 round3-vendor-integrity.json。根目录 .gitattributes 为 vendor 设置 text=auto/eol=lf，并保留原 PDF 的 -text 规则，没有修改全局 Git 配置。

换行恢复不构成 1377 个内容改造。Git 状态缓存仅对已核对内容哈希等于索引的文件刷新，前后断言暂存差异不变，不将业务改动一起暂存。

13 种策略的可达性和边界由工程测试覆盖；本轮真实模型只覆盖上文列明场景，不能称为 13 种策略全部教学效果验收。最终 git diff --check 通过。

后续收尾与合并验收见 [第三层收尾记录](2026-11-01-teaching-strategy-engine-closeout.md)，包含页面选区验收、prepared 候选收窄及 SDK 就绪修复；本报告原有失败与边界记录保留。
