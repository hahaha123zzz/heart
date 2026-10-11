# 记忆系统第一阶段设计与实施计划

已依据六部分调研和用户授权实施。保留 SQLAlchemy、SQLite、MemoryManager，不新增记忆框架依赖。

## 借鉴来源
- Graphiti 的 episode 来源链与时间信息：https://github.com/getzep/graphiti/blob/main/graphiti_core/edges.py
- Mem0 的受用户范围约束的记忆记录与历史：https://github.com/mem0ai/mem0/blob/main/mem0/memory/storage.py
- Letta 的记忆边界和版本化：https://github.com/letta-ai/letta-code/blob/main/src/agent/memory-constraints.ts
- 知识追踪的观测与状态分离：https://github.com/CAHLR/pyBKT/blob/master/source-py/pyBKT/models/Model.py
以上复用设计思路，不复制源码；现有 EMA 不称为 BKT。

## 实施边界
1. 新建 learning_events、event_evidence、memory_revisions 三表，避免改变旧 evidence 表结构。旧记录保留，缺少事件来源的证据标为 legacy_unverified。
2. 模型分析阶段只产生暂存数据。回答质检通过后，以短事务一次写入事件、证据、误区、画像、状态、计划、对话及版本记录；事务中不调用 LLM。
3. 来源事件唯一、同事件同类型证据合并，同事件同误区只计一次。用完整记忆指纹检查并发修改，冲突时保留回答与行为记录，不覆盖新状态。
4. 提问、自述理解、情绪和辅助作答不提高掌握度或步骤进度；独立作答必须有来自学生输入的原文证据。AI 推断为 provisional，不等同规则核验；仍可用于有原文的独立作答估计，但不能仅凭 step_completed 把掌握值强行抬到目标阈值。误区确认需要独立多事件，不能只凭单次模型置信度。
5. 教学错误丢弃本轮状态推断，保留原有计划、状态、画像及可审计错误事件。避免旧 rollback 后又保存错误新状态。
6. PDF 圈选作为带原页定位的行为事件；做题批改结果与事件证据在同一事务提交，记录规则核验/AI 暂定、帮助记录与题目版本。

## 顺序与验收
先实现可嵌套事务、新表和数据接口；再实现证据资格与统一回合提交；最后接入对话、圈选、练习。只运行本次修改的隔离 SQLite 和模拟模型检查，不继续教材真实 API 测试，不自动重启服务。检查重复提交、事务故障、并发冲突、直接提问、教学错误与级联删除。

## 暂不包含
全历史语义检索、稳定 concept ID 迁移、后台反思、BKT 拟合。聊天事件 ID 标识一次服务调用；客户端重试幂等需要后续传入 request_id，不能根据文本相同直接去重。
