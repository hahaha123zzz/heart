# 上游源码核验与取舍

核验日期：2026-10-16。固定提交、原始文件、下载结果与 SHA256 见 `upstream/manifest.json`。GitHub CLI 配置在本会话不可读，使用公开仓库原始文件后备访问；没有更改 GitHub 身份或凭据。

| 上游 | 许可证核验 | 本次使用 |
| --- | --- | --- |
| DeepTutor `6cf793bd868ba5ecbe64722936d4be8fab5a01df` | 根 `LICENSE` 为 Apache-2.0；根 `NOTICE` 未找到（404） | 适配 `normalized_with_map`、`selection_range` 的反向映射机制，保留原文字符位置；改为列出全部匹配，不取首次命中。代码在业务目录 `knowledge/grounding_text.py`，许可及修改说明在 `third_party/DeepTutor/`。 |
| Kotaemon `9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9` | 实际许可文件为根 `LICENSE.txt`，Apache-2.0；`LICENSE`、`LICENSE.md`、根 `NOTICE` 均404 | 采用结构化证据选择的思路，接入已有 Pydantic 和 LLM 网关，没有复制 theflow/Gradio 组件。`find_text` 只作对照，不作为精确定位判据。 |
| RAGFlow `987457c07f98828f9c61e8bffd5d75bb4962bd7c` | 根 `LICENSE` 为 Apache-2.0；根 `NOTICE` 未找到（404） | 借鉴来源 ID、显示编号、页码、矩形分离；没有复制 React 组件或坐标工具。当前坐标直接由 MuPDF 转到既有 PDF.js 的 0～1 可见页面坐标。 |
| LlamaIndex `619d74664e8404612038bc15a1a40c686037277c` | 根 `LICENSE` 为 MIT；根 `NOTICE` 未找到（404） | 借鉴大块检索背景与小引用单元分离，没有引入 LlamaIndex 运行时；每次切分显式重新记录原文范围。 |

## 同一开发集对照

报告：业务目录 `artifacts/citation-grounding/upstream-development-fair.json`。全部函数输入相同的原文引句及已对齐块的 PDF 文字窗口（无块限制时使用全文）；只抽取已逐行审阅的纯函数，不导入上游运行时。95 条支持记录中有88条正例、7条负例。早期全文对照也保留，但采用窗口一致的对照作为取舍依据。

- DeepTutor 原 `selection_range` 完整匹配 9/88 条正例。
- Kotaemon 原 `find_text` 返回的跨度完整等于引句 11/88 条正例。该函数容许部分匹配及跨度合并，不能用“有返回值”代替完整匹配。
- 本项目适配的规范化及带块范围索引在这88条正例中全部唯一匹配；开发集独立读取 PDF 字形也包含完整引句。
- 上游纯函数不负责文档版本、重复语句歧义、几何坐标或结论语义；上述数字不是对上游平台整体的准确率评判，也不能外推本项目全教材语义准确率。

选择结果：保留 DeepTutor 的低依赖映射方式及其他项目的证据协议思路；精确坐标、版本、歧义和裁图核验由本项目补齐。没有安装新的运行依赖。

## 规范化的明确边界

只去除匹配用空白并转换全角 ASCII；不使用通用 NFKC，因为它会混同 `x²` 和 `x2`、`H₂O` 和 `H2O`。数字、负号、上下标和公式符号保留。旧构建缺少新规范化标识时拒绝加载，须重建索引。换行拼接仍可能使某些英文空格差异无法区分，因此语义核验仍是独立门槛。

审计目录中的上游文件只用于来源核验和可重复对照，不代表全部已移植。教材数据的再分发授权不由这些代码许可证提供。
