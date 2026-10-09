# 教材习题交互化：开源调研与改造方案

## 结论
教材习题可以全部纳入逐题交互系统。现有实现只拆出十章31组练习PDF，没有建立逐题题库；现有评分仅支持knowledge/course.py里的20道选择题。31组不等于31道题，需按原题号及子题号建立全量清单。

## 开源参考

1. PrairieLearn：https://github.com/PrairieLearn/PrairieLearn
   - 题目元数据info.json、展示question.html、生成与判分server.py分离；支持复合题、多种输入控件和部分分数。
   - 文档：https://docs.prairielearn.com/question/overview/
   - AI批改：https://docs.prairielearn.com/aiGrading/ 。按题干、参考答案、rubric和学生提交逐项评估，支持证明、推导、图片作业。文档中的托管计费流程不代表本地可无配置复用。
2. STACK：https://github.com/maths/moodle-qtype_stack
   - 数学答案测试与潜在响应树控制分数和错误反馈，适合等价形式与具体错误诊断。
   - https://docs.stack-assessment.org/en/Authoring/Answer_Tests/
   - https://docs.stack-assessment.org/en/Authoring/Potential_response_trees/
3. Numbas：https://github.com/numbas/Numbas
   - 题干、子题、讲解分离；子题各自输入、评分；探索模式支持渐进提示和学习路径。
   - https://docs.numbas.org.uk/en/latest/question/reference.html
   - https://docs.numbas.org.uk/en/latest/question/explore.html
   - 表达式判分中随机取值比较是近似校验，不能作为一般数学证明：https://docs.numbas.org.uk/en/latest/question/parts/mathematical-expression.html
4. MathLive：https://github.com/arnog/mathlive
   - Web Component数学输入、虚拟键盘、LaTeX导出。可在现有页面中局部集成；输入组件本身不提供作业评分。
5. MinerU：https://github.com/opendatalab/MinerU
   - 可参考其版面、公式、图与表提取来构建导入管线；提取后仍需题号、子题和跨页图表绑定校验。不是自动题库与标准答案生成器。

## 推荐实现
沿用当前后端及页面框架，参考PrairieLearn的数据分离方式、STACK的判分反馈、Numbas的分步作答，局部接入MathLive。直接迁移整套LMS会额外引入课程、账号和部署体系，当前没有必要。

### 导入与题库
建立全量逐题清单：chapter、exercise_group、original_number、subparts、type、stem_blocks、assets、source_page/bbox、knowledge_points、answer_spec、rubric、review_status。文字公式使用结构化内容；复杂图形独立图像资源；原题裁图仅作校验溯源，不作为整个做题页面。
原题缺少参考答案时，AI生成候选答案与rubric，程序校验与人工/独立审校后发布。禁止把未经校验的候选答案当作已确认标准答案。

### 前端
移除“教材原版练习”PDF展示区，统一题卡、题号导航、章节小节筛选与作答状态。
选择/判断：单选或多选；填空：每空独立输入；集合/公式：数学输入；矩阵/真值表：网格输入；证明/简答：文字与公式分步输入，可扩展上传手写；构图：绘制或上传图形，并提交文字说明。
每题提供保存草稿、提交、逐步提示、重做、请AI解释、回到教材。AI讲解接入相关教材上下文、该题作答记录、当前用户相关记忆。

### 后端
新增题目、小题、答题会话、提交、逐项评分和提示记录模型。区分公开题干与仅服务器可访问的标准答案/rubric。提交绑定题库版本，支持幂等、重试、异步AI批改状态与结果保存。
判分按类型路由：选择判断规则匹配；集合与矩阵结构化比较；公式做指定定义域下等价校验；命题逻辑可用真值表/逻辑检验；图用图论性质与结构校验；证明按rubric逐项AI辅助反馈。不能确定时显示待复核，不写入已确认掌握。仅补充几个输入框再统一调用LLM，无法形成可靠判分体系。

### 用户流程
阅读或AI学习 → 点击去练习 → 对应章节/小节题目 → 作答并提交 → 规则/AI反馈 → 修正重做 → 更新个人学习记录。

## 全量验收
1. 十章31组按原题号、子题号逐项清点，题目和图公式无遗漏；跨页题不重复、不截断。
2. 所有题具备真实作答、保存、提交与反馈入口；各题型均有代表性验证。
3. 规则判分接受应当等价的答案，拒绝已知反例，参考答案不泄露。
4. 证明题反馈指出具体步骤、依据与评分项；不确定结果进入复核。
5. 章节/小节跳转、草稿恢复、重做、教材定位、错题和记忆更新可用。
6. 先以第一章验证全流程并修正导入与判分规则，再用同一管线覆盖其余九章；最终交付仍要求全教材覆盖。

本轮完成调研与方案；没有将现有项目宣称为已经逐题交互化。
