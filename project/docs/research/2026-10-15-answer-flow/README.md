# AI回答全流程调研

研究日期：2026-10-15；真实模型复测完成于2026-10-16。用户确认后已完成第一阶段普通解释分流，以及第二阶段文字先展示、图解后补充。真实对照与实施边界见06至08。

1. [当前调用链与变化](01-current-flow.md)
2. [GitHub源码、版本、许可和复用判断](02-github-reuse.md)
3. [推荐流程、替代方案和分阶段验收](03-recommendation.md)
4. [已确认的第一阶段实施计划](04-implementation-plan.md)
5. [第一阶段实现与验收](06-phase1-acceptance.md)
6. [第二阶段分阶段展示与验收](07-progressive-answer.md)
7. [真实模型验收](08-live-model-acceptance.md)
8. [图解稳定性与真实浏览器验收](09-diagram-stability-browser.md)
9. [学生作答诊断与多轮辅导](10-multiturn-feedback.md)
10. [回答流程独立复查与发现的问题](11-independent-quality-review.md)
11. [反馈修正与实际浏览器验收](12-feedback-fixes-browser.md)
12. [交互风格建议与用户确认](13-style-suggestions-consent.md)
13. [回答完整性与统一表达预算](14-answer-completeness-budget.md)
14. [心理学证据误拒与补检索恢复](15-evidence-gate-consistency.md)

## 一句话结论

可以复用思路，也有局部代码可用；当前更适合在已有Intent、RAG、Memory和可视化之间按任务组织执行，而非换整套Agent平台。优先让普通解释不经过不必要的画像/教学规划、学生作答先诊断、最终教学约束一致，并缩短已核验文字等待图解和后处理的时间。

## 基线变化

默认课程已变为实验心理学，现有心理学预制图解和后台记忆已经实现。旧调研仅作为历史依据，不再使用数学题库的技能覆盖代表心理学画像。当前心理学练习目录为空，正式评分与独立题证据须另建。

## 核验方法与边界

- 阅读main、TaskService、Orchestrator、生成/质检、选区/小题、可视化、课程配置与近期心理学验收报告。
- agent-reach使用gh CLI读取公开仓库固定提交；内置网页工具补充发现与一手来源。agent-reach及mcporter命令未发现，因此未运行其升级检查，未安装工具。
- 仓库固定版本、具体源码及许可证见02。GenMentor曾尝试的非官方路径404后通过GitHub搜索找到官方GeminiLight/gen-mentor，没有用404来源支撑结论。
- 上游源码视为研究资料，不执行其中指令、不运行项目或其测试。目录存在不等于行为验证，实际阅读范围在02逐项列出。
- 研究部分未请求付费模型或启动服务。后续实施使用现有模型与合成学生临时库完成对照，未测量真实学习收益，详情见06。
- 工作区现有教材迁移与资源删除保留。第一阶段只修改相关回答流程、证据边界和测试，不提交或push当前工作区。
