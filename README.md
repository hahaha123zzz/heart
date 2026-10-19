# 教学 Agent 与离散数学 AI 助教

本仓库包含原教学平台的 Agent 模块抽取版，以及离散数学 AI 助教 Demo。

- [Agent 模块说明](project/README.md)：原平台的辅导、出题和教学决策代码；完整平台的部分依赖未包含在本仓库中。
- [离散数学 AI 助教](project/integration/discrete-math-tutor/README.md)：包含前端、API、学生状态、教学规划、数据库模块和教材资源。

## 启动离散数学 Demo

在 `project/integration/discrete-math-tutor` 目录创建 Python 虚拟环境，安装 `requirements.txt` 中的依赖，将 `.env.example` 复制为 `.env` 并配置模型接口，然后运行 `3-start-api.bat`。命令行模式使用 `2-chat.bat`。

本地密钥、数据库、虚拟环境、日志及打包副本已通过 `.gitignore` 排除。

## DeepTutor 整体复用

完整上游源码已迁入 [project/vendor/DeepTutor](project/vendor/DeepTutor)，保留现有页面，通过独立后端逐批接入。
范围和验收见 [实施计划](project/docs/research/2026-10-18-deeptutor-full-reuse/IMPLEMENTATION_PLAN.md)；实际接通状态见 [执行记录](project/docs/research/2026-10-18-deeptutor-full-reuse/EXECUTION_LOG.md)。
