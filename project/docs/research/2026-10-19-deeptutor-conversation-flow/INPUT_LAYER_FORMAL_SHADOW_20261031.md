# 输入理解层正式 shadow 灰度

2026-10-31，用户明确授权独立真人标注和正式灰度。本次启动shadow，不启用active决策或三个标签消费开关。

## 已执行

- 启动前8000无监听；正式库存在，未发现仍有效的input_reference澄清任务。
- SQLite backup API生成一致性备份，PRAGMA integrity_check=ok，备份SHA及实际源码指纹保存于 `.runtime/psy6d-formal-shadow-20261031/manifest.json`。源码为当前工作树，尚未提交，不能称为干净发布提交。
- 仅修改本机.env的6个开关：INPUT_UNDERSTANDING_MODE=shadow、INPUT_UNDERSTANDING_SEMANTIC_ENABLED=0、SEMANTIC_LABELS_ENABLED=1、LABELS_POLICY/STRUCTURE/TURN=0。其余模型、数据库、检索配置保持原值。改前配置保存在同一运行目录的config.before.private，不提交Git或对外发送。
- .venv-gpu完成CUDA预热后因缺少lightrag启动失败；日志保留startup.*。改用已有.venv-runtime启动，未安装依赖。正式入口 http://127.0.0.1:8000/ ，进程PID记录在service.pid，运行日志startup-runtime.*。
- health=200。使用独立测试学生发出一条正式HTTP请求，answer_status=answered；正式库中input_mode=shadow，标签非空，理解model_calls=0，input_decision为空；公开结果不含input_understanding。smoke.json保存测试请求与核验结果。此项证明shadow接线与可用性，不证明长期性能或所有入口效果。

## 真人标注交付

`HUMAN_ANNOTATION_PACKET_20261031/`提供150条无既有答案的TSV模板、冻结标签定义和说明。每条需reviewed=1及标注者代号才能导入；空白未审核模板不会被当作弃权计分。

scripts/import_semantic_annotations.py与annotation_agreement.py相关12项测试通过。用户已选择第二位真人标注，本次没有调用模型冒充真人。模板仍待实际填写。现有参考标签是工程来源；人际κ还需可核实的第一位真人同批独立文件。

## 监控与回退

监控以本次manifest时间后的正式task为范围，只汇总shadow数量、解析调用、标签分布、执行决策和公开摘要泄漏，不导出其他学生原话/画像。当前只有专用烟测证据，等待真实使用流量后扩大观察。

回退步骤：

1. 核对8000监听PID与service.pid一致后停止该服务，避免误停其他进程。
2. 读取manifest.previous_flags，逐项恢复六个开关：原值为null则用dotenv.unset_key，其他值用set_key。不要整文件覆盖后来修改的模型配置。
3. 在应用目录使用 `.venv-runtime/Scripts/python.exe -X utf8 -m scripts.start_server --port 8000` 重启，确认health。
4. 单纯关闭shadow无需还原数据库，保留灰度期间正常产生的对话。备份仅用于实际数据恢复事件，不用配置回退覆盖新对话。

本次不会自动升级active，也未删除旧路由。真人标注、扩大样本、完整入口和active上线验收仍待完成。
