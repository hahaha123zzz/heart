# DeepTutor图解稳定性：针对重复验收失败的补充调研

2026-11-03。范围为最新重复验收中出现的JSON错误、内容核验拒绝及预制未命中；不修改业务实现或改变证据门禁。此前固定提交的源码审计与blob比对见[原始调研](DEEPTUTOR_VISUALIZATION_REUSE_20261103.md)，实测记录见[验收记录](VISUALIZATION_ACCEPTANCE_20261103.md)。

## 现状和已证实边界

- 相同合成变量问题两次返回answered，但图解unavailable。并行日志出现一次LLMJSONError和一次图解内容核验拒绝；由于缺少请求关联，不能把具体错误一一分配给这两次请求，也不能判定核验拒绝是误报。
- `visualization/on_demand.py`的`call()`给chat_json设置retries=0；生成阶段的`raw=call(...)`位于两轮结构修复的内层try之外。LLMJSONError是LLMError子类，当前会走最外层异常处理并结束，不进入该两轮计划修订。这是代码控制流事实；是否每个JSON错误都可恢复尚未证明。
- `llm/client.py::chat_json`已有受预算限制的JSON重试接口，`LLMJSONError`与一般LLMError有区别；`chat`可识别长度截断，但当前包装并未提供结构化的截断原因，不能简单把所有失败都当格式错误。
- 预制匹配仍要求回复文本含相关主题、命中指定教材章节和文件身份；后续还校验版本与锚点。只移除“不要出题”不能保证命中，这些条件保护图解与当前问题/教材一致，不应直接去掉。
- 内容审核未通过会抛出ValueError并将反馈交给下一次生成，但同一40秒预算内可能已无足够时间；审核本身失败、超时或误判也需要与图解事实错误分开衡量。

## DeepTutor的可借鉴点

1. **提交前进行可执行的确定性验证。** 固定提交[submit_visualization](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/deeptutor/visualizers/tool.py)按所选类型调用校验器，失败返回具体原因，成功后才提交画布；[validate_visualization](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/deeptutor/agents/visualize/utils.py)检查语法/结构并提供定向修订信息。它不证明心理学事实或教材引用成立，不能取代我们的内容审核和来源校验。
2. **区分输出截断与格式错误。** 上游[正式发布说明](https://github.com/HKUDS/DeepTutor/releases/tag/v1.6.14)说明视觉生成需要区分token上限截断，避免将截断误报为解析错误，并允许调整视觉生成预算。这是上游版本发布说明，不证明本次LLMJSONError必然由截断导致，也不能推断应直接增大本项目预算。
3. **单一结果与可追踪修订。** [VisualizationLoopCapability](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/deeptutor/visualizers/loop_capability.py)要求提交一项有效payload，反馈校验错误并保留宿主循环的限制。我们已有心理学单模板选择，但模型仍会输出额外计划；单模板不能保证输出正确。
4. **结构与呈现分开。** [可视化协议](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/deeptutor/visualizers/protocol.py)有版本、payload与展示信息；我们的guided_visualization已有协议、来源跳转和分步控件，优先沿用而非引入完整画布系统。

## 具体建议与风险

| 问题 | 可借鉴方式 | 本项目最小试验 |
| --- | --- | --- |
| 生成JSON不可解析 | 分类错误后定向修订 | 仅对LLMJSONError在现有总预算和最多两次生成内重试；不重试取消、权限、网络及其他LLMError，继续要求完整schema |
| 截断 | 区分finish_reason与格式 | 先检查当前客户端能否可靠暴露截断元数据，再决定是否在预算内增加token；不根据本次未知原因盲目调大 |
| 内容审核拒绝 | 返回具体原因、有限修订 | 记录非敏感错误类别和request/task关联；比较人工复核与实际source，区分真实错误/审核误判，不降低发布标准 |
| 预制命中波动 | 复用已校验结构 | 分别记录主题词、目标章节是否一致、来源和锚点状态；仅在证据能可靠补充时检索预制主题，不跨版本或使用不相关教材来源 |
| 页面没图 | 错误状态分层 | 记录未请求、未排队、未命中、生成失败、校验失败、过期/取消、发送/展示失败；保留文字和完整状态，不暴露学生正文 |

优先在现有服务中复用本机实现，不引入整套DeepTutor AgentLoop或执行其HTML/JS生成。上游许可为Apache-2.0；若实际复制代码，单独记录SHA、路径、版权和适用NOTICE。当前没有复制源码。

## 建议验收

先用隔离模拟覆盖：首次JSON错误→第二次合法且完成审核；连续错误→停止；非JSON的LLMError不盲重试；取消/超时不发布；审核拒绝后修复仍需重新校验；教材证据/版本不匹配不使用预制。随后在独立测试身份上重复固定问题并逐次记录命中原因、结果、调用数和耗时，人工审查图解与教材。浏览器验收真实消息的翻步、刷新恢复与来源定位。当前未做这些改动、真实A/B或上游整套测试，不能承诺成功率提升。
