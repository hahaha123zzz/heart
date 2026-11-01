# 第三/四层接口契约 v1

状态：已实现独立模型和验证，尚未接入公共回答链路。设计依据为本目录调研，用户已于2026-10-31同意开始第一步实施。

模块：`models/evidence_execution.py`。这是宿主内部接口，不是模型可直接提交的HTTP授权接口。第三层、第四层和未来LangGraph接线方按此交接；改契约需升级schema版本并说明迁移。

## 请求

`EvidenceRequest`沿用现有`ContextHeader`，其中task_id/task_revision必须来自TaskService实际认领结果。documents是当前被授权的document_id→version映射，由宿主注入。request_id和decision_id用于关联原输入与教学决定。

requirements逐项包含id、query、kind（text/image/table/formula）、required和可选LearningTarget。复用现有LearningTarget/SourceRef，不另造教材身份或定位体系。跨章问题用多条需求分别声明；目标指定章/节时，结果不能无声替换到别处。

constraints沿用输入层Constraint，包括no_questions、hint_only、no_full_answer、verdict_only。第四层传递约束，不更改教学策略，也不把约束解释成额外写入授权。预算继续服从宿主ExecutionBudget，本批不新增第二个超时控制器。

## 输出

`EvidencePackage`返回原SourceRef列表、每项需求的RequirementCoverage和工具执行回执。覆盖状态为satisfied/missing/unavailable，缺失必须给原因；来源ID必须存在且版本落在授权文档内。复用SourceRef.location中现有evidence/selection/asset数据，不重新生成引用编号或坐标。

- 必需需求缺失不能构造completed。
- 可选插图缺失不阻断已经齐全的文字讲解。
- partial/insufficient/failed/cancelled均不会产生ready_for_composition=true。
- ready_for_composition为计算字段，调用方不能直接传true。它只描述教材需求是否齐全，不证明reader动作已完成、用户已掌握或来源已教师审核。
- 需要实际像素的image需求必须关联带model_saw_pixels=true的来源；该标记必须由现有模型网关实际发送结果产生，不能由模型规划结果或前端声明赋值。

**形状一致不等于真实证据。** SourceRef必须先经过现有CourseSearch/choose_evidence、validate_source或原文定位验证；语义支持由现有覆盖判断与发布核验负责。新模型不验证真实文件内容，不替代原门禁，不能被当成“任意JSON变为已验证来源”的转换器。

`ToolExecutionReceipt`复用原工具call_id关联结果。reader_goto发出后是requested，实际有效applied回执后才可标completed；失败/取消各自保留。工具回执不直接写成绩或学习进度。

## 暂停与恢复

`checkpoint_payload()`提供纯JSON状态；恢复用`EvidencePackage.model_validate_json(...)`检查内部一致性，再由宿主重新验证学生、会话、epoch、任务revision和教材版本。形状恢复成功不代表原授权仍有效。

SDK实例、锁、数据库连接、服务对象不进入检查点。正式评分/记忆/reader回执继续使用各自唯一权威仓储与幂等收据。

## 对应现有调用链

第三层当前`state['decision']`记录策略选择信息，并非完整证据请求。未来集成方在已认领任务和已确认目标后构造EvidenceRequest；不得在本批适配中重新运行LLM教学Planner。

第四层继续调用`CourseSearch`、`read_material`/`read_source`和既有媒体链路，来源去重仍在原工具/证据模块完成。确认所有coverage后构造EvidencePackage。第五层只使用获得支持的需求；partial时明确限制，不生成缺失对象的结论。

本批没有接线adapter，也没有把新模型插入TaskService或发布门禁；这是下一阶段集成点，避免与第三层窗口同时改公共文件。现有ToolResult中的model_message/pause_for_user/terminate_turn仍由原dispatcher处理，不会被本契约丢弃或改写。

## 验收边界

定向测试覆盖：比较缺一侧、可选图、取消、未知/重复来源、旧版本、stub、目标范围、无像素、伪造ready/private字段、JSON恢复。它们是契约测试，不证明原文核验、页面高亮、语义回答或跨库提交已完成。
