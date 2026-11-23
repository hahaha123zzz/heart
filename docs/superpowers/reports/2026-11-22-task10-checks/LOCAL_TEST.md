# 本机 8000 学生测试环境

入口：http://127.0.0.1:8000 。当前仅监听本机，线上/ECS 未改动。

账号 heart-review-01 至 heart-review-10，永久有效，密码各自随机。初始凭据只在 private/worker-home/.runtime/review-accounts/vendor-accounts.txt；管理员凭据另在 private/admin-account.txt。不要把这些文件或 private/runtime.env 放入网页目录、报告或 Git。

十个账号均从空聊天、空练习、空评估和空个人模型配置开始，分别获授权 11 章教材。首次使用到“设置 → 我的模型”填自己的 HTTPS OpenAI-compatible 配置；图片与评分按需逐项验证并确认费用，不使用共享 Key 兜底。教学偏好统一在“我的记忆”主动添加；关闭记忆不读取长期偏好。

后台服务：新版 Next 在 8000，H 在 18000，厂家 worker 在 18001。运行配置、账号、数据和日志都在 private 外部持久目录，不在应用发行目录内。

PowerShell 中运行 control/student-local.ps1 status 查看状态；start 启动，stop 停止，restart 重启。停止与重启不会清空数据。当前发行选择记录在 active-release.json；实际控制程序在 control，应用快照在 releases。

已实测新版切换 → 回退到 candidate-runtime-20261122 → 再上线 local8000-20261122，新增测试偏好与同一登录会话均保留。测试条目已从有效视图移除，界面恢复空态。两次发行采用同一业务源码的两个本地封装修订；这不是对线上历史运行包的演练。完整厂家目录、环境密钥和三个 PostgreSQL 库已备份到 private/backups，并在新隔离库恢复校验。

初次启动需要加载教材和本地推理资源，可能需要约两分钟。本轮实测回退启动约 41 秒、重新上线约 52 秒；维护期间测试入口会短暂不可用。

此测试环境位于当前工作树的 .runtime/student-release-20261122。保留该目录及 PostgreSQL 测试库才能继续使用同一账号和数据；线上部署待用户完成本地测试后另行处理。
