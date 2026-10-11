# 教材 RAG：证据充分性检查实施记录

## 本轮变化

在混合召回与重排之后、课程规划及掌握度更新之前，增加 ContextSufficiency。重排分数表示相关性，不等同于教材足以回答完整问题。

- 核验输入：学生原问题（保留数学符号）、当前目标、最近四条对话、实际召回正文以及本轮真实附带的教材图像。
- 输出状态：sufficient、partial、insufficient、conflicting；服务错误或协议无效由服务端记为 unavailable。
- 只在 sufficient 时继续生成；其余状态暂停解释，不显示候选教材引用，不推进教学状态。对话仍保存，以便用户补充。
- 普通问答与 PDF 圈选问答均接入，SSE 增加“核验教材依据”阶段。没有展示模型内部思考过程。
- 对来源 ID、缺失项、状态字段作校验，伪造来源或相互矛盾的结论不能放行。
- 单次模型调用设置 25 秒超时并禁用 SDK 重试；有时间限制的调用不再重试空回复。核验暂不可用时与“教材依据不足”使用不同提示。
- 离线 mock 仅用于流程测试，API 标记 mode=mock，不能作为充分性实测。

此外，真实接口测试发现策略模块选择直接讲解而教学计划仍要求诊断题。现统一直接讲解时的计划与质检输入，跳过诊断题设计，并禁止据此提高掌握度或推进步骤。学生作答路径保留原教学策略。

## 评估与局限

所有题目由本项目编制，并非外部独立基准；标签是事先设置的人工预期。不能将这些数量宣称为总体问答准确率。

| 测试 | 结果 | 解释 |
| --- | --- | --- |
| 16 个受控证据题首次运行 | 14/16 | 8 个不足问题全部拦截；误拒最简子集证明与三顶点计数 |
| 明确允许题面条件和定义实例化后复测 | 15/16 | 此集已经成为开发回归集；仍误拒只给最简定义的子集证明 |
| 修改规则后另建 8 个新受控样本 | 8/8 | 4 个数学问题放行，4 个不足问题拦截；仅是小样本首次结果 |
| 原 12 个实际召回诊断题 | 教材内 6/8 放行；教材外 4/4 拦截 | ordered pairs 与分量问题的召回片段仍缺少公式、相关定义，有 2 个被暂停解释 |
| 单元与检索回归 | 45 项通过 | 覆盖无效引用、超时、空回复、圈选拦截、教学副作用保护与计划一致性 |

受控复测的核验延迟中位数约 817ms。这是一次小样本 API 测量，受网络与服务负载影响；不是整个问答时间，也不是 GPU 检索速度。正常问答增加一次远程模型调用及相应成本。

## 真实接口

采用临时测试账户，完成后通过 API 删除，不使用真实学生数据。

- JavaScript 异步调度问题：HTTP 200；insufficient；无教材引用；约 3.27 秒。
- ordered pairs 订单数据库索引：HTTP 200；insufficient；无教材引用；约 2.41 秒。
- 合取命题问题：首次充分性检查通过，但暴露生成计划与质检冲突。修复后真实 API 复测 HTTP 200，充分性与生成后质检均通过；回答“只有 A 和 B 同时为真，A∧B 才为真”，引用教材[2]。未出诊断题、未提升掌握度、未推进步骤；耗时 12.3 秒。首次结果保存在 evidence-real-api-first.json，复测另存 evidence-real-api-inside.json，不覆盖历史。
- 服务已重启，首页与 /health 均为 HTTP 200；reranker 实际使用 CUDAExecutionProvider。测试账户均删除成功。
- 本阶段测试跨越 2026-10-10 至 2026-10-11，文件名保留首次评估日期。

## 尚未解决

1. 核验器仍可能误拒可由极简定义推导的证明。
2. 有序对定义的正文确实缺少数学对象；仅召回正确小节并不代表证据完整。需要补回原 PDF 公式、定义及必要的相邻上下文，不能靠调低门槛。
3. 核验通过也不保证生成答案正确，原有生成后质检继续保留；质检自身的判断也有误差。
4. partial 当前暂停完整讲解，尚未提供“仅解释已证实部分”的交互。

## 复现

使用项目 GPU 环境 Python：

~~~powershell
.venv-gpu/Scripts/python.exe -m unittest tests.test_context_sufficiency tests.test_rag_upgrade tests.test_logic_formula tests.test_inference_runtime
.venv-gpu/Scripts/python.exe -m scripts.evaluate_evidence
.venv-gpu/Scripts/python.exe -m scripts.evaluate_evidence_fresh
.venv-gpu/Scripts/python.exe -m scripts.smoke_evidence_api
~~~

评估与接口脚本会调用已经配置的真实模型 API，产生调用费用。首次数据保存在 artifacts/evidence-controlled-first.json、evidence-followup-first.json、evidence-real-api-first.json；复测文件另存。

## 后续更新（2026-10-11）

有序对的公式与相邻页上下文已通过原 PDF 补充恢复；另修复独立问题检索输入与 ⊆ 术语展开。三个教材内诊断问题均恢复讲解。详细结果及剩余边界见 2026-10-11-rag-pdf-evidence-results.md，历史测试数量保留。
