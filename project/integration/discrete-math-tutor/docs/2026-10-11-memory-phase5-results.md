# 第五阶段结果：持久后台摘要与反思任务

日期：2026-10-11

## 完成内容

- 新增 memory_jobs、memory_artifacts：已提交教学回合与任务原子入库，同事件同类型只入队一次。
- SQLite 短事务领取任务，使用 90 秒租约和随机 lease_token。生成过程不占数据库事务；两个执行者竞争时只有一个领取，过期 worker 不能覆盖新结果。
- 失败按有限指数退避重新排队，最多三次；三次进程中断导致租约超时也会最终 failed。来源失效 canceled。提供学生范围限定的 replay_memory_job 后端接口，支持 failed/completed 任务重放，重放期间旧产物不再可读。
- 发布前和读取时校验原始事件、相邻教学来源、原始对话、原文证据和策略观察的 SHA256。来源内容更新不发布旧结果；原文不一致或已删除、源事件撤销均拒绝。删除学生级联清理任务/产物，晚到结果不会重建学生。
- 默认规则模式摘录本轮学生原文，并保存服务器已有的规则反思。可选 LLM 模式使用既有 LLMClient，仅抽取最多四条连续学生原文；严格拒绝编造原文、其他事件 ID、额外 verification 字段或未知输出结构。
- 摘要和反思为 derived_candidate 历史资料，不更新学生画像、掌握度、误区或策略权重，不充当数学依据。
- 接入 FastAPI lifespan：服务启动开启后台轮询，退出通知 worker 并等待，持久队列在下一次启动继续处理。/health 增加 memory_worker 状态。
- 产物进入统一 MemoryContext.background_memory，并与其他记忆共享字符预算，不占教材引用编号。

## 配置

已更新 .env.example，没有修改实际密钥/环境文件。

~~~dotenv
# 默认启用后台规则任务，不增加模型调用
MEMORY_WORKER_ENABLED=1
# 开启后使用现有 LLMClient；每次生成 timeout=20、retries=0，任务最多三次尝试
MEMORY_REFLECTION_LLM=0
~~~

MEMORY_WORKER_ENABLED=0 时仍持久入队，暂停消费；恢复启用后继续处理。只有下一次启动服务才加载本轮代码与新表。

## 验证

执行：

~~~text
.venv/Scripts/python.exe -m unittest tests.test_memory_jobs tests.test_strategy_memory tests.test_misconception_updates tests.test_memory_retrieval tests.test_memory_events tests.test_quality_guard
~~~

**95 项通过**：新增 20 项，原有 75 项全部通过。新增任务检查使用临时文件 SQLite，实际两个线程竞争领取；模型均为 Mock。

覆盖原子入队、幂等、竞争领取、租约超时接管、旧 token/过期发布、退避/终态/重放、连续崩溃、无效来源取消、生成期间来源更新、证据更新、上一轮教学撤销、原始对话删除、学生删除后晚到结果、读取学生/知识点隔离、重放更新唯一产物、模型调用在事务之外、幻觉原文/外来事件/额外字段拒绝、安全错误代码、发布事务回滚、上下文预算、质检拒绝、worker 停止、服务 lifespan 开关。

新增原始对话一致性检查后，一个旧测试只更改事件 payload、未同步原始对话，按规则被判 source_invalid。按真实更正事务同步两处来源后，验证了 source_changed 的重新排队分支；没有放松来源一致性规则。

main.py 和新增模块 py_compile 通过；定向 git diff --check 通过。保留原有 datetime.utcnow 弃用提示。

## 限制

- 本轮未调用真实 API、未加载新模型、未改生产数据库、未启动或重启服务。已验证代码、租约协议与模拟模型契约，尚未实测在线模型质量/成本及运行延迟。
- 当前 LLM 能力是受约束的摘录式摘要；自然语言教学经验提炼、跨长历史合并及人工审核流程尚未实现。规则反思依然沿用第四阶段 AI 暂定观察，不能冒充因果效果。
- 仅已提交的普通教学回合 enqueue。PDF 圈选与练习事件继续走已有原始记忆检索，本阶段不生成它们的后台摘要，不回填旧历史。
- 读取候选产物按知识点和时间取有限条，不额外建立摘要向量索引；原始历史依然使用第二阶段的混合检索。
- 任务队列针对当前 SQLite Demo 实现，领取互斥依赖 BEGIN IMMEDIATE；不能据此宣称已适配 PostgreSQL 多 worker。
- worker 退出最多等待 25 秒；外部调用异常拖延时可能保留 running 租约，下一执行者在租约超时后恢复。不能保证所有模型请求都在退出前完成。
- 重放和任务状态接口目前是后端 Repository 方法，没有新管理页面；记录 last_error 的安全错误码，不保存模型异常正文。

## 下一步

记忆查看、更正和删除：提供具体记录及来源的管理入口，沿现有事件/证据/索引/任务来源链传播更正或失效，并明确用户偏好和模型推断的区别。随后再做真实模型小规模验收与性能测量。
