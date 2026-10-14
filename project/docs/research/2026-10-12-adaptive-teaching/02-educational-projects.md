# 02 教育项目：可复用的是诊断与评价设计

2026-10-12。已读取ziliao.md 476–613（A51–188）。原附件续读时为空，用户随后提供合并文件，已补齐逐行复核。

|项目|已核验内容|对当前项目的决定|
|---|---|---|
|[Verify-then-Generate](https://github.com/eth-lre/verify-then-generate)|EMNLP 2024研究代码；先核验学生推理，再生成补救；仓库注明实验软件及CC BY-SA 4.0|优先借鉴首个错误步骤、诊断输出结构、针对错误反馈。现有ProofChecker检查AI证明，不能充当学生步骤诊断|
|[MathDial](https://github.com/eth-nlped/mathdial)|2861对话；真人教师与LLM模拟学生；有教师动作、是否揭示答案的标注；README标注CC BY-SA 4.0|借鉴多轮评价和教师动作；不当作中国大学真实学生样本，也不直接投入训练|
|[Book2Dial](https://github.com/eth-lre/book2dial)|教材驱动合成对话；作者明确承认幻觉和重复；仓库存在Persona_models目录|用于产生待教师审核的测试候选，不将合成对话写成真实学习证据|
|[PedagogicalRL](https://github.com/eth-lre/PedagogicalRL)|多轮GRPO和合成课堂、7B模型训练路线|当前不优先：缺可靠本地教学基准和真实学生标签，训练成本不能解决证据质量问题|
|[MathTutorBench](https://arxiv.org/abs/2502.18940)|开放教学能力的数据集及指标集合；GitHub API的license=null仅表示未识别，不能据此认定无授权|借鉴评价维度；实际复制代码/数据前分别核验授权|
|[TutorCoPilot](https://arxiv.org/abs/2410.03017)|真人导师获得AI建议的随机试验；论文报告主题掌握率提高4个百分点|支持“建议由人决定”的思路，但不能推导全自动学生助手同样有效|
|[EduChat](https://github.com/ECNU-ICALK/EduChat)|官方仓库为ECNU-ICALK/EduChat，非资料中DrJZhou地址；提供教育模型及demo|暂不换基座；模型演示不能补齐课程知识点、用户确认和教学验收|
|[LearnHouse](https://github.com/learnhouse/learnhouse)|当前apps/web、apps/api等；AGPL-3.0，企业功能独立许可|学习课程产品流程；不把整个LMS迁入当前轻量助教|

## 代码核验范围

使用gh只读API确认verify-then-generate的verification和verification_based_response目录、book2dial的Persona_models目录，以及mathtutorbench默认分支与元数据。尚未逐函数核验资料提到的全部路径，因此不能宣称源码可直接兼容。

## 优先落点

扩展现有证据链：学生原文→题目和技能→首个可确认错误/证据不足→补救动作→新题独立作答。结果必须包含来源、置信限制和可被学生纠正的诊断。先建设小规模中文课程验收集，再考虑合成学生、微调或RL。

具体代码路径后续核验及MathTutorBench许可冲突见06；不要按资料错误文件名直接复制。TutorCoPilot本轮核验了论文和作者项目页，未对其演示Notebook作生产可用性认证。
