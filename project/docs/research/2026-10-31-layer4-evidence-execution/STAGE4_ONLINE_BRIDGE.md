# 第四步：现有回答流程接线与隔离回归

日期：2026-11-01。基础提交：`fd66987`。分支：`codex/layer4-contract-baseline-20261031`。

## 本次完成什么

将第三步的只读对象读取接到现有`CourseSearch`，由原有`retrieve_course → CourseSearch → Q2选证 → 回答与发布核对`调用链消费。原Agent Loop、TaskService、发布门禁、前端、数据库和教学策略文件没有修改。主工作区仍在`94ba9ca`且有另一窗口的文档修改，本批未合并主工作区、未重启或替换当前运行服务。

普通单一概念问题保留原路径。比较、多对象问题复用已有CoverageNavigator的逐项选证、语义核验、均衡保留和有界补查，不再另写一套在线覆盖器。第三步execute_requirements内部契约保留，但这次在线接线直接使用已有发布门禁消费的coverage_report和retrieval_requirements，避免维护两套结果状态。

## 对象请求如何处理

1. 只从真实用户问题识别本教材表格/公式稳定ID，去重后最多两个。未新增前端按钮或让模型任意读取文件路径。
2. 复用第三步ObjectReadRequest/read_object，核对当前PDF版本、原始DOCX、结构化原文及表格/OMML。来源补齐现有Q2需要的文件、小节、块范围和资产字段。
3. 调用现有CourseSearch.select与choose_evidence，不跳过Q2原文存在性、范围、版本与模型选证。固定教材模式下也要求模型选证，不以规则摘要代替对象核验。
4. 用选证后的同文档、版本、小节、原块以及真实字符范围检查目标对象是否完整取得；邻文、部分对象、跨版本、越界范围、伪造引句都不能代替原对象。单轮结果预算不足时明确失败。
5. 如果任一明确对象不完整，本轮对象结果整体撤下，coverage_report保留缺口，不改用相似教材语义检索。原始公式结构仍不等于已经理解公式，不传递“已看过像素”的假标记。
6. 完整取证时为每个对象标记retrieval_requirements，交给既有发布门禁检查回答是否分别引用两侧。模型只引用一侧时仍会被原门禁拦截；公共门禁代码未改。

对象ID本身不授予新的账号权限。该路径仍是原教材工具的内部检索分支，不增加公开路由；原工具/任务授权、取消与执行预算继续由既有入口负责。旧版本原件或读取异常向上传播，禁止静默回退。

`question_interjection`作为Agent Loop、选区与CourseSearch共用的识别函数，也接纳明确对象问题，使之按本轮插问读取；不把这次提问登记为教学目标推进。当前教学目标保持原值。

## 自然问法的逐项取证

原先CoverageNavigator只在LightRAGNavigator接入时安装。本次在默认本地路径、且已有requirements_for能明确拆出必要对象时，同样接入既有覆盖器。例如“第二章的自变量和因变量有什么区别？”将逐项取证；每项首次查询一次，缺证最多补一次，通过已有Q2语义选证后才标记该项覆盖。

本地路径的逐项结果缓存按同轮复用，不合并后再次全局选证而丢掉另一侧；缺少因变量时保留缺侧报告。普通“什么是自变量？”不增加这层模型调用。显式注入后端与LightRAG原有行为保持，未擅自扩大到所有插件后端。

这里没有宣称任意复杂自然问法都能拆解：沿用现有明确章/比较句法与最多三个对象的预算。后续第三层可以传更明确的需求；本次不重写意图识别或教学策略。

## 验证结果

同一最终代码运行**145项测试通过**。范围覆盖第四层前序契约/采集/对象读取、新增13项在线桥接用例、已有CourseSearch与LightRAG覆盖、首批只读工具与接线，以及输入理解集成。

新增验证包括：明确对象跳过旧课程目标但不推进；选证只调用一次；原件失败不得回退；取消后不返回；预算不足拒绝；邻文、部分内容、旧版本、越界和伪造范围拒绝；对象插问到达共同入口；两对象标记到达既有双方引用门禁；本地自然比较保留缺侧及缓存；普通定义不增加覆盖调用；当前课程不匹配时在读取前拒绝。

首轮82项中的3个错误为测试夹具缺少新来源元数据、Mock没有实现可迭代calls；按实际接口补齐夹具后通过。进一步补共同插问入口、范围校验、双方引用标记与课程范围后，最终145项全部通过。失败/中间日志未覆盖，未放宽生产断言。

另执行`accept_layer4_object_bridge.py`，使用冻结v2中的**12个真实表格/公式对象**，实际经过原DOCX/PDF读取、现有Q2候选与坐标核验；选证LLM使用标明的协议夹具，未调用外部模型、未生成答案。

| 真实接线检查 | 数量 | 含义 |
| --- | ---: | --- |
| verified_original_range | 5 | 原对象全部文字范围通过既有Q2核验；不是生成答案语义通过 |
| withheld_incomplete_object | 7 | 对象本身无法完整映射，撤下结果；不以邻文或相似文本代替 |
| 非预期异常 | 0 | 明确对象没有回退到语义后端 |

第三步48/48统计的是原块/资产是否找到；本轮5/12统计的是更严格的对象完整原文范围通过，二者不可混成同一指标或宣称性能倒退。通过的为5个表格，拦截的为1个表格和6个公式；原来7个未精确定位对象在此仍受到限制，本轮没有“修好全部公式高亮”。

真实接线检查执行前后教材快照、原索引不变，执行源码指纹一致。详细逐例摘要、原产物hash和测试日志身份见`STAGE4_BRIDGE_SUMMARY.json`；完整产物在应用`.runtime/layer4-stage4/object-bridge-verified.json`，测试日志`.runtime/layer4-stage4/tests-verified.log`。

## 复现

在本worktree应用目录运行，检查脚本输出必须为新文件：

```powershell
$layer4Python='E:/项目/heart/project/integration/discrete-math-tutor/.venv-runtime/Scripts/python.exe'
& $layer4Python -B -X utf8 -m unittest tests.test_layer4_online_bridge tests.test_layer4_stage3 tests.test_evidence_execution tests.test_layer4_collection tests.test_layer4_benchmark tests.test_course_search_bridge tests.test_lightrag_coverage tests.test_first_wave_tools tests.test_first_wave_integration tests.test_input_understanding_integration -v
& $layer4Python -B -X utf8 scripts/accept_layer4_object_bridge.py --data tests/data/layer4_textbook_v2.json --output .runtime/layer4-stage4/new-object-bridge.json
```

## 集成与下一步

本批稳定提交依赖前三阶段分支提交，可由集成负责人按顺序合入；不要只摘CourseSearch改动而漏掉对象读取和契约。没有复制其他窗口的未提交代码。

合入后需使用隔离账户验证自然问法的真实模型选证/生成/发布、固定教材索引启用状态与浏览器引用跳转，再决定是否重启正式服务。当前12例是默认原件/live定位模式的隔离检查，不是固定索引、流式问答或页面验收。7个对象需要后续像素读取/公式原页对齐，当前会诚实返回缺证。

本批只复用项目已有代码和接口，无外部源码复制、无新增依赖或许可证变更。未发送学生数据，也未调用DeepSeek；测试结果不证明模型解释正确或完整系统已上线。
