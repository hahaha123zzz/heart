# NT3候选的Q2来源核验

日期：2026-10-27。状态：隔离来源检查已实现，正式单写入切换未实现；本批未提交、未部署。

## 本轮改动

- 新增 `integrations/deeptutor/learning_sources.py::check_candidate_sources`，复用已有迁移结构校验、Q2 `course_navigation.validate`、PDF登记和 `course_release.validate`，不重写目录或教材解析。
- 仅接受当前宿主课程的Q2来源。检查目录目标/版本、document、章/节、原文版本、发布ID、原文范围和目标schema；缺少身份、换版、原文缺失或范围变化返回明确失败。
- 相同来源在本次检查内去重，发布身份每次检查只取一次；不跨调用缓存成功结果，不改变路径、掌握、原始来源或教材ready状态。
- CLI增加 `--verify-sources`，可与 `--bind-sessions` 同用。报告分别保留 `candidate_verified`（迁移结构）和 `sources_verified`（本次来源检查）；显式要求来源检查而未通过时退出码为2。两者通过也保持 `activated=false / ready_for_cutover=false`。
- 发现并修复 `agents/q5_runtime.py::propose_chapter_plan` 的schema固定值：新计划直接保存Q2返回的 `target_schema`。

## 实证失败与兼容

真实备份首次检查中，4条来源全部因schema不一致拒绝。旧Q5保存 `q2.teaching_targets.v1`，Q2实际schema为 `word-heading-targets-v1`；目录版本、原文版本、发布ID均匹配。

兼容仅限上述两个固定值、旧来源范围恰为同一目标ID，并仍通过全部其他身份检查；未知schema、其他范围、Q2拒绝版本都不兼容。旧记录和迁移快照不被改写，新记录不再写错误固定值。

失败保留：`.runtime/teaching-modes/native-sources-schema-failure.log` 与同名 `.json`。

## 验证

- 初始来源/迁移：17项通过。
- 修复后来源/迁移/本次安排：35项通过，33.200秒，日志 `.runtime/teaching-modes/native-sources-tests.log`。
- 来源/原生绑定/迁移/Q5联合：57项通过，109.207秒，日志 `.runtime/teaching-modes/native-sources-joint.log`。与35项集合重叠，不累计为92项；语法编译及定向 `git diff --check` 通过。
- 真实只读备份：沿用 `.runtime/native-learning-migration/20261027-q5-bound-candidate`，执行带 `--bind-sessions --verify-sources` 的迁移CLI。返回 `already_imported`、`candidate_verified=true`、`sources_verified=true`；4条不同来源检查通过，教材 `release_ready=false` 保持。日志 `.runtime/teaching-modes/native-sources-cli-final.log`。

备份、候选库、源记录和报告均含私有学习信息，仅留本机.runtime，不纳入提交。本轮未调用模型、未启动服务器、未做浏览器验收。

## 仍需完成

本函数目前接隔离CLI，不是在线授权、评分许可或正式部署门禁。只支持已有Q2目录来源；PDF选区的不同来源协议仍须单独适配，不能据此宣布所有入口来源通过。

后续须在原生正式请求入口绑定认证身份/删除epoch，重新读取当前来源并将失效传播到待答/评分/复习；教材ready、视觉像素与教师审核独立保留。Q2仍决定教材下一目标。在线唯一写入、旧模式/本次安排/画像映射及回退尚未完成，本批不激活候选、不启用正式评分或到期复习。
