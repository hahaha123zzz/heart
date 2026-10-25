# 教材原图“返回教材”实施与交付记录

2026-10-23；代码、全书审计、隔离浏览器及固定导出已交付；**尚未切换8000**。

## 1. 版本、范围与交付顺序

- 分支 `codex/textbook-image-location`，工作树 `E:/项目/heart-worktrees/textbook-image-location`。
- 开始时核对的 main：`9f2b01c4c525d1fa93d2231f8141150e886f7821`。没有复制主工作区未提交代码或恢复其旧教材删除项。
- 定位核心：`ecaf103`；新回答/API公共接线：`2ba4c66`；前端、reader构建、隔离与导出工具：`86afc1d`；滚轮测试时序：`63ccbf2`；拆分测试导入：`d1a5a5b`。
- 收尾时将新稳定 main `974617d` 合入本独立分支，保留另一窗口的取证/点名原图修复；整合代码版本 **`f2b88cda75d59581787bb1361e9ae52b5a335848`**。没有向main合并或改写其工作树。
- 分批提交已推送至既有 `origin` 的本分支；提交清单可用 `git log main..codex/textbook-image-location` 查看。文档收尾提交在代码版本之后，不改变已验收代码。
- 集成窗口优先合并该分支；若cherry-pick，先采用974617d，再按以上顺序采用本窗口5个实现/测试提交及最后文档提交。不要覆盖另一窗口最新app.js。

## 2. 根因与实际改动

同一输入的旧/新链路实证见 EVIDENCE.json 的 baseline_repro：旧 selected_media 把图1-2生成空rects，阅读器退到第二节第9页；新结果是**生成PDF第14页的实际图片矩形**。不是纸质印刷页码。

- `knowledge/visual_locations.py`：集中只读解析，先核对保存的document/version、真实PDF哈希、资产文件、当前资产登记及原DOCX哈希；读取当前PDF清单避免旧documents缓存伪升级历史。
- 优先比较解码像素，支持文件编码不同但像素一致；不按尺寸、顺序或相似度自动绑定。PNG透明度与PDF mask参与解码。
- 实际PDF已缩放/转码原图。`visual_locations_reviewed.json`绑定6项经并排完整内容核对的位置，每项固定资产SHA、PDF版本、PDF内图片像素SHA和矩形。每次请求仍验证；只确认导航位置，**不是教师批准资产**。
- 用于人工筛选的相似度候选不进入运行算法。第4章二维码候选未纳入精确映射；其余未核对项按诚实降级保留。
- 图注仅接受原资产上下文中的独立完整图注行与PDF完整行相同；正文同号提及不作为图注。重复位置可由已登记小节唯一消歧；仍不唯一或小节不符返回ambiguous，不改学习目标。
- `knowledge/answer_media.py::selected_media`保存新位置；保持图片身份、release字段、pending和model_saw_pixels/质检语义。非心理学课程保留旧分支行为。
- `web_api.py`新增只读定位路由，不改main.py或普通citation-state语义。
- `frontend/app.js`原图点击改走统一接口；旧空rects只使用保存身份同版本重定位，不改历史。用导航序号与现有section请求序号阻止晚到响应；错误时不使用旧位置兜底。
- `reader/src/tutor/markdown.tsx`及普通figure按钮分别显示“返回教材”“查看图注位置”“打开所在小节”；已生成实际 `frontend/tutor-markdown/tutor-markdown.js`。
- reader实测暴露两项问题并修复：同document换URL/版本需重新挂载；页尾小区域不顶到视口最上端，防止PDF.js把下一页计为当前页。复用现有scrollTo/pagechanging/pdf-position；源码及 `frontend/pdf-reader/reader.js`一并交付。

公共调用点：`selected_media → resolve_figure`；`POST /api/course/figure-location → resolve_figure`；`[data-tutor-media] → 接口 → selectSection(record:false) → TextbookPDF.mount`。导航不调用Q5推进、不新增问答、不使用图谱关系安排教学。

## 3. 接口契约

```http
POST /api/course/figure-location
Content-Type: application/json
```

```json
{"asset_id":"image-01-0004","sha256":"b1341a85b7600beb23c829b4723cb5fac418403049fd60d06e605e8a84e7b384","document_id":"experimental-psychology-3:chapter-01","version":"34f4dfc2dd1418397cbc35aa4a2c0b404a11102cf919287b6fd2bfa5be021c7e"}
```

- 四项必须来自保存记录；不接收客户端路径/坐标或额外字段。缺身份/非法格式422。
- `exact/caption/section`带已有selection_ref格式；`exact`为area，`caption`为text且明确只定位图注，`section`空rects仅打开已核验小节。
- `ambiguous/stale/unavailable`的selection_ref为null，禁止导航。source失败不静默使用旧位置。
- 精确结果的page/rects为完整生成PDF坐标，只由reader的page_map换算一次。另有basis、资产/document/version及原review_status；位置成功不改pending、readiness或证据等级。
- 不需要LLM生成或embedding请求。内存缓存以实际PDF版本为键；每次先复核文件哈希。返回坐标不暴露缓存可变对象。

## 4. 固定输入与全书扫描

输入从当前已登记的2ae1e5f运行目录只读取得，未从主工作区可能变化的未跟踪教材取材。独立副本406文件逐个与来源哈希相同；发布候选完整运行资源489文件包含原Q2索引/源件/既有裁图，只读复制，不重建索引。

全书最终审计：11章，178可用视觉资产；exact **6**，caption **108**，section **46**，ambiguous **18**；现有装饰排除 **45**，missing/stale/unavailable均0。45包含原有栏头排除及已有特定扫码入口排除；不是新增缺图修复或把pending变成审核通过。

| 章 | 分类数量 |
|---|---|
| 1 | caption:1 / exact:3 / excluded:4 / section:2 |
| 2 | caption:2 / excluded:4 / section:2 |
| 3 | ambiguous:3 / caption:13 / excluded:4 / section:12 |
| 4 | ambiguous:7 / caption:10 / excluded:4 / section:6 |
| 5 | ambiguous:1 / caption:9 / excluded:5 / section:6 |
| 6 | ambiguous:3 / caption:26 / excluded:4 / section:7 |
| 7 | caption:7 / exact:1 / excluded:4 / section:2 |
| 8 | ambiguous:1 / caption:15 / exact:1 / excluded:4 / section:2 |
| 9 | ambiguous:3 / caption:18 / exact:1 / excluded:4 / section:2 |
| 10 | caption:3 / excluded:4 / section:2 |
| 11 | caption:4 / excluded:4 / section:3 |

完整逐项document/version/asset/hash/page/rect/basis、歧义候选和排除原因见 `TEXTBOOK_IMAGE_RETURN_LOCATION_AUDIT.json`。全部扫描完成不等于178项都能精确返回，更不等于全部人工审核。最终固定导出扫描耗时60.1246秒；初始94.3711秒、6项位置核对后47.7955秒均保留。

精确核对项：image-01-0003（第7页）、image-01-0004（第14页）、image-01-0005（第15页）、image-07-0003（第7页）、image-08-0001（第4页）、image-09-0001（第2页）。

## 5. 验收矩阵与全部尝试

| 项目 | 结果与界限 |
|---|---|
| 已提交最终导出定位/媒体/来源回归 | 58/58，通过；104.832秒，regression-export-final.log |
| 旧数学引用定位 | 对应TUTOR_COURSE=discrete-math下9/9，通过；初次错误课程配置下的8错误+1失败保留 |
| 滚轮手势单测 | 5/5，通过 |
| 新reader滚轮浏览器回归 | 11/11，通过；含上下、惯性、首尾、局部作用域、圈选、引用、200%缩放、刷新、重挂 |
| 最终固定导出原图浏览器 | 10/10，通过；真实API/PDF/前端，浏览器pageerror=[] |
| 原图主复现 | 旧空rects、保存身份不改写，图1-2第14页实际图片高亮与正文视口相交 |
| 跨章/同章多图 | 第1章两图与第7/8/9章样本分别定位；拆分页14→显示1只换算一次 |
| 失败与竞态 | 旧版/错哈希/缺资产/缺身份受控拒绝；503无旧位置兜底；快速连点最后一次生效 |
| 学习与模型 | 零新生成请求、零课程views/学习推进请求；不将测试学生/桩接口计为完整Q5或真实模型联验 |

浏览器新回答使用真实selected_media+确定性来源夹具；历史用保存身份完整但空区域的旧记录。未重新生成模型答案；本轮实际模型调用0。section/caption/ambiguous前端分支用明确响应夹具测试，真实分类由临时PDF单测和全书扫描另行核验。

最终浏览器证据目录：
`E:\项目\heart\.runtime\textbook-image-location-f2b88cd\code\project\integration\discrete-math-tutor\.runtime\visual-location\browser\2026-10-23T13-22-19-905Z`

包含results.json、trace.zip、图1-2第14页、跨章图表、拆分页和最终截图。原文、截图、trace不提交为教材文件；EVIDENCE.json提交全部运行摘要与路径。

失败保留：独立worktree初缺未跟踪教材导致导入未开始；浏览器首轮测试宿主缺Windows JS MIME声明；其次断言错误选到零尺寸AreaHighlight包装层；随后发现并修复真实reader换URL保留旧监听及页尾图片页码跳到下一页问题。其他失败包括错误课程配置、测试共享dict、拆分测试漏patch导入、外部自动化通信间隔把合成惯性误分为多手势。最后一项改为浏览器内连续发送并记录maxGap，而非放宽生产手势门槛。各轮截图/日志/trace保留，详见EVIDENCE.json。

## 6. 固定导出、运行身份与复验

- 代码版本 `f2b88cda75d59581787bb1361e9ae52b5a335848`（包含974617d稳定修复）。
- 固定导出：`E:/项目/heart/.runtime/textbook-image-location-f2b88cd/code`，代码/运行资源9808文件；完整Git archive逐成员哈希与导出清单一致。初始86af导出和中间归档保留。
- `release.json`、`files.json`、`source-f2b88cda75d59581787bb1361e9ae52b5a335848.zip`和未启用`start-approved.py`位于其上级目录。
- 新app.js SHA256 `715d3200ca3a6ff00f695b6a91b334dd3f31a40a0faec28f0bcf7f58eaca1dff`；新reader.js `f884341be48c4de9764f90d49517da29eff3e025e899395e8b3753fb95bf24c4`；Markdown构建`316b97275d483f108ae632dd6549397ef72a25111becda5be842d28cbec15523`。其他关键文件见EVIDENCE.json。
- 当前8000仍PID43028、cwd为 `.runtime/response-portable-20261022/code-proof-2ae1e5f/project/integration/discrete-math-tutor`，加已登记旧滚轮覆盖。实际HTTP reader哈希仍cae56d95…；figure-location返回404，**本功能尚未在用户当前8000生效**。
- 本窗口18981/18982/18983临时服务已按脚本/端口/cwd核对后停止，8000未停止。

复验（应用根目录；使用现有独立Python环境）：

```powershell
$Python='E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe'
$env:DATABASE_URL='sqlite:///:memory:'
$env:COURSE_DATABASE_URL='sqlite:///'+$PWD.Path+'/.runtime/visual-location/unused-student.sqlite3'
& $Python -m unittest tests.test_visual_locations tests.test_visual_location_integration tests.test_source_visuals tests.test_answer_media tests.test_grounded_citations tests.test_citation_publication -v
node --test reader/src/wheel-paging.test.js
& $Python scripts/audit_visual_locations.py --output .runtime/visual-location/scan-new-run.json
& $Python scripts/serve_visual_location_acceptance.py --out .runtime/visual-location/new-server --port 18983
```

另一个终端：

```powershell
$env:NODE_PATH='C:/Users/free/.agents/skills/playwright/node_modules'
$env:VISUAL_LOCATION_URL='http://127.0.0.1:18983'
node tests/browser/visual-return-location.cjs
```

拆分页夹具为该教材源PDF第14/15页的只读派生文件 `.runtime/visual-location/split14-15.pdf`；已在交付导出验收目录准备。若从纯Git重新验收，先用fitz.open原PDF、空PDF.insert_pdf(from_page=13,to_page=14)、save该路径。产物不改源PDF。实际构建命令 `npm --prefix reader run build` 与 `npm --prefix reader run build:chat` 均已通过，未升级依赖。

## 7. 待批准启用与回退

本轮不自动切换。首次组合操作被自动审批拒绝（远端/生产学生库风险）；核验origin及计划P4.1后独立分支push已获准并成功。**生产学生库复制未执行**；另一次因自动审批额度不足未执行的导出最终化，在用户“继续”后重新审批并完成。不得把这些未执行动作写成已备份或已部署。

以下为具体准备，须获准后执行：

1. 复核8000的当前PID、create_time、cwd；核实所有窗口没有正在写入的任务，不能按本报告旧PID直接停止。
2. 从主项目根目录运行已准备的 `E:/项目/heart/.runtime/textbook-image-location-f2b88cd/backup-before-enable.py`。它复用原SQLite online backup和integrity_check流程，只写新目录；未执行。备份期间若源哈希变化会停止，须保留该尝试、另选新备份目录。两库分别一致，不宣称跨库原子快照。
3. 核对新备份、files.json和release.json、候选位置/7项核心哈希；保留当前LightRAG/Q5配置，继续staging/ready=false。只有确认授权后停止已核实的8000监听及相应启动器。
4. 从主项目根目录启动（隐藏窗口；不复制密钥）：

```powershell
$Python='E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe'
$Launcher='E:/项目/heart/.runtime/textbook-image-location-f2b88cd/start-approved.py'
Start-Process -FilePath $Python -ArgumentList @('-B',$Launcher,'--start-approved','--activate-reviewed-candidate') -WindowStyle Hidden
```

启动器复用当前获准模型、SDK、Q5/LightRAG配置和现有候选/缓存；读取原凭据与最新数据库位置，不把密钥写入导出。逐文件预检失败、缺新备份或8000仍被占用都会拒绝启动。启动后须复核实际接口、静态文件哈希和用户页面图1-2第14页；隔离通过不能替代这一步。

回退：核对并停止新监听，运行原 `.../response-portable-20261022/start-lightrag-approved-2ae1e5f.py --start-approved --activate-reviewed-candidate`；确认原reader覆盖仍为cae56d95…。**继续使用当时最新学习库，不恢复旧备份覆盖新学习数据。** 失败的新导出和日志保留，位置缓存可丢弃，教材与候选核心不变。

## 8. 仍未完成/适用界限

- 尚未获准执行生产学生库新备份和正式切换；8000用户页面未声称通过。
- 108项仅图注、46项仅小节、18项歧义保留。后续精确位置需逐项核对，不用相似图片强行补齐。
- 真实模型媒体生成、整轮LightRAG/Q5、真实鼠标/触控板硬件及跨浏览器未在本轮重验。待审核状态、教师审核和发布readiness未改变。
