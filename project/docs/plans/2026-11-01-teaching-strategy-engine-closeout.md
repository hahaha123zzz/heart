# 第三层教学策略改造收尾与合并验收

日期：2026-11-01。基线 94ba9ca，远端 main 校验点 a9725fb。承接前三级实现与验收报告，本记录说明本次提交的边界；不将此前失败结果删除或改写为通过。

## 最终行为与收尾修复

13 种策略沿用原权威注册表，在 TeachingTurn/AgentLoop、旧聊天、PDF 选区、独立小题提示/讲解及原生提示快照消费同一决策政策。候选过滤、动作顺序、回合边界、发布收据及同目标反馈保持一致；恢复和取消继续绑定宿主任务、版本与 epoch，不新增学习状态库或策略选择模型。

收尾审查复现了已准备计划在选区权限收窄后仍残留旧候选的问题。现对 prepared 计划取合法候选交集，并将 fallback 限制为交集中有效策略，保留计划身份及已执行收据。回归验证不能重新选择被禁止的 worked_example。

真实页面首轮暴露 SDK 首次导入占用回合预算：初次 sdk.connection_start 到约 170 秒才发生，随后达到 180 秒活动时限。现仅在配置本地真实模型且存在密钥时，于应用 lifespan 就绪前在线程中加载 openai 模块，不发模型请求；mock、无密钥及远端 DeepTutor 网关路径不准备本地 SDK。工作线程和池的原有退出清理保留。该修改移动冷启动成本，不声称消除冷启动或改善所有延迟。页面脚本等待上限改为 210 秒，以覆盖原有 180 秒服务端预算和流结束；没有放宽服务端执行时限。

## 收尾验证

| 验证 | 结果与范围 |
| --- | --- |
| closeout-core.xml | 103 passed、47 subtests passed；策略、候选权限、恢复、SDK 就绪、记忆任务、教学模式与关闭失败清理 |
| native-io-recovery.xml | 16 passed；固定 vendor 下的路径复用、Windows 属性与恢复边界 |
| node --test tests/chat-transport.cjs tests/reader-actions.cjs | 13 passed；SSE 终止、重放、取消和阅读动作幂等 |
| node --check scripts/check_input_labels_page.cjs | 通过 |
| 前轮完整原生回归 | 17 passed、2 subtests passed；代码与证据见 round3 报告，本次没有改原生运行代码，未重复约 10 分钟的整组测试 |
| 前轮真实教材及学习状态重放 | 98 份通过，0 来源失效，源库哈希不变；源码固定清单 3764 文件一致 |

真实页面使用 127.0.0.1:8153、独立 SQLite、已安装 Edge 的全新上下文与官方 deepseek-flash。测试调用阅读器实际预览处理函数，由服务器重新核验并提取 Release PDF 区域，随后真实点击发送；未自动化鼠标拖选 PDF 的过程。

选区中“自变量/因变量区别”到“还是分不清”两轮均 answered：conceptual_comparison → worked_example，每轮 3 条教材来源；耗时分别 33.641 秒、69.563 秒。页面正文和引用可见，刷新后正文恢复；同一学生的新标签页为新 session、messages=0、hasPending=false；pageerror 为空。正式掌握与 step_advanced 均为 false。

证据位于应用 .runtime/strategy-closeout/page-selection/{report.json,page.png,trace.zip}，耗时与信用边界见 browser-timing.json。验收脚本增加可选第三参数“PDF选区JSON”，缺省仍执行原有普通聊天测试，并记录 canonical strategy_id 与 policy_version。没有把教材、学习库、trace、密钥或模型权重加入提交。

## 保留的失败与发布边界

- 普通聊天的全书向量检索页面路径仍有活动超时：首次包含 SDK 冷导入，后续已进入模型调用，但本地向量检索初始化耗尽剩余预算。记录在 page-cold-start-failure、page 及隔离数据库；选区验收通过不能代替这条路径或向量吞吐验收。
- 扩大的固定书测试中，test_failed_graph_initialization_releases_partial_storage 因当前 Python 3.11 环境未安装可选 lightrag 包而失败；37 项和 4 项子测试已通过后停止。失败报告 closeout-tests.xml 保留；与本次 lifespan 直接相关的关闭异常清理用例在 closeout-core 中通过。本次没有启用 LightRAG 候选或安装/替换生产模型环境。
- 原生全链路仍存在较高文件系统/启动开销，尚未证明并发性能达标；13 种策略的工程覆盖不是全部真实教学效果或因果增益证明。
- 历史报告中的“未提交、推送”描述为当时状态；本次用户已明确授权合并 main 并 push。提交前检查不包含生产部署或功能开关切换。

## 配置与回退

沿用 .env.example 中现有开关：ADAPTIVE_TUTORING_ENABLED=1 与 LOCAL_AGENT_LOOP_ENABLED=1 启用统一教学循环；SELECTED_TEXT_AGENT_LOOP_ENABLED=1 接入文字选区。输入理解和检索仍使用各自既有配置。默认关闭和可回退行为保留，真实模型的 endpoint/key/model 由部署环境提供，不从本报告或仓库读取本机密钥。

合并前确认 origin/main 为当前开发基线的祖先；提交包含当前第三层代码、测试、验收脚本、固定上游本地补丁与文档，不包含 .runtime 或外部数据。合并后的提交与推送结果以 Git 记录为准。

本地 Windows 权限补丁采用零上下文 diff，避免补丁自身的空白上下文触发源码空白检查；应用/反向检查该补丁时使用 git apply --unidiff-zero。提交前已通过反向 --check 验证，补丁对应的实际源码哈希保持与固定清单一致。
