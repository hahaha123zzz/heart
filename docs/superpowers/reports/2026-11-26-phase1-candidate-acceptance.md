# 阶段 1 候选部署与验收报告

日期 2026-11-26
分支 `codex/phase1-textbook-assets-20261126`（隔离工作树，从 `36f33867` 新建）
计划 [2026-11-26 固定教材启动与回答延迟](../plans/2026-11-26-fixed-book-startup-and-answer-latency.md)

## 状态

启动顺序、发行核对、上游快照依赖、教材静态资产、引用坐标索引、冻结输入缺席启动都已在候选部署验证。
旧 SQLite 索引的调用方迁移、图表词表预生成、完整的引用/选区/练习/历史回归仍未完成。

## 1. 隔离与候选环境

- 基线：现有 8000 部署（旧发行 `progressive-context-20261125d`），未改动。
- 候选：`.runtime/phase1-candidate-20261126`，发行 `phase1-candidate-20261126c`，端口 **28000/28001/28002**，
  独立 worker home、独立课程/业务数据库（setup 生成的 `heart_local8000_*`）、10 个新评审账号。
- 教材目录仍是同一份正式教材；LightRAG 候选是共享的只读 PG 索引。
- 评审账号 `heart-review-01` 的个人模型凭据从现有部署复制，候选使用同一 `HEART_MODEL_ENCRYPTION_KEY`；
  这是候选测试的例外，正式部署应各自配置。

## 2. 启动收益（候选，含本批改动）

同一候选连续启动，worker 先行：

| 配置 | 固定教材初始化 | 宿主健康 | worker 检索预热 | 说明 |
| --- | --- | --- | --- | --- |
| 仅教材哈希表，引用索引首次构建 | 32.00 | 51.49 | 174.92（首次冷） | `fixed_book.citation` 15.9 秒在启动内建引用索引 |
| 引用索引也随资产发布 | 11.21 | 30.30 | 11.38 | `fixed_book.citation` 0.0，资产分支 |
| 候选不再提供冻结输入目录 | 24.09 | 34.65 | 12.31 | 图表映射首次从资产读取 4.8 秒；检索正常 |

- 冻结输入 325 个文件已复制进资产；候选的 `candidate-phase1-noinput` 删掉 `input` 后仍能启动，
  `lightrag.manifest.frozen_input` 和 `host_textbook` 均为 0 秒、来源 `install_snapshot`。
- 旧索引预热和样例查询已从启动移除（无 `warmup.local_index`、`warmup.sample_query`）。
- 引用坐标索引来自资产（`branch=install_asset`），不再在启动或首次提问时构建。
- 图表映射来源 `install`（178 个视觉资产），读取的是资产内的冻结输入副本。

对照基线（旧发行，阶段 0 冷缓存样本）：固定教材 33.2–34.8 秒，宿主健康 43.7–44.2 秒，
旧索引预热 5.1 秒、样例查询 1.2 秒，引用索引首次构建 15.9 秒。

## 3. 候选问答（冻结输入目录已删除）

账号 `heart-review-01`，题「自变量是什么」：

| 里程碑 | 候选（无 input） | 阶段 0 基线 |
| --- | --- | --- |
| 首问完成 | 20.41 秒 | 20.13 秒 |
| 同会话第二问 | 6.96 秒 | 19.65 秒 |
| 工具 / 来源 | 2 / 4 | 2 / 4 |
| 输入 / 输出 Token | 13,996 / 843 | 14,345 / 908 |

检索、来源和 Token 规模与基线接近；第二问更快，但两边模型与缓存条件不同，不能作为严格对照。

### 3.1 无旧 SQLite 索引、无冻结输入的候选

- 教材目录复制到 `E:\heart-runtime\phase1-textbook-noindex`（131.9 MiB，408 个文件）：
  删除 `rag_index.sqlite3`，写入 `retrieval_identity.json` 固定已验证的旧索引摘要 `2a052d6d9062…`。
- LightRAG 候选使用 `candidate-phase1-noinput`（已删 `input`）。
- 资产记录绑定这套教材/索引后，`fixed_book.release` 的 release_id 仍是
  `e051f817145b…`，与带旧索引的原教材一致——已有引用不会因移出旧索引失效。
- 启动：`fixed_book.assets` 0.056 秒，冻结输入与正式教材扫描均为 0 秒，
  引用索引来自资产，固定教材初始化 23.39 秒（图表映射首次从资产拷贝读取）。
- 教材问答：首问 26.27 秒、同会话第二问 6.58 秒，1 次工具、4 条来源；检索正常。
- 启动日志没有 `warmup.local_index`、`warmup.sample_query`。
- worker 的旧索引预热（`heart_rag.warm_retrieval`）也已删除；无索引时不再出现
  `rag_index.sqlite3` 的 `FileNotFoundError`，该错误只影响旧预热、不影响 LightRAG 回答。
- 来源事件的 `location` 有章节/小节/块范围，但 `page` 为 null、`reader_citation` 为空；
  页码跳页需要在浏览器里点来源验证，不能只看事件。

### 3.2 图表检索词表
- 资产现在包含 178 个视觉资产的检索词表（`image_terms`）。
- 当前候选发行 `phase1-candidate-20261126d` 建于此改动之前，仍在启动时整理词表（0.86 秒）；
  下一次打包会直接加载资产词表。

四类问题在候选（仍带 input）也跑过：问候 27.16/3.22 秒、原题 15.11/6.16 秒、
明确小节 41.18/4.52 秒（7 工具、16 来源）、无教材证据 6.97/5.17 秒。明确小节题比阶段 0 少 2 次工具、
少 7 条来源，回答延迟更高；属于模型与缓存差异，不能单独归因于本批改动。

## 4. 代码与测试

提交：

- `8d747746` 适配器只校验模块路径与接口，不再要求上游快照哈希
- `825f5c4a` 固定教材资产安装与启动加载
- `9d32904f` 引用坐标索引随资产发布，启动不再预热旧索引
- `ce724235` 资产自带冻结输入副本，启动不再读候选 input

验收：

- 干净提交打包 `phase1-clean-20261126` 通过 `verify`；从该发行启动 worker 15 秒就绪。
- 资产安装记录包含：教材 release_id、5 个控制文件摘要、409 个教材文件哈希与大小、
  325 个冻结输入文件的哈希与大小、宿主额外文件指纹、来源映射、引用索引、冻结输入副本。
- 加载只核对身份与文件大小，0.046–0.22 秒；缺失/版本不一致时明确报“请重新安装教材资产”。
- 相关测试：资产与启动 19 项、启动/索引专项 52 项、适配器 pin 1 项通过。

## 5. 已完成与剩余（按 2026-11-26 决定更新）

用户决定：旧入口不再保留；旧回答/引用数据直接丢弃；先只改线下版本，线上 8000 不动；线下教材副本直接删除旧索引。

据此，第 3 项从“逐个迁移”改为“退役旧入口”：

- 旧索引的启动预热已删除（宿主旧样例查询、worker `warm_retrieval`）。
- 固定教材教材问答、来源、图表词表已不读旧索引；候选在无索引、无冻结输入的副本上完成问答。
- 旧回答数据不再需要兼容，`retrieval_identity.json` 的发行身份固定仅用于教材版本一致性，不承担旧引用迁移。

剩余旧调用（可直接删除/停用，不需要迁移）：

| 调用方 | 处理 |
| --- | --- |
| `agents/agent_loop_service.py`、`agents/q5_runtime.py`、`agents/course_search.py` | 旧聊天/旧检索入口，停用并从路由移除 |
| `knowledge/psychology_retrieval.py` 的旧 retrieve | 固定教材不再使用；保留 `HEADING` 等纯函数 |
| `knowledge/hybrid_retrieval.py` 的 `INDEX`/`_vectors`/`retrieve_hybrid`、`knowledge/textbook.py` 的 `load_textbook` | 旧全文检索；只保留 `_reranker_on_device` 等固定教材需要的能力 |
| `integrations/deeptutor/knowledge_client.py`、`published_course.py`、`course_preview_api.py` | 预览/发布工具；改为显式归档路径或停用 |
| 脚本 `check_local_rag.py`、`check_course_navigation.py`、`check_deeptutor_sessions.py` 等 | 离线工具，改归档路径或标记退役 |

其余未完成：

| 项 | 状态 |
| --- | --- |
| 候选最后一次打包（worker 启动不再预热旧索引） | 进行中：`phase1-candidate-20261126f` |
| 引用跳页/图表/选区/练习/旧会话回归 | 旧回答数据已决定丢弃，只需验证新回答的页码与跳页；尚未跑浏览器 |
| 在线教材目录移出旧索引 | 未执行（按决定先只改线下） |
| 候选 LightRAG PG 独立 | 不做（功能验收不需要） |

## 6. 当前运行

- 基线 8000 部署保持原位、可访问。
- 候选 28000/28001/28002 正在运行，指向 `candidate-phase1-noinput`（199.2 MiB，无 input），
  资产目录含冻结输入副本（约 100 MiB）和引用索引。
- 候选停止：`manage_student_local.py stop --root .runtime/phase1-candidate-20261126`。
