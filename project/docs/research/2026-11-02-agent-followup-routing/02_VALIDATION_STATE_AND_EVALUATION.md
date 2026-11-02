# 第二批：完成判定、状态传递与回答校验

2026-11-02。承接第一批跨轮理解调研；只读上游源码及隔离函数实验，没有修改业务代码。固定版本、文件哈希与许可证见SOURCE_AUDIT.json。

## 1. DeepTutor：完成之前允许能力模块要求补做，但不是语义正确性保证

固定提交f7aed0744c36c5afef16a4261c31ebee1208cac2。

核对[runtime loop](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/deeptutor/runtime/agentic/loop.py)、[实际loop_host](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/deeptutor/agents/loop/loop_host.py)及[pipeline](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/deeptutor/agents/loop/pipeline.py)。chat/agentic_pipeline.py现在是入口转发，不能只读该文件就断言分析了实际循环。

通用循环有终止校验和修复接口。实际check_finish会调用能力的finish_instruction，有补做要求则丢弃待发布内容并回到循环；也允许能力提供最终文本覆盖。其机制适合借鉴“模型说结束之前，业务检查是否有未完成义务”。但能力钩子异常会记录后继续，且检查内容由各能力实现，不能把它当成教材语义校验器直接接入。我们应保留现有发布门禁和取消语义。

pipeline的_build_loop_messages实际读取conversation_history；对应消息构建测试覆盖摘要system消息不能被过滤。对我们有价值的是检查最终发给模型的上下文，而不只检查数据库中存在历史。本次失败已有历史，因此不能把补全历史存储当作主要修复。

## 2. OpenTutor：有一次修订，但中文适配与失败策略不满足直接复用条件

固定提交3afba67fb809e85559d904ee4e901869d60f5eb9。

核对[verifier.py](https://github.com/zijinz456/OpenTutor/blob/3afba67fb809e85559d904ee4e901869d60f5eb9/apps/api/services/agent/verifier.py)及[turn_pipeline.py](https://github.com/zijinz456/OpenTutor/blob/3afba67fb809e85559d904ee4e901869d60f5eb9/apps/api/services/agent/turn_pipeline.py)。它检查部分泛泛而谈、请求词覆盖与证据词覆盖，发现问题后可修订一次并再次检查。_salient_terms使用ASCII词项正则，主要面向英文；词重合也不能证明事实被教材支持。流水线预算耗尽或部分异常时会跳过检查并保留草稿，不适合作为我们正式教材的强制发布规则。

隔离执行原始确定性函数，控制模型调用为0。结果见MECHANISM_PROBES.json：

| 夹具 | 实测结果 | 含义 |
| --- | --- | --- |
| 中文费希纳教学请求，返回全书文件清单，中文证据 | 未报问题，请求词为空 | 这套词项检查漏检本次同类错误 |
| 中文请求，正常费希纳讲解，中文证据 | 未报问题，请求词为空 | 无法据此区分两类交付 |
| 英文请求，错误文件清单 | response_misses_requested_points | 英文受控夹具能命中部分偏题 |
| 英文请求，泛泛服务承诺 | response_does_not_address_request | 有反泛化回答检查 |
| 中文讲解，证据标签为英文 | answer_lacks_evidence_coverage | 混合语言夹具可能出现误报 |

另对DeepTutor原始路由执行5个夹具：普通教学追问、含糊“考考我”、明确生成测验、已有学习工作区、功能禁用；结果分别为保留chat、保留chat、转deep_question、保留chat、保留chat。

共10个夹具，仅验证选定函数边界，未运行上游完整应用或测试套件，不代表中文教学性能排名。首次实验的英文证据标签触发了额外检查，因此重新分离“纯中文证据/英文标签”两个变量；未修改上游规则或阈值来迎合预期。

## 3. LangGraph：可承载统一状态，不自动判断任务完成

固定提交ee3c043bddcc514012885167dd5916b15d6e4731。

[tools_condition](https://github.com/langchain-ai/langgraph/blob/ee3c043bddcc514012885167dd5916b15d6e4731/libs/prebuilt/langgraph/prebuilt/tool_node.py)根据最后一条AI消息是否有tool_calls决定进入tools还是__end__。这里的结束是工具协议结束，不是学习目标已经满足。ToolRuntime/InjectedState可以注入服务端状态，使工具读取已确定的主体与权限，避免让模型随意重写这些事实。

[Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)可以表达节点、边与共享状态；我们仍须自己定义“知识讲解不能交付成文件清单”等业务约束。把现有purpose正则原样搬进图，只会让相同错误换一种执行形式。

## 4. PydanticAI：结构化输出与有界修订可借鉴，规则仍由我们提供

固定提交129c94ef2940565af3bc9f638196fcc994d1ed4d。

核对[_output.py](https://github.com/pydantic/pydantic-ai/blob/129c94ef2940565af3bc9f638196fcc994d1ed4d/pydantic_ai_slim/pydantic_ai/_output.py)、[_agent_graph.py](https://github.com/pydantic/pydantic-ai/blob/129c94ef2940565af3bc9f638196fcc994d1ed4d/pydantic_ai_slim/pydantic_ai/_agent_graph.py)及[输出文档](https://github.com/pydantic/pydantic-ai/blob/129c94ef2940565af3bc9f638196fcc994d1ed4d/docs/output.md)。OutputValidator支持带RunContext的校验，ModelRetry可将具体问题反馈至模型。

值得借的是“输出类型+业务校验+有限重试”，不是把类型合法当成内容正确。项目已有Pydantic类型和门禁，先扩展现有边界；不为几条规则新增整套Agent框架。若以后采用该库，使用公共API，不导入本次所读私有实现。流式路径还须核对何时承诺最终结果，不能绕过现有已验证内容发布机制。

## 5. τ-bench：看最终任务结果，不能只统计工具成功

固定提交59a200c6d575d595120f1cb70fea53cef0632f6b。

核对[Env.calculate_reward](https://github.com/sierra-research/tau-bench/blob/59a200c6d575d595120f1cb70fea53cef0632f6b/tau_bench/envs/base.py)及[论文](https://arxiv.org/abs/2406.12045)。其环境比较实际与目标数据库状态，并检查要求的回答字符串；论文还关注重复运行的一致性。适合借鉴“真实多轮、任务结果、重复成功”，不是限定唯一工具顺序。

但我们是只读教材教学，文件清单和正确讲解可能都不改变数据库。因此不能直接复制其数据库哈希作为完成指标，字符串出现“费希纳”也不足以证明已经教学。应另查主体、交付类型、教材证据、教学覆盖和任务状态，必要时增加人工语义评审。

补充参考[HAConvDR](https://arxiv.org/abs/2401.16659)：历史感知检索需处理历史噪声和话题变化。本次只核对其摘要层面主张，没有复现训练或实验，不据此宣称其模型能解决本教材问题。

## 本批结论

成熟实现提供的是可组合机制：共享上下文、独立检索问题、窄能力路由、完成检查、有界修订、多轮结果评测。没有哪个已检查库能直接替代我们对中文人物指代、教学意图、教材支持与学习完成的业务定义。保留当前六层主体，收敛层间契约，比叠加另一个路由器更符合本次证据。
