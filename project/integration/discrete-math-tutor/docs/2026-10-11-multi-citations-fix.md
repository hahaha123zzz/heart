# 多来源教材引用显示修复（2026-10-11）

## 原因

定理7.7回答的后端来源中，第3项已包含定理7.2（PDF第4页），正文也引用[3]。前端只保存 textbook_sources[0] 并渲染单个 selection_ref，因此仅显示第10页。历史记录也只保存主选区，刷新后无法恢复前置来源。

## 修改

- ProofEvidence.public_references：为主证明及前置单元返回独立 source_index、标签、版本核验后的选区及原文裁图。引用序号保留原位置，未把[3]改成[2]。
- orchestrator：返回 pdf_references；将来源列表与引用列表一并保存进已有 PDFCitationRow.reference JSON，兼容原选区字段，无数据库迁移。
- conversation API：返回保存的多引用信息。
- 前端：按正文使用的引用编号显示来源、各自的页码按钮与裁图；按钮选择自身的选区，不再统一使用主证明位置。
- 更新 app.js 的版本参数，避免旧脚本缓存。

## 验证

- 新增后端回归用例先失败，再修复；86项 Python 回归测试通过。
- scripts/test_chat_references.cjs：引用序号、两个页码、背景过滤、旧选区兼容、HTML转义通过。
- 真实 GPU API 调用：主证明[1]对应PDF第10页，前置定理[3]对应PDF第4页；两张裁图HTTP200。
- 浏览器验证：两个引用均可见，实际PDF跳到第4页和第10页；刷新后引用仍可见；无pageerror。
- 测试账号删除HTTP200。

验收记录：artifacts/multi-citations-browser-results.json；截图：artifacts/multi-citations-chat.png、artifacts/multi-citations-page4.png。

## 使用与限制

打开 http://127.0.0.1:8000/ ，Ctrl+F5刷新后重新发送同一问题。旧回答未保存完整多引用数据，不能仅靠刷新补全；新回答已保存完整引用。此次修复不代表其他数学回答质量问题已解决。

服务 PID 文件沿用 artifacts/long-proofs-gpu-server.pid（当前42800），日志为 artifacts/multi-citations-server.log。健康检查HTTP200，reranker使用CUDA。此次预热47.8秒；未修改GPU初始化逻辑，不据此宣称此前冷启动问题已解决。
