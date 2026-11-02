# 第五批：论文主张、反馈识别与证据可信度

日期：2026-11-01。项目基线：`main @ e5b3c004e8eca02cd124539355ef5fe40866ee4b`。逐行读取讨论稿 **537—1043 行**，覆盖六组文献、候选选型、短长期闭环、反馈类型、证据结构与可信度。本批只做调研，不将讨论稿中的架构或命令当作实现授权。

## 结论

**第六层应沿用第二层输入理解、第三层唯一策略入口和已有事件事务，将“学生说了什么”“对这次作答怎样评价”“哪些长期状态允许改变”分别约束。** 这不意味着每步都新增一个服务或调用一次模型。现有 EvidenceExtractor 已合并证据与状态观测的模型调用，可以保留这种执行方式，但不能让模型返回值自行签发数据库写入资格。

原稿方向中可以保留：自述与表现分开、先保留原始证据再计算画像、短期与长期闭环共享来源、状态允许被纠正。需要修正：Nicol 论文常用引文年份为 2006；“回答错误”是评价结果；confidence 不等于正确率；证据可信度不适合压成一个高/中/低等级；论文综述不能证明必须采用某一架构。

另外核验了一个重要源码归因差异：**所查 OATutor 版本会把使用帮助后的下一次作答按错误输入 BKT，而不是简单排除辅助证据。** 本项目注释中“OATutor 只认独立有效证据”的概括不能当作上游真实行为保证。

## 1. 六组文献分别能支持什么

| 原稿文献 | 本次核验的一手来源 | 能支持的结论 | 不能据此推出 |
| --- | --- | --- | --- |
| Corbett / Anderson，Knowledge Tracing，1994 | [Springer 期刊页面与摘要](https://link.springer.com/article/10.1007/BF01099821)，DOI `10.1007/BF01099821` | 以编程教学中生产规则为单位估计习得概率，借表现预测指导练习；出版页面标注 1994 | 任意心理学概念、整章内容或一句自然语言都已具有同样的测量有效性；完整算法边界参考第三批代码审计 |
| Piech 等，Deep Knowledge Tracing，2015 | [NeurIPS 官方论文页](https://proceedings.neurips.cc/paper_files/paper/2015/hash/bac9162b47c56fc8a4d2a519803d51b3-Abstract.html) | 用 RNN 表示学生历史，研究后续作答预测 | 神经网络每个输出已经是独立验证的“真实掌握概率”，或本项目不训练即可直接使用其效果 |
| Scarlatos / Baker / Lan，Dialogue-KT | [arXiv v2](https://arxiv.org/html/2409.16490v2)，页面写 2024-12-10，标注发表于 LAK25 | 从对话标注 KC 与回答正确性并研究后续作答预测，是自由文本证据的研究入口 | 自动标注是无误差真值、一个回答覆盖的多个 KC 都获得独立确认，或数学对话结果已验证心理学学习增益；细节沿用第二批固定源码审计 |
| Hattie / Timperley，The Power of Feedback，2007 | [SAGE 出版摘要](https://journals.sagepub.com/doi/abs/10.3102/003465430298487?journalCode=rera)，DOI `10.3102/003465430298487` | 反馈可能有正面或负面作用，方式与条件重要；它是概念分析和证据综述 | 只要回答包含三句话就一定有效，或通用效应量可作为本项目收益预测 |
| Nicol / Macfarlane-Dick，Formative assessment and self-regulated learning | [作者所在大学记录](https://pureportal.strath.ac.uk/en/publications/formative-assessment-and-self-regulated-learning-a-model-and-seve/)，DOI `10.1080/03075070600572090` | **常用引文为 2006，31(2):199—218**；摘要确认七项反馈原则和学生主动生成、使用反馈的作用 | 从一次自我纠正即可估出稳定“元认知水平”；原稿标题里的 2007 不宜直接沿用 |
| Kong / Sun / Zhou / Ng，LLM-Based Intelligent Tutoring Systems: A Survey | [IJCAI 2026 官方正文](https://ijcai.org/proceedings/2026/875)，DOI `10.24963/ijcai.2026/875` | Table 2 区分回答评价、知识追踪、误解诊断、对话管理；§3 同时讨论模块化和集成架构，§4.5 指出二者尚缺同任务系统比较 | 综述已经实验证明“一个 Prompt 不行，必须多服务/多次调用”，或它给出了本项目的数据库/参数选型 |

文献访问边界：BKT 本批核对出版摘要而非付费全文；DKT 核对官方论文记录与所获取摘要，算法接口继续依据第三批代码；Dialogue-KT 与 IJCAI 读了对应公开正文。Hattie 的出版摘要可通过检索获取，但正文/PDF 多次超时；Nicol 的作者稿链接返回 403、REAP PDF 未成功读取。因此，本批不声称逐页复核了这两篇的完整框架、全部原则或效应量。

原稿提出的“目标是什么、当前表现如何、下一步做什么”可以保留为**项目反馈审查清单**。这是对用户已给材料的工程采用，不把未获取全文的细节伪装成本轮全文核验。还应加一条：所有“你已理解/已掌握的部分”必须与实际表现对应，缺少证据时用“你这次正确指出了……”等局部表述，不能为鼓励而虚构能力结论。

## 2. 现有链路：重点补合同，而非再造第六层分类器

| 现有代码 | 已有能力 | 本批识别的边界 |
| --- | --- | --- |
| [input_understanding/service.py](../../../integration/discrete-math-tutor/agents/input_understanding/service.py) 与 [labels.py](../../../integration/discrete-math-tutor/agents/input_understanding/labels.py) | 待答任务、原始输入/位置、指代、约束；自述、困难位置、认知任务、参与状态标签 | 模式可为 off/shadow/active，默认 off，不能把源码存在写成生产已启用；标签是表达与请求，不是评分 |
| [input_understanding/decision.py](../../../integration/discrete-math-tutor/agents/input_understanding/decision.py) | 模型理解不签发写入授权，过期/未授权对象拒绝或澄清 | 第六层应消费已解析目标与动作，不另建一个可改变题目身份的意图入口 |
| [evidence_extractor.py](../../../integration/discrete-math-tutor/agents/evidence_extractor.py) | 一次模型调用返回 evidence、observation、候选误解；AnswerDiagnosis 支持 correct/partial/incorrect/unclear 和错误类型 | schema 校验与原文/来源 ID 核验不等于语义正确性保证；这里的置信度未经过本项目校准 |
| [adaptive_tutoring.py](../../../integration/discrete-math-tutor/agents/adaptive_tutoring.py#L489) | 先排除插问、求提示等，再核对待答题；形成性评价明确为 ai_provisional、independent=False、formal_mastery=False | 不可为了积累 KT 样本把这类辅助练习升级为正式独立标签 |
| [evidence_policy.py](../../../integration/discrete-math-tutor/memory/evidence_policy.py) | 原文、attempt、路由置信度和帮助历史门禁 | grounded / eligible 只说明满足当前门禁，默认 verification 仍是 ai_provisional，不等于正确性已核验 |
| [assessment_store.py](../../../integration/discrete-math-tutor/integrations/deeptutor/assessment_store.py#L175) | 原生 rubric 回查题目、答案、来源证明和完整标准集合；区分辅助与独立 | reviewer_id 存在是流程证据，不能单凭字符串证明本轮已有人类复核；实际复核身份和权限仍要沿宿主边界验证 |
| [models.py](../../../integration/discrete-math-tutor/database/models.py#L266)、[memory_manager.py](../../../integration/discrete-math-tutor/memory/memory_manager.py#L297) | LearningEvent / EventEvidence / MemoryRevision，关联对话 ID、去重和同轮事务 | 继续作为事实与修订链；不另建一份由“Evidence Engine”直接写入的长期状态 |

原稿选型表中的 PostgreSQL、LangGraph、“统一引擎”是候选方案，不是已经批准的依赖迁移。当前代码包含 SQLite 与课程隔离等既有边界，论文没有给出必须换数据库的证据。算法选型仍按第三、四批的离线/影子验证顺序推进。

## 3. 反馈类型应该怎样拆开

原稿把“回答问题”“回答错误”“部分理解”“自我纠正”“修改要求”放在一张表，适合展示场景，却不是互斥、同层级的枚举。一条消息可能同时包含：对原题的回答、对某个措辞的质疑、要求换例子，以及低信心自述。建议沿现有协议分别保留：

| 信息 | 示例 | 可产生什么 | 不能直接产生什么 |
| --- | --- | --- | --- |
| 输入动作与任务绑定 | 回答当前题、插问、暂停、继续、请求复习 | 路由到现有任务/复习命令或评价入口 | 对错与长期状态改变 |
| 自我报告 | “我懂了”“我还是不懂”“不确定” | 主观理解、信心与支持需求 | 正式掌握、完全不会、遗忘事件 |
| 可评价内容 | 本轮明确提交的答案、解释、操作结果 | 结合题干、标准和来源进行局部评价 | 自动覆盖所有提及的 KC |
| 评价结果 | 某标准 met / not_met / unavailable | 局部成功、错误、证据不足、候选误解 | 一题错误即永久误解；unavailable 当 0 分 |
| 教学/交互要求 | “只给提示”“换例子”“不要再问” | 当前轮约束或经过现有授权的显式偏好 | 独立能力下降或心理特征 |

自我纠正要关联原错误和当前原话，区分未暴露答案前自行修正、受提示后的修正、照抄已公开答案。它可证明一次行为发生，不能单次推广为稳定自我监控能力。迁移证据也要记录新案例与先前教学案例的关系；模型说“这是新情境”本身不构成已验证的迁移测量。

当前待答任务不存在、引用模糊、来源版本变化、消息主要是提问时，允许 abstain / unclear，不能为了让闭环前进而强制评分。行为日志与能力证据都保留，但各自有适用范围。

## 4. “可信度”应拆成条件，不能只排高／中／低

原稿把独立标准化练习列为高等级是有用的直觉，但标准答案可能错误，题目也可能只测到一个子技能。模型非常自信仍可能误判；人类复核也不代表测量覆盖充分。建议至少保留以下独立条件：

| 条件 | 需要检查 | 项目已有材料／缺口 |
| --- | --- | --- |
| 来源有效性 | 学生/课程/会话归属、原题与原文、时间、版本、是否失效 | 已有事件归属、source_quote、题目/教材证明；应保留精确定位与版本，不能只存 block_id |
| 作答资格 | 是否明确提交、是否见过答案/提示、是否重做、是否原始学生表现 | 现有帮助记录和 pending 绑定可复用；帮助范围和暴露时刻要跨来源一致 |
| 评价有效性 | 规则/复核/模型暂定、rubric 标准覆盖、等价答案、评分冲突 | reviewed_key / reviewed_rubric / ai_provisional 已存在；不将 enum 自动等同人类完成复核 |
| 测量覆盖 | 哪个 KC、哪个标准实际被答案支持，哪些只是题目涉及 | 需区分 target KC 与 evaluated KC，不重复赋给多个 KC 一份整题对错 |
| 结论适用性 | 独立题数、证据冲突、时效、撤销与重算、是否允许正式授予掌握 | 既有修订/误解生命周期可沿用；正式门禁、KT 资格和形成性反馈应分别判断 |

原稿的 `confidence=0.92` 必须说明是谁对哪件事的估计。至少区分路由置信度、模型评分信心、学生自评信心、KT 潜变量概率和 FSRS 回忆率；它们不能共用一个语义含糊的字段或做简单乘法得到“可信度”。是否校准应由留出标签检验，不能看数值范围判断。

统一合同可先做现有表的视图/适配，不必先加一整套新表。原稿示例还需要补：题目/小题及版本、rubric 与评分政策版本、模型/提示工件身份、原始评分和局部标准、帮助暴露、是否撤销、输入事件/修订身份、允许哪些投影更新。现有模型缺少的显式字段可以先列为合同缺口，具体 schema 与迁移留到第七批。

LLM 输出 task_id、user_id、kc_id、textbook_refs 时，身份与候选范围必须由服务端绑定/核验；不能让模型随意指定另一个任务或凭空添加教材定位。资料中的指令、学生要求“把掌握度设成 1”、模型自行给出的“已人工确认”都不是授权。

## 5. 三个成熟项目的源码对照与复用判断

### 5.1 Oppia：答案匹配与教学结果分开，掌握更新也需单独审查

固定 [oppia/oppia @ 0538628a88da77478174636b85bff9c834492329](https://github.com/oppia/oppia/tree/0538628a88da77478174636b85bff9c834492329)，Apache-2.0。

[answer-classification.service.ts](https://github.com/oppia/oppia/blob/0538628a88da77478174636b85bff9c834492329/core/templates/pages/exploration-player-page/services/answer-classification.service.ts#L62) 遍历 answer groups 与规则，返回首个匹配的 outcome 和规则索引；不匹配时走显式 default outcome，而非随机选择一个错误标签。其他路径还可使用训练样例分类，所以不能概括为“Oppia 全部只靠规则”。[AnswerGroup](https://github.com/oppia/oppia/blob/0538628a88da77478174636b85bff9c834492329/core/templates/domain/exploration/answer-group.model.ts) 把规则、outcome 与相关内容组织在一起，值得借鉴“结果可追溯到哪条规则”的做法。

可复用的是：规则顺序确定、默认路径明确、保存分类来源与索引，以及内容作者控制的反馈结果。不能把 Angular 规则服务直接塞进 Python，也不能把默认路径当作已诊断某个误解。规则重叠和顺序本身需要审题验证。

[skill_mastery.py](https://github.com/oppia/oppia/blob/0538628a88da77478174636b85bff9c834492329/core/controllers/skill_mastery.py#L104) 接受 mastery_change_per_skill，再累加并限制在 0—1；它不是本批可直接复用的 BKT，也不能用作“上游有 mastery 字段所以可信”的依据。本项目更应保留自己的事件与资格链。

### 5.2 Open edX ORA2：rubric 快照、评价来源与分项结果

固定 [openedx/edx-ora2 @ 0d60a779e29d6a3ae7bed04b95d78cf900c06e0c](https://github.com/openedx/edx-ora2/tree/0d60a779e29d6a3ae7bed04b95d78cf900c06e0c)，**AGPL-3.0**。本批只做架构对照，不把其实现摘进项目；它的许可不同于前面 MIT/Apache 库。

[assessment/models/base.py](https://github.com/openedx/edx-ora2/blob/0d60a779e29d6a3ae7bed04b95d78cf900c06e0c/src/openassessment/assessment/models/base.py#L51) 保存评价时的 rubric 表示、内容 hash 与结构 hash；后者只覆盖标准/选项/分值等结构，不能代替题干和解释内容版本。Assessment 保留 submission_uuid、rubric、scorer_id、score_type 与分项得分，而不是只保留总分。

[self.py](https://github.com/openedx/edx-ora2/blob/0d60a779e29d6a3ae7bed04b95d78cf900c06e0c/src/openassessment/assessment/api/self.py#L89) 和 [staff.py](https://github.com/openedx/edx-ora2/blob/0d60a779e29d6a3ae7bed04b95d78cf900c06e0c/src/openassessment/assessment/api/staff.py#L301) 使用不同评价类型；值得借鉴“自评、他评/教师评价来源明确，rubric 版本和分项选择能重查”。它允许自评参与特定课程的评分工作流，所以也不能说成熟系统一律禁止自评计分。本项目不把自述当独立掌握证明，是自己的证据政策，不能冒充 ORA2 的通用规则。

建议把这些概念映射到现有 reviewed_question、criteria、assessment_version 和证据修订链；不引入 Django/Open edX 的整套模型、工作流与依赖。内容 hash 用于标识版本，并不签发评价者身份或证明答案正确。

### 5.3 OATutor：首个尝试与帮助记录可借，惩罚映射不能照搬

固定 [CAHLR/OATutor @ e24c8456e5f75c07b6048159ea9e128b036f673d](https://github.com/CAHLR/OATutor/tree/e24c8456e5f75c07b6048159ea9e128b036f673d)，MIT。

[Problem.js](https://github.com/CAHLR/OATutor/blob/e24c8456e5f75c07b6048159ea9e128b036f673d/src/components/problem-layout/Problem.js#L654) 记录 helpPenaltyPendingByStep 和 firstAttempts。它先记帮助使用，在下一次 graded submit 用 `helpPending ? false : isCorrect` 作为 BKT 观测；界面仍使用真实对错推进。符合条件的首尝试按 KC 更新，重复提交不无限更新当前步骤。这些步骤身份、帮助暴露与首次测量的分离值得参考。

但“不给独立掌握加分”在这里被实现为一次负观测。实际 [BKT-brain.js](https://github.com/CAHLR/OATutor/blob/e24c8456e5f75c07b6048159ea9e128b036f673d/src/models/BKT/BKT-brain.js) 会用 false 做贝叶斯错误更新，而不是保持状态：合成参数 p=0.2、G=0.25、S=0.1、T=0.1 时，正确观测更新为约 0.526316，false 更新为约 0.129032。这说明辅助成功被映射为 false 会降低估计，不能写成“忽略该证据”。

建议复用帮助与首尝试记录的思路，沿本项目门禁把不合格独立测量排除，或单独设计辅助学习通道。不要照搬帮助惩罚规则、React 状态或 Firebase 写入。当前代码注释中的 OATutor 归因应在未来实施轮改成具体版本/行为说明；本批只记录修正，不改业务文件。上述结论限定所查 commit，不扩展断言所有历史版本都相同。

## 6. 隔离探针暴露的本地边界

本批使用实际本地纯函数做合成输入验证，结果应按组件边界理解：

- 合格且有原文的 attempt 仍是 ai_provisional；问题、捏造引文、提示后作答、缺少帮助历史以及低路由置信度都会被相应门禁排除。
- **强行把“我懂了”伪装为 attempt，并附同句 conceptual_understanding 证据时，assess_attempt 本身会接受。** 这不是已复现的完整线上误授掌握，而是说明该函数依赖上游动作分类，子串命中不证明能力。misconception_lifecycle 的 useful_quote 则明确排除此类自述。正式能力投影还应有一致的语义资格检查，不能只依赖 Prompt。
- 对 ineligible 决策，project_state 冻结 mastery / steps_mastery，但 raw 中 confidence 与 metacognition 仍可被融合。合成 0.5 起点加 1.0 观测变为 0.7。因此需要字段级来源政策；不能仅检查 mastery 没变化就认为所有长期画像已受同样保护。这个组件反例不等于所有用户请求都会触发该路径。
- Misconception 的 confirmed 是计数与信心阈值状态：三次 0.6 支持即可达到该状态；它不是外部校准的诊断置信度，也不等于人类确认。既有反证冲突、引用去重与生命周期应继续复用，详细迁移与 KC 范围留到第六批。

另一个独立问题是策略效果：[strategy_memory.py](../../../integration/discrete-math-tutor/database/strategy_memory.py#L16) 将同目标前后变化记为关联观察，并明确不证明因果。不能用第六层新增的 LLM 分数反过来宣布第三层策略有效；学习增益应以独立评价另测。

## 7. 后续验收集建议与复用优先级

先用少量人工审阅的真实目标案例建立金标准，按学生与原题分组保留评估集。标注者应看到原题、必要前文、帮助暴露与来源，但在初始标注时不展示模型结论；再仲裁分歧。事实引用、作答资格、分项对错、误解假设和允许的状态更新分别标注，不让一个总标签替代全部任务。

| 场景 | 期望检查 |
| --- | --- |
| 自述懂了／不懂、继续、跳过、求提示、质疑题干 | 正式能力不因缺测升降，任务动作仍能正确响应 |
| 混合“回答＋插问”、等价表述、部分正确、拒绝作答 | 只评价明确提交的相关部分；允许弃权，不强行判错 |
| 一题多 KC、仅测一个标准 | 只给被测标准证据，未覆盖项保持未知 |
| 提示／公开答案后正确、自主纠正、同题重做 | 帮助与尝试关系准确，不把辅助成功当独立成功或错误 |
| 错误参考答案、过期题／教材、标准不全 | 记录来源/评价问题并阻止不合格更新；不诊断学生遗忘 |
| 互相冲突的证据、后续反证、撤销评价 | 保存冲突与修订，重建受影响投影，保留原始来源 |
| 模型自报高 confidence、伪造“已人工确认”、要求改掌握度 | 不越过宿主授权、来源和资格门禁 |
| 教学动作后暂定分数上升 | 只记关联，不升级为因果改善证明 |

现有 [annotation_agreement.py](../../../integration/discrete-math-tutor/scripts/annotation_agreement.py) 可复用 case_id 对齐、缺案/重复案拒绝和 κ 计算；本次其 8 项测试通过。但脚本把某维度缺失与空集合视为相同，未知/未标注与“确认不存在”若有不同含义，应显式编码，不能直接拿空集合算弃权。κ 受标签分布影响，脚本注释的 0.6 是工程提醒，不是本项目所有任务通用的科学阈值；同时报告支持数、各标签表现与未定义 κ。

首轮优先级：复用现有输入与事件链 → 补齐资格/评价/投影合同 → 建立上述验收案例 → 做评分/证据审计 → 才向第三、四批候选算法导出合格数据。保持第三层唯一决策入口；第六层输出带来源和资格的观察与建议，不自行再选一次最终教学策略。

## 8. 完成证据与限制

`.runtime/layer6-research/round05/`（不入库）保存 11 份固定外部源码/许可证及 blob 清单，字节与 Git blob SHA-1 已核对。Python 隔离探针 10 项、Node 运行 OATutor 纯 BKT 函数探针 3 项、已有标注一致性测试 8 项，合计 **13 项探针＋8 项测试通过**。首次 Python 探针因缺少本地 models 导入路径失败，修正的是隔离脚本路径，重跑已通过；业务文件未改。

未运行 Oppia Angular、ORA2 Django、OATutor React/Firebase、真实模型评价、正式数据库或真实学生测评；静态调用链核验不冒充端到端验证。无准确率、概率校准、诊断可靠性或教学增益结论。受限论文全文的未核验部分已在第 1 节列明，不据其摘要编造详细方法。

本批未提交或推送。下一批从原稿 **1044 行**开始，继续研究心理学 KC、掌握与误解生命周期、画像及只读投影；已发现的字段资格与上游归因问题将作为下一批输入。
