# 第二部分：真实模型验证记录

> 最新复测：[PHASE2_MIXED_CHAIN_REPAIR.md](PHASE2_MIXED_CHAIN_REPAIR.md)。出题后翻第 2 页、applied 回执及刷新恢复题卡已通过真实模型验证；其余能力仍未全部验收。

日期：2026-11-09。模型：当前宿主配置的 DeepSeek `deepseek-flash`，目的地 `https://api.deepseek.com`；`LLM_MOCK=0`，未启动受控模型服务。用户已明确授权发送测试问题、教材片段与必要上下文。使用独立端口、隔离账号/数据库/原生 home；保留当前正式检索与来源校验配置。

**结论：部分通过，不能宣称全部真实链路通过，也不能宣称第二部分已全部验收。**

## 已通过

| 场景 | 实际结果 |
| --- | --- |
| 宿主 → 原生 AgentLoop → 真实模型 → rag → read_source | 正式回复 answered，2 条 PDF 引用、2 条教材来源，原文/版本/坐标校验通过 |
| 引用历史恢复 | 会话历史接口返回保留的 PDF 引用 |
| 真实原生 QuestionPipeline → 浏览器题卡 | 成功生成 1 道题、4 个选项，实际页面显示 |
| 私有答案边界与保存 | 公开 summary 不含 correct_answer/explanation；宿主 pdf_citations 中保存的安全题卡结构与页面一致 |
| 全新会话 reader_goto | 浏览器实际到达当前文档第 2 页，/reader-receipt 为 applied；文档 ID/版本与 actualReaderPosition 一致，无脚本错误 |
| 相关回归 | 6 个模块，38 项通过（231.877 秒）；JS 语法、git diff --check 通过 |

题目样本是“设置照明强/中/弱，记录校对时间，辨认自变量”，题干及四个选项的概念对应合理；未将私有解析发送到公开题卡。本轮样本不能代替大规模题目质量验收。

## 未通过：出题后切换阅读并指定页码

复现：在同一会话中先生成上述题目，再选择 immersive_reading，发送“请立即调用 reader_goto，把当前教材翻到 PDF 第2页（locator=2）。只需完成翻页，不需要解释教材。”

实际：原生保存的当前用户消息和模型最后用户输入都包含正确请求，但模型继续上一轮题目的讲解，调用 search_material/read_material 并最终 reader_goto 到第 28 页。页面执行了该动作，Playwright 的 expected=2 / actual=28 断言失败。

对照：在新的隔离运行中，仅发送相同的翻页请求，真实模型正确调用 reader_goto，PDF 到第 2 页且回执 applied。因此动作映射/SSE/页面执行链已经接通，带出题历史的意图切换仍不可靠。尚未证明其因果根因，不能把问题直接归咎于模型或某个单独上下文字段。

附带观察：原生出题回合的 assistant 历史正文仍是“现在为你出 1 道题”等前言，而实际题卡结构保存在宿主结果中。该历史表述可能影响后续意图切换，需要继续核对原生结构化交付与后续模型历史的一致性。

题卡刷新后的浏览器恢复断言在混合测试中位于翻页之后，因此未到达；本次只确认真实题卡已经保存到宿主历史，不能把这项浏览器刷新记为通过。

## 本轮发现并修复

1. 原先的工具组合依赖原生 KB 记录；宿主虽然注册 rag/read_source，但真实模型实际看不到。已在宿主教学作用域挂载当前教材 rag/kb_files，并挂载配套 read_source；保持原生阶段白名单、独占能力边界和 31 个隐藏工具。补测无原生 KB、受限阶段与独占能力。
2. 验收脚本原先硬编码 .venv-gpu，而当前完整启动环境是 .venv-runtime。现改为沿用运行脚本的解释器；没有安装新依赖或关闭正式检索配置。

## 证据与复跑

- 混合运行：`.runtime/native-delivery-live/20261109-080600/`，含 rag.json、rag-history.json、browser.json、隔离原生工具事件。
- 独立阅读：`.runtime/native-delivery-live/20261109-081123/`，含 browser.json 与已目视检查的 delivery.png。
- 工具未挂载的原始失败：`.runtime/native-delivery-live/20261109-080315/`，回复 quality_rejected，未放宽引用门禁。

复跑：在宿主目录用 `.venv-runtime/Scripts/python.exe -X utf8 -B scripts/check_native_delivery_browser.py --live`；独立阅读加 `--reader-only`。

尚未验证其余研究/媒体/掌握学习能力，也未开展外部模型的大样本稳定性测试。下一处待修复项是“结构化出题交付后的会话历史与新请求切换”，不应靠删除历史或跳过页码断言把失败记为通过。
