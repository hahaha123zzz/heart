# 第三步：原始对象直读与逐项证据覆盖

日期：2026-10-31。基础提交：`2a5780f`。继续使用独立分支`codex/layer4-contract-baseline-20261031`。

## 实施边界与接口

本批落实第二步已确认的后续方案：明确表格/公式对象先直读，复合需求分开召回，缺证必须保留。没有改公共Agent Loop、TaskService、发布门禁、第三层策略、学生数据库或前端。没有增加依赖，也没有替换教材解析器、embedding或重排模型。

### 1. 原始对象读取

`knowledge/evidence_objects.py`提供`ObjectReadRequest`与`read_object(request)`；参数schema另见`object-read-v1.schema.json`。

必填：`document_id`、当前PDF SHA256 `version`、`object_id`、`kind`（`table`或`formula`）。表格ID为`experimental-psychology-3:chapter-XX:bN`，公式使用原登记的`experimental-psychology-3:chapter-XX:omml-NNN`。不接受任意文件路径。

读取过程核对课程登记、PDF当前hash、章节DOCX当前hash、结构化文件的源身份；再用原导入器的序列化逐块核对原DOCX。表格返回真实二维单元格；公式按原DOCX中的全局顺序及所在块核对OMML字节，拒绝改名、错位、篡改及越出章节的路径。相邻最多前后一块仅在同小节内扩展。结束时再次核对源文件身份。

返回`payload`、最多三个块的`SourceRef`、只读scope及明确限制。每个来源单独调用现有LiveCitationIndex定位：成功才给exact与rects，不能定位则保留unlocated和空rects；不使用邻文坐标冒充公式框。来源携带实际原文交集、当前结构化文件hash、原DOCX hash和对象ID。

公式payload为原始OMML及其hash，`semantic_verified=false`，`model_saw_pixels=false`；**没有声称公式含义已核验、已识别为可靠LaTeX或已看过PDF像素**。PDF段落文字能唯一匹配也不代表整个公式结构语义正确。

该内部接口只提供教材对象读取，不是新的公开工具权限入口。未来接公开入口时，必须先检查任务和课程授权；不能仅凭用户传来的document_id就授予读取权限。read_object自己核对的是对象真实性和版本，不执行学生身份鉴权。

### 2. 逐项执行与覆盖

`agents/tools/evidence_requirements.py`提供`execute_requirements(request, retrieve=..., verify_support=..., check_cancelled=...)`，复用第一阶段EvidenceRequest/EvidencePackage，无新增数据存储。

调用方必须提供两类回调：按当前需求返回候选SourceRef的`retrieve`，以及核验该来源是否真正支持该项需求的`verify_support`。**不能将verify_support写成“有结果就True”或仅检查分数。** 本批没有偷偷实现一个等同命中的默认语义验证器。

每项最多一次retrieve调用；回调内部如有补召回，必须自行限定预算。执行器在语义回调前检查文档/版本、非空原文、stub、章/节范围与像素要求；成功后才记录satisfied。未找到为missing，读取或核验异常为unavailable并附失败回执。缺少任一必需项时不返回可组合状态；可选图片缺失不阻断已齐全的文字需求。最多24个来源，发生取消则抛出，不交付完成包。

scope为只读教材证据，不写记忆、不导航、不发布。该执行器由隔离测试验证，尚未替换在线覆盖/发布判断；原文、语义、业务授权仍需原系统核验。

### 3. 离线适配与调用方

`scripts/collect_layer4_stage3.py`复用第二阶段采集器：对象ID只从实际问题中提取，当前文档版本从教材登记读取；不从supports取得对象位置或原文。比较、实验及跨章问题有两段明确引号内容时分别取前三个候选，总预算最多六个；查询片段只来自用户问题，章范围仍用现有explicit_chapters提取。没有引号的自然语言需求尚不自动拆分。

第二阶段采集器仅增加可注入的采集函数和指纹文件列表；原入口默认仍执行原逻辑。旧基线结果未覆盖，固定v2数据未改。每条trace保留走过的路径，不以本批取证结果冒充完整在线CourseSearch或LightRAG执行。

## 同一冻结集复跑结果

基线与本批使用同一`layer4_textbook_v2.json`，SHA256：`eb438195e1dbbd7c3e08315b149eb2d37a43fbe60dfc19bba046a31fe7dbb6cd`。原索引hash、教材快照在执行前后均一致。

| 诊断项 | 第二步 | 第三步 |
| --- | ---: | ---: |
| 已执行教材场景 | 48 | 48 |
| 全部预期锚点出现 | 36 | 48 |
| 部分出现 | 1 | 0 |
| 未出现预期锚点 | 11 | 0 |
| 数据表全部锚点出现 | 1/6 | 6/6 |
| 公式原块出现 | 0/6 | 6/6 |
| 实验条件两侧出现 | 5/6 | 6/6 |
| 宏平均锚点召回@6 | 0.7604167 | 1.0 |
| MRR@6 | 0.728125 | 0.8645833 |

所有类别各六例。执行路径：普通单查询6、双需求分别召回18、PDF选区6、原始对象12、点名原图6。12个对象中5个自身原文得到exact文字框，7个仍为unlocated；**没有把原块命中率提升写成精确页面定位全部完成。**

这48例含明确ID和原文片段提示，已用于开发诊断，未经教师审核，不是自然问法盲测。1.0表示原块或登记资产出现，不能写成“回答准确率100%”或“公式理解100%”。需求执行器的语义回调未在48例中接入实际模型，本轮不评价生成讲解质量。

本轮没有远端LLM调用。现有embedding与reranker均实际使用CUDA session，部分算子可在CPU；本批约31.421秒的逐例累计时间含不同路径和暖缓存，不是完整问答耗时或严格速度对照。额外召回增加了模型调用次数，不宣称零成本提升。

## 测试、记录与复现

34项定向测试在同一最终运行通过：原22项及新增12项。新增覆盖二维表原件、原始公式限制、旧PDF、源DOCX篡改、行数据篡改、公式内容篡改/改名、路径越界、缺侧阻断、可选项失败、章/像素范围、取消，以及拆分查询不读取金标。

首轮5个失败均为测试夹具过早替换课程路径，导致业务模块首次导入读取了精简清单；修正初始化顺序后通过，没有放宽生产校验。失败日志仍保留。

原始产物在应用`.runtime/layer4-stage3/baseline-v2/`：manifest、逐条runs.jsonl、runs.json、report.json；最终测试日志`.runtime/layer4-stage3/tests-final.log`。可提交的汇总、逐例变化和产物hash见`STAGE3_BASELINE_SUMMARY.json`。

```powershell
$layer4Python='E:/项目/heart/project/integration/discrete-math-tutor/.venv-runtime/Scripts/python.exe'
& $layer4Python -B -X utf8 -m unittest tests.test_layer4_stage3 tests.test_evidence_execution tests.test_layer4_collection tests.test_layer4_benchmark -v
& $layer4Python -B -X utf8 scripts/collect_layer4_stage3.py --data tests/data/layer4_textbook_v2.json --course-dir knowledge/courses/experimental-psychology-3 --cache-dir E:/项目/heart/.runtime/response-portable-20261022/model-cache/fastembed --output .runtime/layer4-stage3/new-run
```

在本worktree应用目录运行，输出目录必须不存在。执行前后核对冻结输入及索引，执行源码变化时拒绝出稳定报告。

## 复用与许可记录

本批直接复用项目已有的SourceRef、EvidencePackage、LiveCitationIndex、fixed_book.digest、source_mapping、parse_converted_textbook的paragraph_text/block_paragraphs与DOCX包读取，以及现有检索和重排。沿用第一阶段研究形成的对象直读与逐项覆盖设计，不拷贝外部项目源码。本批无新增第三方源码、模型或依赖，已有许可证和NOTICE保持原样；不将思路借鉴写成代码复用。

## 下一阶段

由集成负责人在当前任务/课程授权下接入只读工具，提供真实原文与语义支持核验回调，保留取消、预算、旧版本和缺证状态；不允许凭本批诊断分数绕过发布门禁。另做自然问法、教师审核与公式/表格像素定位验收，再决定是否需要图像读取或解析增强。LangGraph公共接线仍是后续集成工作。
