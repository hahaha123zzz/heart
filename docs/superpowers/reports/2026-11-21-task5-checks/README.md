# 任务五验收材料

2026-11-21 归档；测试于 2026-11-20 在隔离工作树执行。最终浏览器 15 组通过，未捕获异常为 0。browser-results.json 中唯一 HTTP 503 为脚本主动注入的档案故障，刷新后恢复。

browser-task5.js 使用可见 Chromium、两个随机密码的临时账号、三个随机 PostgreSQL 数据库、本地 httpx.MockTransport 和实际厂家会话/路径/档案接口。临时档案的 26 条记录仅用于分页验收，不是正式学习成绩；没有伪造正式测评。

browser-harness.py、browser-task5.js 和 provenance.py 是本次审阅副本，不是独立应用。复验须在 H 目录、既有 Python 运行环境和隔离 PostgreSQL 支持下，将 harness 放回 H/.runtime/browser-check-12d290667b/，保留同目录 python-deps，设置 HEART_BROWSER_SCRIPT 指向浏览器脚本，并准备 H/.runtime/task5-build.json 对应的生产包。Playwright 执行器为 C:/Users/free/.agents/skills/playwright。不得将临时账号数据复制至正式目录。

任务五使用同一源码生产副本，946 个运行源码、资源、契约和构建配置文件哈希一致，依赖沿用任务二独立 npm ci 目录。provenance.json 核验原始导入基线与累计补丁，不覆盖上游原始哈希。

首轮发现未配置模型时路径/档案被整体门禁遮挡，随后修复只读管理页面门禁；模块辅导还缺少显式 mastery_path 授权，已更新项目初始化/评审授权脚本并添加正反权限回归。脚本中的嵌套 main、两个取消按钮定位歧义也已修正。最终全部通过。

未运行全仓所有 Vitest；390px 是浏览器视口模拟；模型为本地传输替身。图片处理暂缓，正式服务与正式账号权限未切换，旧聊天未迁入。
