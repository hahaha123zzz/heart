# psychology-platform-20261125 分支说明

本分支交付的是《实验心理学（第 3 版）》教学平台的可用版本，包含教材阅读、助教问答、练习测评与只读知识图谱四个入口。

## 与来源分支的关系

- 基点：`codex/ta5-acceptance-20261029` 的 `bf8bd0e`（2026-11-14）
- 本分支在该基点上提交了本次改版内容。来源分支在该日期之后的提交（ProgreSQL 存储迁移、DeepTutor 原生检索增强等）**不在本分支内**，如需合并请以来源分支为准重新评估。

## 四个入口

| 入口 | 地址 | 说明 |
| --- | --- | --- |
| 学习平台 | `http://127.0.0.1:8000/` | 对话、练习、学习记录 |
| 教材样章 | `http://127.0.0.1:8000/textbook-preview/psychology` | 单栏阅读版式 |
| 知识图谱 | `http://127.0.0.1:8000/knowledge-graph` | 只读候选图谱，281 实体 / 2,180 关系 |
| 教材阅读器 | 平台内左侧「教材」 | PDF 阅读与引用定位 |

## 本次提交的内容

1. **教材解析与排版**：`scripts/rebuild_psych_book.py` 把原教材文本解析为 11 章 `document.json` 与逐页可定位的 PDF；`scripts/make_psych_sample.py` 生成独立样章索引。
2. **问答链路**：`agents/psychology_qa.py` 的离线分支改为摘录教材证据原文并带 `[n]` 引用，不再恒定返回不可用。
3. **图谱页**：`scripts/build_graph_candidate.py` 以本地规则（术语表 + 定义句式 + 段落共现）生成候选图谱；`graph_viewer.py` 抽出 `attach()` 供主站内嵌；前端为 Cytoscape 视图。
4. **前端改版**：`frontend/theme.css` 主题层（深墨侧栏、学术蓝、引文琥珀），练习页两栏布局，学习记录空态，`app.js` 关闭心理学模式下无意义的离散数学接口请求。
5. **阅读器视觉**：`reader/src/reader.css` 重排，`frontend/pdf-reader/reader.css` 同步构建产物。

## 教材资产不在仓库内

以下目录被 `.gitignore` 排除，需按 README 的「教材接入」步骤在本机生成：

- `knowledge/courses/experimental-psychology-3/`：11 章正文、PDF、页面坐标、检索索引
- `knowledge/graph/psychology-candidate/`：候选图谱与来源 PDF

生成前提是准备原始教材文本，然后执行：

```bash
python scripts/rebuild_psych_book.py
python scripts/make_psych_sample.py
python scripts/build_psychology_sample_index.py --all
python scripts/build_graph_candidate.py
```

排除原因：体积（约 230 MB）与教材版权，仓库约定教材资产单独分发。

## 启动

```bash
python -X utf8 -m scripts.start_server --port 8000
```

`LLM_MOCK=1` 为离线演示模式；配置 `DEEPSEEK_API_KEY` 后设 `LLM_MOCK=0` 走真实模型，教材引用仍逐条核验，核验不过时宁可不答。
