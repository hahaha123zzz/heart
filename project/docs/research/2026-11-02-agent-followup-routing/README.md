# 六层Agent跨轮理解与执行一致性：开源源码调研

日期：2026-11-02。针对“费希纳是谁→教材中与他相关的内容有哪些，我想学习，你教一教我吧”的真实失败，先调研再修复。本轮没有修改业务代码、8000运行配置或学生数据库，没有调用真实模型。

## 结论

问题不是简单缺少聊天记录，而是主体未绑定、原句被下游再次分类、错误工具义务覆盖教学请求，最后以文件列表冒充学习任务完成。优先让已有六层共享同一解析后的学习请求，并在完成处检查交付目标；不是再叠一个独立路由器。

可借鉴DeepTutor的窄能力路由与工具语义、LlamaIndex/LangChain的历史感知检索问题、PydanticAI的输出校验与有界修订、τ-bench的结果导向多轮验收。LangGraph能承载这些状态和步骤，但不会自动解决主体指代和教学正确性。OpenTutor的上下文与修订流程值得参考，其当前英文规则不适合直接作为本教材的中文门禁。

## 分批结论与证据

1. [跨轮理解与路由](01_CONTEXT_AND_ROUTING.md)：历史改写、窄路由、kb_files的适用边界。
2. [完成判定、状态与校验](02_VALIDATION_STATE_AND_EVALUATION.md)：真实循环实现、中文校验实验、框架能力限制与论文启示。
3. [项目复用决策与验收设计](03_PROJECT_DECISIONS_AND_ACCEPTANCE.md)：借代码还是借机制、最小改造顺序、拟议24条多轮验收。
4. [源码审计清单](SOURCE_AUDIT.json)：7个仓库、固定提交、40份源码/测试/文档/许可证文件，含下载来源与哈希。
5. [隔离机制实验](MECHANISM_PROBES.json)：10个原始确定性函数夹具结果，不等于完整应用性能评测。
6. [实施计划](IMPLEMENTATION_PLAN_20261102.md)：待执行的P0–P5阶段、24条验收用例、兼容检查和8000集成回退要求。

相关本地证据：[六层失败核查](../2026-10-31-layer4-evidence-execution/FECHNER_FOLLOWUP_SIX_LAYER_AUDIT_20261102.md)、[此前第五层参与情况](../2026-10-19-deeptutor-conversation-flow/RESPONSE_COMPOSITION_FECHNER_AUDIT_20261102.md)。未将学生原始聊天复制进本调研目录。

## 调研范围和许可

| 仓库 | 许可 | 本次重点 |
| --- | --- | --- |
| HKUDS/DeepTutor | Apache-2.0 | 能力路由、上下文、实际循环及工具说明 |
| zijinz456/OpenTutor | MIT | 上下文、路由、校验和修订 |
| run-llama/llama_index | MIT | condense-plus-context与测试 |
| langchain-ai/langchain | MIT | history-aware retriever与测试 |
| langchain-ai/langgraph | MIT | 工具节点、状态注入和结束条件 |
| pydantic/pydantic-ai | MIT | 输出验证、重试、流式输出边界 |
| sierra-research/tau-bench | MIT | 最终结果奖励与多轮任务评测 |

仓库版本、许可证文件和具体链接以审计清单为准。上游公开源码保存在系统临时目录，不作为项目运行依赖。下载过程出现过两项SSL错误，通过公开Git blob接口恢复，未绕过TLS验证，最终40项内容校验通过。

本轮未运行上游完整测试套件，未证明其中文教学整体质量，未验证最新上游版本与本机依赖兼容。HAConvDR仅阅读摘要层面主张，未复现训练；τ-bench额外核对了奖励源码。后续实施仍需本项目回归与教材语义验收。
