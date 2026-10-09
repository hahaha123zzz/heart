# 教材图表阅读与处理进度优化
日期：2026-10-09

## 问题与处理
1. 原聊天接口在多个 LLM 调用完成后一次返回，前端仅禁用按钮。新增 POST /api/chat/stream，经 SSE 返回真实阶段的开始和完成事件；阶段包括理解问题、检索教材、读取资源、组织讲解、生成、质检及保存。记录耗时，失败保留提问和已执行阶段。展示的是可验证的执行状态，不输出模型内部推理。
2. 原阅读器依赖纯文本和 3 张静态图片，未使用批量提取结果。读取原 Flat OPC 的有序正文块，将公式图像放回内联位置，表格保留行列、合并单元格和单元格内公式，图片使用服务端资产 ID。
3. 导航仅使用原正文片段，避免 RAG 补充片段重复生成小节。学习历史恢复图片引用。
4. Word 局部导出会重编号 shape ID，不能用它匹配原始 XML。脚本在只读打开的文档内存副本添加零长度书签，导出全文获得正文块索引，关闭时不保存。块数一致才接入绘图。

## GitHub 实现参考
- [Chainlit Step](https://github.com/Chainlit/chainlit/blob/main/backend/chainlit/step.py)：步骤开始时 send，结束时 update；前端可以展示步骤生命周期。
- [Dify StreamEvent](https://github.com/langgenius/dify/blob/main/api/core/app/entities/task_entities.py)：NODE_STARTED/NODE_FINISHED 和完成、错误事件。采用阶段通知与最终答案分开的协议。
- [Docling 文档结构](https://github.com/docling-project/docling/blob/main/docs/concepts/docling_document.md)：正文树维护阅读顺序，文本、表格、图片采用不同类型，并保存来源关系。阅读数据与检索片段分别构建。
- RAGFlow 的多模态文档解析思路与现有提取流程相符；本次采用上面可直接核对的源码和文档，不引入整套服务。

这是思路借鉴，本次代码为当前 Demo 的本地实现，没有复制框架代码。

## 验收
运行 test_reader_progress.py 及原多模态测试；浏览器验证第 10 章绝对值表格、内联公式及绘图，第 8 章图像，以及聊天等待阶段、完成后回答、失败提示。
公式当前以教材原图显示，尚未转成可复制 LaTeX；绘图锚点预览可能包含多个子图，图号尚未逐一核定。

## 验证结果
- 16 项单元与回归测试全部通过，覆盖 20 张表格、1209 张公式原图和 133 个绘图锚点。
- Playwright 验证第 10 章表格、公式和插图，第 8 章匹配图；没有页面 JavaScript 错误。
- 真实 DeepSeek 请求显示全部 8 个处理阶段，质量检查通过，回答引用 image-08-9055，刷新后图片引用恢复。
- 浏览器模拟流式失败后保留提问并恢复发送按钮。
- 补齐 Word Symbol 字符及正文上下标，绘图文本框内容由原图展示，避免重复混入正文。Symbol 转 Unicode 使用官方映射：[Unicode Symbol mapping](https://www.unicode.org/Public/MAPPINGS/VENDORS/ADOBE/symbol.txt)，原映射文件保留许可声明。
