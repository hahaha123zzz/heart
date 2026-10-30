# 回答流程独立复查：功能已接通，效果尚不稳定

日期：2026-10-16。用户要求“重新检验这一部分做的效果”。本轮按当前完整代码重新运行，不筛选成功轮次，不修改业务代码。

## 结论与范围

上轮“10轮通过”是当次运行的结果，不能作为稳定教学质量已达标的结论。本次同一组10轮重新运行只有8轮正常回答；另外3个语义边界场景中只有1轮发布了回答。功能链条已连通，持续提示、短句接续和用户明确选择仍有影响实际使用的缺口。

复查使用现有模型、隔离临时数据库、合成账户及生产API相同的TaskService。关闭图解和后台记忆，未做浏览器/视觉、并发负载、真人学习收益或长期画像校准测试。适用负载为一次一名合成学生顺序对话。

## 验证数据

| 检查 | 本次结果 |
| --- | --- |
| 已有相关单元与兼容回归 | 62/62通过，9.392秒 |
| 原3场景10轮重新运行 | 8轮answered；1轮quality_rejected；1轮evidence_rejected |
| 额外3个语义边界 | 1轮answered、2轮quality_rejected；发布的1轮内容回应了问题，但内部错误进入check_self_report |
| 原10轮响应耗时 | 中位数17.63秒，最长29.016秒；不含图解 |
| 受保护轮次 | 原场景7轮及边界3轮的mastery、steps_mastery、interaction_preference均保持原值 |

“answered”仅表示发布通过，不能代表所有教学要求满足。原脚本的required是记录用文字，实际只检查状态、反馈模式、提示级别和部分数值，没有自动验证语义或用户选择。

## 必须先修

### 1. 当前明确要求会被自述理解规则覆盖

输入：“我明白了双盲的定义，先不做题，请继续解释它为什么能减少实验者偏差。”

真实路由识别了explain，但后续策略仍因“明白了”切到check_self_report，插入理解检查。本次生成的两份回答都在末尾加了任务，最后又因长度超过260字被拒，用户得不到解释。

另一个输入：“只判断我这句话对不对，不要再问我理由：双盲实验要求被试和执行实验人员都不知道被试接受的是哪种处理。”路由误输出no_full_answer；TaskExecution.hint_only把它转成仅提示。于是“给出正确判定”与“禁止最终判定”同时存在，两次生成后拒答。

最小修复方向：当前的解释/只判对错/不要出题等请求先确定允许的教学动作；自述理解只在没有后续明确任务时触发检查。区分“只要简短判定”和“只给提示”的任务约束，不能都当no_full_answer。

位置：agents/learning_feedback.py:59，models/task_understanding.py:38，agents/task_execution.py:15，orchestrator.py:458。

### 2. “我明白了”的短接续会被教材证据门误拒

双盲纠正被确认后，下一轮“我明白了。”未进入理解检查，而在更早的教材证据门被拒。理由是“没有可核验的实质要求”。用户看到的却是“教材内容不足”，与真实情况不符。

最小修复方向：先把短接续解析成已知教学动作，再核验该动作所需的教材事实；不能拿原始确认语当新的完整问答需求。保留证据门，但避免把“无新问题”显示为“教材不足”。

位置：orchestrator.py:265至307（证据门在反馈规划之前）。

### 3. 分层提示质检边界不稳定，连续辅导会中断

被试间设计的第3次求提示，初稿只让学生回到定义圈数量词，没有给出“一种”或最终判断。质检却把定位“每名被试”后面的数量词本身当成答案泄露，同时建议用几乎相同的方式定位。修订稿重复上一轮，被规则正确拦截，最终用户看到通用拒答。

首次提示到第2级也主要是反复读定义、圈词，数字级别变化比教法变化更明显。当前“只允许一个动作、不得给关键数量词”等规则过紧，生成与质检对“可用提示”没有稳定的一致理解。

最小修复方向：给生成和质检同一份提示等级示例，区分“指出教材位置/数量维度”和“直接给正确数量”。允许一个有意义的教学步骤包含圈词后比较，不将所有操作拆成违规的多个任务；只阻止真正公布答案。最后修订失败应保持前一有效提示和任务接续，不把教学困难泛化成教材核对失败。

位置：agents/response_generator.py:182至184；agents/quality_checker.py:155至156；agents/learning_feedback.py:88至90。

### 4. 摘要截断会删除辅助例子后的重答邀请

repeat_error/repeat_wrong确实切成worked_example，给出标注“辅助例子（非原书例题）”。模型原文末尾有“请用一句话重述……”，但发布前concise_terminal_text删掉了这一段，用“（可继续追问）”结尾。于是“例子→学生再试”的教学闭环不完整，质检仍放行。

最小修复方向：辅导模式在生成时压缩篇幅，或把重答邀请作为必须保留的结构。不能在质检之前静默删掉必需教学步骤，再仅凭模式字段宣称闭环完成。

位置：agents/response_generator.py:86、204；agents/quality_checker.py:125至128。

## 应修的辨识边界

### 5. “理解了”的主体不受限定，普通教材问题会被误当学生自述

输入：“如果被试理解了实验目的，为什么可能产生要求特征？请解释，不要出题。”

真实结果内部plan.action=ask_question、feedback.mode=check_self_report；但“理解了”描述的是实验被试。此轮生成器仍遵循用户请求给出解释、没有出题，因此本次学生最终拿到了可用内容。错误发生在计划/检索/题目设计，可能引发后续不必要的检查或额外调用，不能把本次发布成功当作策略正确。

最小修复方向：只识别学生当前自我报告，不对所有包含“懂了/理解了”的句子触发。与已对“被试不知道”做过的语境保护保持一致。

位置：agents/learning_feedback.py:19；orchestrator.py:697。

## 确实有效的部分

- 受挫后的完整解释先说“这一步确实绕，我陪你把它拆开看”，随后解释双盲与实验者偏差，未出现训斥或能力评判。
- 双盲修正可以确认条件完整；连续误判可以从targeted_hint切到worked_example级别2。
- 被测试的辅导后重答、自述及明确请求轮次都没有虚增掌握度、推进步骤或改长期交互偏好。
- 普通提示没有直接公布最终正确数量，质量门保留了拒绝发布的能力；主要问题在误拒、边界和接续。

## 原场景逐轮记录

| 场景/轮次 | 发布状态 | 反馈模式 | 秒 |
| --- | --- | --- | --- |
| designs/first_error | answered | targeted_hint | 22.546 |
| designs/hint_again | answered | hint_only | 14.954 |
| designs/still_stuck | quality_rejected | — | 18.188 |
| designs/corrected | answered | confirm_and_reflect | 16.985 |
| double_blind/first_error | answered | targeted_hint | 29.016 |
| double_blind/frustrated_explanation | answered | explain_feedback | 19.906 |
| double_blind/corrected | answered | confirm_and_reflect | 18.0 |
| double_blind/self_report | evidence_rejected | — | 2.969 |
| repeat_error/first_error | answered | targeted_hint | 17.265 |
| repeat_error/repeat_wrong | answered | worked_example | 15.485 |

## 可复查产物

均位于project/integration/discrete-math-tutor/artifacts：

- multiturn-feedback-independent-review-20261016.json：原10轮的新报告，保留全部模型草稿和质检。
- multiturn-feedback-boundaries-independent-20261016.json：3个额外边界的新报告。
- feedback-boundary-policy-20261016.json：两句输入在确定性反馈策略中的复现结果。
- multiturn-feedback-boundary-cases-20261016.json、recheck_feedback_boundaries_20261016.py：边界输入与复查入口，复用原验收流程，不改变原10轮测试集。
- multiturn-independent-review-tests-20261016.txt：62项回归结果。

建议修复顺序：当前任务与教学检查的优先级→短确认语的证据门→提示质检尺度→保留重答步骤，再重新跑同一组13轮。上面的计数是本次样例结果，不是估计出的总体成功概率。此次仅新增复查产物和文档，未改业务代码、未提交或push。


修正进展：用户已确认修正并启动浏览器。实施、发现的额外UI上下文问题、保留的失败与最终定向复验见[12-feedback-fixes-browser.md](12-feedback-fixes-browser.md)。
