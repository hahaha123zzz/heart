# 教材阅读器卡顿与重复计算实测

日期：2026-10-25。结论：**本轮最明确的等待来自小节接口及其逐图全书发布校验；同章重复挂载、全书Canvas渲染、相邻页完全未预渲染和事件监听泄漏均未被本次样本证实。** 本轮只测试/调研，未修改生产阅读器或后端实现。

## 1. 测试对象与方法

- 实际服务 `http://127.0.0.1:8000`，PID49972，cwd `.runtime/q4-switch-20261024/release`，发布记录e8edcf4；PID为测试时快照，不可据此停未来进程。
- 实际reader.js SHA256 `cae56d95ffe3c022ce12699235f7c8d1f8db105f20a068b9d9633c89a98c6992`，原PDF.js及PDF Worker版本4.4.168。主线8d62c30；核心后端热点函数AST与运行副本相同。
- Microsoft Edge可见窗口，1550×1000，DPR1；3轮完整复核。每轮新浏览器上下文并清浏览器HTTP缓存，不清操作系统/服务器缓存；同机存在其他任务，不作为独占硬件基准，不作p95结论。
- 页面、接口、PDF、字体、worker均来自实际8000，未mock教材/API响应。使用独立`reader-perf-20261025`测试身份，无AI调用；产生了该身份的普通阅读浏览记录，没有读取用户现有对话。
- 引用测试在测试浏览器内注入一个带实际PDF版本和当前文字坐标的诊断引用，点击真实“打开教材”处理器，并走实际citation-state校验。**不是新生成AI回答，也不证明所有历史引用的数据质量**。
- 浏览器侧记录资源/TTFB/字节、worker协议、真实PDFViewer事件、渲染函数、长任务、rAF间隔、文档对象与监听器；采样带观测开销。坐标/高亮函数计时为同步部分，不代表全部异步布局成本。

### 原始证据

应用/仓库根 `.runtime/reader-performance-20261025/`：

- `listener-verified/report.json`：最终三轮完整记录。
- `listener-verified/summary.json`：最终聚合与每轮细项。
- `listener-verified/runtime.json`：实际进程与静态资源哈希。
- `listener-verified/trial-1.cpuprofile`至`trial-3.cpuprofile`：可在DevTools Performance加载的主线程采样。
- `listener-verified/reader-after-scroll.png`：滚动后截图。
- `backend-profile.json`：独立进程直接剖析当前发布代码的六组后端样本；未import main或调用模型/数据库。
- 根目录report.json保留首轮观测；`verified/`保留第一次修正引用等待的记录。最终结论使用`listener-verified/`，不覆盖历史尝试。
- 诊断脚本在本机临时目录 `C:/Users/free/AppData/Local/Temp/playwright-test-reader-performance-20261025.js`，通过Playwright技能run.js运行，URL与证据目录可用环境变量指定。

## 2. 五条用户路径的结果

| 路径 | 最终三轮结果 | 判断 |
| --- | --- | --- |
| 打开页面→第一页面Canvas绘制完成 | pagerendered中位1.56s，范围1.28—1.60s | 大部分发生在reader mount前；初始小节API约0.84—1.03s。此前最早观测一次4.8s中，小节接口单次TTFB约3.49s，不能全归为页面渲染 |
| Canvas绘制完成→文字层完成 | 89.6/132.4/129.1ms，中位129.1ms | 有额外成本，但当前不是主要秒级等待；实际Range能选中文字 |
| 同章点击另一小节→目标页与文字就绪 | 0.867/1.091/1.099s，中位1.091s | 无新GetDocRequest、无新worker；主要重新请求小节API；目标页本身约几十毫秒完成新渲染 |
| AI引用处理器→高亮与完成回执 | 首次中位0.978s；同引用重复中位0.872s、0.798s | 无重新解析整文档；每次重复citation-state和selectSection→小节API才是主要等待 |
| 滚轮/普通滚动→稳定页面 | 12次独立滚轮翻页、12步scrollTop测试完成，无滚动阶段>50ms主线程长任务 | 固定输入间隔占总测试时间，4.1s不代表单次翻页卡4.1s；没有捕获到持续滚动冻结，不能否定真实设备其他手势场景 |

跨章到第二章中位350ms，返回第一章中位1.417s。第二章第一节没有额外图片列表，API只需几毫秒；返回第一章同时经历重新加载文档与较慢小节接口。

## 3. T0—T5时间线

以下为最终三轮的各时间点中位数，单位ms，相对navigation开始。各点的独立中位数相减不等于同一轮阶段中位数；阶段差以配对样本计算。

| 时间点 | 观测事件 | 中位数 |
| --- | --- | --- |
| T0 | 页面navigation；交互用浏览器click和phase marker | 0 |
| T1 | window.TextbookPDF.mount入口 | 1210.4 |
| T2 | PDF Worker返回GetDoc，文档元数据加载完成 | 1335.5 |
| T3 | 首次GetOperatorList请求，绘制准备开始的代理事件 | 1362.1 |
| T4 | 目标页面pagerendered | 1557.4 |
| T5 | 目标页面textlayerrendered | 1689.8 |

边界：T1记录的是mount调用，不是React commit精确结束；T3是取绘制指令的代理点，不是GPU raster开始。单纯检测Canvas存在/data-loaded会早于绘制完成，因此原始`first_visible_canvas`不作为正式首屏绘制指标。文字可选择另经真实DOM Range验证；不是只检查文本层DOM存在。未测物理显示器出光时间或GPU compositor帧。

## 4. 已证实的主要热点：按每张图重复全书发布校验

实际调用链：

`GET /api/course/chapters/{chapter}/sections/{section}`
→ `web_api.course_section`
→ `section_figures`
→ 对每张图调用`Figure.public`
→ `course_release.binding`
→ `validate(refresh=True)`
→ `clear_cache`（同时清visual缓存）
→ `snapshot`扫描11章、PDF/原件/图片/索引并统计visual。

**一个返回两张图的导航请求会做两次全书发布扫描。即使PDF模式不展示这份figures数组，也要等待它。**

独立只读剖析第一章第一节热样本：

| 项目 | 实测 |
| --- | --- |
| section_figures返回数量 | 2 |
| section_figures总耗时 | 725.34ms |
| 两次binding/validate/snapshot累计 | 约713ms，约占该组件98% |
| Path.read_bytes调用 | 1,016次 |
| 累计读取字节 | 262,874,930 bytes，约263MB（十进制），并非263MB网络下载 |
| get_chapter/get_section/section_blocks/section_pdf | 热样本各约0.01—0.02ms |

独立进程首次该组件约2.01s，累计文件读取约1.42GB，含初次visual加载和校验；不等于正式服务冷启动总时间。第十一章第一节1张图约371—374ms，508次读取；第二章第一节0张图约0.01—0.02ms且无该扫描读取。

cProfile包含计时和读取观测开销，独立进程缓存也不等同服务进程；但实际HTTP第一章秒级、第二章毫秒级的差异与调用链一致。其中特别明显的是本地Windows路径resolve、反复JSON/图片清单处理和哈希，并非仅文件读盘时间。

已对Figure、section_figures、binding、validate、snapshot、SourceVisual做AST对比：运行副本与主线实现相同，不能认为部署最新main便自然修复此热点。

## 5. 生命周期逐项核对

### 5.1 createRoot、getDocument、Worker

- `window.TextbookPDF.mount`内部以host DOM为key存Map，同一host复用ReactRoot。每次mount调用不等于每次createRoot。
- PdfLoader只在初次挂载/URL变化load；同章切小节和重复引用，实际GetDocRequest与worker.new均不增加，文档对象仍为同一个。
- 章节1→2→1会创建3个PDF文档和3个worker；返回旧章没有应用层已加载文档缓存，约1.27MB的第一章PDF再次请求。
- 实际chunk初始化会为文档各页发GetPage：第一章42、第二章34。GetPage是取得页面对象/元信息，不能把它当42页Canvas均已绘制。

### 5.2 监听器

同章、跨章、返回旧章和重复引用后，window/document的wheel相关、resize、keydown、selectionchange、pointerup等观测有效数量保持稳定；当前reader的wheel为1。

最初只统计add/remove时误见递增；继续核对发现PDF.js通过AbortSignal自动清理。最终观测纳入signal.abort后计数稳定，**本轮不报告全局监听器泄漏**。按多个DOM合并的scroll计数不能作为内存泄漏证据；未做长时间heap retained-object检查。

## 6. 相邻页预渲染、文本/高亮重复工作

- 在约320ms间隔的12次滚轮翻页中，三轮共36个目标页在pagechanging前都已有pagerendered记录。已有PDF.js渲染队列确实预先准备相邻页，不是每翻一次才从零绘制。
- 该结论限定正常节奏；未覆盖极快连续手势、真实触控板惯性、跨浏览器和高DPR。
- react-pdf-highlighter的componentDidUpdate通过highlights引用变化触发renderHighlightLayers；Reader每次生成新highlights数组，空数组也可能引发遍历。
- renderHighlightLayers按整份文档页数扫描，renderHighlightLayer又计算分组，确有重复工作。最终一轮全流程观测68次renderHighlightLayers、434次groupHighlightsByPage；前者同步累计约9.8ms，后者约0.7ms，坐标转换20次累计约0.2ms。它是可清理开销，但无法解释每次引用约0.8—1秒。
- 引用入口每次selectSection后先renderContent/syncPDFReader，再设置pdfFocus并再次syncPDFReader，存在重复mount调用/高亮更新；没有证据显示同PDF重新getDocument。
- 初始Canvas后文字层约0.09—0.13s，未观察到切小节导致全书文字层重新生成。

## 7. 页面数量与下载

- 第一章42个page容器不等于42张已渲染Canvas。测试峰值10个Canvas，总约7,917,000像素，RGBA基础缓冲约31.7MB；最多约4,101个文本span。该数字不包含全部浏览器/GPU内存。
- 滚动后保留约15—17个访问过页面的高亮根/文本相关结构，值得在更长会话做内存观测；本轮无持续长任务证实“全书一次绘制”导致冻结。
- PDF请求实测200全文件流与206范围请求共存，Range有效；最终组PDF请求最大约44ms。某些Range与全文件流字节有重叠，不能把每个同URL请求当重新解析。
- 文件响应Cache-Control为no-cache，跨章返回本次确有网络字节和新文档；no-cache允许重新验证，不等于no-store。后续可评估版本化URL/ETag策略，必须保留换版失效。
- 每上下文reader主模块没有在切小节/引用时重复下载；跨章worker会重建。控制台无pageerror，未见worker版本不匹配/失败退化证据。
- 首屏还加载约1.15MB reader脚本、1.55MB reader样式及MathLive/Cytoscape等资源；最初观测MathLive下载约1.55s。它是启动负担，但样本中后端小节TTFB更显著，不能仅凭包大小推断主线程被其阻塞。

## 8. 修复优先级建议（未实施）

1. **P0：把发布身份获取从逐张Figure.public移出，至少同一请求只计算一次。** 显示PDF所需轻量导航与整份图表列表分离；保留实际图片读取、引用发布和换版时的内容校验，不靠永久缓存ready跳过身份检查。
2. **P0：同一小节引用跳转复用当前section/PDF状态。** 完成必要citation-state检查后直接更新focus，不反复拉完整小节；需要换小节才加载。让渲染/定位一次提交，避免先清focus再连续mount。
3. **P1：有限容量复用最近文档/Worker。** 优先评估当前章与上一章，配销毁/取消和版本键，避免为11章各保留整套Canvas/文本造成内存增加。
4. **P2：稳定highlights/metadata引用，仅更新有变化的高亮页。** 先按真实耗时复验，不能将每次毫秒级扫描包装成主要秒级收益。
5. **P2：启动资源按需加载与版本缓存。** 与现有构建/资源版本一致；已存在的相邻页预渲染先保留，不另叠加全章预渲染。

修复后复用相同脚本和实际教材，重复五条路径；保持选择、框选、引用、滚轮、缩放、版本失效与图片定位，不以删文本层或校验换速度。

## 9. 限制与未做项目

只覆盖实际部署的第一/二章以及后端第十一章组件，不是11章浏览器全覆盖。没有新AI回答、真实用户历史引用、移动端/触控板实机、跨浏览器、弱网/高DPR、长期内存泄漏或GPU compositor测试。浏览器CPU采样和50ms DOM观测有开销；只用3轮报告范围/中位数。

没有修改生产代码或重启服务，没有替换PDF.js，没有删除任何真实用户记录。临时学生的阅读记录保留，未将其作为学习/掌握证据。初轮47ms重复引用是未等待异步处理结束造成的测量缺陷，已修正并单独保留原记录，不计入最终引用耗时。
