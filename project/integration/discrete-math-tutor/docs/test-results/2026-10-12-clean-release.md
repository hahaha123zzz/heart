# 2026-10-12：撤回七个未完成补丁后的整理版

## 版本与范围

基线是 `heart-main-accounts-mindmap-20261011.zip`。当前源码中的七个未完成教学补丁已撤回，并逐文件核对为该交付包的原始内容；账号与聊天历史问题图功能保留。

撤回的文件：

- `agents/conversation_router.py`
- `agents/quality_checker.py`
- `agents/response_generator.py`
- `knowledge/textbook.py`
- `database/models.py`
- `database/repository.py`
- `memory/memory_manager.py`

撤回前的七个源码文件已备份到本机 `backups/unfinished-7-patches-20261012.zip`，该备份不随交付包发布。此前数据库备份、原始源码 ZIP、账号与历史图 ZIP，以及另一个 teaching-fixed ZIP 均保留。

本次额外修改仅为 `.env.example`、`3-start-api.bat`、`README.md` 和本说明：配置示例默认 `LLM_MOCK=0`，启动提示说明真实模型与固定模拟模板的区别。未引入新教学功能，也未将其他 teaching-fixed 包中的教学改动合入。

## 验证结果

Python 3.11，所有涉及学生数据的回归均使用独立临时 SQLite 数据库，不调用真实 LLM。

| 验证 | 结果 |
|---|---|
| `tests/test_account_history.py` | 1 个综合测试通过：注册、登录、账号隔离、跨浏览器恢复、CSRF、退出与会话到期、历史节点和原始问答关联、聊天 SSE |
| `tests/test_interactive_practice.py` | 10 项通过：练习草稿、隔离、提交历史、幂等与失败恢复 |
| `test_reader_progress` | 6 项通过：教材阅读、图片/公式资源和流式接口 |
| `test_pdf_selection` | 7 项通过：选区校验、学生记忆隔离和引用保存 |
| `test_figures`、`test_multimodal`、`test_figure_focus` | 共 10 项通过 |
| `tests/test_legacy_migration.py` | 旧库迁移前备份、无损迁移检查通过 |
| `test_discrete_math.py` | 原有话题切换、卡住降难度、误解去重和记忆保存检查通过 |

共 34 项框架测试通过，另有 2 个断言式检查脚本通过。流式失败用例主动注入异常并检查错误事件，因此测试日志中的 `Chat turn failed` 为预期行为。PDF 测试出现 AnyIO 资源关闭警告，未导致测试失败。

在独立临时数据库、本机 8766 端口启动 Uvicorn 后，`/health` 返回 `status=ok`、`version=0.9.0`、`mock_mode=false`；首页、app.js、history-map.js 和 styles.css 均返回 200，JavaScript 和 CSS MIME 正确。未登录的 `/api/auth/me` 返回 401。检查完成后测试服务已关闭。

### 启动脚本的实际运行补验

随后复现到 Windows CMD 直接运行 `3-start-api.bat` 时将多行误读为命令片段，导致服务未启动。该脚本原为 UTF-8、仅 LF 换行；备份后仅将行尾规范为 CRLF（26 个 CR 与 26 个 LF），脚本逻辑未变。再次通过 CMD 运行同一个脚本，正常显示 Python 3.11.8、Uvicorn 启动成功，8000 端口的 `/health` 和首页均返回 200，浏览器成功加载并恢复已登录账号。交付 ZIP 中的启动脚本已同步为 CRLF。

## 使用与验收边界

1. 解压交付包，进入 `heart-main/project/integration/discrete-math-tutor`。
2. 首次在自己的机器运行时，用 Python 3.11 或 3.14 安装 `requirements.txt`。
3. 复制 `.env.example` 为 `.env`，填入自己的 DeepSeek API Key，保持 `LLM_MOCK=0`；已有 `.env` 应保留并核对配置，不直接覆盖。
4. 双击 `3-start-api.bat`，通过网页注册或登录正式账号。
5. `/health` 的 `mock_mode` 应为 `false`。`LLM_MOCK=1` 只检查离线流程，固定模板不能用于验收教学质量或历史问题的语义分叉。

本轮未进行真实 DeepSeek 多轮教学或语义关联验收；启动脚本补验仅加载本机配置并检查网页服务，不向大模型发起请求。此次撤回也不意味着此前报告的教学重复与引用问题已被修复；教学改进留待与队友统一版本和分工后处理。

交付包不含本机密钥、数据库、虚拟环境、补丁备份、测试缓存或临时 PDF 裁图。现有本机账号和学习数据库保留原样。
