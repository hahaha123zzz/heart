# 六个教学 Skill 仓库调研与本项目接入建议

日期：2026-11-04。范围：用户给出的六个公开仓库，以及本项目课程对话的输入、策略、技能读取、内容生成和发布边界。本文是静态调研与接入方案，不是已接入或效果验收记录。

## 1. 结论

可以复用这些技能来改善教学对话，但首批应选择少量、按场景激活的教学方法，而不是安装六个仓库后全局执行。它们主要提供给模型阅读的行为说明，安装到 Codex/OpenCode 并不会自动进入本项目 Python 后端的学生对话。

推荐首批采用：

1. **讲不懂时实际换讲法**：参考 edu-agent-skills 的 simplify-topic / teach-concept，补充类比适用边界、逐步恢复准确术语。
2. **只给下一步提示**：参考 ai-teaching-skills 的 ai-socratic-tutor，在学生明确选择引导或提示时使用，保留切回直接讲解的出口。
3. **根据作答纠正具体错误**：结合 ai-solution-study 与 misconception-detector，先指出有效部分，再定位第一个实质缺口，区分不同但有效的解法。
4. **评价这些行为有没有出现**：参考 Anthropic 的评估框架和理解检查验证方法，改写成大学实验心理学案例。评估先离线使用，不在每条消息后自动增加一次裁判模型调用。

anything-to-course 更适合后续课程建设和明确的复习活动；Hermes 更适合作为中文表达与场景边界参考；book-tutor 暂不复制进入项目，因为没有找到适用于该技能的许可证。

上述是依据源码的适配判断，尚不能证明学生学习效果一定提升。

## 2. 六个仓库逐项比较

| 来源 | 实际提供内容 | 对当前对话的价值 | 原样使用的主要问题 | 建议 |
| --- | --- | --- | --- | --- |
| anthropics/k12-teacher-skills | 四项：lesson-plan-creation、lesson-differentiation、lesson-prep、check-for-understanding；附 CSV rubrics | 教学目标、支架层级、干扰项与错误思路对应、下一教学动作、评估标准 | 面向 K–12 教师；美国课程标准；理解检查技能限定数学；输出教师文件/学生材料，不是当前对话协议 | 优先借鉴评估与检查设计；教师备课功能后续再接 |
| bstellato/ai-teaching-skills | ai-socratic-tutor、ai-novice、ai-solution-study；纯 SKILL.md，无专属工具依赖 | 一轮一个有效步骤、学生教 AI、对照参考解答定位第一处实质问题 | 强制维持角色、不给完整答案；部分技能不作正确性背书；与直接讲解和正式评估存在冲突 | 有条件接入 tutor / solution-study；novice 留作明确选择的活动 |
| lowwwbank/anything-to-course | 课程生成主技能，配 course-blueprint、practice-design、study-mode、quality-rubrics 等 | 从“知识点”转成可观察能力、支架渐退、练习反馈、变式迁移 | 全课程文件写作；学习模式坚持先作答、不以总结代替测验；自建日志和复习日程 | 后续课程/复习场景使用，不做普通问答默认行为 |
| yugash007/edu-agent-skills | 20 项教育技能，含概念教学、简化、误区诊断、理解检查、记忆等 | 普通解释、没听懂、作答反馈最容易映射现有教学策略 | 编程教学取向；teach-concept 强制回忆问题和迁移作业；部分技能产生新画像/弱点记录 | 首批挑 simplify-topic、teach-concept、misconception-detector 的有效步骤，删改强制项 |
| xixiaofinland/agent-skills 的 book-tutor | 读项目 CLAUDE.md、按章学习、约 200 词讲解、理解检查、vault 进度与概念笔记 | 教材位置连续性、困难后改用类比、少量长期概念笔记 | 强制先问、每次讲完都检查、通过检查才推进；直接写 vault；未发现适用许可证 | 仅参考思路，暂不迁入原文；不借用其他技能目录里的许可证 |
| hezkvectory/hermes-edu-skills | 大量中文场景 SKILL.md、目录和校验/打包脚本 | 中文讲题、提示强度、不适用场景、解释步骤的理由 | 技能声明依赖 context.load、entitlement.check、workflow.create、memory.write 等；公开树中未找到这些教学 workflow 的可运行实现 | 选读中文教学边界，避免引入整个平台或虚构工具调用 |

### 2.1 Anthropic：最值得拿的是检查设计与评价方法

四项技能覆盖新课生成、已有课分层、教师备课、数学理解检查。不要把“理解检查只支持数学”误写成整个仓库只支持数学；其他备课技能也覆盖 ELA、science、social studies。

理解检查设计的两个具体优点：

- 判断选项时，逐个检查题干是否确实排除了其他可辩护答案，而不是因为答案键指定了某项就判其他项错误。
- 检查干扰项是否真的由指定的错误思路产生，避免随意凑三个错误选项再倒推误区。

该数学理解检查 rubric 当前有 35 条，包含可观察作答、下一步教学、语言、图示、教师/学生材料分离等。对我们有价值的是独立评分维度与可操作判据；K–12 数值范围、课程标准代码、教师材料格式等不能直接用来评分大学心理学对话。

另有一个明确冲突：该技能要求产物不出现第三方来源归属，本项目则要求教材事实有来源。因此它的展示规则不能覆盖本项目引用机制。它还有先确认教学焦点再继续的教师工作流，不适合让每个学生问题都等待一次确认。

### 2.2 ai-teaching-skills：依赖最少，但教学边界最严格

ai-socratic-tutor 每轮限定为一个问题、一个提示或一个必要前置解释，且不泄露后续完整解法。ai-solution-study 强调先有学生尝试、先肯定有效部分、只处理第一处实质差异，并明确不同但有效的路径不是错误。这些可以直接改善“只提示”和“帮我看看错在哪里”。

但原版 tutor 在技能激活期间，即使学生改口要求完整答案也不会退出，必须显式结束技能。原版 novice 不提供纠正或事实补全。这种约定可以用于学生明确选择的学习活动，不能变成普通聊天默认规则。接入时由现有教学模式决定边界；用户切回直接解释时，技能约束应当随之撤下。

### 2.3 edu-agent-skills：最贴近目前的“讲解质量”目标

simplify-topic 不是只把句子变短，而是改变抽象层级，解释类比在哪些地方成立、哪些地方不成立，然后回到准确术语。misconception-detector 要求针对有证据的错误模型换方法纠正，而不是重复原解释。两者适合当前心理学教材的变量、控制、被试设计、信号检测等主题。

不能原样保留的内容包括：默认编程例子、每次解释结尾必须同时有回忆问题和应用任务、强制公开误区分类、通过其他技能写入永久弱点记录。没有足够证据时，只保留待检验的困难假设；不能从一句“没懂”直接认定存在深层误区。

### 2.4 anything-to-course：课程生成与对话辅导是两种入口

它不仅总结资料，还生成能力目标、先修关系、课程文件、练习、分离的答案文件和复习日程。对准备课程和有明确范围的复习活动很有用。

但 study-mode 明确把“只提醒一下”转成提取练习，并要求创建 study-log.md、按自己的规则安排复习。我们已经有学习状态和 RetentionScheduler，不应再建第二份日志或用技能里的固定日期替代现有算法。若后续使用，应将其作为练习设计参考，实际到期项目和掌握证据仍从宿主服务读取。

### 2.5 book-tutor：教材方向相近，不代表可以照搬

它通过 CLAUDE.md 绑定书名、章节、源文件、进度和概念笔记路径，适用于个人文件工作区。我们已有课程文档版本绑定、章节导航、会话状态和教材核验，应使用这些可信数据，不让模型自行读取用户任意配置路径或维护另一个 vault。

GitHub 仓库元数据的 license 为 null，递归树中没有根许可证或 book-tutor 许可证；发现的 skills/clean-apex/LICENSE 只位于另一个技能目录，不能据此认定 book-tutor 获得同样授权。当前结论是“未找到适用许可证”，不是断言作者禁止一切使用。

### 2.6 Hermes：中文说明可读，工具名字不等于已有实现

抽查 agent-socratic-tutor、agent-question-explanation、agent-mistake-review、agent-weakness-boost 与大学 Python 技能，重点阅读了前两项的完整契约。优点包括一次只问一个关键问题、连续追问导致挫败时增加帮助、解释每一步依据。

它同时声明平台 entitlement、workflow、practice、memory 工具。读取 SKILL.md 不会在我们项目中自动出现这些工具；公开目录的 validate/pack 脚本也不等于这些教学工作流的实现。无平台时输出三轮问答脚本或学生不回复继续提示等 fallback，也不适合当前需要真实等待学生的活动边界。不要把元数据里的 curated/recommended 当作已验证的教学效果。

## 3. 本项目已经有什么，缺口在哪里

以下为当前工作区静态发现；没有更改环境变量或重启服务，不能据此断言某条带开关的路径正在生产运行。

| 位置 | 已有能力 | 接入影响 |
| --- | --- | --- |
| agents/tools/skill_tools.py | _skills / _read / ReadSkillTool；限定技能根目录、路径和大小，支持 allowed_skills | 可以复用读取，不需要通用插件框架 |
| agents/tools/first_wave_runtime.py:91 | skill_catalog；按课程展示允许技能 | 新技能必须进入清单，否则模型不知道用途 |
| agents/agent_loop_service.py:507、561、731 | 根目录绑定、清单注入、运行时白名单 | 目前心理学只允许 reasoning-diagrams / experimental-design；只放文件不够 |
| agents/teaching_strategy.py | 依据模式、困难、作答结果、上次策略和交互边界形成 TeachingStrategyPlan | 用已有 strategy id 选适配技能，不另做一个意图判别器 |
| knowledge/teaching_strategies.json | 已有 13 项教学策略及 moves/停止条件 | 候选技能是策略的详细教学说明，不新增平行策略体系 |
| agents/teaching_policy.py | direct/guided/practice/review 及用户显式教法边界 | 全局强制苏格拉底式、强制每轮练习会与此冲突 |
| agents/response_composition.py、response_composition_adapters.py | 按既定策略/任务生成内容块、核验 claims 与 source_ids | 新技能的 Markdown/教师文件输出不能覆盖 JSON 内容协议 |
| agents/agent_loop.py:295、562 | 在模型调用时附加 ResponseComposer.instructions | 附加技能必须兼容实际生成阶段，不能只挂到前期探索提示里 |
| tests/test_first_wave_integration.py:186 | 已测课程技能清单和执行许可一致性 | 沿用测试补新技能可见性和拒绝行为 |

另外两个容易忽视的细节：

1. _skills 只枚举根目录的直接子目录；yugash 和 Hermes 的多层目录结构不能整仓放入就期待被发现。应按现有目录约定整理首批技能及其必要 references。
2. skill_catalog 当前摘要取第一个非空、非标题/分隔线行。对标准 YAML front matter，这通常是 name: 行，而不是 description；多行 description 也不会正确展示。若接入新技能，需要同时解决摘要提取，否则只展示名称仍不足以让模型正确选择。

之前 2026-11-03 的 TEACHER_LIKE_RESPONSES_RESEARCH_20261103.md 已指出固定内容块会影响表达灵活性。本轮与之相容：技能可以改变某块内的解释质量，但不能靠技能提示词绕过已经确定的 ResponsePlan 或声称解决全部结构问题。先做窄场景对照，不顺手重构整条生成链。

## 4. 三种接入方式

| 方式 | 结果与代价 | 判断 |
| --- | --- | --- |
| 在 Codex/OpenCode 全局安装六套技能 | 改变开发助手的行为；不会自动改变学生 /api/chat 的后端上下文 | 不满足本次目标 |
| 每轮注入所有 SKILL.md | 文字多、模式与输出规则互相冲突，工具/存储要求超出现有契约 | 不推荐 |
| 固定版本、选少量适配技能，按现有教学策略读取 | 复用现有权限、状态、检索、生成和核验；便于知道哪种方法生效 | 推荐 |

## 5. 推荐首批实现范围（尚未实施）

### 5.1 四个场景，复用现有策略

| 学生输入/状态 | 适配内容 | 现有策略衔接 | 必须保留的行为 |
| --- | --- | --- | --- |
| “没懂，换个讲法，不要问我” | simplify-topic 的单一类比、类比边界、回到正式概念 | scaffolding / worked_example，读取已有困难信号 | 实际换表示；不新增题目，不猜学习风格 |
| “只提示下一步” | ai-socratic-tutor 的单步提示、渐进披露 | hint / socratic_questioning | 不泄露后续解法；只有允许互动才提出一个问题 |
| 学生提交具体解释或推理 | misconception-detector 的错误模型对照、纠正依据 | direct_correction / guided_revision / conceptual_comparison | 区分执行失误与概念问题；没有证据不贴误区标签 |
| 有学生尝试和已提供/核验参考解答 | ai-solution-study 的有效部分＋第一处实质差异 | guided_revision | 不把不同解法当错误；参考解答未取得则不编造 |

普通“解释一下”继续直接回应。学生明确改口要求完整解释时，撤去提示模式约束；不是要求学生记住某个退出咒语。ai-novice/学生教 AI 可作为后续明确选择的 self_explanation 活动，首批不增加入口或 UI。

### 5.2 接入步骤与影响面

1. 把首批适配版本放入项目管理的技能目录，记录上游 commit、许可证、保留/修改了哪些规则；不在运行时拉最新分支。MIT 保留版权与许可；使用 Anthropic 内容时保留适用 Apache-2.0 LICENSE/NOTICE 和修改说明。
2. 复用现有读取与课程授权，统一维护技能清单和允许读取列表，补正确的用途摘要。不要因为加入教学技能而开放 workspace 写权限、任意网络或 Hermes 平台工具。
3. 在现有 TeachingStrategyPlan 已确定后，用模式、策略和交互边界选择至多一个主要教学说明；一般问答不必强制选技能。不要再从原始用户文字建立第二套独立分类器。
4. 选定技能只读本地文件；宿主在现有生成上下文中加载必要短段，或在已具备工具调用空间的路径使用 read_skill。对需要稳定生效的首批场景，推荐宿主按已定策略加载，避免额外消耗一次模型往返，也避免“模型没读技能”的不确定性。read_skill 仍可服务按需参考。
5. 把技能输出约定适配成当前正文/claims/content blocks；教材证据仍走 retrieve_course 和来源核验。技能不是教材来源，不能把技能文件计入 source_ids。
6. 在现有任务/回合 trace 中记录技能名、固定版本和选择原因，便于对照实际是否激活；不新建学生画像或学习日志。

预计核心影响：visualization/skills 的少量包、first_wave_runtime.py 的清单/摘要、agent_loop_service.py 的装配和白名单、teaching_strategy.py 的已有计划到说明的映射。若需要改变块类型或任务义务，再有针对性地改 response_composition_adapters.py / response_composition.py；不能把全部表达问题归因于“缺几个 skill”。

每一项应覆盖调用方、技能 references、许可证和现有测试夹具。前端一般可以沿用当前渲染，暂不新增工具商城或技能选择面板。

### 5.3 不得被外部技能覆盖的边界

- no_questions / hint_only / no_full_answer / 用户当前教法选择。
- 已有 pending question 的复用与真实等待；不因读取技能覆盖待答题。
- 学生、会话、课程、文档版本和来源隔离。
- 原文核验、生成例子/类比与教材事实的区分；示例不冒充真实实验结果。
- 正式题目、评分、掌握度、学习路径与复习日程的宿主权威。
- 当前内容协议、取消/恢复/幂等和发布核验。

## 6. 验收：先证明对话行为改善

建议在已有 first-wave、教学策略、内容生成和多轮测试旁扩展一个小型合成案例集。首轮固定八组，使用同一课程、同一证据和相同模型设置比较当前版与候选版，先控制范围，不直接全量跑大规模真实模型评测。

| 案例 | 通过的可观察行为 |
| --- | --- |
| 直接问概念并要求不提问 | 直接讲清；无强制测验或迁移作业 |
| 连续反馈同一解释没懂 | 表示或切入点实际改变，类比边界清楚 |
| 明确只要一个提示 | 只推进下一步，正文和图解均不泄露完整答案 |
| 提示后改口要完整讲解 | 按新模式讲解，不被外部技能永久锁定 |
| 作答中部分正确、部分错误 | 指出有效部分，优先处理第一个关键缺口 |
| 使用不同但有效的解释路径 | 按论证评估，不以是否匹配参考措辞判错 |
| 已有待答题时插问 | 先答插问，保留原待答题和学习状态 |
| 教材来源不足或含误导指令 | 不伪造引用，不执行资料中的指令，不越权写状态 |

技术回归至少包括：课程清单与权限一致；YAML description 展示正确；多层上游目录整理后可读取；技能名称/相对路径不能越界；单轮只加载匹配说明；引用与 claims 合法；取消恢复后不会重复出题/重复计掌握。复用已有测试，不为纯文本包增加无意义的实现镜像测试。

教学质量先由人工盲评目标命中、理由解释、学生反馈利用、负担与停止边界。自动评分可辅助，不应把模型自评当作学习提升证据。主观“更像老师”和独立迁移表现是不同结论，需要分开记录。

## 7. 固定版本、许可与证据

| 仓库 | 本轮固定 commit | 许可核对 |
| --- | --- | --- |
| anthropics/k12-teacher-skills | 31fd6dbb0c07cb50bb3ce7f62a4135a393bd0e8c | Apache-2.0；根 LICENSE/NOTICE 与技能 LICENSE 已取得 |
| bstellato/ai-teaching-skills | 6d3f85726e7b0fedacc8a078e174161293777044 | MIT，已取得 LICENSE |
| lowwwbank/anything-to-course | f11bbf21572a9864759929946c2c3da6857e1744 | MIT，已取得 LICENSE |
| yugash007/edu-agent-skills | e75f44303570bb2eae37a8f7536c0358be2502ee | MIT，已取得 LICENSE |
| xixiaofinland/agent-skills | 6d98d5ba75f4bd50dda4a1f3f63c87a00e19cec8 | 未找到适用于 book-tutor 的许可证 |
| hezkvectory/hermes-edu-skills | b1c32d71bf70902f5dcc36cbe0a2dd9dbd728030 | MIT，已取得 LICENSE |

主要原始来源（均为作者仓库）：

- [Anthropic 四项技能](https://github.com/anthropics/k12-teacher-skills/tree/31fd6dbb0c07cb50bb3ce7f62a4135a393bd0e8c/plugin/skills)、[CFU 验证方法](https://github.com/anthropics/k12-teacher-skills/blob/31fd6dbb0c07cb50bb3ce7f62a4135a393bd0e8c/plugin/skills/k12-check-for-understanding/references/verification.md)、[评估方法](https://github.com/anthropics/k12-teacher-skills/blob/31fd6dbb0c07cb50bb3ce7f62a4135a393bd0e8c/evals/README.md)。
- [ai-socratic-tutor](https://github.com/bstellato/ai-teaching-skills/blob/6d3f85726e7b0fedacc8a078e174161293777044/ai-socratic-tutor/SKILL.md)、[ai-solution-study](https://github.com/bstellato/ai-teaching-skills/blob/6d3f85726e7b0fedacc8a078e174161293777044/ai-solution-study/SKILL.md)、[ai-novice](https://github.com/bstellato/ai-teaching-skills/blob/6d3f85726e7b0fedacc8a078e174161293777044/ai-novice/SKILL.md)。
- [anything-to-course 主技能](https://github.com/lowwwbank/anything-to-course/blob/f11bbf21572a9864759929946c2c3da6857e1744/SKILL.md)、[study-mode](https://github.com/lowwwbank/anything-to-course/blob/f11bbf21572a9864759929946c2c3da6857e1744/references/study-mode.md)。
- [simplify-topic](https://github.com/yugash007/edu-agent-skills/blob/e75f44303570bb2eae37a8f7536c0358be2502ee/skills/teaching/simplify-topic/SKILL.md)、[teach-concept](https://github.com/yugash007/edu-agent-skills/blob/e75f44303570bb2eae37a8f7536c0358be2502ee/skills/teaching/teach-concept/SKILL.md)、[misconception-detector](https://github.com/yugash007/edu-agent-skills/blob/e75f44303570bb2eae37a8f7536c0358be2502ee/skills/assessment/misconception-detector/SKILL.md)。
- [book-tutor](https://github.com/xixiaofinland/agent-skills/blob/6d98d5ba75f4bd50dda4a1f3f63c87a00e19cec8/skills/book-tutor/SKILL.md)。
- [Hermes 启发式讲解](https://github.com/hezkvectory/hermes-edu-skills/blob/b1c32d71bf70902f5dcc36cbe0a2dd9dbd728030/skills/learning-core/agent-socratic-tutor/SKILL.md)、[AI 讲题](https://github.com/hezkvectory/hermes-edu-skills/blob/b1c32d71bf70902f5dcc36cbe0a2dd9dbd728030/skills/learning-core/agent-question-explanation/SKILL.md)。

[source-audit.json](source-audit.json) 记录下载来源、commit、SHA-256、临时副本路径和本地核对文件哈希。上游文本只放系统临时目录；研究目录未复制无明确许可的 book-tutor 原文。

工具边界：使用 agent-reach 的 GitHub CLI 路由；GitHub connector 返回 Unknown tool 后改用公开网页、GitHub API 与 gh。匿名 API 限流后用已连接的 gh 只读访问；未运行上游安装器、教学 workflow 或仓库脚本，未调用付费模型。

## 8. 本轮交付与未做事项

已完成六源真实性、核心规则、许可证、依赖及项目接入点核对，提供首批适配范围和八组多轮验收建议。详细阅读首选 tutor/solution-study、simplify/teach/misconception、book-tutor、Hermes 两项及 Anthropic CFU 核心规则；其余下载文件主要用于目录、规则或许可证抽查，下载数量不代表逐条完成了全部技能评估。

本轮只新增调研报告与审计清单，未修改业务代码、现有计划、开关、依赖、模型配置或数据库；未安装任何技能、未运行应用或对照评测。当前工作区已有其他进行中的改动，本轮未覆盖这些文件。

实施应从少量适配技能和固定案例开始。原版强制提问、答案披露与存储规则若不改，会让当前对话更僵硬或绕过现有状态边界；静态调研不能替代运行验收。
