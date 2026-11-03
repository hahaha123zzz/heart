# DeepTutor 图解生成机制：源码与本项目复用判断

日期：2026-11-03。针对两个已复现问题：教学限制词阻断预制匹配；模型生成的模板计划数量不匹配。详细现象见[验收记录](VISUALIZATION_ACCEPTANCE_20261103.md)。本次为源码调研，不修改业务或触发模型。

## 版本与证据

以上游GitHub固定提交`f7aed0744c36c5afef16a4261c31ebee1208cac2`为比较版本，Apache-2.0。使用此前公开GitHub树记录，核对本机`project/vendor/DeepTutor`文件的Git blob哈希：`visualizers/tool.py`、`loop_capability.py`、`protocol.py`、`builtin.py`、`agents/visualize/utils.py`及`tests/agents/visualize/test_validate_visualization.py`均匹配。`visualizers/registry.py`、`agents/visualize/capability.py`、`agents/loop/agent_loop.py`与该树不匹配；不将它们的本地实现当成该固定版本事实。

本机vendor目录内`git rev-parse`可能向上找到宿主仓库，不能把宿主HEAD当作DeepTutor版本。GitHub对应固定链接本轮网页抓取出现cache miss；源码事实来自本地文件与此前公开树blob校验，不宣称重新在线下载并验证了每一文件。

## 1. 一次提交一个可视化

[submit_visualization工具](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/deeptutor/visualizers/tool.py)接收一个visualizer ID和对应完整payload；检查类型已安装且可由Agent使用，调用该类型的validate_payload。类型不一致、不可用或payload校验失败时返回明确错误，成功才把结果写入context metadata并返回提交成功的工具结果。

[VisualizationLoopCapability](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/deeptutor/visualizers/loop_capability.py)在visualize mode指示模型选择最轻量的一种类型、提交完整payload；未提交有效结果时finish_instruction要求修复并重新提交。它缓冲/丢弃协议工作阶段的正文，避免把尚未提交的payload当讲解展示。具体重试次数和超时由宿主循环控制，不能从该类单独断言固定上限。

与本项目对照：我们一次选最多两种并要求plans数组匹配。真实故障选择1种、第二次返回2项；此前“两选一”降级不覆盖过量。值得借鉴的是**单次只要求一个确定类型、一次提交一个完整计划、明确失败原因**；这并不能保证模型绝不返回多项，也不能随意拿第一项。对过量输出应以选定ID、唯一性、来源和有效性为前提处理，无法确定时修订或失败。

## 2. 确定性校验 + 定向修复

[protocol.py](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/deeptutor/visualizers/protocol.py)定义带版本的VisualizationEnvelope和VisualizerPlugin，校验空值、大小、JSON/schema等；[builtin.py](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/deeptutor/visualizers/builtin.py)按不同类型调用不同校验器，含可访问性与渲染约束。

[validate_visualization](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/deeptutor/agents/visualize/utils.py)执行本地确定性检查，并提供可用于定向修复的错误；对应[测试](https://github.com/HKUDS/DeepTutor/blob/f7aed0744c36c5afef16a4261c31ebee1208cac2/tests/agents/visualize/test_validate_visualization.py)覆盖若干渲染输入边界。此机制证明结构/格式可检查，不证明教材事实、来源或学生目标正确。

我们已有VisualPlan、render_plan、证据定位和模型内容核验，宜保留。可扩展错误分类：无计划、超量、重复、未知类型、参数错误、来源失效、专业内容未通过、模型超时。修订只给具体可修复的问题，限制轮次和总时间；日志只记录类别、数量、ID/耗时，不记录学生正文或原始模型响应。

## 3. 预制主题与教学限制

已核查的visualize mode在被激活后选择可视化类型，没有发现其解决中文“只讲解不要出题”对本项目预制主题匹配的完整机制，也不能据此断言它会自动识别任何普通教学对话。

我们的“主题判断”和“输出限制”应分别使用已有输入理解结果：是否需要题目由no_questions等约束表达，不能将这些词残留当作额外教材主题，也不能删除用户给出的实验条件。只剥离明确的输出形式短语，不对所有未知词宽松放行；再检查主体、授权章节、预制版本和引用锚点。用户指定的新实验不能被一般预制图覆盖。

## 4. 复用代码还是思路

| 上游部分 | 许可/依赖 | 建议 |
| --- | --- | --- |
| 一类型一提交、明确错误与有限修订 | Apache-2.0；tool依赖UnifiedContext/BaseTool/registry等 | 借契约和测试思路，适配现有build_guide；避免引入第二套AgentLoop |
| VisualizationEnvelope版本化数据 | Pydantic及DeepTutor renderer协议 | 我们已有guided_visualization/v2，先沿用；必要时参考字段，不重复建协议 |
| 结构校验与有界payload | 依具体渲染器 | 借检查项；保留本项目VisualPlan、来源与心理学核验 |
| HTML/SVG生成器 | 不同渲染器各有规则 | 不直接执行模型生成HTML/JS；当前需要低交互、可核验的固定模板 |
| 预制匹配 | 当前已核查源码未给出对等解决方案 | 在现有心理学匹配器实现，须测中文否定、混合指令、自定义实验 |

如果后续复制实际代码，须记录原仓库、SHA、文件与修改，保留Apache-2.0版权/许可和适用NOTICE；本轮没有复制上游代码。依赖兼容、许可证清单和上游完整测试套件尚未验证。

## 5. 建议的最小实验

1. 把用户表达中的教学约束与主题分离，对“不要出题”“只讲解”等正反例做测试；主体和实验条件不丢失。
2. 限制按需每次选择一个模板，保留现有不需要图解的空选择；过量输出只接受唯一且确定归属的合法计划，否则使用现有有限修复并记录具体错误类别。
3. 模板结构、教材证据定位、心理学内容核验和最终发布按现有顺序保留。来源或内容失败不能降级发布。
4. 用固定合成请求在隔离账户重复验收预制命中、按需修复、无图、仅提示和取消；分别报告每次结果、耗时和原因。浏览器再检查流式更新、步骤高亮、历史恢复与引用。

预期是减少多模板协调成本与无意义模型调用，并改善可诊断性；尚未做A/B，不能声称成功率或速度已提升。
