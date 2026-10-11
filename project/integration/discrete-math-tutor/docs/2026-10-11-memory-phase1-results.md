# 学生记忆系统第一阶段实施结果

日期：2026-10-11。依据六部分研究结论，借鉴开源架构并扩展当前工程，没有新增 Mem0/Letta/Graphiti 运行依赖，也没有复制其源码。

## 已完成
- 新增 learning_events、event_evidence、memory_revisions：保留事件、原文、规则核验/AI 暂定标记，以及更新前后的完整投影。旧 evidence 无需改列，保留并标为 legacy_unverified。
- session_scope 复用当前工作单元；SQLite 最终写入用 BEGIN IMMEDIATE，模型调用在事务之外。
- 生成前不再持久化候选证据/误区。回答核验后一次提交事件、对话、证据、误区、状态、计划和策略画像；事务失败全量撤销本次写入。
- 同一事件重复提交不重复写记录；同轮两个抽取器输出的相同来源证据合并，同一误区不重复计数。
- 数值状态最终从回合开始状态融合一次。提问、自述理解、辅助作答和无原文测量不增加掌握度/步骤分数；步骤推进需实际累计值达标，不再因模型 step_completed 强行抬分。AI 作答评估仍为暂定估计，并不是经过校准的正确率或 BKT。
- 单次高置信度误区不直接确认；带原文的独立多事件累计支持，已解决误区再出现时可重开。笼统 resolve_misconceptions 不再一次解除全部误区。
- 教学错误直接丢弃本轮候选状态，保留原投影与错误审计，不再 rollback 后又保存错误新状态。
- 使用投影指纹防止旧回合覆盖并发修改；冲突记录为 conflict，仅保存对话和原始事件。
- 没有有效测量的讲解不算策略失败。
- PDF 圈选保留实际选中小节、文档版本/页码/坐标，问答及事件原子保存；不改变掌握度。
- 练习结果与事件证据同事务写入，按 submission_id 幂等；逐小题区分 rule_verified/ai_provisional，并记录帮助经历。练习事件暂不自动投影掌握度。
- 删除学生级联删除新表记录； MemoryManager.reset 同时清理该学生的进程内快照和教学动作。

## 借鉴关系
|参考|落地方式|
|---|---|
|[Graphiti 来源边](https://github.com/getzep/graphiti/blob/main/graphiti_core/edges.py)|事件关联原始对话、练习与教材位置；证据保留来源|
|[Mem0 历史记录](https://github.com/mem0ai/mem0/blob/main/mem0/memory/storage.py)|按学生隔离记忆，保存写入历史，事件幂等|
|[Letta 记忆约束](https://github.com/letta-ai/letta-code/blob/main/src/agent/memory-constraints.ts)|本地规则限制模型直接修改重要记忆，保留更新版本|
|[pyBKT 观测与状态](https://github.com/CAHLR/pyBKT/blob/master/source-py/pyBKT/models/Model.py)|分离行为、测量与状态估计；当前只保留项目既有 EMA，不宣称已实现 BKT|

## 验证结果
命令：

```text
.venv/Scripts/python.exe -m unittest tests.test_memory_events tests.test_quality_guard -v
```

在独立进程中设置 DATABASE_URL=sqlite:///:memory:；测试逐项创建隔离 SQLite。**25 项通过：19 项新增记忆检查 + 6 项回答质量检查**。四项记忆测试运行真实 TutorOrchestrator.handle_turn，模型和教材检索输出均模拟。覆盖幂等、来源去重、事务故障、旧版本冲突、独立/辅助作答、质量拒绝、教学错误、误区复发、圈选两条对话原子性、提交外层事务撤销、旧记录兼容与学生删除。

未调用真实模型 API，未继续教材测试，未改生产数据库，也未重启正在运行的服务。SQLite 并发验证为旧版本冲突场景，不是高负载压力测试；当前保证面向 Windows SQLite，其他数据库隔离级别需要单独适配。

## 生效与限制
- 应用下次正常启动时 init_db 会自动建立三个新表，不重写旧记录；当前已运行进程尚未加载新代码。上线前应备份现有数据库。
- 聊天 event_id 对一次服务调用幂等，尚未提供客户端 request_id 的网络重试去重。练习复用已有 request_id/submission_id。
- 原文匹配是资格必要条件，不是语义正确性的证明；路由与 AI 评分仍可能误判。缺少历史辅助信息时保守地按辅助作答处理。
- 练习帮助信息按同题同版本查询，有帮助记录则按辅助作答，暂未区分每次尝试独立的提示边界。
- 新主流程通过暂存与原子提交消除了部分回滚；旧 snapshot/rollback 兼容接口仍只负责状态，外部调用不能将它视为全数据库历史恢复。持久化 revision 现在用于追踪，尚无面向用户的任意版本恢复 API。
- 保留现有知识点名称；稳定 concept ID、全历史检索、来源可信度在记忆上下文中的展示、逐项误区解除和后台反思尚未实施。

## 下一阶段
统一 MemoryContext：在严格学生过滤后，检索全部历史而非仅最近 20 条，将画像、知识状态、误区和来源证据分开，接入普通对话、PDF 圈选与练习讲解。
