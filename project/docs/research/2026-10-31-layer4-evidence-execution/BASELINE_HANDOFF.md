# 第四层首批契约与评测基线交接

日期：2026-10-31。独立worktree：`E:/项目/heart/.worktrees/layer4-contract-baseline-20261031`。应用路径位于该目录下`project/integration/discrete-math-tutor`。

## 已完成

- E0：固定输入教材文件/PDF/对象hash，独立开发。
- E1：EvidenceRequest/RequirementCoverage/EvidencePackage，复用ContextHeader、Constraint、LearningTarget、SourceRef。
- E2：`tests/data/layer4_textbook_v1.json`含60个候选：定义、比较、实验精读、跨章、选区、表格、公式、图像、学习记录、执行边界各6个。前48个教材场景共66个锚点；后12个是受控边界场景说明，不冒充已执行的真实学生流程。
- E3：只读冻结校验和离线结果诊断评分，来源旧版本不计命中、缺跑场景保留在分母，重复结果拒绝。
- E4：17项定向测试通过；真实教材文件和来源冻结核验通过（`BASELINE_VALIDATION.json`）。未执行检索对照或真实模型验收。

数据SHA256：`0af1c33ba18a36a6a31a1ca35343099148071cc52a506d048036feb20ceceffd`。这是来源锚定候选，不是教师批准的答案金标准；semantic_reference全部为空、teacher_reviewed全部false，reserved不是盲测。按章连接分组得到development=30、reserved=30，不为凑20/40拆散同组。

位置结果：50个锚点通过现有PDF字符映射唯一定位，16个未由该方法定位。后者包括图片/公式和表格，并不等于现有reader原图定位失败；它们是需要单独核对对象定位/像素/结构的候选。不能将此结果宣称为全系统引用成功率。

候选问题使用教材原文片段定位，适合检索和身份诊断，容易程度不代表真实学生问法。实验类是条件精读探针，尚未由教师核对为完整实验单元；不能据其数量宣称完成全书实验标注。后续先审核对象完整性和语义参考，再另冻结自然问法及独立盲标集。

## 使用

在worktree应用目录执行，复用本机原有Python环境；无需复制.env、学生数据库或模型。

```powershell
$layer4Python = 'E:/项目/heart/project/integration/discrete-math-tutor/.venv-runtime/Scripts/python.exe'
$layer4Course = 'E:/项目/heart/project/integration/discrete-math-tutor/knowledge/courses/experimental-psychology-3'
& $layer4Python -B -X utf8 -m unittest tests.test_evidence_execution tests.test_layer4_benchmark -v
& $layer4Python -B -X utf8 scripts/evaluate_layer4_benchmark.py --data tests/data/layer4_textbook_v1.json --course-dir $layer4Course --output .runtime/layer4-baseline/new-validation.json
```

输出文件已存在时拒绝覆盖，复验换新名称。生成新批次用`build_layer4_benchmark.py --course-dir ... --output 新文件`，不会重新生成模型向量或原文索引。

离线检索结果格式为数组，每项包含case_id、status、sources；sources保持现有SourceRef的document_id/version/location.evidence或source_spans。给校验器加`--runs 结果.json`可统计@6原文块出现情况。评估只识别结构化原块身份，不用正文猜来源；没有原块信息的结果不计命中。

评分始终标记`diagnostic_original_block_presence_not_semantic_support`，不是答案正确率、语义支持率或发布通过率。学习记录/执行场景不混入教材召回分母，也尚未由该脚本自动执行。

## 保留的开发失败与修正

- 第一轮采样每章最多一个公式，实际只收集5个；修改为同章可选两个不同原块，未伪造第六个。
- 第二轮图片未读到，是脚本错误地去掉了assets/chapter_XX相对路径；保留登记完整路径并检查路径边界、尺寸和重复文件hash后生成成功。没有修改教材数据或既有图片服务。
- 构建过程在写出文件前完成所有检查，失败未产生/覆盖冻结数据。
- 交付前发现Windows默认CRLF会被Git规范化，导致签名在checkout后变化。旧候选/报告保留在忽略的.runtime，生成器改为明确LF后重新冻结最终候选；语义与来源不变，最终hash以上文为准。

## 下一阶段

1. 第三层负责人确认接口语义，用固定completed/partial/insufficient样例测试教学决策，不先改检索实现。
2. 对16个未由文本法定位的锚点，复用现有visual_locations/公式原件/表格结构做定向核验；核验记录独立于原冻结文件。
3. 接已有检索的只读采集适配，记录真实路由/耗时/候选和原块身份，跑48个教材场景基线。随后审核语义与实验单元，再决定切片/解析改造。
4. 集成负责人统一接公共Agent循环和未来LangGraph；保留任务/会话/版本/epoch、来源门禁及单写入约束。

本批新增文件未被公共回答入口导入；没有部署、改变正式服务、数据库、教材ready或其他窗口的改动。

## 第二步续交付

已完成只读采集、原16个对象核对与修正v2的48场景本地基线，详见`STAGE2_READONLY_BASELINE.md`。v1原样保留，不能再将其中4个单格排版栏框当数据表金标准。后续对照使用明确版本的v2，不能跨数据版本直接宣称召回提升。
# 第三步后续交付

对象直读、逐项覆盖和同一冻结集对照见[STAGE3_OBJECT_READ_AND_REQUIREMENTS.md](STAGE3_OBJECT_READ_AND_REQUIREMENTS.md)。本批仍是内部接口与离线验收，不是线上发布；公式OMML原件命中不等于语义或像素核验通过。
# 第四步后续交付

现有CourseSearch对象接线、本地逐项覆盖和隔离回归见[STAGE4_ONLINE_BRIDGE.md](STAGE4_ONLINE_BRIDGE.md)。代码仍在独立分支，未替换正在运行的服务；严格核验后7个对象仍缺少自身完整原页证据，不以邻文冒充通过。
