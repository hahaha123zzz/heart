# 04 平台、知识追踪与复习组件的取舍

2026-10-12。已读取ziliao.md 43–171（B43–171），以下组件已核验一手仓库/文档。

|组件|核验|当前取舍|
|---|---|---|
|[OATutor](https://github.com/CAHLR/OATutor)|分步题、提示路径、技能BKT参数、适应性题目选择；内容有逐项CC BY 4.0归属|优先借鉴题目→步骤→提示→技能的内容结构；不替换现有FastAPI和前端，不迁Firebase|
|[pyBKT](https://github.com/CAHLR/pyBKT/blob/master/README.md)|fit/predict/evaluate/crossvalidate；AUC、RMSE、accuracy|第二阶段离线对照候选；必须有按技能的独立序列与留出数据。装库不能自动校准当前EMA|
|[EduStudio](https://github.com/HFUT-LEC/EduStudio)|MIT，PyTorch的认知诊断与知识追踪实验库|数据规模与标注不足时暂缓；可参考评估与Q-matrix，不把全部训练框架接入在线请求|
|[Py-FSRS](https://github.com/open-spaced-repetition/py-fsrs/blob/main/README.md)|Card、Rating、ReviewLog、调度和可选参数优化|适合定义/辨析等提取卡片；不能把记住一张卡的概率等同整个技能掌握或实验设计能力|
|[jsPsych](https://www.jspsych.org/latest/overview/timing-accuracy/)、[lab.js](https://lab.js.org/resources/performance/)|浏览器实验刺激、反应与计时；官方说明计时受设备/浏览器影响|若转入实验心理学，选其一做可检查的实验教学活动。离散数学当前画像与风格不依赖它们|
|[LearnHouse](https://github.com/learnhouse/learnhouse)、[Kolibri](https://github.com/learningequality/kolibri)|完整课程平台，分别不同技术及产品范围|作为平台流程参考，不作为三个重点差距的紧急依赖|

## 先于模型/库的必要工作

当前可靠规则评分和技能覆盖有限。先补少量代表技能的题、概念辨析、已审提示与新题验收，再形成稳定course_id/skill_id/item_id及版本。心理学应独立定义变量辨认、混淆控制、实验设计、数据解释技能，不能继承数学技能参数。

复习任务应有目标技能、待复测误区、截止时间、题目版本、提示状态、结果和关闭依据。用户可跳过或改期。FSRS仅负责适用卡片的时间建议，业务证据和用户控制仍由现有系统负责。
