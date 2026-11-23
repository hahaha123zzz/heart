# UnifiedContext 关联链路迁移

日期：2026-11-08

用户授权：按 D:/deeptutor/.ua 图谱查找 UnifiedContext 关联文件，保留已接入的一致实现，替换不同的现有实现，并接通宿主实际链路，不能只保留闲置文件。

## 实施边界

从 core/context.py 出发，以实际 imports、构造点和消费者补全图谱未分析的 services/session、agents/loop；逐文件记录来源、已有实现、替换与实际调用位置。保留完整 vendor 源码及其固定版本，不重复搬入另一份完整应用。

替换宿主简化的上下文对象、历史构建和提示词实现；统一接入 TaskContextBuilder、run_agent_loop_turn、LocalAgentLoop 和 ToolContext。任务身份、教材版本、来源核验、取消、发布门禁和正式学习状态归属继续由宿主负责。上下文 runtime 和 extension_state 不能整体序列化，模型可见材料继续去除私有答案、身份与物理路径。

## 验收

1. 关联文件清单明确每个文件的处理方式，不以源码存在冒充已接通。
2. 从实际任务入口到模型请求、工具调用均消费同一个回合上下文。
3. 历史压缩、工具白名单、来源隔离、ask_user 暂停恢复和取消测试通过。
4. 现有教学、选区、学习计划和工具注册相关回归通过；无法运行的检查如实记录。

## 执行结果

上下文基础链路已替换并接入实际任务入口。逐文件清单：project/docs/research/2026-11-08-unified-context-migration/FILES.md。核心 235 项与扩展 55 项通过；十项旧失败已用 Git 原版复现，详情见同目录 VALIDATION.md。未调用真实模型或重启现有服务。
