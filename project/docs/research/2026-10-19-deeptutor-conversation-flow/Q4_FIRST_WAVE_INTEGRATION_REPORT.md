# Q4 首批工具集成与分层验收交付

日期：2026-10-24。分支：`codex/q4-first-wave-integration`。
工作目录：`E:/项目/heart/.worktrees/q4-first-wave-tools`（沿用原独立目录，原工具分支仍保留）。

## 1. 本次接入的稳定版本

- 工具模块：`2dd14ee60dc2fb275c2fa8d9731d90da895cf3c5`。
- 学习安排：main 基线 `be7cc9c7b18530b2660d5df33cede4efbd76e10f`，包含 `9d5f5f6`、`79becb1`、`9cb5431` 等已提交功能。
- 流式：最初合入 `1b5aba8`；交付前同步最终稳定 `47a9c363ff154d354fe4257267490e62854a0819`。
- 集成检查点：`77224ca`、`27cc256`、`7db64f1`。最终交付提交以本分支 HEAD 为准。

没有复制其他窗口未提交代码。两次 frontend/app.js 合并冲突均只涉及错误状态列表，保留学习安排错误、取消、中断、长度不足和超时状态。本次磁盘曾耗尽，删除的是本窗口新建且成果已提交的重复 worktree；原目录、主项目、其他窗口和所有稳定提交均保留。

## 2. 已接通的工程能力

### TW2：真实入口、来源、状态发布

- 在 run_agent_loop_turn 的实际 extra_tools/extra_scopes/tool_state 中注入当前学生、会话、任务、课程、发布版本、授权文档及只读服务。
- material_outline、read_material、read_source、read_memory、kb_files、reader_goto 有真实 schema 和执行实例；仍由既有 ScopedToolRegistry 和唯一 dispatcher 执行。
- retrieve_course/ContextualRetrieveCourseTool 与精读共用 register_sources、编号游标及去重。检索正文向模型提供可补读的来源ID；同一段原文不会因一个结果带页码、另一个只有坐标而多分配编号。
- 暂停恢复重建服务并重新核验来源，保留原编号；服务、锁、数据库 session 不写入快照。
- 对“刚才/这个来源”的明确指代，只读取同学生、同会话最近已发布的引用，核验当前文档范围后重新附加到本轮；最多4条、总正文12000字符，不把任意历史聊天升级为证据。
- 页级证据的最终发布去重加入实际页和证据ID，避免不同页被合为一项。重新精读相同来源不抹去已有原图和像素接收标记。
- 纯目录、资料盘点、画像/偏好、页面请求按宿主识别的任务用途分流，直接用真实工具结果生成正文，不接受模型自报类别绕过事实门禁；所需工具没有成功时拒绝发布。
- 纯结构化状态拿到结果后结束模型循环，不额外调用一次模型改写；混合讲解仍须先取得教材证据，要求偏好时还须成功读取记忆。
- 当前课程技能清单加入准确名称与短描述；心理学排除 finite-structures，同时在 read_skill 执行期检查课程白名单。读技能不代表生成图解。
- 目录/画像/跳页标记为学习插问，不让本轮回应把 Q5 或教材游标改成“已讲解”。read_memory 保持现有画像与明确偏好读取，不新增记忆写入或数据库。

### TW3：reader_goto 与页面回执

1. 工具验证当前授权的来源ID或文档/版本/页码，生成稳定 action_id 和 requested 状态。
2. 引句只在该页唯一定位成功时携带真实 rects；找不到引句只定位页，不假高亮。
3. 任务保存成功后，既有 SSE 发 reader_action；前端只在本次请求结果确认后消费。
4. 前端验证当前学生/标签会话、最新消息、页面可见性、阅读选择是否变化、有无用户选区；执行既有 selectSection/syncPDFReader。
5. 必须观察到本次实际 PDF 位置事件确认文档、版本和页码，才上报 applied，否则 rejected。生成请求时不会宣称已到达。
6. 新接口 `POST /api/chat/tasks/{task_id}/reader-receipt` 校验归属、最终 revision、任务有效期、记忆 epoch、实际观察页和文档文件版本；新任务已开始则拒绝旧动作。
7. 回执复用既有 LearningTaskRow.result/TaskRequestRow.result，幂等保存；不新增表、不修改学习掌握度。重复动作、历史显示、收据恢复或事件恢复不会自动重新跳页。

kb_files 仍只列授权的公开阅读 PDF manifest；按章阅读文档数不冒充教材书籍数，不枚举缓存、索引或部署目录。

## 3. 验收结果与实际边界

### 自动化回归

组合脚本 `scripts/check_first_wave_integration.py` 覆盖首批工具、公共入口、来源编号、恢复、Q4底座、Q3循环、流式角色、SDK事件、学习安排、provider参数兼容。临时 PDF 与 SQLite 自行创建，不使用正式学生库。

最终组合回归 **174项通过**；结果、被测源文件SHA256及浏览器和模型摘要见 `Q4_FIRST_WAVE_INTEGRATION_CHECKS.json`。JavaScript transport 11项通过；reader-actions 的重复/恢复/后台/错误页保护检查通过；app.js 与 chat-transport.js 语法检查通过。

新增 SQL 回执专项证明：归属、页码、版本、revision、epoch、新任务拒绝以及回执幂等；回执同时写入既有任务与请求收据，可恢复真实最终状态。

### 真实浏览器/PDF.js

`tests/browser/first-wave.cjs` 使用实际页面、实际编译阅读器和 PDF.js；API 为隔离夹具，PDF由测试生成。

- 第1页自动到第2页，实际位置与 applied 回执一致；引句在页面显示真实高亮。
- 只收到一次回执；刷新并恢复历史文本后不重新执行动作。
- 页面无 JavaScript 异常；截图和原始报告在独立 worktree 的 `.runtime/q4-joint-browser/`。

交付截图另保存在同目录 `Q4_FIRST_WAVE_READER_GOTO.png`。

这是**真实页面、合成API**的浏览器验证，不写成正式服务或真实模型浏览器端到端成功。

### 三条真实模型验收

使用项目配置的 DeepSeek，发送的只有三页自建教材、合成偏好和固定问题，没有正式教材内容、已有聊天、学生记录或密钥输出。

| 问题 | 模型实际工具 | 回合 | 结果 |
|---|---|---|---|
| 第一章目录 | material_outline | 1 | 成功，服务端真实目录正文 |
| 已确认讲解偏好 | read_memory | 1 | 成功，合成已确认“简短”偏好，无教材引用 |
| 读取第2页并引用 | read_material | 2 | 成功，真实PDF原文与 `[1]` 核验通过 |

这次实际发现并修复了兼容缺口：非流式 chat_with_tools 没有与流式 `_stream_call` 一样关闭 DeepSeek 思考模式，`tool_choice=required` 因而返回400。补齐现有参数路径后，三条均通过；另有 provider 单元测试确保其他服务不接收 DeepSeek 专用参数。

旧 deepseek.env 未解析到标准密钥字段，第一次未发出请求；后续使用项目 .env。没有修改任一密钥文件。

## 4. TW4 完成口径

已完成跨窗口代码集成、隔离回归、真实浏览器/PDF.js、回执数据库专项与三条合成数据真实模型验收。

**尚未完成**：正式心理学教材 + 正式服务入口 + 真实模型 + 浏览器的整条联合验收，尤其是跨章插问、真实学习安排、取消/多标签页及混合偏好讲解。此前原工具交付里的正式第一章只读验证仍是独立资产检查，不能与本次测试拼成一条未实际运行的端到端成功。

本次未改 main 工作区、未停止或重启8000服务、未切换部署环境或正式数据库。运行中的页面不会因此自动加载本分支。LOCAL_AGENT_LOOP_ENABLED 仍由既有部署配置控制，没有把工具无条件开放到旧入口。

## 5. 复现

在独立 worktree 的 `project/integration/discrete-math-tutor` 中：

```powershell
& 'E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe' -B scripts/check_first_wave_integration.py
node tests/chat-transport.cjs
node tests/reader-actions.cjs
$env:PLAYWRIGHT_MODULE='C:/Users/free/.agents/skills/playwright/node_modules/playwright'
node tests/browser/first-wave.cjs
```

真实模型脚本会发送合成数据并使用配置中的API：

```powershell
& 'E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe' -B scripts/check_first_wave_model.py --env-file E:/项目/heart/project/integration/discrete-math-tutor/.env
```

## 6. 后续部署交接

集成负责人从本分支稳定提交接入；本分支历史已包含学习安排和流式稳定提交，不能再把相同提交手工复制覆盖一次。先确认教材资产路径、原有独立数据库和运行配置，再做正式教材联合验收与服务切换。

回滚须同时撤销公共入口、SSE动作、前端脚本引用和回执路由，不能只删除新模块。没有数据库 schema 迁移或教材索引重建需要回滚。


## 2026-10-24 后续状态（替代上文未部署说明）

已完成正式教材五类真实问答分步验收及两处精读、一处用途识别修复，部署固定提交e8edcf458fa1b76625952250671f35d5a78c1ccd到8000。原有数据库记录逐表核验无丢失或改写。具体被测版本、剩余TW4边界、教材staging状态和回滚路径见Q4_FORMAL_TEXTBOOK_ACCEPTANCE.md及同名JSON。
