# 本地服务切换记录

日期：2026-11-04。

## 当前运行版本

- 服务：[http://127.0.0.1:8000/](http://127.0.0.1:8000/)。
- 应用代码提交：`1a7905b`。
- 分支：`codex/ta5-acceptance-20261029`，代码已推送远端；本次未合入 main。
- 服务使用提交导出的干净副本，目录为 `E:/项目/heart/.runtime/workspace-layout-release-1a7905b/project/integration/discrete-math-tutor`。
- `E:/项目/heart` 工作区中其他窗口未提交的教学技能、文案、进度与阅读器代码仍保留，未作为本次运行版本发布。

## 数据与配置

- 配置在启动进程内读取原应用的 .env；密钥未写入提交或部署说明。
- 正式库沿用 `E:/项目/heart/project/integration/discrete-math-tutor/ai_tutor.experimental-psychology-3.db`。
- 停止旧服务前，核实其工作目录为本项目、监听 8000，且正式库没有执行中任务。
- 切换前 SQLite backup：原应用目录 `.runtime/workspace-layout/backups/pre-switch-20261104-153308.sqlite3`，备份 quick_check 为 ok。
- 教材普通目录副本位于运行副本内，保留原文件；没有重建索引或改 ready 标记，也没有把教材、数据库、配置密钥或验收数据上传 GitHub。
- .cache 复用本机缓存。教材根未用 junction：早期被安全校验拒绝后已改为普通复制，没有绕过该校验。

## 启动与回退

当前本机重启命令：

```powershell
Set-Location 'E:\项目\heart\project\integration\discrete-math-tutor'
& '.\.venv-runtime\Scripts\python.exe' -B '.runtime\workspace-layout\start_release.py' --port 8000
```

启动器与运行副本是本机 `.runtime` 产物，不包含在源码提交中。重新部署机器时需要准备教材、候选索引、原配置与 Python 环境，不能仅克隆代码就声称具备教材库。

回退前先核实并停止本次 8000 进程，再恢复指定已验收代码版本运行；保留现有学习数据库，不因页面回退恢复旧数据库。确需数据恢复时，先单独备份当前库，再使用上述切换前备份，避免覆盖切换后的学习记录。

## 切换后验证

- `/health`：status=ok、mock_mode=false、fixed_book.ready=true。
- 实际 HTTP 返回的 `/static/app.js` SHA-256 与提交 `1a7905b` 的文件一致。
- 新浏览器上下文进入真实 8000：默认教材收起；点击后教材 Canvas 出现；无横向溢出；pageerror=[]。
- 正式页面检查不调用模型，不读取已有用户历史。

证据位于原应用目录：

- `.runtime/workspace-layout/server-8000-release.log`
- `.runtime/workspace-layout/official-smoke.json`
- `.runtime/workspace-layout/official-closed.png`

90 项 Python、11 组布局交互、15 项传输测试及真实模型重点入口的证据见 WORKSPACE_LAYOUT_ACCEPTANCE.md。人工教学质量标注、独立可访问性审计和实体触摸设备测试不在本次完成声明内。
