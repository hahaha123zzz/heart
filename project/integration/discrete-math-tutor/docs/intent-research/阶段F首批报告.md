# 阶段F首批：扩展任务评测入口

日期：2026-10-12。

## 完成内容

scripts/eval_intent.py 新增 --router task，传入TaskContext的冻结对象、历史和偏好；默认legacy仍用于旧路由基线。入口不导入Orchestrator、不初始化业务数据库，模型调用前校验所有所选上下文。

新增任务字段评分：learning_intents按顺序精确匹配，target_refs、answer_constraints、missing_slots按无重复集合匹配；单列多意图顺序准确率及分母。继续保留流程宏F1、必要澄清召回、误澄清率、失败状态及延迟。没有足够对象的旧target标签列为无法评分，不能加入正确率分母。

录制预测检查严格任务Schema、对象白名单及原问题保真；失败不能获得空列表字段的正确分。replay检查数据哈希和路由模式，保留最初source_mode，支持回放离线/真实录制结果，不把回放伪装成新模型调用。记录样例、路由、评测代码、任务Schema哈希及模型标识。

real模式新增 --max-api-calls，覆盖网关调用尝试及应用重试，关闭OpenAI兼容SDK内部隐式重试。到达上限后阻断进一步调用。api_call_attempts含配置/连接失败，不等于供应商收费次数或精确费用；默认上限为所选样例数乘2，可显式收紧。本批未执行real模式。

## 开发样例

新增tests/data/intent/task12.jsonl及来源audit，构建脚本为scripts/build_intent_acceptance_cases.py。选区由真实第7章PDF第4页的版本/坐标服务端解析，小题来自真实第1章首题p1，裁图在临时目录生成并清理。

12条覆盖定义、公式、证明、例子后证明、选区提示、小题提示、检查作答、对象缺失、用户纠正、比较加例子、情绪加学习请求、结束学习。上下文不从expected或desired_task构造，防止答案标签泄漏。

这是一组Agent编写、待独立审核的development样例，不是盲测集。没有补齐原计划120段或独立审核；部分歧义任务标签仍须审核，不能凭这12条声称模型达标。

## 验证

- test_intent_evaluation、test_routing_validation、test_task_context共36项通过，输出见[测试输出](阶段F首批测试输出.txt)。
- 新检查覆盖多意图顺序、对象集合评分、未知对象、不可评分标签、缺失任务字段、问题改写、Gold隔离、网络预算与SDK重试关闭。
- task12 mock运行成功，replay指标一致；旧seed20 legacy mock也可运行。
- 新mock只会固定输出explain，因此学习任务字段仅3/12匹配；这是夹具覆盖不足，明确不代表真实模型识别质量。没有修改夹具使其迎合Gold标签。

结果见[任务mock报告](阶段F任务评测mock.json)、[回放报告](阶段F任务评测replay.json)、[旧路由mock报告](阶段F旧路由mock.json)。

## 复现

```powershell
& ./.venv/Scripts/python.exe -X utf8 scripts/eval_intent.py --router task --data tests/data/intent/task12.jsonl --mode mock --output artifacts/intent/task12-mock.json
& ./.venv/Scripts/python.exe -X utf8 scripts/eval_intent.py --router task --data tests/data/intent/task12.jsonl --mode replay --predictions artifacts/intent/task12-mock.json --output artifacts/intent/task12-replay.json
```

真实模型验收准备命令（本批未执行，需要有效模型配置，最多10次调用尝试）：

```powershell
& ./.venv/Scripts/python.exe -X utf8 scripts/eval_intent.py --router task --data tests/data/intent/task12.jsonl --mode real --limit 5 --max-api-calls 10 --output artifacts/intent/task5-real.json
```

## 尚未完成

任务识别评分不代替澄清恢复率、提示泄露、回答正确性及RAG Hit@k/MRR。后几项需HTTP交互录制与真实回答人工审核。GPU检索、真实模型旧/新对比、样例扩充与独立审核、灰度开关和回滚验证仍待完成，F保持未勾选。

下一步先以少量固定样例跑真实新旧识别对比，分析失败；再补齐灰度开关/回滚及完整报告。发布验收不能使用本轮mock数字。
