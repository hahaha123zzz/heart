# 教学 Agent 与离散数学 AI 助教

本仓库包含原教学平台的 Agent 模块抽取版，以及离散数学 AI 助教 Demo。

## V3：正式账号与聊天历史思维导图（2026-10-12）

本版发布在 `v3-accounts-history` 分支，以原始 `heart-main.zip` 对应的提交 `89e429e` 为基础，使用已验收的 `heart-main-clean-20261012.zip` 源码。它是独立交付版本，尚未合并 `main` 中队友后续的检索、记忆和 UI 升级。

- 正式账号注册、登录和退出：Argon2 密码哈希、后端会话、CSRF 与学生数据归属校验；不再使用 24 小时体验账号。
- 横向聊天历史思维导图：增量保存问题节点，点击节点查看关联的原始问答，支持拖动、缩放和分支折叠。
- 保留现有教学 Agent 策略；此前七个未完成的教学补丁已撤回，不属于本版修复成果。
- Windows 启动脚本保留 CRLF 换行，模型配置示例默认使用真实模型。

测试范围、迁移说明与已知限制见 [整理版验证记录](project/integration/discrete-math-tutor/docs/test-results/2026-10-12-clean-release.md)。真实模型多轮教学质量仍需单独验收。

- [Agent 模块说明](project/README.md)：原平台的辅导、出题和教学决策代码；完整平台的部分依赖未包含在本仓库中。
- [离散数学 AI 助教](project/integration/discrete-math-tutor/README.md)：包含前端、API、学生状态、教学规划、数据库模块和教材资源。

## 启动离散数学 Demo

在 `project/integration/discrete-math-tutor` 目录创建 Python 虚拟环境，安装 `requirements.txt` 中的依赖，将 `.env.example` 复制为 `.env` 并配置模型接口，然后运行 `3-start-api.bat`。命令行模式使用 `2-chat.bat`。

本地密钥、数据库、虚拟环境、日志及打包副本已通过 `.gitignore` 排除。
