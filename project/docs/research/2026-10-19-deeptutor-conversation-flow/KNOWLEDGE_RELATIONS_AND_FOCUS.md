# DeepTutor 知识关系与教学重点源码调查

日期：2026-10-20。范围：本机 `D:/deeptutor` 的学习路径生成、目标关系、状态返回、复习排序及相关前端。本文记录已有实现和候选借鉴方案，不将方案标为已实现。

## 核心结论

DeepTutor 通过“目标→模块能力→知识点”的结构帮助组织学习，支持显式先修关系和来源关联，但本次源码中的先修边仍是结构元数据，不控制学习解锁或检索。没有在本次核查范围内发现统一的教材重要度/考试重点评分器。复习 priority 是复习紧迫性，不能用作教材重点。

## 确认的源码机制

| 机制 | 源码 | 已实现行为与边界 |
| --- | --- | --- |
| 目标驱动路线 | `learning/prompts/zh.yaml::topic`、`learning/topic_generation.py` | 提示模型按主题、学习目的地组织模块，模块必须写出可观察能力 objective，而不只是名词列表；提示“清晰先修关系”不等于必然生成显式边 |
| 全材料视图 | `topic_generation.py::_source_payload/_knowledge_base_inventory/_coverage_report` | 资料目录清单与有界摘录共同输入，报告模块关联材料；源码明确少量相关段落不能代表整个知识库。覆盖报告不证明每章每个概念已教学或核验 |
| 显式关系 | `learning/models.py::KnowledgePoint` | prerequisite_ids 保存先修目标；topic_source_ids 保存计划设计来源，不是事实正确性或访问授权证明 |
| 关系解析与校验 | `learning/objective_relations.py` | client_ref/prerequisite_refs 映射为持久ID；去重、未知目标/来源、自依赖、循环依赖校验。文件顶部明确关系暂不控制 learning/retrieval |
| 局部调整关系 | `capabilities/mastery/tools.py::MasteryReviseTool` | 删除仍被依赖的目标会拒绝；重写新ID时更新依赖引用，防止悬空关系；模块能力限定局部改动边界 |
| 每轮路径上下文 | `tools.py::MasteryStatusTool`、`learning/policy.py::map_summary` | 返回学习目标、资料、模块能力、知识点类型、状态、先修ID等，供导师决定讲解。模型拥有关系数据不等于每轮必然解释这些关系 |
| 下一动作 | `learning/policy.py::next_objective` | 优先待答题、到期复习，再按module.order和点内顺序找未掌握目标，支持延后；未按先修图拓扑调度 |
| 学生当前重点 | `learning/scheduler.py` | 根据遗忘风险、逾期、错误记录和类型生成复习任务及reason；重点是当前需要复习，不是考试频率或学科重要性 |
| 可见学习结构 | `web/components/space/learning/ModuleOutline.tsx`、`LearningBoard.tsx` | 模块能力和目标卡呈现学习结构；本次 prerequisite_ids 前端检索主要命中类型及编辑字段透传，不能宣称已有完整先修图可视化 |
| 划重点 | `capabilities/reading/prompts/zh/reading.yaml` | reader_annotate 在学生要求时做持久标注；这不是自动计算全书知识重要度 |

## 对我们项目的具体借鉴

1. **先呈现结构与用途**：Q5 计划保留模块能力句，每次新目标注入当前模块、相关已学目标及后续用途；Q3 用自然语言解释衔接。无需先开发图形地图。
2. **优先迁入关系实现**：复用 objective_relations 的引用解析、DAG校验与修改保护，适配现有路径ID和来源ID。我们当前仅有 prerequisite_ids 字段，不等于已经具有有效关系图。
3. **区分路线生成入口**：上游 topic 草稿生成的输出示例主要是模块和知识点；mastery_build 才显式提供 client_ref/prerequisite_refs。实施时统一目标身份分配和关系写入，不能只复制提示词中的“先修”二字。
4. **关系分别验证**：依赖、对比、例证和应用关系各有含义。LightRAG 抽取的实体边先回原文确认，再作为教学关联候选，不能批量转成先修边。
5. **重点提供理由**：区分教材明确强调、支撑当前目标、学生薄弱/到期复习；考试重点仅在有教学大纲、教师或试题依据时显示。不要用图谱连接度或相似度分数直接排名重点。
6. **最早可用体验**：开始模块说明学习目的，转入新知识点简短回连前知，讲解结尾按需总结核心与易混点；不是每轮强制重复模板。对相关知识未讲或学生卡住，提供必要补讲；普通讲解不强制测验。

第1/2/3项可纳入 Q5 路径与 Q3上下文接线；第4项由LightRAG提供候选、Q2核验原文；第5/6项需增加显式教学输出和验收要求。以上是本项目候选改造，不能写成DeepTutor现成完整实现。

## 核查与验证

在本项目 `.venv-deeptutor` 运行上游原测试，`PYTHONPATH=D:/deeptutor`、禁用字节码与pytest cache，临时目录和DEEPTUTOR_HOME均指向本项目隔离 `.runtime`：

`python -B -m pytest -p pytest_asyncio.plugin -p no:cacheprovider deeptutor/learning/tests/test_objective_relations.py deeptutor/learning/tests/test_policy.py -q --basetemp <隔离目录>`

结果：**40 passed，0.69s**。覆盖关系有效性和推进策略，不是模型生成关系的准确率或页面体验验证。首次未显式加载 pytest_asyncio 插件导致配置项错误，未运行测试；补齐插件后完整重跑通过。没有修改上游源码、执行真实模型、验证浏览器或修改本项目业务链路。
