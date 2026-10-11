# 第五阶段设计：持久后台记忆任务

沿已批准的阶段路线实施，使用 brainstorming 的职责边界检查。此阶段采用 SQLite 持久任务和单后台 worker，不引入 Celery/Redis；外部队列适合规模化部署，但当前 Demo 可先复用短事务与服务 lifespan。完整 LangMem 运行时迁移仍延后。

## 任务协议

- 同一事件和任务类型唯一，随已质检通过的教学回合在同一事务 enqueue。失败/冲突回合不 enqueue。
- queued → running → completed；异常采用有限指数退避，三次后 failed。来源失效 canceled。超时 running 可重新领取，lease_token 防止旧 worker 覆盖新结果。每次领取和发布均为短写事务。
- 来源快照包括本轮事件、上一轮教学事件、策略观察及其原文证据。发布前重新计算 SHA256，状态/内容/证据变化均不得发布过期结果。
- 删除学生级联删除任务和产物；晚到结果只返回失效，不重建学生或来源。读取产物时再次校验来源，已发布旧产物也不能继续被用。
- failed/completed 任务可以通过学生范围限定的 Repository 重放接口重新排队；旧产物仅在任务 completed 且来源仍匹配时可见。

## 生成边界

- 默认规则模式：截取学生原文，附本回合已有策略观察的规则反思。
- 可配置 MEMORY_REFLECTION_LLM=1：已有 LLMClient 生成最多四条连续学生原文摘录，Pydantic 严格校验、逐条校验原文来源。模型不能自定学生、事件、verification 或误区状态。不是无约束的自然语言推断。
- 产物仅为 extractive 摘要与规则反思，标为候选历史；不写掌握度、误区、画像或策略权重。在线上下文仍以原始状态/证据为权威。
- MEMORY_WORKER_ENABLED 默认启用规则 worker，可关闭。模型调用 timeout=20、retries=0；lease=90 秒，最多三次。服务退出通知并等待 worker 结束，启动后持续扫描持久任务恢复。

## 接线与检查

新增 MemoryJobRow / MemoryArtifactRow、memory_jobs Repository mixin、MemoryWorker、FastAPI lifespan。统一 MemoryContext 使用 bounded background_memory 字段，继续共用字符预算。

使用临时 SQLite 和模拟生成器验证事务 enqueue、去重、领取互斥、超时接管、旧 token、退避/失败/重放、删除传播、来源变更、候选校验、上下文预算、worker 生命周期与实际 Orchestrator 路径。不启真实模型，不改生产 DB，不重启服务。
