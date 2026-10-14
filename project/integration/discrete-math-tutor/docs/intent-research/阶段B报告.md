# 阶段B实施报告：统一任务上下文

日期：2026-10-12。状态：阶段B核心契约和入口接线已完成；真实模型语义验收及阶段C–F尚未完成。

## 已完成

- 新增models/task_context.py：章节位置、练习目标、服务端资源对象、有限历史与偏好；学生/会话ID不进入模型Prompt。输入预算为最近4轮、每轮1200字、最多20个已学点和最多4个对象。
- 新增models/task_understanding.py：严格任务输出及旧RoutingResult兼容出口。支持explain/proof/example/hint/check_answer/practice/summary/compare的顺序列表、对象引用、回答约束和必要缺失项。拒绝非法枚举、重复项、未提供的对象ID、模型自由改写及缺失项与流程动作矛盾。
- 新增agents/task_context_builder.py：章节/小节服务端查询，PDF对象使用真实解析结果而非网页预览，练习检查题库版本、教材版本和小题存在性，只读取题目不读取答案或他人草稿。明确练习按钮可直接构造hint/explain任务，不需要分类调用。
- 新增models/chat_request.py并保持main.ChatRequest导入兼容。旧请求仍可使用legacy会话；新增reader_location、exercise_target、session_id、request_id。此批仅接收身份字段，不宣称已实现任务持久化或请求幂等。
- main普通问答构建上下文后进行一次模型识别；Orchestrator接受已构建上下文，校验学生与消息匹配，保留旧直接调用。HTTP/SSE在连接/工作开始前检查教材与练习定位。
- PDF选区原页定位结果复用给分类器；分类失败或需要澄清时停止生成和保存，明确换话题的请求复用已识别结果交给普通流程，不重复分类。解释Payload带本轮任务，仍使用既有证据核验、原图、引用保存与删除epoch。
- frontend/app.js在普通教材提问时附带当前chapter_id/section_id，布局未改变。选区定位以已校验PDF为准，避免附带另一章节的阅读位置。
- 离线mock只补齐新协议字段，旧协议行为保持；不将mock结果作为实际模型效果。

## 验证

61项相关测试通过：tests.test_task_api、tests.test_task_context，以及阶段A的校验/评测/质检/证据恢复/记忆事务测试。节点覆盖：

1. 实际教材section ID查询与不存在的小节拒绝。
2. 网页伪造选区文字不进入Prompt。
3. 练习版本、题号、小题与按钮动作校验。
4. 对象ID不得来自候选集合之外，原公式问题不得被模型自由改写。
5. 多意图/比较的顺序与两个目标保留。
6. 同一句指代可产生明确对象结果或缺目标澄清；此项使用记录型fake LLM测试接线，不证明实际模型准确率。
7. 其他学生TaskContext拒绝；HTTP和SSE旧请求兼容及失效资源前置拒绝。
8. 选区解释只定位一次，并保持引用保存、无掌握/课程状态更新；换主题不重复识别。

node --check frontend/app.js及git diff --check通过。测试替换应用启动依赖/采用临时或内存数据库，不启动真实后台worker，不读取或更改真实学生数据。未重启现有8000服务，未进行GPU/真实模型调用。

## 仍需完成

- 阶段A的120段扩样、独立人工审核、真实模型基线尚待完成；初始20段仍是开发种子样例。
- session_id目前仅在请求与上下文中传递，最近对话仍按学生读取；不具备会话任务隔离保证。阶段C增加pending任务与会话指代状态。
- pending持久化、补充回复恢复、取消/过期/幂等和晚回调拒绝未实施。当前澄清消息还是一次性提示。
- exercise_target与按钮构造契约已提供；既有practice help按钮接口尚未改为消费这一任务对象，自由文本练习专门执行路由将在阶段D接线。
- 普通问答的回答约束及target_refs已经被识别，但尚未系统传到检索/Planner/质检全部环节。阶段D完成保守改写与任务执行对齐，不能据本报告宣称已消除旧章节检索偏向或保证只给提示。
- 不增加在线反思、完整框架迁移或微调，真实准确率仍待独立评估。

## 下一批

实现阶段C：LearningTaskRow与TaskRepository、awaiting_clarification任务恢复、同学生/会话隔离、revision/请求去重、取消到期和删除epoch。先在临时数据库验证，再接现有API和SSE。
