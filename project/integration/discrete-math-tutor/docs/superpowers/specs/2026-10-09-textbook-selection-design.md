# 教材选中内容后向 AI 提问
日期：2026-10-09
状态：待用户确认设计；尚未修改功能代码。

## 目标与交互
在首页教材区和“课程学习”教材区启用同一功能：
- 鼠标划选正文、原生文本公式或表格单元格文字，松开后出现“向 AI 提问”浮动按钮。
- 点击教材图片或公式原图后高亮选中对象，出现“向 AI 提问”和“查看原图”。点击提问不直接触发原图跳转。
- 点击“向 AI 提问”后，聊天输入区显示选中内容卡片。默认问题为“请解释这段内容”或“请解释这张图/这个公式”，用户可以修改，再点击发送。
- 首页回答出现在右侧聊天；课程学习页跳转到智能答疑页并携带选中内容。取消选择、切换章节、Esc 会清除浮动菜单；已加入提问的内容保持绑定原章节。
- 第一版选择完整图片或公式对象；图片内局部矩形裁剪可后续增加，不把点击整图描述成局部圈选。
- 连续文本可以跨段落并包含内嵌公式；单次最多附带 2 张原图，与现有模型输入限制一致。超过限制明确提示用户缩小选择，不悄悄丢弃对象。

## 可选实现方式
1. 仅用选中文字做关键词检索：改动较少，但“这个公式”或重复语句可能找错位置。
2. 结构化教材定位 + 用户记忆：推荐。利用现有 Word 内容块和原图资产，精确取得选中对象及邻近内容，复用答疑与质量检查。
3. 对阅读区域截屏后让视觉模型解释：适合图片内局部圈选，但额外增加裁剪、缩放、坐标换算与图片传输，本次不作为默认路径。

## 推荐的数据流
选中内容 → 位置验证 → 取得原教材上下文 → 读取相关用户记忆 → 个性化讲解 → 质量检查 → 保存对话及引用。

### 教材定位与上下文
- 在 knowledge/content.py 为正文块提供稳定 block_id，保留 Word 正文块索引；图片和公式另外携带 asset_id 与所在块，表格保留行、列和段落位置。
- 前端发送 chapter_id、section_id、教材版本、起止块及文字偏移，或图片/公式的 asset_id 和所在块。后台从自己的教材数据重建所选内容，检查对象属于指定小节，避免重复公式定位错误。
- 源数据版本由导入的教材哈希标识。教材更新造成旧位置失效时提示重新选择。
- 上下文包括所选正文/原图、所在段落、相邻正文与原教材图注；优先按位置获取，再按问题补充相关定义。保持上下文有长度上限并明确标记来源。
- 不采用前端传来的图片路径或上下文作为教材事实依据。教材材料在模型输入中明确标为资料。
- 原文、原图和公式显示继续遵循之前的清理要求，阅读区不重新出现文件来源等附加描述。

### 用户记忆
复用 MemoryManager，按当前 student_id 读取：
- 最近对话、相关知识点的学习状态和已有误解；
- 回答长度、举例频率、学习节奏偏好；
- 与本节有关的已有学习证据，限制数量和长度。
优先匹配本小节与已存知识点，再选相关历史；不会只因为旧的 active_goal 在其他章节，就把所选内容解释成旧话题。
首次学习且没有记忆时正常解释，不编造“你以前不懂”。单纯点击提问不视为掌握或错误证据，不自动推进原课程步骤。

### 接入现有流程
- ChatRequest 新增可选 selection 字段；普通聊天请求继续可用。
- /api/chat 和 /api/chat/stream 使用相同的后台位置解析；发送模型请求前完成位置校验。无效选择返回明确提示。
- 扩展 TutorOrchestrator 的选中内容分支，优先解释选中对象；相关记忆进入教学状态和生成输入，所选原图同时进入生成与质量检查。
- SSE 增加“定位选中内容”和“读取学习记录”阶段，后续沿用生成、核对和保存反馈。
- 回复附带 selection_ref、context_refs、image_refs，以及简短的 memory_summary，便于确认实际使用的教材和学习偏好；不在聊天中倾倒全部学生状态或原始记忆。
- 对话保存选中文字/对象引用及教材位置，刷新后能恢复引用，并支持针对同一对象继续追问。复用学生请求锁，避免同时写入同一学生状态。

## 边界与验收
- 文字：第 7 章定理的一部分可划选，后台得到准确片段与相邻证明。
- 图片：选第 8 章匹配图，模型收到该图的真实图像与正确正文，而非靠“这张图”关键词猜测。
- 公式：选第 3 章二项式公式，模型收到对应原图；同一个公式资产在多个段落出现时上下文跟随当前段落。
- 用户记忆：两个学生对同一对象提问时读取各自记录；有基础薄弱证据者采用基础讲解，无历史者不编造历史。
- 表格及文本公式：文字选择保留数学符号与上下标语义，并允许携带内嵌公式原图。
- 浏览器检查选中菜单、预览、取消、修改问题、章节切换、移动端点击、原图查看和原有聊天。
- 检查位置越界、外小节资产、旧教材版本和超过图片数量上限的错误处理；真实 DeepSeek 验证至少一张图和一个公式。

## GitHub 调研补充（2026-10-09）
本节为源码调研结论，尚未在本项目接入或验证第三方组件。GitHub CLI 缺少登录态，本次使用公开仓库页面和 GitHub API/raw 源码核对。

### 1. Zotero GPT：选中文字与相关正文分别取得
- 项目：[MuiseDestiny/zotero-gpt](https://github.com/MuiseDestiny/zotero-gpt)
- 源码：[src/modules/Meet/Zotero.ts](https://github.com/MuiseDestiny/zotero-gpt/blob/bootstrap/src/modules/Meet/Zotero.ts)
- getPDFSelection 取得当前阅读器所选文本；getRelatedText 从当前 PDF 或所选条目组织文档，再 similaritySearch，返回带编号的相关内容。getPDFAnnotations 另存 annotationPosition 和文档 key。
- 借鉴：所选内容是明确的解释目标，相关检索是补充证据。不能让检索结果覆盖用户已经选中的句子。
- 适用程度：交互和资料组织很接近我们的需求；依赖 Zotero 阅读器，不能直接安装进现有 HTML 教材。仓库 LICENSE 为 AGPL-3.0，本方案采用交互和数据流思路借鉴。
- 已核对该项目存在选中文字丢失/空值的历史 Issue #220。设计上应在用户松开选区时保存引用与快照，再点击按钮；空选择不发送。

### 2. react-pdf-highlighter：选区事件、位置和区域截图
- 项目：[agentcooper/react-pdf-highlighter](https://github.com/agentcooper/react-pdf-highlighter)
- 源码：[PdfHighlighter.tsx](https://github.com/agentcooper/react-pdf-highlighter/blob/main/src/components/PdfHighlighter.tsx)、[types.ts](https://github.com/agentcooper/react-pdf-highlighter/blob/main/src/types.ts)
- onSelectionFinished 将 position 与 content 分开传递；文字选区保存文本、矩形和页码，区域选择通过 screenshot 取得图像，并支持选区附近的弹层。README 明确为 PDF.js 上的 React 注释组件，有示例和 e2e 目录，MIT 许可。
- 借鉴：选区内容与定位信息同时保存；显示位置与持久位置分离；选中后菜单是可替换的操作入口。
- 对现有 HTML 教材采用 block_id + 文字范围 + asset_id。后续增加图内局部裁剪时，用相对原图的归一化矩形，避免缩放和滚动使坐标失效。
- 这个组件负责选区和注释，没有提供完整的用户记忆问答后端。现有前端不是 React/PDF.js，第一版采用原生 DOM selection。

### 3. Kotaemon：图文证据输入与引用回溯
- 项目：[Cinnamon/kotaemon](https://github.com/Cinnamon/kotaemon)
- 源码：[citation_qa.py](https://github.com/Cinnamon/kotaemon/blob/main/libs/kotaemon/kotaemon/indices/qa/citation_qa.py)、[pdf_viewer.js](https://github.com/Cinnamon/kotaemon/blob/main/libs/ktem/ktem/assets/js/pdf_viewer.js)
- 多模态分支把 prompt 和 image_url 一起传入 HumanMessage，并限制图片数量。prepare_citations / match_evidence_with_context 将引用匹配到文档的 start/end 范围；PDF 预览使用文件、页码和检索片段定位高亮。
- 借鉴：选中图或公式时发送真实图像、邻近正文与对应来源；返回回答时保留结构化引用，支持回到所选位置。
- Apache-2.0 许可，完整文档问答应用。它的 PDF 引用高亮不等同于本次所需的用户主动圈选菜单，也不包含离散数学学习状态管理。

### 4. Mem0：按用户和问题检索相关记忆
- 项目：[mem0ai/mem0](https://github.com/mem0ai/mem0)
- 源码：[mem0/memory/main.py](https://github.com/mem0ai/mem0/blob/main/mem0/memory/main.py)
- 当前公开源码 search 接口接受 query、filters、top_k、threshold，要求 user_id/agent_id/run_id 至少一个范围标识；add 接口将新记忆绑定这些标识。公开 SDK 为 Apache-2.0。
- 借鉴：使用“所选内容 + 用户问题”检索当前用户相关记忆；数量和相关性有上限；解释结束再考虑新增记忆。
- 保留当前 MemoryManager 与 SQLite 的学习状态、误解和偏好，先增加相关性筛选。Mem0 可作为未来独立的语义记忆适配器。
- 仓库 README 明确部分托管服务算法优化不在开源 SDK 中，因此本方案不采用其托管服务性能宣传作为本地成熟度证明。

### 调研后的具体实施建议
优先级一：文字划选、完整图片/公式选择 → 引用卡片 → 用户问题 → 教材准确定位 → 相关学习记忆 → 现有生成与质检 → 保存引用。
优先级二：矩形裁剪、返回教材位置并高亮、对同一选区连续追问的引用恢复。
模型输入明确区分教材证据、用户学习记忆和本次问题。记忆用于决定讲解难度与节奏，教材证据用于数学事实与引用。
以上四个项目提供可借鉴的组件和流程；尚未找到能够直接覆盖“当前 Word/HTML 教材 + 图文公式圈选 + 离散数学教学记忆”全部需求的单一项目。
