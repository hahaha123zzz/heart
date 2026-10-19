# 完整原生对话实施记录

## P0：基线、接入契约与质量口径（2026-10-19）

起点为 c639a4f。保留用户的完整调研、计划和 11/14/100 台账；没有覆盖无关工作区修改、旧课程删除、心理学教材及数据库。完整工作区状态只保存于本机隔离运行目录，不将文件内容或学生数据带入提交。

新增 scripts/check_deeptutor_native_baseline.py，以仓库固定副本运行原调研的6个上游测试模块，校验全部3,764个文件，登记 Python/依赖元数据及8000/18001监听状态，不读取密钥或源项目配置。此次8000监听、18001未监听，仅代表端口状态；SentenceTransformers未安装，不能宣称原生重排环境齐备。

复现命令（宿主目录）：`.venv-deeptutor/Scripts/python.exe -B scripts/check_deeptutor_native_baseline.py`。输出 `.runtime/deeptutor-native-baseline/20261019T071211Z-8d9a8f/`，包含 report.json、原始工作区状态、upstream.xml 和 upstream.log。实际225项：224通过、1失败、无collection错误或跳过；耗时308.91秒，CLI保留退出码1。

失败仍为 test_cold_start_stalled_provider_settles_with_bounded_retries[partial_stream] 的消费者事件断言，与原 VALIDATION.md 一致。未修改上游测试或将失败静默排除；此前已验证emit与异步消费时序的诊断继续保留。新增基线汇总自检1项通过，确保失败、错误、跳过不被算作成功。

本次report.json的SHA-256：ec8eef8a7ded9e21937ca21a9893d7cb151832dd601d58ec3b861aa564477893。

接入契约见 NATIVE_CONTRACT.md，明确原生与旧投影分离、工作区及课程作用域、submission去重、取消/答复命令、DONE尾部事件、正文持久化和独立发布状态。P1—P5后续负责逐项实现这些行为，契约通过不等于门禁已经实现。

质量优先落实为 QUALITY_BASELINE.md 与6组连续对话样本，复用原9类心理学问题；从P0建档，P3起做同模型同教材的新旧对照，不等P8才评估。此次没有运行在线模型、质量A/B、浏览器或原生RAG，不声称对话质量已经提高。

P0完成后按用户约定自动提交/推送；下一检查点接入P1内部原生持久化回合，仍不切学生默认入口。
