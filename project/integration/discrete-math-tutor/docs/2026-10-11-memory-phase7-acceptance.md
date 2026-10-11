# 第七阶段：记忆系统页面与后台整体联调

## 结论

已用真实浏览器完成设置页、记忆管理接口、普通问答 SSE 和后台 worker 的整体联调。9 项主流程检查通过，另 1 项删除后对话显示回归通过。修复了删除一个知识点后聊天区暂时清空所有知识点对话的问题。

这说明当前记忆系统的操作流程可以工作；不能据此判断真实模型的教学质量、掌握估计准确度或长期个性化效果。

## 验收环境与边界

- 使用项目真实 main.app、现有前端、FastAPI 路由、MemoryManager、SQLite 事务和持久后台任务。
- 新服务只监听 127.0.0.1:8011，学生为 demo-memory-acceptance；数据库在本机临时目录，与用户原数据库分离。
- LLM_MOCK=1；MEMORY_REFLECTION_LLM=0，后台使用规则摘录。
- 教材检索使用确定性 TextbookChunk 夹具；dense 分支禁用，不加载或下载 GPU/embedding 模型。本轮不是教材检索验收。
- 未调用真实 DeepSeek/OpenAI API，未展示或修改用户密钥。
- 原 8000 服务未停止或重启；本轮隔离服务已停止。若体验完整新后端功能，需要正常重启项目服务。
- 记忆管理目前限本机 test 账户；该限制不能替代正式身份认证。

## 浏览器验收结果

|操作|结果|
|---|---|
|打开设置页，展开学习记忆管理，切换知识点|能显示两个知识点的独立记录|
|查看摘要正文及来源|后台 worker 生成的有效摘要与原文事件 ID 可查看|
|提交逐项误区更正|只将目标误区设为 dismissed；另一个误区不变；mastery 不变|
|清除回答长度偏好|后台移除该偏好，页面同步移除|
|重新保存偏好|来源显示 explicit_user，页面立即更新|
|删除集合知识点|集合记录消失；关系记录及其对话保留|
|刷新页面|已删知识点未恢复|
|删除后重新提问|真实 SSE 路由返回 done，无 error 事件；按钮恢复可用|
|新回合与后台摘要衔接|集合重新出现，后台自动生成新回合摘要|
|页面异常与显示回归|主流程无 pageerror；删除后无须刷新也能看到关系对话|

主流程检查记录见 [browser-results.json](artifacts/memory-phase7/browser-results.json) 和 [browser.log](artifacts/memory-phase7/browser.log)。删除显示问题的失败复现、修复后回归分别见 history-before-fix.log、history-after-fix.log。

## 修复详情

原 frontend/app.js 在按知识点删除成功后执行 state.chat = []，只重新加载记忆面板，未恢复后台保留的其他对话。因此页面显示欢迎语，刷新后才出现剩余记录。

现实现：先清除本地旧对话，再读取当前学生的剩余 conversation 记录；统一通过 messagesFromHistory 转换引用结构，保留已有教材、PDF、图片引用。如果等待期间开始了新提问，不覆盖正在生成的消息；如果剩余记录读取失败，明确提示记忆已删除、需要刷新查看剩余对话。

验证：修改前浏览器断言实际失败（收到欢迎语），修改后相同操作通过。node --check frontend/app.js 与定向 git diff --check 通过。后台 Python 未因本次显示修复改变；上一阶段的 110 项隔离检查结果保持原有记录，本轮不把它们重复计为新检查。

## 截图

- [记忆与摘要](artifacts/memory-phase7/01-overview.png)
- [误区更正与偏好](artifacts/memory-phase7/02-correction.png)
- [删除后剩余知识点](artifacts/memory-phase7/03-after-delete.png)
- [删除后保留的对话](artifacts/memory-phase7/04-surviving-conversation.png)

## 可复现夹具

artifacts/memory-phase7/isolated-server.py 每次创建新的临时数据库，使用 mock 模型和明确的教材夹具；browser-acceptance.cjs 驱动真实浏览器操作。先确认所选端口空闲。

在项目根目录启动：

~~~powershell
.\.venv\Scripts\python.exe docs/artifacts/memory-phase7/isolated-server.py --port 8011
~~~

在另一个终端运行，PLAYWRIGHT_PACKAGE 指向已安装的 playwright 包目录；未指定时使用正常 Node 模块解析。若改变端口，同时设置 MEMORY_ACCEPTANCE_URL。

~~~powershell
$env:PLAYWRIGHT_PACKAGE='C:/Users/free/.agents/skills/playwright/node_modules/playwright'
$env:MEMORY_ACCEPTANCE_URL='http://127.0.0.1:8011'
node docs/artifacts/memory-phase7/browser-acceptance.cjs
~~~

浏览器脚本会修改并删除夹具学生的记录，请仅对上述隔离服务执行。重复验收前重启夹具服务创建新数据库。服务运行期间保留临时数据库，正常退出后由 TemporaryDirectory 清理。

## 后续建议

记忆基础改造六阶段及本轮浏览器联调已完成。下一步可评估跨会话个性化效果：偏好是否影响新回答、误区更正是否被后续教学尊重、练习证据是否进入合适的教学决策。题目到技能/误区的可靠映射、掌握估计与策略阈值校准仍需单独完成；本轮未补齐这些能力，也未恢复之前停止的真实 API 测试。
