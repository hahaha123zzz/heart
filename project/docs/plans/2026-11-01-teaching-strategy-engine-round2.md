# 教学策略决策器：Release 验收与第二轮改造

日期：2026-11-01（Asia/Shanghai）。基线：用户指定的 `94ba9ca0223b164ac44cabdcb424b759b5e6e116`。工作分支：`feat/teaching-strategy-engine-20261031`。

## 测试数据与模型

测试数据来自用户提供的 [GitHub Release](https://github.com/hahaha123zzz/heart/releases/tag/test-data-20261031-94ba9ca)。官方 Release API 通过本机既有 Git 凭据读取，凭据不进入文件或日志；附件跳转至 GitHub 附件域名时不发送该凭据。以下压缩包大小及 SHA-256 与 Release 的 manifest 和附件 digest 一致：

| 文件 | 字节 | SHA-256 |
| --- | ---: | --- |
| textbook.zip | 126659153 | c1dfcb1c0dcece3904c97ddc21b9bd1febf0d29fb8ee9a5b8a1bcc6462aa635e |
| learning-state.zip | 4739482 | 513de2c995fd32e988c118f282b384d484799317dee4c6b348557768a7608870 |
| lightrag-candidate.zip | 199994184 | 09ac6188b75d10580fa7ed0be411d5eb20c50ee06bfe84e939fddf3c60a8bfd0 |

数据仅恢复到本独立工作区；没有覆盖其他项目副本的学习库。学习状态快照用 `mode=ro&immutable=1` 打开，前后 SHA-256 相同。教材目录已加入本地数据忽略规则，不把约 1800 个数据文件作为业务源码提交。原图审核状态和 staging 发布状态保持原样。

模型密钥由用户指定的 `C:/Users/xinzi/Desktop/agent-extracted/deepseek.env` 在测试进程内读取。用户先指定 `deepseek-v4.1-flash-1017`，官方接口明确以 HTTP 400 拒绝该名称后，用户确认改用官方 `deepseek-flash`。测试端点为 `https://api.deepseek.com`；没有修改全局代理、密钥文件或正式服务配置，未记录密钥。

## 第一轮真实数据与 HTTP 验收

`scripts/accept_strategy_release_data.py` 验证：11 章、37 节、11 个 PDF / 376 页、1465 个教材片段；PDF 实际哈希与清单一致；SQLite integrity_check=ok；98 份历史 TeachingTurn 快照能进入新决策器，来源失效 0，重放没有新增学习证据、正式掌握或发布收据。快照文件没有变化。

实际 Release 仍为 staging，有 178 个原图资产待教师审核。数据完整可用于测试，不等于教材已正式发布。LightRAG 包只做结构、签名和来源映射核对，未启用固定教材服务、未测试嵌入模型查询，也未把备份当成独立部署验收。

`scripts/accept_teaching_strategy_live.py` 使用真实 PDF 选区、真实模型和独立 SQLite，通过 HTTP 跑通：直接讲解且不出题、困难后的教法调整、开放题登记、一级提示、重复 HTTP 请求幂等、新进程重启后的原题恢复。各次均未获得正式掌握信用。恢复阶段保留相同 question_id / prompt，模型回合数为 0；修复后的单次耗时 6.03 秒。失败过的恢复样例仍保留在本地测试日志，不能把其历史结果抹去后称全部首次通过。

第一轮真实测试发现并修复：

1. 恢复规则只接受很短的固定句式，`回到刚才的小检查，原样显示题目，不要给答案` 被误当作讲解，调用模型并在题干后追加解释。现仅把限定的显示/不泄答修饰纳入纯恢复；含解释任务、否定恢复的输入继续正常解析。
2. 章节图片响应对每张图反复调用整书发布核验。现同一章节响应共享一次新鲜 release 身份，逐图有效性及审核状态校验保留。增加单次绑定的回归测试。
3. 旧教材接口测试错误要求心理学图片为空，与基线已接入的原图功能冲突。改为核验实际图像的章节、小节、来源有效性和审核状态。全书逐节验证在无竞争的单独运行中通过；并发扩大回归时也出现 180 秒超时，不能用前一次通过掩盖该性能失败。

先前 FastAPI TestClient 挂起已定位为沙箱 Windows socketpair；沙箱外的最小同例立即通过。其后的 HTTP 测试运行在沙箱外且使用临时库。该环境问题没有用删除权限或发布校验解决。

## 第二轮实施

第一轮上述数据、模型及恢复验证通过后开始第二轮。没有引入独立策略服务、另一个状态库或额外策略选择模型。

`agents/teaching_strategy.py` 中 `_decide(StrategyInputs)` 是共同策略入口。TeachingTurn 使用 `decide` 投影，旧入口使用 `decide_for_context` 投影；13 个 ID 仍来自原 JSON 库。注册表、候选过滤、有序动作、互动边界、回退 ID 和版本语义共用。原来 9 个工具名仅作为兼容投影。

| 入口 | 接入位置 | 执行与状态边界 |
| --- | --- | --- |
| Q3 聊天 / 选区 | adaptive_tutoring、agent_loop_service | 沿原循环调用工具和发布；模型可在已有 teaching_step 内选择合法候选 |
| 旧聊天 | orchestrator | ADAPTIVE_TUTORING_ENABLED=1 时跳过旧 TeachingPlanner 与 StrategyRouter 的重复选择；课程规划、证据分析、质检和提交仍保留 |
| 旧 PDF 选区 | pdf_selection_tutor | 生成及质检使用同一计划；已校验且已绑定的简单 GroundedTurn 复用现有投影，不重复分类 |
| 独立小题提示 / 讲解 | practice_api.ai_parts、exercise_task_tutor | 绑定题目、小题和题库版本；仅当前小题答案进入载荷；grade 分支不进入教学策略选择 |
| 原生 DeepTutor 提示 | teaching_prompt_adapter、native_bridge | 保存到已有 teaching_style 快照；校验学生、会话、task/revision；不向没有 teaching_step 的入口注入该工具调用要求 |

TaskContext 只增加可选 task_id / task_revision，由 TaskService 认领任务后填写，意图模型载荷排除这些身份字段。内部 session/request 长度与原生 100 字符协议兼容，HTTP ChatRequest 的现有长度和权限限制不变。

外部入口的发布收据只在原质检、引用校验及保存路径成功后登记；质量失败不留下成功收据。发布证明交付，语义动作仍为 not_observed；这些入口没有伪造 reported_strategy、理解或掌握。原生快照只代表决策已保存，不伪造原生动作执行收据。

策略历史和反馈按 target_ref 匹配。另一目标的最近策略不改变当前困难应对，也不会接收当前目标的反馈；插问入口不得重写另一个有效待答题的 last_strategy/last_summary。自报困难只保存 self_report、causal_effect=false。

明确不出题、只判对错和不完整答案优先于高提问频率及旧直接讲解模式。新题登记不能越过 plan.allow_check。普通 Q3 答复也检查显式不提问边界，不只在新题登记时检查。正式批改、掌握、Q5 路径、答案键隔离和原图像素标记不由此层重新实现。

## 验证与性能记录

新增 `test_shared_teaching_strategy.py` 覆盖旧聊天跳过双重选择、生成/质检消费同一计划、选区复用已绑定输入、提示披露、只判对错、仅当前小题答案、正式 grade 不进入策略器、质量失败无收据、发布幂等、跨目标反馈以及原生快照任务版本隔离。

真实旧选区验证使用关闭 AgentLoop 的独立进程和独立库，两次运行都通过直接讲解、仅提示和原文引用质检。第一次 direct=84.16 秒、hint=23.33 秒；复用已校验输入后的 direct=171.16 秒、hint=22.97 秒。direct 的 SDK 完成调用从 5 次变 4 次，但后一次首个模型调用耗时约 106 秒，不能声称总延迟改善，也不能把两次不同负载的请求当受控性能对照。

本机固定上游提示文件 SHA-256 与 UPSTREAM_SNAPSHOT 一致。默认环境会导入仓库外的 DeepTutor，原有启动保护正确拒绝；测试通过显式 PYTHONPATH 使用仓库内版本。固定版本的原生工作进程挂载测试通过，但后续真实原生应用用例在 Windows 反复 ensure_scope_workspace / chmod 与事件读取阶段超时：1 passed、1 failed（TimeoutError），没有报告整套原生验收通过。未修改固定上游文件、关闭权限处理或放宽授权门禁来规避此问题。

机器可读结果与完整合成对话仅存于本工作区 `.runtime/strategy-acceptance/`；测试快照原始对话没有写入本报告。具体最终分批结果见附录。

## 未完成与风险

- 原生应用全链路超时仍需解决并复测；本轮只证明策略快照与提示适配边界，不能称原生端到端已验收。
- 完整教材接口在并发测试负载下有超时；旧入口真实调用存在高延迟，尚未通过受控性能基线验收。
- 没有浏览器页面/移动端交互验收，没有学习增益结论。
- LightRAG 没有激活或做向量模型查询；数据包不含嵌入/重排权重，不能声称全量 RAG 部署完成。
- 来源缺口后的自动局部修订及通用未完成动作执行器仍未实现；fallback 为受约束的规则回退声明及原流程失败处理，不是无限重试器。
- 业务变更未提交、推送或部署。生产配置与用户原库未改。

## 最终分批验证附录（2026-11-01）

以下结果按各批原样记录，包含重复覆盖，不相加作为唯一测试数：

| 结果文件（应用目录 `.runtime/strategy-acceptance/`） | 结果 | 说明 |
| --- | --- | --- |
| round2-final.xml | 232 passed、70 subtests passed、1 failed | 完整教材子进程在并发负载下超过 180 秒，失败保留 |
| round2-serial.xml | 86 passed、43 subtests passed | 最新策略入口、跨目标约束、教学模式、执行边界及完整教材接口串行复核通过 |
| round2-feedback-final.xml | 62 passed、5 subtests passed | 最新反馈、证据、提示生命周期、输入理解及决策回归通过 |
| round2-native-probe.xml | 1 passed、2 subtests passed、1 failed | 固定上游挂载通过；原生应用 TimeoutError 尚未解决 |
| round2-release-replay.json | 98 份快照通过 | 0 来源失效；快照 integrity=ok、SHA-256 不变；未调用模型 |

最终真实教材重放再次确认 11 章、37 节、11 个 PDF、376 页、1465 个片段，release_ready=false。LightRAG 结构验证确认 7 个签名索引文件及 11 章来源映射，结果为 lightrag-validation.json。真实模型 HTTP 用例和重启恢复的独立记录见 live-round1；旧入口复核见 live-round2-legacy 及 live-round2-legacy-reuse。

最终 `git diff --check` 通过。上述分批通过不抵消原生超时和并发教材接口超时；它们仍属于待解决项，不能标记为全部验收完成。

2026-11-01 后续：第三层恢复/取消边界、来源受限补救、原生路径复用和完整回归结果见 [第三轮改造与验收](2026-11-01-teaching-strategy-engine-round3.md)。本报告的历史失败记录保留，后续通过不覆盖原始记录。
