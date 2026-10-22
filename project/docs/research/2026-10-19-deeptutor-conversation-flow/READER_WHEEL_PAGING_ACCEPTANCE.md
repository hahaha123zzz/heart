# 中间教材阅读器滚轮翻页交付

2026-10-22（浏览器证据使用 UTC 时间；本地为 2026-10-22 夜间）。

## 分支、范围与调用链

- 分支：`codex/reader-wheel-paging`。
- worktree：`E:/项目/heart-worktrees/reader-wheel-paging`。
- 实际基线：`2ae1e5fd9618ea80a999a22cb30339a153e15d0c`；没有采用旧 LightRAG 分支基线。
- 已只读阅读主工作区 `READER_WHEEL_PAGING_PLAN.md`；主工作区对应 reader、构建目录和浏览器测试无未提交改动。
- 已核对唯一实际挂载调用：`frontend/app.js::syncPDFReader → TextbookPDF.mount → Reader`。
- 实现：`viewer.container` 的局部、可取消 wheel 监听 → 现有 `jump` → PDF.js `pagechanging` → 现有 `pdf-position` → 原 `Workspace` 保存/恢复。
- 不改 `frontend/app.js`、`workspace.js`、学习状态、LightRAG、TaskService、Q5、数据库或公共样式。

## 修改文件

以 `project/integration/discrete-math-tutor/` 为根：

| 文件 | 改动 |
|---|---|
| reader/src/reader.jsx | 绑定正文 wheel、选区/拖动保护、实时页码边界、监听清理 |
| reader/src/wheel-paging.js | 纵向手势累计、单位归一化、空闲复位及惯性抑制 |
| reader/src/wheel-paging.test.js | 5 项确定性测试 |
| tests/browser/reader-wheel.cjs | 真实前端、真实 PDF、独立端口的可重复浏览器验收 |
| frontend/pdf-reader/reader.js | `npm run build` 生成的实际页面入口 |

另附本交付文档及 `READER_WHEEL_PAGING_ACCEPTANCE.json`。依赖/锁文件无修改；构建后的 CSS、PDF.js chunk、worker、字体、cmaps 与基线字节一致，因此无重复提交。

## 行为

- 正文中部普通纵向滚轮立即调用相邻页跳转，首尾仍拦截该动作但不越界，不循环、不跨章、不推进学习点。
- 累计 8 CSS 像素才触发；line/page 单位归一化。每次事件延长手势；连续事件只翻一页，空闲超过 280 ms 后接受新手势。圈选结束后同一手势剩余惯性也不触发翻页。
- Ctrl/Meta/Shift、以横向为主的动作、输入控件、文本选区、鼠标/触摸框选及选区菜单不触发分页。
- 正文以外无 wheel 监听。保留 `.PdfHighlighter { overflow:auto }`，放大后页内剩余内容仍能通过滚动条访问。
- 使用最新 `viewer.currentPageNumber` 和 metadata 引用；组件卸载移除 wheel/pointer/blur 监听，不积累重复监听。

## 隔离验证与证据

使用可见 Microsoft Edge / Playwright、1550×1050 视口。启动独立 127.0.0.1 临时端口，加载本 worktree 的实际 `frontend/index.html`、`app.js`、`workspace.js` 和新构建 reader。测试学生 `reader-wheel-isolated-student`。

仅从当前服务只读抓取课程目录、reading-map、第 1/2 章首节 metadata 及 PDF 到内存。所有学生接口、写接口由独立测试服务返回测试桩；不向正式服务转发，不使用学生数据库，不进行模型调用。不把该测试写成完整后端或真实硬件验收。

最终完整运行：`artifacts/reader-wheel/2026-10-22T15-52-30-011Z/`。

- `results.json`：11/11 组通过，浏览器 `pageerror=[]`，包括源码/教材 SHA256 和请求清单。
- `events.json`：包含刷新前后的 wheel 及原 `pdf-position` 事件。
- `trace.zip`：浏览器截图、DOM 快照、操作及网络请求。
- `citation.png`：真实章节标题引用坐标，已验证高亮在正文可见范围。
- `zoom-lower-half.png`：200% 下通过原滚动容器到达页下部（脚本操作原 scrollTop，未以真实设备拖动滚动条）。
- `final.png`、`last-state.png`：最终页面。

11 组覆盖：正文上下翻页；小幅累计及 80 个连续惯性事件；按钮/页码输入与首尾；局部作用域及修饰键/横向；目录和聊天实际 CDP 滚动；文字层选区与取消；鼠标框选拖动与菜单；真实教材标题引用；200% 缩放和页下部可达；现有 Workspace 刷新恢复页码/缩放；换章、重复挂载、卸载后重挂及 page_map 来源页映射。

全部运行摘要保存在随提交的 JSON，不仅保留最终结果：

1. 首轮 10/10；初版引用坐标为合成坐标。
2. 手势边界补强后 10/10。
3. 换用真实已核验章节标题坐标后 10/10。
4. 增加实际目录滚动测试时 4 组通过、第 5 组超时，后续未运行。原因是测试错误地读取 `#course-tree.scrollTop`；CSS 中真正滚动的是其父节点 `#course-panel-body`。原失败 trace/results 保留。
5. 修正验收节点后 11/11，生产代码未为此修改。

初始三次运行的事件文件只保存最后一次刷新后的文档事件；最终脚本已将事件发送给宿主统一汇总，最终运行保留完整事件。所有本机截图/trace 留在 artifacts，不提交教材 PDF 或大量运行产物。

## 复验命令

在本分支 `project/integration/discrete-math-tutor/reader`：

```powershell
npm ci
node --test src/wheel-paging.test.js
npm run build
```

本次为保持环境隔离，将主工作区已安装、与锁文件一致的 node_modules 复制到新 worktree 后构建；`npm ls --depth=0` 无错误。未重新下载或升级依赖。

依赖版本：React/ReactDOM 18.3.1，react-pdf-highlighter 7.0.0，PDF.js 4.4.168，Vite 6.4.1。

在应用根目录，已安装 Playwright 时：

```powershell
$env:NODE_PATH='C:/Users/free/.agents/skills/playwright/node_modules'
$env:READER_FIXTURE_SOURCE='http://127.0.0.1:8000'
node tests/browser/reader-wheel.cjs
```

脚本只读读取 fixture source 的课程数据，自行分配验收端口；每次结果写入新的 UTC 时间目录。可选 `BROWSER_PATH` 指定浏览器，`READER_WHEEL_ARTIFACTS` 指定证据目录（自行指定目录时注意避免覆盖）。本次同时通过 Playwright 技能 `run.js` 执行。

## 交付与当前服务状态

- 集成窗口采用本分支交付提交即可；包括页面实际加载的 `frontend/pdf-reader/reader.js`，不需要改共享调用方。
- 新 reader.js SHA256：`cae56d95ffe3c022ce12699235f7c8d1f8db105f20a068b9d9633c89a98c6992`。
- 只读检查当前 8000 服务 `/static/pdf-reader/reader.js`：SHA256 为 `0a16910c957b242117ae9396999b5a471d7cc8ade9af8d8da1ef66d2c22f97c5`，与新构建不同，故当前正式页面尚未实际生效。
- 本窗口没有合并 main、部署或切换现有服务；验收临时服务器已关闭。
- 集成后请从实际服务读取该文件复核哈希并刷新浏览器；如浏览器仍缓存旧入口，需强制刷新/按部署惯例失效缓存。当前 index.html 的资源版本参数未改，以避免共享文件冲突。
- 回退：恢复该提交之前的 reader 源码与构建入口，不涉及数据迁移。

## 已知限制

- 未使用真实鼠标/触控板硬件测试。CDP wheel 和合成事件序列已覆盖行为，但不同设备的惯性间隔仍需实机确认；280 ms 空闲分组是浏览器没有标准手势结束事件时的本地判定。
- 未验证真实触屏设备/跨浏览器；保留原触屏逻辑。本轮不验收聊天模型、学习路径或 LightRAG。
