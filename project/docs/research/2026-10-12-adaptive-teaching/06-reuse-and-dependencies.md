# 06 源码复用、工具与依赖

读取：ziliao.md 691–722、372–414（A266–297、B372–414）。2026-10-12。

## 推荐路径错误及授权歧义

- Verify-then-Generate HEAD `161019e6cc29968bb9a9ae7f261daf63f00e6fc7`包含`verification/error_identification.py`，资料的`verification/error_verification.py`不存在；`verification_based_response/main.py`存在。[固定版本树](https://github.com/eth-lre/verify-then-generate/tree/161019e6cc29968bb9a9ae7f261daf63f00e6fc7)。
- OATutor HEAD `a40eff7d0bd8073d2f82dd879dba22da2b320a55`入口是`src/models/BKT/BKT-brain.js`、`src/components/problem-layout/HintSystem.js`、`src/platform-logic/checkAnswer.js`、`src/models/BKT/problem-select-heuristics/`。[固定版本树](https://github.com/CAHLR/OATutor/tree/a40eff7d0bd8073d2f82dd879dba22da2b320a55)。这是入口核验，尚未完成全部函数行为及移植验证。
- PedagogicalRL的`src/classroom.py`和`prompt_templates/`已确认存在。
- MathTutorBench HEAD `6faed173ec2bef55cb899b2a3e0f93982f9cb176`有tasks、dataloaders、main.py。但README顶部CC BY 4.0徽章与末尾CC BY-SA 4.0不一致；复制代码/数据前应核清。[固定README](https://github.com/eth-lre/mathtutorbench/blob/6faed173ec2bef55cb899b2a3e0f93982f9cb176/README.md)。

## 不照单接入框架

|推荐|项目判断|采用条件|
|---|---|---|
|[Pydantic Evals](https://pydantic.dev/docs/ai/evals/evals/)|可选运行器；现有pytest与结构化案例可先做基线|需要统一异步样例、评分和报告时小范围接入；先定义准则|
|[Langfuse](https://langfuse.com/handbook/chapters/open-source)|有追踪价值，非第一步必需部署|先串联决策、证据、最终输出和学生结果；需要跨版本管理再部署。核心MIT，ee另授权|
|[LangGraph](https://docs.langchain.com/oss/python/langgraph/interrupts)|持久暂停与恢复；当前已有编排和任务澄清|普通偏好确认可用数据库proposal+API。真正需要长流程恢复时再比较|
|Agents SDK|本轮未作兼容源码核验|暂不接入，不同时增加两个Agent运行框架|
|[DSPy](https://dspy.ai/3.4.0/api/optimizers/MIPROv2/)|依赖训练样例与metric，可能对评分器过拟合|稳定教师标签和独立留出验收集后离线试验|
|SymPy|项目已有依赖和受限表达式评分|沿用受限解析、资源限制；不给LLM任意Python执行|
|NetworkX|有限图算法候选|关系反例可先用小型确定性函数，复杂图算法需要时再加|
|[Pingouin](https://pingouin-stats.org/)|心理学统计辅助候选，非甲方独立要求|需实验设计、检验前提和评分准则；会运行ANOVA不等于会解释因果|

[lab.js仓库](https://github.com/FelixHenninger/lab.js)确认核心Apache、Builder AGPL。OATutor平台和课程素材也须分别记录许可。

## 执行边界

工具采用结构化输入，设规模、时间与输出上限，返回验证域及失败原因。有限实例通过不构成一般证明。LLM诊断不确定时不能给已验证标记。工具输出、教材事实与学习证据分别保留来源。
