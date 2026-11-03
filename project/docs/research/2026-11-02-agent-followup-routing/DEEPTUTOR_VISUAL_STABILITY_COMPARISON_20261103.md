# 自动图解为何仍不稳定：DeepTutor 源码对照与当前阻塞复核

日期：2026-11-03。本轮只调研、读取源码和既有合成测试记录，不修改业务代码、不重启8000、不调用真实模型、不发送学生历史。以用户提供的最新验收状态为起点，不把此前的信号检测取证失败当作当前仍未解决的问题。

## 一、结论

普通问答自动图解主链路已有成功实例；当前不是所有场景都不能出图。四个正向实例中，三个走确定性教材预制，一个走按需生成，证明两条路径都可运行，但不能代表重复成功率或完整验收完成。

剩余两个阻塞发生在不同环节：方法选择的首次计划进入了内容审核并被拒绝；第一章知识关系计划连续两次无法解析JSON。日志未保留足够的具体拒绝理由与结构化解析错误，无法认定审核误报，也不能断言JSON错误由截断引起。

DeepTutor可借鉴的是“一个明确产物、局部校验、具体错误反馈、有限修订、成功提交后展示”。它没有在所核查的通用图解提交路径提供与本项目等价的心理学教材事实、原页锚点和回答一致性保证。因此不能通过照搬其发布标准来声称解决本项目的稳定出图。

长期不收敛的主要工程原因：模板与匹配覆盖持续扩大，但按需生成的知识组织、结构填充、证据选择、语义审核仍在串联依赖模型；失败原因没有充分分类；Mock回归通过与真实重复成功率没有分开验收。应该先缩小运行时生成责任，而不是继续主要依靠扩提示词、加模板名称或重试。

## 二、证据与版本

本轮通过GitHub插件在线核查HKUDS/DeepTutor默认分支最新提交：`f7aed0744c36c5afef16a4261c31ebee1208cac2`，提交日期2026-10-31，发布v1.7.1。固定版本链接如下，避免用本地vendor的宿主Git HEAD推断上游版本。

| 上游文件 | GitHub返回blob SHA | 本机vendor内容比对 |
| --- | --- | --- |
| [visualizers/tool.py](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/deeptutor/visualizers/tool.py) | `76842c4a14ceace1b31532ea205acb130fe84da5` | 匹配 |
| [visualizers/builtin.py](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/deeptutor/visualizers/builtin.py) | `0c616c1a2141b57a4d25f4ca3fc5d468af5a6421` | 匹配 |
| [visualizers/loop_capability.py](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/deeptutor/visualizers/loop_capability.py) | `91822ec5d22e868abdf1cccc627f5f17633d1692` | 匹配 |
| [agents/visualize/utils.py](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/deeptutor/agents/visualize/utils.py) | `2c925666078fd11cbf91409305f3156ff99b4e5a` | 匹配 |
| [agents/visualize/capability.py](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/deeptutor/agents/visualize/capability.py) | `69fe9008dee0cafda04162b366e9dd2cb9e75b50` | 不匹配；本轮结论采用在线源码 |
| [test_validate_visualization.py](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/tests/agents/visualize/test_validate_visualization.py) | `eaa1eceef2f07bcfd2d7626f167b78b5baf26d04` | 匹配 |

本机文件比对时统一CRLF为LF后计算Git blob SHA。许可沿用已审计的Apache-2.0；本轮未复制实现代码，未新增依赖。

本项目证据来自`visualization/on_demand.py`、`templates.py`、`psychology_presets.py`、`skills/experimental-design/SKILL.md`、`agents/task_service.py`、`llm/client.py`，以及最新[验收记录](TEACHING_VISUALIZATION_ACCEPTANCE_20261103.md)。正式数据库仅以两个已知合成问题精确筛选、只读核查任务ID与结果状态，没有遍历其他学生历史。

## 三、两个失败究竟发生在哪里

### 3.1 方法选择

问题：做实验时，观察法、相关研究和实验法应该怎么选择？

- 最新任务：`8c72b6b6-5f7f-469c-8697-f1e64a0ea50d`；图解trace：`30c5157889c1`。
- 结果为`answered`，文字821字，图解`unavailable`，既有脚本记录总耗时19.46秒。
- 相同trace的日志：`stage=visual-check error=ValueError attempt=1 selected_count=1 plans_count=1`。
- 由控制流可确认：第一次计划已通过JSON解析、VisualPlan、本地渲染和来源定位，进入模型审核；审核结果没有同时满足`passed is True`与`issues == []`。
- 相邻日志随后有`stage=visual-generate reason=no_plan`，与修订后返回空计划相符，但该日志没有trace，不把它作为独立精确关联证据。
- 当前不能判断是图解真的混淆了观察/相关/实验，还是审核误报；原有日志只记录异常类型，没记录具体issue类别。不能靠降低审核标准解决。

### 3.2 第一章知识关系

问题：梳理第一章各节之间的知识关系，帮我建立整体框架。

- 最新任务：`3ae6db27-0843-4a21-bb8f-47b559fc3054`；trace：`2c367774c486`。
- 结果为`answered`，文字1339字，图解`unavailable`，既有脚本记录总耗时22.3秒。
- 同trace两条日志均为`stage=visual-generate error=LLMJSONError`，分别attempt1和2，随后`validation_failed`。
- 可确认生成结果没有形成可解析JSON对象，尚未到内容审核，不能称为审核器误杀。
- 现有记录不足以区分具体格式错误、返回非对象或其他解析原因；不能从异常类别推出网络失败或token截断。

## 四、DeepTutor实际如何处理

### 4.1 通用图解：共享Agent循环，不是固定三次模型调用

在线`capability.py`将SVG/Mermaid/Chart.js/HTML等通用图解交给`AgenticChatPipeline`，设定最多5轮；默认max_tokens为16000，并允许从可视化配置读取。模型通过`submit_visualization`提交单一类型和完整payload。

`loop_capability.py`明确要求优先最轻量类型、根据工具返回的具体错误修复，尚无有效提交时继续提示提交。成功后将产物放到统一envelope中展示；循环结束仍无产物则明确抛错，并区分工具调用能力未开启的情况。最多5轮不是五次必定成功，也不能与本项目40秒附加图解预算等同比较。

本地仍存在`VisualizePipeline`的分析/生成/修复辅助类，但不能因此断言最新通用图解主路径始终执行三个Agent。Manim动画另有专用渲染与重试路径，不作为当前心理学分步图的直接迁移目标。

### 4.2 校验重点不同

`tool.py`先调用插件的`validate_payload`，校验失败返回具体错误，不提交产物。`builtin.py`与`utils.py`的通用检查主要包括：

- SVG的XML结构、viewBox和可访问性标签；
- Chart.js的JSON格式、图表类型、数据集结构及标签；
- Mermaid的起始关键词；mindmap的根节点及子节点层级；
- HTML文档基本结构、viewport、控件与标签。

这些检查并不逐项证明心理学专业事实或教材引用准确。质量要求虽然写在提示词里，已核查的通用提交路径没有强制独立教材语义审核。本项目按需路径要求额外模型审核，以及可定位的教材原页，因此需要解决更多问题。

`utils.py`虽然保留`build_fallback_html`辅助函数，但当前在线通用主路径无有效envelope时会报错，不能将该辅助函数的存在误写成“所有失败自动生成备用图”。`tool.py`的fallback字段也不等于已经重新生成了一张正确的SVG。

### 4.3 上游也曾出图失败

在线核查[Issue #1546](https://github.com/HKUDS/DeepTutor/issues/1546)：报告者描述推理模型耗尽输出预算、提交参数被截断，造成空白画布。该Issue已关闭；当前源码已读取可视化预算配置并提供无有效产物的错误说明。这证明上游也遇到过类似可靠性问题，不是其平台天然稳定。

Issue中的具体token统计来自报告者的环境，不能外推到我们。我们直连DeepSeek路径默认关闭thinking，JSON格式错误日志也不同；没有证据将本次两轮LLMJSONError归因于同一原因。

## 五、我们的长期阻塞在哪里

| 环节 | 当前实现与问题 | 判断 |
| --- | --- | --- |
| 自动触发 | 已能在普通问答后出图 | 不是当前两案的主因 |
| 高频预制 | 主题包绑定原文hash、PDF版本、位置 | 当前最稳定的已有路径；成功样本仍不等于长期统计 |
| 按需结构 | 心理学四模板中三个共用nodes/edges/steps；知识组织主要由模型完成 | 模板固定了渲染格式，没有固定知识关系 |
| 新模板与Skill | `knowledge_map`已加入目录，但experimental-design Skill还没有专门的章节关系生成规则；experiment_flow主要描述实验程序 | 任务边界欠明确；是源码可见的短板，未证明是两次JSON错误的直接原因 |
| 参数约束 | 外层VisualPlan严格；payload为dict，嵌套字段靠渲染时验证，模型看到的是提示中的示意参数 | JSON mode只保JSON对象，不保证完整契约、专业正确或证据覆盖 |
| 证据粒度 | 每个按需计划选一个source_index/evidence_index；证据按300字符机械分段 | 适合局部图示；不能由一个引文推出整个章节关系均有证据。现有审核运行会看到更多材料，但缺少节点/关系级证据映射 |
| 修订 | 循环把错误文本传回，但没有把上次完整计划显式作为修订输入，而是重新生成；审核JSON错误也会触发整轮重生 | 容易把已经可用的结构和来源选择一起重做，扩大波动 |
| 预算 | 总40秒，选择8秒、生成14秒、审核8秒；若两次都走满，名义合计52秒 | 剩余预算会截短修订。是结构性风险，最新19/22秒两案没有证明因此超时 |
| 可诊断性 | ValueError未保留具体原因；部分空选择/空计划日志无trace；None统一落到unavailable | 无需出图、无计划、格式错误、来源失败、审核拒绝混在一起，妨碍针对性修复 |
| 验收 | 现有心理学回归使用Mock固定返回合法计划和审核通过；knowledge_map主要验证共用renderer可执行 | 回归保护有效，但不能替代真实模型重复验收、内容抽检和浏览器验收 |

这解释了为何“又加了模板、改了提示、测试通过”仍会遇到下一类失败：每次主要修复了局部覆盖，未形成按失败阶段统计、最小修订与重复验收闭环。此前没有足够证据把可运行描述成稳定完成，后续应明确区分两者。

## 六、建议借什么、保留什么

1. **优先补可诊断性。** 沿用已有trace，区分not_needed、no_plan、json_invalid、schema_invalid、source_unlocated、audit_rejected、audit_invalid、budget_exhausted等内部原因；用户界面仍保持简洁。不记录原始学生正文或模型内部思考。审核理由可保留受控错误类别与必要的已脱敏摘要。
2. **先稳定两类任务的数据来源。** 章节图从已有`course_navigation.outline()`与`agents/chapter_overview.py`的章节包提取章/节包含关系，不能把目录顺序当因果或前置依赖。方法选择先核对本教材实际支持的分类，再形成审定节点、关系和边界条件；教材未支持的“相关研究”分类不硬凑成三分法。
3. **预制知识结构，不必把所有答案预生成。** 高频任务复用已审定的关系、步骤和锚点，运行时选取相关部分，使用现有structure renderer；文字讲解仍按本轮问题生成。非高频任务允许模型从允许的节点/关系集合填充有限字段，校验后展示。
4. **按阶段修复。** 借DeepTutor的具体错误反馈机制：结构失败修结构，审核输出格式失败重取审核，内容失败修具体关系；不要每次从选择、计划重来。合法JSON不等于可发布，仍保留来源与专业事实检查。
5. **验收按交付结果。** 建议固定两个阻塞问题及自然改写，先各重复5次记录分阶段结果、调用数、耗时、实际帧数；全部结果如实纳入分母。预制路径相同输入结构和锚点须一致；按需路径需内容抽检。浏览器验证分步高亮、历史恢复和教材跳转，未通过不宣称T4/T5完成。

不建议替换现有AgentLoop、引入整套DeepTutor画布、执行模型HTML/JS或取消内容审核。需要借用的是其产物提交与校验修订机制；本项目已经有Pydantic、固定渲染器、图解协议、预制包、章节目录和来源定位，可优先复用，不需要重建。

若后续确实复制上游函数，应记录固定SHA、原路径、改动及Apache-2.0许可和适用NOTICE。当前阶段没有发现必须复制一整段DeepTutor实现才能解除阻塞的理由。

## 七、边界

本轮未运行DeepTutor整套服务，不能给出其相同教材、相同模型下的成功率；未重新跑完整测试矩阵或浏览器验收。当前模型审核拒绝的具体专业原因、两次JSON解析失败的原始类别仍缺少记录，须在下一次受控复现中补证据。以上方案为基于源码与已存任务的调研建议，尚未实施。
