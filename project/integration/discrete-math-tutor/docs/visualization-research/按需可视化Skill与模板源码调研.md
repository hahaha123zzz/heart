# 按需可视化：模板、Skill与Agent调用的源码调研

日期：2026-10-13。状态：调研结论，未接入业务代码。

## 一、用户新方向与结论

用户明确不希望预生成全部题目的成果，改为提供代码模板、将经验沉淀为Skill，让教学AI需要时调用。本文件替代《全教材多形式可视化调研》中“逐题离线生成成果”的主要路线；题库目录可用于检索与覆盖评估，但不先制作788个解答。

推荐采用：复用的教学模板与渲染器 + 按需加载的Skill + 实际题目数据与步骤生成 + 内容/数学校验 + 展示与版本化缓存。已有教材检索、记忆、回答核验和消息组件继续使用。

每个模板对应一类教学表达，不绑定某一道题。例如mapping_diagram处理具体题目的定义域、陪域、映射；proof_flow表示前提、推理规则及结论；set_regions表示区域与元素。AI可以组合不同形式，学生只需上一步/下一步。

## 二、实际读到的源码

| 来源 | 源码中实际做法 | 适合复用的部分 | 适配与许可证 |
| --- | --- | --- | --- |
| DeepTutor | SkillService提供list_skills/get_detail/read_skill_file；VisualizerRegistry组织类型目录与schema；SubmitVisualizationTool校验payload并返回可修复错误，再生成渲染信封 | 包元数据、按需文件读取、目录生成、错误结果结构和提交协议；少量独立校验逻辑可摘取 | Apache-2.0；依赖UnifiedContext、ToolDefinition等自身框架，不能整文件原封运行 |
| A2UI | catalog.json以结构化类型描述可用组件，Agent提交声明式UI，客户端负责渲染 | catalog/schema与数据/组件分离模式；选定协议版本后可复用相应schema与验证器 | Apache-2.0；通用组件没有我们的数学步骤语义，需要扩展；不必先引入整套协议与客户端 |
| CopilotKit示例 | useComponent注册名称、说明、参数schema和renderer；提供独立的自由生成网页sandbox桥接 | 组件登记字段、工具状态与显示连接；在使用iframe时研究其bridge及参数校验 | MIT；示例React/Next.js hooks不能直接用于当前原生JS前端；沙盒方案还依赖Websandbox等环境 |
| Anthropic algorithmic-art skill | SKILL.md要求先读取viewer.html，保持固定结构，只替换算法与参数等变量区域 | Skill目录结构、模板固定区/可变区约定、参考文件渐进加载的组织方式 | 该skill单独LICENSE.txt为Apache-2.0；原模板含品牌、种子/参数控件且面向艺术，教学版应改为简单步骤并核对依赖 |

结论是能够复用部分代码，并非只能借鉴思路。框架绑定强的UI组件与主流程以借鉴/适配为主；独立schema、校验、格式处理、模板及测试最容易复用。采用时保留许可、版权说明和改动记录。本轮下载源码仅作调研，没有直接引入运行。

## 三、Skill、工具、模板的不同职责

- Skill：告诉教学AI什么时候可视化、选择何种表现形式、怎么分步讲解、如何保留教材出处及检查答案。描述不负责执行。
- Tool：项目提供真正可调用的能力，接受结构化参数、取模板/资源、执行校验、发布显示结果，并返回错误。
- Template/Renderer：固定布局与显示行为，接收题目条件和步骤；决定怎样显示集合、树、矩阵、映射、公式或流程。
- Cache：保存已核验的生成结果，避免完全相同的问题反复生成；不是预先生成题库答案。

本机Codex的skills和运行在项目里的教学AI是两个系统。给Codex增加skill不会自动赋予项目DeepSeek调用能力。当前检查llm/client.py与讲解流程，未发现可视化工具调用循环或read_skill接线；需要实现受控调用接口，或先用结构化计划驱动等价的服务端执行。

## 四、建议的运行流程（本项目设计）

1. 读取问题、选区、原题和相关教材上下文，判断是否需要可视化。
2. 注入简短能力目录；选中Skill后才读取正文、所需schema、示例与模板，不把全部文件塞入每次请求。
3. AI输出VisualPlan：教材锚点、题目条件、教学目标、渲染器及步骤。依据实题生成，不套用无关辅助例。
4. 工具校验参数、资源限制和教材来源。可计算的数学结果调用既有NetworkX/关系验证器；新增领域配置相应验证器。证明流程保留规则及前提，不能把图画得对视为证明正确。
5. 错误以具体字段/步骤返回，限定修复次数；仍不通过时保留文字/PDF依据，不发布无核验的完整解答。
6. 渲染器把批准的数据组成步骤画面，学生点下一步。不增加模板选择、代码编辑或参数面板。
7. 保存内容版本、模板版本、题目条件摘要、来源和展示数据以便历史恢复。缓存避免跨学生混入学习记忆，完整解答与提示投影分别处理。

以上是设计建议，并非声称上述项目都采用完全相同流程。

## 五、动态自由度建议

第一层：AI生成schema约束的数据、步骤与组件组合，复用已审核代码；这里没有为每道题预生成答案，但学生仍能看到为本题生成的解释。

第二层：当目录无法表达教学目标时，允许在指定模板的可变区域生成SVG/受限网页。先做格式与内容校验，再在隔离容器中进行运行/显示检查，限制宿主访问与资源；不能直接把完整生成脚本插入聊天主页面。

先实现第一层和新载体；第二层单独测试后开放。JSON合法、网页能运行与数学正确是不同检查。A2UI避免任意代码执行的方法不等于所有数学内容都会正确。仅iframe标签也不是完整沙盒实现。

## 六、拟沉淀的教学Skill

| Skill方向 | 输入 | 可能使用的模板 |
| --- | --- | --- |
| 概念直觉与反例 | 定义、论域、问题与教材锚点 | 集合区域、对象分组、量词覆盖、映射 |
| 逐式推导与证明 | 前提、目标、允许规则、引用 | 公式板、证明流程、归纳结构 |
| 有限结构与算法 | 顶点/关系/矩阵、目标算法 | 图树、关系矩阵、路径步骤 |
| 计数与枚举 | 对象、限制、目标数量 | 计数树、分组图、逐步排除 |
| 知识结构与方法选择 | 相关知识单元、明确联系 | 概念图、定理判定流程 |

不按788题建立788个Skill。一个Skill可调用多种模板，一个模板可处理很多题。模板库有范围限制，不能承诺任意题的可视化均正确；全教材覆盖通过逐章抽样与失败案例扩展能力来检验。

目录结构可包含SKILL.md、templates/、schemas/、references/、examples/；正式开发时按现有项目命名确定。教学skill要求与代码模板需通过版本关联。

## 七、可具体借鉴的接线顺序

1. 从DeepTutor的catalog/schema/submit错误修复设计裁剪最小注册与提交协议，把现有guided.frames注册为首个渲染器。
2. 添加项目教学AI使用的Skill读取与能力选择。无需先替换现有意图识别和RAG框架。
3. 让AI按实际题目输出结构化步骤，接通数学验证与教材引用；先覆盖现有图、关系与真值表。
4. 增加集合、映射、计数树、公式与流程图模板，允许同一讲解组合载体。
5. 用历史恢复、提示边界、题目忠实性及渲染结果检查验收，再评估受限代码生成。

## 八、源码依据（固定commit）

- [HKUDS/DeepTutor / deeptutor/services/skill/service.py](https://github.com/HKUDS/DeepTutor/blob/6cf793bd868ba5ecbe64722936d4be8fab5a01df/deeptutor/services/skill/service.py)
- [HKUDS/DeepTutor / deeptutor/visualizers/registry.py](https://github.com/HKUDS/DeepTutor/blob/6cf793bd868ba5ecbe64722936d4be8fab5a01df/deeptutor/visualizers/registry.py)
- [HKUDS/DeepTutor / deeptutor/visualizers/tool.py](https://github.com/HKUDS/DeepTutor/blob/6cf793bd868ba5ecbe64722936d4be8fab5a01df/deeptutor/visualizers/tool.py)
- [HKUDS/DeepTutor / deeptutor/visualizers/README.md](https://github.com/HKUDS/DeepTutor/blob/6cf793bd868ba5ecbe64722936d4be8fab5a01df/deeptutor/visualizers/README.md)
- [a2ui-project/a2ui / catalogs/basic/v1/catalog.json](https://github.com/a2ui-project/a2ui/blob/3eafe0bafae3b5d33f7647e5d089bda3e76abf8d/catalogs/basic/v1/catalog.json)
- [CopilotKit/OpenGenerativeUI / apps/app/src/hooks/use-generative-ui-examples.tsx](https://github.com/CopilotKit/OpenGenerativeUI/blob/9c982df1a16b734a49d8dd9d1c29b0e4b1b1805b/apps/app/src/hooks/use-generative-ui-examples.tsx)
- [CopilotKit/OpenGenerativeUI / apps/app/src/lib/sandbox/sandbox-functions.ts](https://github.com/CopilotKit/OpenGenerativeUI/blob/9c982df1a16b734a49d8dd9d1c29b0e4b1b1805b/apps/app/src/lib/sandbox/sandbox-functions.ts)
- [anthropics/skills / skills/algorithmic-art/SKILL.md](https://github.com/anthropics/skills/blob/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills/algorithmic-art/SKILL.md)
- [anthropics/skills / skills/algorithmic-art/templates/viewer.html](https://github.com/anthropics/skills/blob/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills/algorithmic-art/templates/viewer.html)
- [anthropics/skills / skills/algorithmic-art/LICENSE.txt](https://github.com/anthropics/skills/blob/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills/algorithmic-art/LICENSE.txt)

CopilotKit仓库链接当前会重定向至OpenIntelligentUI；本次记录为API取得的commit快照，不混用搜索缓存版本。A2UI版本在演进，实际接入应锁定版本，不能拼接不同版本的消息格式。
