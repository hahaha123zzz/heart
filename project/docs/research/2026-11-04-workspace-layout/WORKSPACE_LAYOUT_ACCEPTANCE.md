# 学习工作台布局交付与验收

日期：2026-11-04。

## 已接入

- “继续学习”和“教材阅读”合并为“学习”；旧 home 请求映射至 course。
- 最左侧固定图标导航，悬停与键盘聚焦显示名称；旁边为新对话和真实历史会话列表。
- 教材默认收起，正文与输入区居中；展开后恢复教材/对话分栏、目录和比例调整。
- 教材采用延迟首次挂载。折叠保留阅读器；展开走现有 resize 机制，来源跳转会自动展开。
- 三条浅色建议分别填入学习安排、继续学习和复习提示词，由用户编辑、发送。
- 建议收起教材时位于输入框下方，展开时位于上方；两种状态共用关闭标记。
- 点击叉号、发送首条消息或恢复已有聊天后隐藏建议；当前标签刷新与新建会话不重新显示。新开空白标签可显示。
- 移除左上角搜索表单及事件绑定，保留检索 API。

## 修改边界

本任务修改 frontend/index.html、frontend/app.js、frontend/workspace.js；新增 frontend/workspace-layout.css。新增 web_api.py 的只读 conversation-sessions 接口，以及会话身份和浏览器测试。

未替换 PDF.js、未重建教材索引、未修改正式数据库结构、未重写 AgentLoop 或评分逻辑。其他窗口已有的教学提示词、chat-renderer、styles.css、workspace.css 和阅读器变更均保留。

历史会话列表按真实 session_id 分组，最多显示最近 100 个会话；无 session_id 的旧记录保留在学习记录中。显式打开同一历史会话允许多标签共用，后台任务仍依赖现有 revision 和任务 guard 处理冲突；不会因 BroadcastChannel 自动改号而把历史与发送目标分离。

## 浏览器证据

预览服务：http://127.0.0.1:8066/。

实际运行 main:app，数据库为应用目录下 `.runtime/workspace-layout/acceptance.sqlite3`，与正式库隔离。workspace-ui 的两组历史仅用于验收；不是用户的真实学习数据。

执行：

```powershell
$env:NODE_PATH='C:\Users\free\.agents\skills\playwright\node_modules'
node tests/browser/workspace-layout.cjs
```

11 组交互全部通过，pageerror 为 0：

1. 默认收起、单一学习入口、无搜索入口；默认不请求 PDF。
2. 建议填入草稿、不自动发送，教材展开时移动至输入框上方。
3. 连续展开/收起 10 次，PDF 请求数不增加、Canvas 节点不变、页码 3 和 125% 缩放保留。
4. 关闭建议后，跨教材状态、刷新及新建会话保持隐藏。
5. 从隔离数据库恢复真实历史，会话切换与刷新后身份一致。
6. 第二标签显式打开同一历史，不会导致第一标签重新编号。
7. 收起状态点击上标来源、打开教材，展开并到达目标页。来源状态核验使用夹具，不据此声称真实来源校验通过。
8. 生成中禁止切换；首次发送隐藏建议；发送失败后不重新显示。
9. 375px 窄屏无横向溢出，列表抽屉及教材/对话切换可用。
10. 新标签空白会话可重新显示建议。
11. 设置、学习记录、练习页面及习题目录入口可用。

应用目录下证据：

- `.runtime/workspace-layout/browser-results.json`
- `.runtime/workspace-layout/desktop-closed.png`
- `.runtime/workspace-layout/desktop-open.png`
- `.runtime/workspace-layout/mobile.png`

浏览器的发送成功和失败均使用 SSE/HTTP 夹具，没有调用真实大模型；历史列表、历史恢复、目录和 PDF 来自隔离服务真实接口。

## 相关回归

- app.js、workspace.js、浏览器测试语法检查通过；web_api.py 编译检查通过。
- `tests.test_conversation_identity` 的 3 项隔离 SQLite 测试通过，包含会话分组、排序、学生隔离和旧历史兼容。
- `node tests/chat-transport.cjs`：15 项通过。
- `node tests/response-composition.cjs`：通过，覆盖正文、来源、内容块与安全展示。
- Python 联合回归：52 项通过，使用以下显式测试配置：

```powershell
$env:RESPONSE_COMPOSITION_ENABLED='0'
$env:RESPONSE_BLOCK_STREAMING_ENABLED='0'
.venv-runtime\Scripts\python.exe -B -m unittest tests.test_conversation_identity tests.test_conversation_context tests.test_q3_task_loop -q
```

必须保留的首次失败：沿用当前环境内容组合配置时，上述 52 项中有 3 项 ask_user 恢复测试返回 model_unavailable。关闭内容组合及块流式开关后 52 项通过；失败与内容组合配置有关，具体失败分支未进一步定位，不构成默认配置真实 ask_user 已通过的证据。本任务未改 AgentLoop 解决此问题，也未修改正式开关。

## 初轮剩余验证与发布状态（历史记录）

布局与建议交互已实现并完成上述页面验收。未重新执行真实大模型的 PDF 选区、ask_user、多媒体、学习计划全链路；未完成独立可访问性审计或实际触摸设备测试。

未提交、未 push、未切换正式服务。预览服务使用隔离数据库，正式数据保持原状。现有服务若直接读取当前工作区的静态文件，刷新后可能读取新前端，但新增后端会话接口需要运行新代码的服务。


## 最终收尾记录（2026-11-04）

本节更新前面的初轮状态，不覆盖或改写失败证据。

### 修复与提交

代码提交 `1a7905b`，已推送至 `origin/codex/ta5-acceptance-20261029`，尚未合入 main。

1. 原 3 项 ask_user 失败已实证定位：普通文本脚本模型受到本机内容组合开关影响，进入 JSON 格式修订后耗尽脚本。旧协议测试现在显式固定旧协议配置，并新增开启内容组合的暂停/恢复测试；正式开关未关闭。
2. 真实图5-2联验发现“不要跳转”仍触发页面定位：路由与主循环的重复关键字判断已统一为 reader_requested；保留肯定的跳转指令，否定的跳转不再强制 reader_goto，图像解释不再直接变成导航。
3. 真实模型按既有图片协议输出 media 标记时被内容块当作外链拒绝。现在仅允许当前 claim 所绑定来源中的原图 ID，未知 ID、普通外链、HTML 和纯图片无正文仍拒绝。新增安全边界测试。

### 干净提交副本验证

为排除其他窗口的并发改动，app.js、index.html 和 agent_loop_service.py 按差异分离后提交；其他窗口的图片预览、进度样式、教学技能和阅读器修改未带入。本次测试使用提交导出的独立代码副本。

- Python 联合回归：90 项通过，日志 `.runtime/workspace-layout/committed-regression.log`。
- 浏览器布局交互：11 组通过，pageerror 为 0；在 8067 已提交副本服务复验。
- 流式传输：15 项通过；内容块前端测试通过。
- 混合主工作树后来出现 5 失败/3 错误，保留于 `final-regression-complete.log`。同期其他窗口正在修改同一工作区；独立提交副本 90 项通过。没有为消除该混合树失败而覆盖别人的代码。

### 真实模型与页面

用户已明确授权本次向 api.deepseek.com 发送合成问题及必要教材片段、插图；不读取真实用户学习历史。

已提交副本的实际结果：

| 用例 | 结果 | 证据 |
| --- | --- | --- |
| 学习安排生成 | 待确认计划正常显示，约 8.2 秒 | `live-1793777267146/plan.json` |
| 刷新后确认安排 | 页面恢复计划并确认，进入 active，生成当前讲解 | 同目录 `plan-confirm.json` |
| ask_user | 真实问题卡暂停，约 2.8 秒；答复后同一任务继续并保存讲解 | 同目录 `ask.json`、`ask-resume.json` |
| PDF 选区解释 | 真实坐标经过预览接口，真实模型回答保存，约 6.8 秒 | 同目录 `selection.json` |
| 图5-2解释 | 实际原图回答保存，约 7.3 秒，原图身份与 model_saw_pixels=true 返回 | `live-1793777161191/image.json`、`image.png` |

以上路径均相对于应用目录 `.runtime/workspace-layout/`。选区用例通过当前页面 askPDFSelection 接入真实坐标，并非实鼠标拖拽全过程。初轮不带精确工具触发词时模型普通文字提问、图像被误路由、media 被拒绝等失败均保留在前序 live 目录。SSE 原文采集曾因浏览器读取已取消流报错，之后使用页面状态与任务持久化结果复核，未把脚本错误当作模型失败。

### 部署

- 运行代码：`E:/项目/heart/.runtime/workspace-layout-release-1a7905b/project/integration/discrete-math-tutor`。
- 重启入口：原应用目录的 `.runtime/workspace-layout/start_release.py --port 8000`，使用原项目虚拟环境启动。
- 正式配置从原项目 .env 在进程内加载，没有向仓库复制密钥。
- 正式学习库沿用原数据库路径；切换前确认执行中任务为 0，再用 SQLite backup 备份，quick_check=ok。
- 最新切换前备份：`.runtime/workspace-layout/backups/pre-switch-20261104-153308.sqlite3`。
- 教材为本机副本，未上传；初次用 junction 被 LightRAG 输入校验拒绝，已改为普通目录复制，没有绕过 reparse point 校验或重建正式索引。
- 切换与健康检查记录见 `WORKSPACE_LAYOUT_DEPLOYMENT.md`。

未进行人工教学质量标注、独立 WCAG 审计或实体触摸设备测试；不宣称覆盖所有输入或所有 Agent 工具。
