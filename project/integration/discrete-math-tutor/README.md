# 离散数学 AI 助教（Demo）

这是从原心理学助教项目改造的离散数学教学 Demo。保留原有的对话路由、学生状态/画像、短期教学计划、教学策略、记忆和 API；教学内容改为用户提供的十章离散数学教材文本。它不是心理咨询或心理学教学平台。

Windows 双击 `2-chat.bat`，或在本目录运行 `.venv\Scripts\python.exe chat_cli.py`。输入 `exit` 退出。默认只显示助教回复和教材出处；如需查看内部状态可用 `--debug`。默认是测试账户，退出时清除本次测试记忆。建议先问：`我对图这一章不太懂，该怎么学？`，接着试 `不知道`、`还是不会`、`我想换到集合`。

真实模型：在本地 `.env` 配置 `DEEPSEEK_API_KEY`、`OPENAI_BASE_URL=https://api.deepseek.com`、`OPENAI_MODEL=deepseek-flash`、`OPENAI_VISION_MODEL=deepseek-flash`、`LLM_MOCK=0`。不要分享密钥。没有密钥时设置 `LLM_MOCK=1`，模拟回复仅用于流程测试，不代表真实教学质量。

默认 `DATABASE_URL=sqlite:///./ai_tutor.db`，也支持现有 MySQL 配置。不要覆盖现有 `.env`、数据库或虚拟环境。测试账户有效期 24 小时；每次代码版本变化时只清理测试账户记忆，正式账户保留。

网页 Demo：双击 `3-start-api.bat`，等待浏览器打开 `http://127.0.0.1:8000/`；同一服务同时提供 API，接口文档位于 `http://127.0.0.1:8000/docs`。启动与检查脚本调用本目录 `.venv\Scripts\python.exe`。若该虚拟环境尚不存在，先在本目录运行 `python -m venv .venv` 和 `.venv\Scripts\python.exe -m pip install -r requirements.txt`。`1-smoke-test.bat`、`4-test-dedup.bat`、`5-test-routing.bat`、`6-eval-tutor.bat` 是离散数学场景的离线检查。

`orchestrator.py` 负责统一教学回合；`agents/` 负责路由、学生证据、教学规划、出题、回复与质检；`models/`、`memory/`、`database/` 负责学生状态、画像和持久化；`knowledge/textbook_text/` 是十章教材纯文本；`llm/client.py` 是单一模型接口。

教材源自 Word 提取的纯文本，公式和图片可能显示为 `[公式或对象]`，不能据此臆造公式。当前没有独立课件文件或教师认证，已批量恢复公式预览和 Word 绘图，部分插图的教材图号尚未核定；网页会标记缺失的资源，也不提供全班统计页。统计只限当前演示学生账户。回复尽量控制在约 200 个汉字、一个小步骤和一个小问题；教材依据用 `[1]` 等编号引用，出处在返回值 `textbook_sources`。演示级检索不保证所有复杂证明无误，正式使用仍需核对教材。

图片试点：现已从第七章原始 `.doc` 中提取并核对图 7.8、图 7.20、图 7.23。相关小节和问答会显示原图、图号与来源；问答返回 `image_refs`，历史记录也保留图片引用。`knowledge/figure_assets/README.md` 记录了图号核对依据，`python scripts/extract_doc_png_candidates.py` 可重复扫描原稿中的 PNG 候选。设置 `LLM_MOCK=0` 并配置密钥后，相关问答会把已核对的原图传给视觉模型，用于生成和质检回答；模拟模式仅测试引用流程，不会识别图片内容。图片文件在每次读取前校验 SHA-256，目录中的资产按来源、文件路径和哈希验证后发送；新增绘图以锚点对象编号展示。明确询问图号时，助教优先引用该图所在的教材原文。

`chat_cli.py --account production` 会持久保存学习数据，仅在明确需要时使用。`chat_cli.py --keep` 会保留测试数据到过期或下一次代码更新。

## 图片、表格与公式批量导入

已处理十章原始 DOC：20 个 Word 表格、1,209 张公式预览、4 个嵌入图片和 133 张 Word 绘图锚点预览。一个公式块可能包含多个公式对象，一个绘图预览也可能包含多幅图或标注；这些数量不等于教材独立图号数量。

双击 `9-import-multimodal.bat` 可以重建。导入需要本机 Microsoft Word 和 Windows System.Drawing；运行网页问答只读取导入产物。流程为 DOC → WordOpenXML → 表格/公式/媒体解析 → 绘图锚点导出 → PNG 预览与检索索引。原始 WMF、EMF 和 OLE 文件保留，发送模型的预览最长边限制为 2,048 像素。导入后重启 API 服务以刷新缓存。

- 提取统计：`knowledge/extracted_multimodal/import_report.json`。
- 插图及公式核对页：`knowledge/extracted_multimodal/review.html`，可用浏览器打开。
- 表格和公式块：`multimodal_chunks.jsonl`；绘图正文：`vector_chunks.jsonl`。
- 真实模型验证：`.venv\Scripts\python.exe -X utf8 scripts\eval_multimodal.py`，结果保存到 `knowledge/extracted_multimodal/real_validation.json`，使用临时数据库。
- 离线验证：`.venv\Scripts\python.exe -m unittest test_figures test_figure_focus test_multimodal`。

检索使用本地正文关键词和资产关联：表格保持行列；公式按邻近正文检索，再把原公式图片交给视觉模型；插图按图注、邻近正文或已核定图号定位。回复、质检和历史记录共用同一组图像引用，每轮最多附两张。公式尚未自动转成 LaTeX，也没有独立的图片向量索引。

可试问：“根据绝对值函数的表格，x=-3 时 f(x) 是多少？”、“解释牛顿二项式定理公式中的 C(n,k)”、“结合特殊图章节的完全匹配配图，解释粗边表示什么”。新增绘图显示对象编号；已核定的图 7.8、7.20、7.23 保留教材图号。
