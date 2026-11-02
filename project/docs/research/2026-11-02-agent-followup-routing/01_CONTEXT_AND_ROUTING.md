# 第一批：跨轮理解与路由源码调研

日期：2026-11-02。目标是解释并改进“费希纳是谁→教材中与他相关的内容有哪些，我想学习，你教一教我吧”的失配。本批仅调研，不修改应用或运行开关。

## 证据口径

使用agent-reach的GitHub调研流程。gh读取本机配置被权限拒绝，未获取凭据，改用公开GitHub API及官方文档。七个仓库均固定提交，下载文件另外核对Git树中的blob SHA；完整记录见SOURCE_AUDIT.json。不能把项目受欢迎、框架功能或README描述直接当成本项目中文追问成功证据。

此前本地DeepTutor 6cf793bd、OpenTutor a890519等仅用于定位目录，本批结论以新下载的固定源码为准。没有把本机已修改依赖文件算成上游源码。特别注意OpenTutor存在同名仓库，本批是zijinz456/OpenTutor，不能与opentutor-ai/opentutor混用。

## 1. DeepTutor：明确请求才切能力，工作区承诺优先

版本f7aed0744c36c5afef16a4261c31ebee1208cac2，Apache-2.0。

核对[capability_routing.py](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/deeptutor/runtime/capability_routing.py)、[对应测试](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/tests/services/session/test_capability_routing.py)和[kb_files工具说明](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/deeptutor/tools/prompting/hints/zh/kb_files.yaml)。

该路由器只处理明确的测验题集生成，默认不随意离开chat；已有工作区时不自动切换能力，并分别记录用户请求能力和实际能力。kb_files面向知识库本身的文件数、文件名、文件是否存在，不负责讲教材知识。不能把这一窄路由函数解释成完整中文意图分类器。

对我们最直接的借鉴是“窄自动路由+保留原请求+工作区保护”。本项目purpose把“教材……内容有哪些”泛化成文件查询，违反了这一边界。工具可用、工具适合本轮、工具必须执行是三种状态，不能因为挂载kb_files就把它设成必需工具。

源码中的标准库路由数据结构和测试形状可以抽取；不能照搬测验正则去修中文知识查询。我们已有决策和任务类型，应优先复用其结果，减少并列的意图权威。若实际复制Apache代码，须保留版权/许可并记录修改；本批未向业务复制代码。

## 2. LlamaIndex：先把追问凝练为独立检索问题

版本619d74664e8404612038bc15a1a40c686037277c，MIT。

[CondensePlusContextChatEngine](https://github.com/run-llama/llama_index/blob/619d74664e8404612038bc15a1a40c686037277c/llama-index-core/llama_index/core/chat_engine/condense_plus_context.py)的_run_c3读取历史，调用_condense_question，用所得condensed_question检索；生成仍使用原消息和聊天上下文。没有历史或skip_condense时可直接使用输入。还核对了对应测试，未运行其完整依赖环境。

这解决的是“追问原句没有检索主体”的工程入口：检索问题不能始终是“与他相关”。但模型改写不提供主体必然正确的保证，也不提供我们所需的会话epoch、教材版本、任务权限绑定。

本项目已使用LlamaIndex检索组件，理论上可评估直接复用chat engine或_condense_question相近接口；直接替换整个引擎会重复管理记忆和生成，影响TaskService/取消/来源发布。推荐先借其独立问题转换与测试边界，作为现有输入理解的一步；是否调用已安装API需核对本机版本和调用成本，不能直接引用本次HEAD的私有方法。

## 3. LangChain：历史改写与检索分开

版本aa13e9c0e94c4e9d203a15a5960b91e29088a98a，MIT。

[create_history_aware_retriever](https://github.com/langchain-ai/langchain/blob/aa13e9c0e94c4e9d203a15a5960b91e29088a98a/libs/langchain/langchain_classic/chains/history_aware_retriever.py)使用RunnableBranch：无历史直接检索，有历史则prompt→LLM→字符串解析→retriever。它只返回文档，不负责整个教学回合的权限和完成语义。当前位置属于langchain_classic，不能套用老教程假设现行导入路径仍一致。

该实现可作为“原话、独立问题、查询结果”分层记录的参考，不能直接作为我们最终ResolvedRequest：它输出普通字符串，没有中文人物候选、绑定依据或歧义类型。在本项目中，需要把主体/任务的结构化结果统一交给检索和选证，而不是只改写向量查询后让工具路由继续读原话。

## 4. OpenTutor：有统一上下文，但并未自动解决我们的中文场景

版本3afba67fb809e85559d904ee4e901869d60f5eb9，MIT。

[router.py](https://github.com/zijinz456/OpenTutor/blob/3afba67fb809e85559d904ee4e901869d60f5eb9/apps/api/services/agent/router.py)按规则写入AgentContext.intent，orchestrator再按意图选Agent并加载上下文。当前规则主要为英文，没有模型分类兜底，不能宣称复制即可获得成熟中文理解。

[context_builder.py](https://github.com/zijinz456/OpenTutor/blob/3afba67fb809e85559d904ee4e901869d60f5eb9/apps/api/services/agent/context_builder.py)区分偏好/记忆/RAG加载，部分记忆接口收到历史，但可见RAG路径仍传ctx.user_message。本批没有发现该入口提供通用中文人物指代→独立问题的完整证明。共享Context设计可借鉴，现有英文规则不建议迁入。

## 对本项目的初步决定

优先修“同一个回合有两套任务解释”，再补指代，不以堆更多teach/教一教正则作为最终方案。应保留原句，并得到有来源约束的主体与任务，再生成检索查询。人物不唯一、最近话题已变、历史失效时保留不确定或澄清，不能强行取最近姓名。

不需要为此重建记忆库、重解析教材、换embedding或立刻迁移整个AgentLoop。历史已在本次context中；首先需要让现有历史在正确边界被使用。
