# PDF 阅读器与选区问答验收
日期：2026-10-09
版本：0.8.0

## 完成项
- 保留平台布局，教材区使用局部 React + PDF.js + react-pdf-highlighter。
- 十章 PDF 共 223 页，102 个小节的 Word 原生位置与 PDF 标题行核对通过。源 Word 只读打开且不保存。
- 文字划选、单页区域框选、选区预览、修改问题、移除引用、相关教材上下文和当前用户学习记忆检索。
- 从服务端原 PDF 裁图，生成与质检使用相同原图；单次最多相邻两页，区域框选限一页。
- 实际处理阶段反馈、引用保存、刷新恢复、点击引用返回并高亮、对同一选区继续追问。
- KaTeX 排版公式回答；PDF worker、字体和 CMap 均本地提供。

## 验证结果
- Python 单元与 API 回归：23 项通过，包含 7 项 PDF 选区测试。覆盖文档页码、伪造文本、版本与坐标拒绝、图像白名单、记忆隔离、状态不推进和引用恢复。
- 真实 DeepSeek：第 8 章图 8.4 粗边解释、第 3 章二项式组合系数解释均通过质量检查；模型实际收到服务端裁图。初次图片解释曾未通过质检，收紧生成长度与稳定性后完成验收，未放宽质量门槛。
- 浏览器：文字选择、桌面框选、手机真实触屏框选、章节跳转、PDF 缩放、表格框选、引用返回、刷新恢复和普通聊天验证通过。
- 最终 UI 验证：0 个脚本错误、0 个控制台错误，390px 手机无页面横向溢出。
- PDF 缩放实际页宽从 495px 增至 1191px；表格选区取得绝对值函数正确输入与输出行。
- 点击引用恢复第 3 页与原选区；公式引用恢复第 8 页，聊天数学公式生成 KaTeX 节点。
- 课程学习阅读器、统计页 4 项指标仍可用；移除引用后的普通聊天请求不携带 selection。

## 证据
- artifacts/pdf-reader/ui-validation.json
- artifacts/pdf-reader/zoom-table-validation.json
- artifacts/pdf-reader/formula-real-validation.json
- artifacts/pdf-reader/image-quality-diagnostic.json
- artifacts/pdf-reader/reference-restored.png
- artifacts/pdf-reader/answer-formula.png
- artifacts/pdf-reader/table-selection.png
- artifacts/pdf-reader/mobile-reader.png
- pdf-browser-final-flow.log（真实图片问答及阶段反馈；其后手机问题已由最终 UI 验证解决）
- pdf-browser-ui-cleanup.log（最终零错误与触屏结果）

## 使用
打开 http://127.0.0.1:8000/ 后 Ctrl+F5 刷新。划选文字或使用“框选图 / 公式”，点击“向 AI 提问”，修改问题后发送。引用可通过 × 移除。框选限一页；图表及原式保留在 PDF 中。
