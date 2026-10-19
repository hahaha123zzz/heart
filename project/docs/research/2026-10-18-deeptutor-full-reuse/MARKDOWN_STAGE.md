# B3 聊天富文本接入

沿用已批准的“保留现有页面，大块接入后端与组件”方案。本小阶段复用固定副本中的 SimpleMarkdownRenderer、markdown-renderer-core、markdown-display、latex 和 latex-normalize，不改写 vendor 文件。

在现有 reader 构建环境增加独立聊天构建入口，直接导入上游源码；以同步静态 HTML 接入原 ChatMessageRenderer，保留组件、焦点、滚动及断线恢复。沿用上游 GFM，补入同版本 remark-math/rehype-katex。只在宿主边界限制图片、附件、URL，禁用原始 HTML 执行；正文引用仅调用同一消息已有的来源按钮。练习反馈沿用相同渲染函数。

验收：标题、列表、表格、代码、删除线、勾选列表、中英文强调、原有高亮、行内/块级公式、公式与代码内引用保护、外链策略、恶意 HTML/URL、同消息引用、历史与恢复、组件生命周期和窄屏溢出。测试不调用模型或学生数据库。

这次不接 Mermaid、代码主题设置、上游附件操作或完整 AgenticChatLoop；它们继续留在后续组件/业务接入范围。完整心理学真实模型黄金集仍待独立验收。


## 验证结果

2026-10-19：聊天/阅读器两个构建通过；扩展真实浏览器生命周期、富文本、安全、来源、窄屏与练习兼容检查全部通过；Node 传输 8 项与原显示降级自检通过；固定上游 3,764 个文件完整性通过。测试调用现有静态文件，自建临时 API 替身，不调用模型或学生数据库。

在宿主目录执行 `node --test tests/chat-transport.cjs`、`node tests/browser/answer-emphasis.node.cjs`；有 Playwright 的 Node 环境可执行 `node tests/browser/chat-lifecycle.cjs`。浏览器脚本自动选择空闲本机端口，退出时关闭服务；可用 TASK_TEST_ROOT 指定宿主绝对路径，CHAT_TEST_SCREENSHOT 指定截图路径。重建方式见宿主 README。
