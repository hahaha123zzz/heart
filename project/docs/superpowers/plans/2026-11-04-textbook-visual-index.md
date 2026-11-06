# 教材图表索引实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为实验心理学教材建立按章/节检索的 Markdown 图表索引，并接入 `lookup_figures` 工具，让回答模型在答题前按需查看本节图表。

**Architecture:** 先用一个脚本从现有 `document.json` / `assets.json` / `pdf_manifest.json` 生成紧凑候选；再按章并行交给子代理做视觉核对并写 MD 片段；最后合并、校验、生成单文件索引。工具只解析该文件并按当前 `learning_target` 截取本节条目，不引入新数据库或检索服务。

**Tech Stack:** Python 3、现有 `agents` 工具协议、Pillow（候选尺寸）、Markdown。

**Spec:** `project/docs/superpowers/specs/2026-11-04-textbook-visual-index-design.md`

## Global Constraints

- 索引路径固定：`knowledge/course_visual_index.md`。
- 只收录真实图/表；二维码、装饰条、缺图占位、章节教学目标排版表一律排除。
- 不改教材原文件、`assets.json` 审核状态或发布清单。
- 工具默认只返回当前小节；图号明确点名时才跨节。
- `缺图` 条目不得返回 `asset_id`。
- 现有 `retrieve_course` 行为保持不变。

## Review Focus

- 图注错配：现有 `labels` 可能把二维码标成“图3-8”，必须视觉复核，不能直接信。
- 表格拆分：同一张表被拆成多个 `table` 块，合并错误会重复或漏表。
- 缺图占位：400×300 占位图不能当教材原图展示。
- 小节定位：条目必须落在正确 `section_id`，否则工具会返回错节图表。
- 工具越界：默认不得返回同章其他节，否则违背“其他一概掠过”。

---

### Task 1: 候选提取脚本

**Files:**
- Create: `scripts/build_visual_index.py`
- Test: `tests/test_visual_index.py`

**Interfaces:**
- Produces:
  - `chapter_candidates(chapter_id: int) -> dict`
  - `write_candidates(out_dir: Path) -> list[Path]`
  - `merge_drafts(drafts_dir: Path, out_path: Path) -> dict`
  - `validate_index(path: Path) -> dict`

- [ ] **Step 1: 写失败测试**

在 `tests/test_visual_index.py` 中断言：第 3 章候选包含 `image-03-0003` 且 `caption` 含“图3-1”；`image-03-0002`（400×300）被标记为 `excluded`；表格分组包含 blocks `18,20` 且 caption 含“表3-1”；候选小节标题含“第一节 相关设计”。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_visual_index.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现脚本**

解析 `knowledge/courses/experimental-psychology-3/chapters/chapter_*/document.json` 与 `assets.json`：
- 图片候选：读取尺寸；`809x50`、`1688x58`、`235x235`、`335x735`、`400x300` 标为 `excluded`；其余为 `candidate`；从 `context` 和邻近 block 提取 `图X-Y` 图注。
- 小节：取每个 block 之前最近的短标题（`一、`、`（一）`、`1.`）。
- 表格：按同 `section_id` 且块间距 ≤4 合并；跳过 `section_id is None` 的章首表；提取 `表X-Y` 表题；保留 `blocks`、`header`、`text`。
- 输出 `.runtime/visual-index/candidates/chapter_XX.json`。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_visual_index.py -q`
Expected: PASS

- [ ] **Step 5: 生成全部候选并记录统计**

Run: `python scripts/build_visual_index.py candidates`
Expected: 生成 11 个 JSON；报告每章 candidate/excluded/table 数。

- [ ] **Step 6: 提交**

```bash
git add scripts/build_visual_index.py tests/test_visual_index.py
git commit -m "feat: add textbook visual index candidate builder"
```

---

### Task 2: 按章并行视觉标注

**Files:**
- Create: `.runtime/visual-index/drafts/chapter_XX.md`（临时，不提交）

**Interfaces:**
- Consumes: Task 1 的候选 JSON。
- Produces: 每章 MD 片段，条目格式与 Spec 一致。

- [ ] **Step 1: 启动 8 个子代理**

分配：`01-02`、`03`、`04`、`05`、`06`、`07`、`08-09`、`10-11`。每个子代理读取对应候选 JSON，逐张打开 `candidate` 图片核对，按 Spec 输出本章片段。

- [ ] **Step 2: 子代理自检**

每个片段检查：无装饰/二维码/缺图；每条有章/节/编号/状态；表格不重复；`缺图` 不带 `asset_id`。

- [ ] **Step 3: 合并**

Run: `python scripts/build_visual_index.py merge`
Expected: 生成 `knowledge/course_visual_index.md`；输出条目/状态统计。

---

### Task 3: 索引校验与抽查

**Files:**
- Modify: `scripts/build_visual_index.py`（`validate` 子命令）
- Test: `tests/test_visual_index.py`

- [ ] **Step 1: 校验结构**

检查 11 章、节标题存在、条目字段齐全、无重复编号、`asset_id` 在 `assets.json` 中存在且不是 excluded。

- [ ] **Step 2: 抽查**

抽取 10–15 条，逐条对照原图/原文；错误退回 Task 2 重标。

- [ ] **Step 3: 输出报告**

Run: `python scripts/build_visual_index.py validate`
Expected: 打印 `chapters=11 entries=N errors=0`，并列出 `待核`/`缺图`。

---

### Task 4: `lookup_figures` 工具

**Files:**
- Create: `knowledge/visual_index.py`（解析/查询）
- Modify: `agents/q3_tools.py`（注册工具）
- Test: `tests/test_visual_index.py`

**Interfaces:**
- Produces:
  - `load_index(path: str | Path | None = None) -> VisualIndex`
  - `VisualIndex.lookup(*, chapter_id: int | None, section_id: int | None, query: str, limit: int = 8) -> list[dict]`
  - `LookupFiguresTool`，参数 `query? / chapter_id? / section_id? / limit?`

- [ ] **Step 1: 写失败测试**

覆盖：默认当前小节只返回本节；同章其他节不返回；`图3-1` 跨节精确命中；本节无条目返回“本节无图表”；`缺图` 条目无 `asset_id`。

- [ ] **Step 2: 实现解析与工具**

按 `## 第X章` / `### 第Y节` / `#### 图|表` 解析；条目按 `｜` 切分；`lookup` 先按章节过滤，再按 query 命中知识点/名称/内容；图号正则优先。工具从 `context.state['learning_target']` 取默认章节。

- [ ] **Step 3: 注册与协议**

`build_registry` 的 `overlay`/`names` 加入 `lookup_figures`；`loop_prompts.py` 增加“回答教材知识问题前先调用 lookup_figures”的协议行；更新 `tests/test_first_wave_tools.py` 的工具名集合断言。

- [ ] **Step 4: 运行测试**

Run: `python -m pytest tests/test_visual_index.py tests/test_first_wave_tools.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add knowledge/visual_index.py agents/q3_tools.py agents/loop_prompts.py tests/test_visual_index.py tests/test_first_wave_tools.py
git commit -m "feat: add textbook figure index lookup tool"
```

---

### Task 5: 端到端验证

- [ ] **Step 1: 索引可用**

Run: `python scripts/build_visual_index.py validate`
Expected: `errors=0`。

- [ ] **Step 2: 工具查询**

对第 3 章第 1 节查询“正相关”，应返回图3-2/3/4 或表3-1，不返回第 2 节；查询“图6-10”应跨节精确命中（即使当前在第 3 章）。

- [ ] **Step 3: 回归**

Run: `python -m pytest tests/test_visual_index.py tests/test_figures.py tests/test_answer_flow.py -q`
Expected: PASS；若既有测试因注册表工具数变化失败，按新工具数更新断言，不改 `retrieve_course` 行为。

- [ ] **Step 4: 人工抽查**

至少 10 条对照原图/原文，记录通过数；未通过条目退回重标。
