# 阶段E联合验收：真实HTTP、PDF与练习页面

日期：2026-10-12。

## 结论

阶段E的前端接线与交互链路完成。真实FastAPI服务、SQLite临时数据库、教材PDF、React/PDF.js阅读器、练习题库及SSE请求完成联合验收。模型仍使用确定性夹具，此结论只验证工程链路，不代表真实模型的任务识别、看图理解或数学回答质量。

新增 scripts/serve_intent_acceptance.py 和 tests/browser/intent-http-acceptance.cjs。实例绑定127.0.0.1独立端口8767，数据库及裁图位于临时目录，退出时关闭连接并清理。禁用后台记忆任务、向量推理及付费模型调用。测试专用路由只在脚本启动实例中注册，普通main.py启动不包含这些路由。

## 五个通过场景

|场景|验证|
|---|---|
|教材框选|真实鼠标框选第1章PDF；点击提问；服务器裁图可读取；提示返回保留原坐标和对象。|
|文字划选|真实鼠标划选PDF文本；弹出提问入口；返回文字选区引用。|
|澄清恢复|真实任务持久化；刷新恢复pending；选择服务端选项继续原选区；任务编号相同且版本推进。|
|小题辅导|真实第1章首题p1保存选择A；聊天读取该草稿；夹具仅收到p1作答及两张实际题面裁图；不推进课程步骤。|
|失效版本|题库版本校验在建立SSE前返回422。|

五项通过，浏览器pageerror为空。详见[验收数据](阶段E联合验收.json)和[页面截图](阶段E联合验收.png)。上一批十组隔离交互检查已覆盖键盘选择、标签隔离、账户切换、保存失败和重试，没有重复计入本轮。

替身只替换LLM输出，未替换业务路由器、任务服务、HTTP接口、PDF裁图、记忆存储、练习执行器或页面SSE解码。语义质检及充分性判断处于明确mock模式，不能据此宣称数学正确或提示绝不泄露。

## 复现

项目目录两个终端：

```powershell
# 终端1：隔离测试实例。
& ./.venv/Scripts/python.exe -X utf8 scripts/serve_intent_acceptance.py --port 8767
```

```powershell
# 终端2：Edge检查，结束后自动请求测试实例退出。
Copy-Item -LiteralPath tests/browser/intent-http-acceptance.cjs -Destination "$env:TEMP/playwright-test-intent-http.cjs"
node C:/Users/free/.agents/skills/playwright/run.js "$env:TEMP/playwright-test-intent-http.cjs"
```

URL可通过INTENT_ACCEPTANCE_URL覆盖；脚本先检查测试实例标志，仅用于隔离环境。Playwright运行器需要技能目录临时文件写权限，当前环境经过审批执行。

## 调试与限制

- 测试等待函数改为明确布尔条件，避免直接返回页面对象导致不稳定。
- Edge不能稳定读取已经cancel的SSE响应体；改为记录页面实际解码结果，请求仍为真实HTTP。
- Windows数据库文件占用导致初次清理失败；退出时增加engine.dispose，后续运行正常退出。早期残留目录已校验路径边界并清理。
- 一次临时目录清理的自动审批因连接故障未完成，操作未执行；通过相同流程重试成功，没有绕过权限检查。
- 本轮未修改生产回答逻辑，仅第1章样例；不代表所有章节、跨页公式、数学输入或全部题型完成验收。
- 未执行GPU模型或DeepSeek验收，未启动/替换用户日常8000服务。

## 下一步

E勾选完成。A独立审核与真实基线、D真实模型效果及F评测/灰度/回滚仍待完成。下一批更新评测入口，使其消费统一上下文和扩展任务字段，固定样例与模型调用预算，再记录真实表现。现有eval_intent.py仍只评旧路由字段，不能据此宣称升级有效。
