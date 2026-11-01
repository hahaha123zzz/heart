# 第二层运行路径对照与目标边界修复

日期2026-10-31。延续未提交工作树，不修改正式服务或开关。

## 评测口径修正

此前5条快照对照在新路径上无条件调用resolve，等同于短句诊断实验，不代表正式入口。保留原始结果，撤回将其当作生产新旧路径差异的解释。

check_semantic_shadow.py现区分：--live为诊断解析；--live --legacy为运行路径对照，新路径调用understand的真实按需升级逻辑，旧路径调用ConversationRouter。简单规则输入的新路径解析调用为0。调用分开计数、上下文深拷贝；每完成一条保存complete=false检查点，全部完成才写complete=true，防止中断丢失已有证据。样本预期标签不传模型。

## 30条真实模型结果

从现有100条工程输入/上下文集合每3条取1条，取前30条；按既有夹具构造无题、待答选择题、历史例子、歧义例子和学习安排上下文。这些是工程回放，不是独立盲测。

原始结果：30条全部新路径rule、0次新解析、30次旧路由调用；上下文均不变。7条具备快捷投影，4条字段差异，其中3条涉及intent/student_move。其余23条由原路由处理。

具体分析：

- 比较请求的explain+compare与compare差异属于表达粒度，不等同于答案错误。
- 提示请求的旧路由statement与新投影question差异不能机械向旧模型对齐；新路径保留hint_only/no_full_answer。
- 当前目标为自变量时，“随机区组与拉丁方的区别”被快捷投影强制标成continue，存在目标误绑定风险。

数据与完整原始结果：.runtime/psy6d-runtime-parity/{snapshots.jsonl,report.json}。

## 目标边界修复

agents/input_understanding/adapters.py::legacy_routing仅在以下情况快捷投影：原话明确包含当前知识点、已有resolved对象引用，或提示请求已有绑定待答题。其他明确新概念请求保留原路由的目标判定。没有清空待答题、切换学习计划或修改Q2游标。

新增回归验证：新概念不强制continue、绑定待答的提示仍直接消费输入协议并保留答案约束。

复用同批已保存旧模型结果、按修复后的规则重新投影，新增模型调用0：3条可走快捷投影，27条回到原路由，1条仍有字段差异；整体观察差异1/30，尚不达到原计划2%阈值，且不支持删除27条所依赖的旧路径。结果after-target-boundary.json与原始失败/差异报告同时保留。

## 验证与剩余

- tests.test_semantic_shadow、tests.test_input_understanding_integration、tests.test_input_understanding_rules、tests.test_conversation_context：62项通过。
- shadow专项6项通过，覆盖简单输入不强制调用模型、上下文不变、关键差异可见、批次中断保留结果。
- 未重复运行与本次旧路由适配无关的页面模型场景；此前页面两轮、刷新与新标签页会话隔离证据继续有效。
- 旧路由保留；短句语义候选仍未提升到正式执行。独立标注、扩大真实学生数据、正式灰度仍待完成。未提交、推送或部署。
