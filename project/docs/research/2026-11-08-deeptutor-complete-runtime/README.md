# DeepTutor 完整迁入审计与方案

- [第一部分复核](PHASE1_AUDIT.md)：明确已迁入模块与尚未完成的原生行为。
- [第二部分迁入方案](PHASE2_MIGRATION_PLAN.md)：完整内核、工具和能力的接入/替换/验收安排。
- [第二部分实施进度](PHASE2_PROGRESS.md)：已接通的原生执行链路、验证结果与未完成项。
- [100 个工具的状态分类](TOOL_STATUS.md)：已跑通、可补测、待宿主补接、需外部服务、暂不验收。
- [工具与能力矩阵](TOOL_CAPABILITY_MATRIX.md)：100 个工具、11 个回合能力、14 个循环扩展的逐项清单。
- SCOPE.json：来源、现有工具定义、迁入模块哈希和候选依赖的机器清单。
- GRAPH_SUBGRAPH.json：从 D 盘原图谱重新提取的上下文、运行内核和注册器相关子图。
- SOURCE_FILES.txt：975 个静态 Python 候选依赖文件；已包含 worker 的 API 入口。
- VENDOR_PACKAGE_FILES.txt：既有固定包的 3,764 个文件。动态服务、提示词和包元数据不能按静态 imports 裁掉。

原生执行内核已接入默认主聊天与文字选区入口；能力、工具和扩展的逐项真实执行验收仍在进行，完成情况见 [PHASE2_PROGRESS.md](PHASE2_PROGRESS.md) 与 [TOOL_STATUS.md](TOOL_STATUS.md)。

- [第二部分源码与架构复核](PHASE2_SOURCE_AUDIT.md)：按最新工具范围重新核对，记录四处已复现的实际接线缺口；当前结论为尚未完全迁入。

- [四处接线缺口修复验收](PHASE2_REPAIR_VALIDATION.md)：37 个不同回归用例、22 项真实 HTTP 检查，以及实际题卡/PDF 跳转浏览器验证；其余能力未全部验收。

- [真实模型验证（部分通过）](PHASE2_LIVE_VALIDATION.md)

- [混合链路修复与真实模型复测](PHASE2_MIXED_CHAIN_REPAIR.md)

- [旧教学依赖的原生覆盖核对](LEGACY_DEPENDENCY_COVERAGE.md)

- [直接复用原生模块的深入替换调研（以此轮目标为准）](NATIVE_REUSE_REPLACEMENT_RESEARCH.md)

- [TurnEngine与ChatOrchestrator：一次回合编排详解](TURN_ENGINE_ORCHESTRATOR_REVIEW.md)

- [下一轮实施计划：1请求与会话 → 3记忆 → 2教学](NATIVE_132_IMPLEMENTATION_PLAN.md) · [执行清单](NATIVE_132_TODO.md) · [图谱依赖](NATIVE_132_GRAPH_DEPENDENCIES.json)
