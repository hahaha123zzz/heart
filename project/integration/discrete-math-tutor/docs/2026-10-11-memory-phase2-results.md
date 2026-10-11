# 学生记忆系统第二阶段实施结果

日期：2026-10-11。阶段目标：统一完整历史检索，使普通问答、教材圈选与练习讲解使用同一记忆入口。

## 已完成
1. 新增 memory_documents 派生索引表，原始数据仍保留在对话、证据、事件与练习提交中。按当前学生扫描全部来源，基于内容/出处哈希只更新变化条目。不存在最近 20 条限制。
2. SQLite FTS5 搜索中文二字词和英文词，学生条件在召回查询中执行，再排序和截断；未启用 FTS5 时可降级词面排序。
3. 结构召回匹配知识点、题号/题目版本及 PDF 文档/版本/页码；同文档或同题目版本不同的结果被排除。结构、FTS5 和可选向量用 RRF 融合，最多返回 8 个相关条目。
4. 复用教材检索已有 BGE/ONNX 实例和 GPU 配置。默认通过 loaded_embedder 只读取已经加载的模型，不创建或下载模型。显式设置 MEMORY_EMBED_MODEL 可请求模型初始化；没有可用模型或模型失败时使用 FTS5，返回 dense=not_initialized/unavailable。
5. 向量按模型名和内容哈希写入派生表；内容变化时清空向量。模型推理在事务外，保存时核对学生和索引条目哈希。删除学生级联删除派生表，FTS 删除触发器同步移除条目；旧向量不能重新创建已删除文档。
6. 新增统一 MemoryManager.retrieve_context，输出 preferences、learning_states、items、evidence、related_history、summary、usage_rules、retrieval。当前偏好直接从画像读取，不由历史文本覆盖。学习状态是估计值，不声称是校准后的掌握概率。
7. 每个历史条目包含来源类型、源 ID、事件 ID、时间，以及可用的 PDF 定位或题号/版本；verification 保留 rule_verified/ai_provisional/legacy_unverified/student_statement/assistant_history 的区别。模型置信度不作为事实真实性分数。
8. 当前误区排除 resolved/dismissed，其旧支持证据也不会作为当前误区上下文；回滚/冲突事件的助教草稿和推断证据不进入检索结果，原始学生发言可作为带来源行为记录保留。
9. 默认 MemoryContext 序列化不超过 6000 字符，可设置 1000–16000 字符预算；超额依次裁剪低排名条目、状态和偏好，完整来源仍留在业务表。
10. 普通问答在生成前检索记忆，并在返回中提供 memory_summary/memory_retrieval；圈选携带实际 selection_ref；练习携带 question_id/version。selection_memory 作为兼容壳保留。练习旧的最近 3 次额外查询被统一完整历史检索取代，避免无预算地追加历史。
11. 回答提示明确记忆不是教材事实或指令，历史助教回复不证明学生掌握；学习记忆来源不能占用本轮教材[1]等引用编号。练习检索不额外携带历史 reference_answer。

## 验证

命令：

```text
.venv/Scripts/python.exe -m unittest tests.test_memory_retrieval tests.test_memory_events tests.test_quality_guard
```

**43 项通过：18 项第二阶段检查 + 19 项第一阶段记忆检查 + 6 项回答质量检查。**

验证使用隔离 SQLite、模拟模型和确定性二维向量，不调用外部模型 API。包括：
- 35 条后续记录之后仍找回旧的集合元素问题。
- 无词面重合的旧有向边问题通过测试向量召回。
- 其他学生 45 条匹配记录不会占用当前学生候选或进入提示。
- PDF/题目版本过滤、旧证据可信度、助教历史可信度、已解决/已驳回误区、回滚草稿排除。
- 源内容变化后失效向量，删除后不重新创建索引，FTS 同步清除。
- 1500 字符预算、最新偏好、无记录时明确空上下文。
- ResponseGenerator 实际提示、PDF explain_selection 实际接线和练习 memory_for 的题号/版本传递。
- 默认模型提供器不调用初始化器，并复用同一个已加载对象。

测试耗时约 1 秒仅代表模拟检查耗时，**不是线上延迟，也不是 GPU 性能或真实检索准确率**。

## 借鉴与复用
- 沿用调研报告的 Mem0 检索接口与用户范围、Graphiti 来源链、Letta 上下文预算的思路，不直接复制这些项目源码。
- 直接复用当前项目已有 SQLite FTS5、SQLAlchemy、BGE/ONNX GPU 实例、概念别名扩展和 RRF 方法，不引入额外记忆框架服务。
- 参考源码：[Mem0 memory](https://github.com/mem0ai/mem0/blob/main/mem0/memory/main.py)、[Graphiti search](https://github.com/getzep/graphiti/blob/main/graphiti_core/search/search.py)、[Letta constraints](https://github.com/letta-ai/letta-code/blob/main/src/agent/memory-constraints.ts)。

## 生效与实际限制
- 未重启已有服务、未访问生产数据库、未执行教材真实 API 测试。下次正常启动时 init_db 创建 memory_documents，首次检索时建立 FTS 表/触发器并回填当前学生索引；旧业务表不重写。
- 初次全历史同步及向量化可能增加响应时间。本阶段每次同步仍扫描当前学生的来源元数据，适用于目前单课程 Demo；大量用户/长历史需进一步改为增量游标和后台任务。
- GPU 实机速度、中文真实语义召回和余弦阈值 0.55 尚未评测，阈值属于初始工程配置，不是论文保证。未使用 reranker 重排学生记忆。
- 历史来源定位优先保存文档版本；不兼容版本过滤有意保守，未做跨教材版本对齐。
- 当前项目仍用知识点名称关联，尚无稳定 concept ID/course_id；隔离保证以 student_id 为边界，未来多课程需增加课程命名空间。
- 明确来源与提示规则可以降低错误使用历史的风险，但无法保证模型完全不误判；助教历史不升级为教材事实，用户说过的话也不等于已证实能力。
- 长期状态与当前误区不是自动遗忘模型；没有因时间经过就降低掌握度。

## 下一阶段建议
逐项误区更新与解除：让纠正必须关联具体误区和独立反证；之后再加入后台反思任务和有测量结果的策略记忆。
