# 阶段E首批：聊天澄清交互

日期：2026-10-12。

## 改动

- 现有聊天气泡显示服务端澄清选项和“取消本次问题”。选项是原生按钮，可鼠标或键盘操作；自由文本也携带原任务ID和版本继续原问题。
- 浏览器按标签保存 session_id，每次新请求生成 request_id。BroadcastChannel 检查新标签复制 sessionStorage 的情况，为重复的存活标签换编号。刷新恢复相同标签的待澄清任务。
- 初始化恢复失败时保留输入并阻断新提问，显示“重新恢复”；过期、版本冲突、记忆删除、处理中等返回触发状态恢复。
- 网络失败提供“重试原请求”，重用原始请求编号、对象和参数；质量拒绝或后端 task_failed 后提供重新提问入口。
- 重新圈选其他教材对象时先取消旧澄清任务；保留原选区补充时继续原任务。跨标签修改账户ID会刷新当前页，清除旧任务界面。删除知识点记忆后重新读取待澄清状态。
- 动态标签、错误和正文按既有转义规则输出；教材引用跳转路径沿用原实现。app.js 静态版本更新，避免旧缓存。

## 验证

使用 Playwright 技能运行器及本机 Edge，测试脚本为 tests/browser/task-clarification.cjs。脚本临时启动只读静态服务，加载实际 index.html、app.js、workspace.js；API由浏览器路由替身提供。测试移除 PDF、MathLive 和练习脚本，集中验证聊天交互；未调用真实后端、模型或学生数据库。

八组浏览器检查通过：

1. 键盘选项、task_id/revision 和 HTML 标签转义。
2. 刷新恢复及模拟复制标签的 sessionStorage 隔离。
3. 取消后的新问题与自由文本补充。
4. 断开流连接后使用完全相同的请求重试。
5. 任务过期后的状态恢复。
6. 恢复失败阻断和恢复按钮。
7. 重新圈选先取消旧任务，再发送不绑定旧任务的新问题。
8. 跨标签切换账户后不显示旧账户待澄清任务。

浏览器无 pageerror，node --check frontend/app.js 和 git diff --check 通过。后端 test_task_api 和 test_clarification_tasks 共35项通过，输出单独保存在阶段E首批后端测试输出.txt。

复现浏览器检查：

```powershell
Copy-Item -LiteralPath tests/browser/task-clarification.cjs -Destination "$env:TEMP/playwright-test-task-clarification.cjs"
node C:/Users/free/.agents/skills/playwright/run.js "$env:TEMP/playwright-test-task-clarification.cjs"
```

运行器会在技能目录创建临时执行文件，当前受限环境需要文件权限提升；权限检查后运行成功。没有改写技能源码。

## 尚未完成

- 练习页面当前按钮沿用既有辅导接口；尚未把聊天编辑器绑定到当前小题 exercise_target。下一批补齐这一入口及对象摘要/纠正操作。
- 本次是实际前端与模拟接口检查，不能替代真实模型、真实 PDF 选区及练习页面的联合验收。
- 对话历史接口仍为学生级历史，不宣称已完成聊天记录按标签过滤；模型任务上下文由后端非 legacy 会话路径隔离。
- 正在执行任务的结果恢复沿用后端现有能力；本次刷新自动恢复的是待澄清问题，不提供执行中任务自动重跑。
- 标签去重依赖现代浏览器 BroadcastChannel；不支持此 API 的环境及后台长时间节流仍需后续兼容验收。当前测试基于 Edge。

阶段E保持未勾选，待小题聊天对象接线和联合验收后更新；真实模型基线、阶段D效果验收与阶段F灰度/回滚仍未完成。
