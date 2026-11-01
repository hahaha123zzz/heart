# C4：开源评测做法与当前落地

## 调研结论

- [Ragas 的 Faithfulness](https://docs.ragas.io/en/v0.2.5/concepts/metrics/available_metrics/faithfulness/) 将回答拆为陈述，逐项判断能否由检索上下文支持。它适合补充来源支持度筛查；指标本身不能证明教学正确，也不能将生成的上下文当成完整教材。
- [Langfuse 的评测模型](https://github.com/langfuse/langfuse-docs/blob/main/content/docs/evaluation/core-concepts.mdx) 区分规则检查、模型评分与人工标注；[裁判校准说明](https://github.com/langfuse/langfuse-docs/blob/main/content/docs/evaluation/evaluation-methods/llm-as-a-judge.mdx) 要求用标注样本核对裁判的判断。本项目现有自动检查和盲审表可以沿用这一分层，不把模型评判伪装成人工教师评价。
- [DSPy 优化指南](https://dspy.ai/3.0.4/learn/optimization/overview/) 将提示词探索与留出测试区分，提醒小数据过拟合。之前的单条留出问题不足以证明候选改进；候选已撤回，不能用其宣布优化通过。
- [Unifying AI Tutor Evaluation](https://github.com/kaushal0494/UnifyingAITutorEvaluation) 针对数学辅导中学生错误的回应提供教学维度，适合参考维度设计；其数据与心理学教材不同，不直接当作本项目金标准。

## 本轮实施

保留现有 `prepare_c4_review.py` 生成的随机盲审材料，新增 `scripts/summarize_c4_review.py`：分别统计通过、不通过、无法判定、未审核；有评分必须填写审核人与时间，不通过或无法判定必须填写原因，拒绝重复编号。脚本只读输入，不改变已有评分，不检查审核人身份或资质。调用：

```powershell
python scripts/summarize_c4_review.py .runtime/layer5/c4-paired-2/review-sheet-v2.json
```

当前复核表共16条，四项维度均16条未审核；这不是16条不通过，也不是16条通过。自动检查仍仅覆盖引用编号闭包等形式，不能证明每项回答的事实或教学质量。

## 保留的验收条件

C4 尚需具备教材教学背景的独立人工复核、扩充与冻结独立样本、对照中记录完整调用链消耗、对提示词候选执行独立留出集验证。本次未部署第三方评测平台或把尚未与人工标注校准的模型评分作为验收；也没有更改正式模型、服务或索引。

agent-reach 可用命令未在本机 PATH 中发现；GitHub CLI 读取其用户配置被拒绝，因此通过官方项目文档进行只读检索。未复制上游源码或引入新依赖。
