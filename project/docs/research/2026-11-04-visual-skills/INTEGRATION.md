# 首批可视化技能接入记录

日期：2026-11-04。范围：Draw.io、Visual Explainer、Interactive Educator 的项目内适配。不是在 Codex 安装后便假定学生端可调用。

## 实际调用链

教学准备 `read_skill` → 原有教材问答/选区回答及发布核验 → `visualization.on_demand.build_guide` 延迟任务 → 结构化生成 → 参数、原文与定位校验 → 图文核验 → 原有 `TaskService` 补图、`attach_guide` 保存 → `GuidedVisualization` 展示及刷新恢复。

接线覆盖普通 Q3 循环、旧 Orchestrator 和 PDF 选区入口；没有新增循环、数据库或任意代码执行工具。普通回答不额外启动这三个模板。明确请求省去模板选择模型调用，直接生成目标模板；生成和核验仍在正文保存后运行，失败保留文字回答。

## 调用条件和产物

| 技能 | 调用示例 | 实际产物 |
| --- | --- | --- |
| drawio | 画第一章的知识关系图；用 drawio 画变量关系 | 逐步查看关系图、下载合法可编辑 `.drawio` |
| visual-explainer | 分步图文讲解自变量与因变量 | 图与文字同步的步骤、重点节点及关系说明 |
| interactive-educator | 交互式讲解变量；`/aha 自变量` | 困惑→探索→概念→挑战；点情境改变关注节点和反馈；换情境可换整张图 |

各自 `visualization/skills/<name>/SKILL.md` 以及 `teaching-skills/SKILL.md` 已登记调用条件。技能在 `agents.teaching_skills.allowed_skills` 可见。

仅提教材图号不触发重画。只要文字、不要图、提示模式、正式待答状态或缺可核验材料时不发布这些图解。辅助探索不计分、不写掌握度。探索选项的临时选择不跨刷新保存；图解本身随回答保存并恢复。

## 上游复用与边界

固定上游提交、许可和修改说明见 `visualization/skills/visual-skills-sources.json`。每包保留上游 `UPSTREAM_SKILL.md`、参考资料和 LICENSE。

- Draw.io：`bahayonghang/drawio-skills` @ `2aa612ef9d5b65179eeebe7ab33f97f39d2315b4`，MIT。直接摘取 `scripts/shared/xml-utils.js::escapeXml`；生成 mxGraph 文件的薄适配由宿主实现。没有引入整套 Node CLI、图标库或桌面应用。
- Visual Explainer：`nicobailon/visual-explainer` @ `3d592addcc1689ea2251ee67991f12f8a30fd2d9`，MIT。复用技能指令及参考资料，宿主数据模板取代自由 HTML/脚本执行。
- Interactive Educator：`Wamikmk/interactive-educator` @ `f1044a03327771fc892dd89237101660b911897e`，CC BY 4.0，作者 Wamik。复用四阶段结构及交互约束，改写 Claude Artifact 环境接口，使用本项目受控组件。不是直接运行上游 React Artifact。

Next AI Draw.io 的独立应用和 MCP 实时编辑未部署；当前 `.drawio` 可导入 draw.io 或 Next AI Draw.io 编辑。没有声称已接通该服务。

## 验证与保留失败

- 相关 Python 集合：20 项通过，包括新技能、已有心理学图解和渐进补图保存/删除/账户隔离。
- 浏览器 `tests/browser/learning-visual-skills.cjs`：窄屏交互、情境反馈、节点关注切换、返回步骤、下载、XML 转义、序列化重新挂载通过；三种真实模型产物展示通过，无 pageerror。
- 真实模型：仅发送合成课程材料，官方 DeepSeek 端点；不是实际教材完整聊天验收。关系图、分步图文在 `live3.json` 通过；交互课程修正换情境换图后在 `live4.json` 通过。证据位于应用 `.runtime/learning-visual-skills/`；早期 `live.json`、`live2.json` 和失败输出保留，没有改写。
- 早期实际失败：概念连线过度暗示因果、交互 edges 使用 from/to、迁移题目换例子但图仍是旧例子。已明确结构协议、校准连线语义核验并支持阶段图覆盖；没有关闭事实和引用核验。
- 扩大至 `tests.test_q3_task_loop` 的混合工作树回归：3 失败、1 错误，均在 ask_user 暂停预期处。关闭本次三技能和新增启用逻辑后，代表性暂停测试仍得到相同 loop_failed；尚未修复这组问题，不能宣称全套回归通过。

本次未提交/推送、未重启 8000、未更改正式数据库。共享文件含其他窗口的未提交改动，集成时需按来源对账。真实页面从登录→提问→补图→刷新这一整条链尚未独立验收，不能把组件验收等同正式服务通过。
