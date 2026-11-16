# PostgreSQL 全量存储迁移设计（宿主业务库 + LightRAG 教材库 + mem0 记忆层）

日期：2026-11-16（2026-11-14 初稿，经 grill-me 修订）
状态：经 brainstorming 与逐题质询确认；本文固化需求与设计，尚未实施。
后续独立设计：LangGraph 接入（本设计为其提供 psycopg 与 PostgreSQL 基础，不在本轮范围）。

## 0. Grill-me 决策记录（2026-11-14 ~ 11-16）

| # | 问题 | 决定 |
|---|---|---|
| 1 | 实施顺序 | 先 PostgreSQL 基础，再 LangGraph |
| 2 | PostgreSQL 位置 | 本机原生 Windows 安装，不用 Docker |
| 3 | pgvector | 有 VS C++ 生成工具，按官方 `nmake` 编译 0.8.7 |
| 4 | LightRAG 存量索引 | 一次性导入，不调用 LLM 重新建图 |
| 5 | SQLite 是否保留 | 只支持 PostgreSQL，删除 SQLite 分支 |
| 6 | LightRAG 切换方式 | 硬切，不保留文件存储后端 |
| 7 | 向量对照门禁 | 门禁时 `enable_indexscan=off` 精确扫描，运行用 HNSW |
| 8 | 旧业务数据 | **全部丢弃**，空库起步，只保留教材文件与 LightRAG 索引 |
| 9 | 记忆层架构 | 账本权威 + mem0 卡片（卡在 PG 留表，mem0 做索引） |
| 10 | mem0 写入模式 | `infer=False`，卡片内容由本项目规则决定 |
| 11 | 卡片存储 | PG `memory_documents` + mem0 索引，双向可对账 |
| 12 | mem0 写入时机 | 异步：PG 先落库，后台 worker 写 mem0；PG 关键词检索兜底 |
| 13 | mem0 embedding | 复用 `BAAI/bge-small-zh-v1.5`（512 维，fastembed） |
| 14 | LangGraph | 本轮不接入，需求保留；本设计先交付 PostgreSQL 与 mem0 |

被取代的旧结论：`docs/2026-10-11-student-memory-research.md` 曾决定"mem0 暂不设为默认记忆后端，保留 provider 接口"。本轮明确改为接入 mem0，该文档需要同步更新。

## 1. 已确认的需求

1. 宿主业务库从 SQLite 迁移到 PostgreSQL，**只支持 PostgreSQL**，删除 SQLite 双后端分支。
2. LightRAG 教材库的 KV、向量、图、文档状态、LLM 缓存全部存 PostgreSQL，**硬切**，不保留文件存储后端。
3. 现有教材索引用**一次性导入**进入 PostgreSQL，不调用 LLM 重新建图；教材原文、doc_id、chunk_id、release 身份和引用坐标不变。
4. **旧业务数据全部丢弃**：学生账号、会话、学习任务、引用记录、学习进度、旧记忆，一律不迁移。PG 空库起步，只导入教材与索引。
5. 记忆层改为：PG 存账本（会话/证据/学习事件）与卡片，mem0 存卡片向量并负责语义检索；卡片内容由本项目规则决定（`infer=False`）。
6. 测试也只跑 PostgreSQL；vendor 里 DeepTutor 自己的 `chat_history.db` 等 SQLite 不在本轮范围。
7. PostgreSQL 用本机原生安装（Windows），pgvector 用源码编译；不使用 Docker。

## 2. 环境与库布局

| 项 | 值 |
|---|---|
| PostgreSQL | 18（EDB Windows 安装包），服务 `127.0.0.1:5432` |
| 扩展 | `pgvector 0.8.7`，`nmake /F Makefile.win` + `nmake /F Makefile.win install`，`PGROOT=C:\Program Files\PostgreSQL\18` |
| `heart` | 旧课程业务库（空库，仅保留非心理学入口可用） |
| `heart_psychology` | 当前课程业务库：账本表、卡片表、mem0 的 pgvector 表 |
| `heart_rag` | LightRAG 全部存储（11 张 `LIGHTRAG_*` 表） |
| Python 驱动 | `psycopg[binary]` 3.3.x + `psycopg-pool`，SQLAlchemy 方言 `postgresql+psycopg` |

环境变量：

```
DATABASE_URL=postgresql+psycopg://heart:<pw>@127.0.0.1:5432/heart
COURSE_DATABASE_URL=postgresql+psycopg://heart:<pw>@127.0.0.1:5432/heart_psychology
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_USER=heart
POSTGRES_PASSWORD=<pw>
POSTGRES_DATABASE=heart_rag
MEM0_HISTORY_PATH=.runtime/mem0/history.sqlite
```

`COURSE_DATABASE_URL` 必须显式指定，保持现有 `course_database_url()` 的"课程库不得与旧库相同"约束。LightRAG 直接读取 `POSTGRES_*`。

## 3. 宿主业务库改动

| 文件 | 改动 |
|---|---|
| `database/database.py` | 删除 SQLite event/`BEGIN IMMEDIATE` 分支；PG 连接池（`pool_pre_ping`、`pool_size`、`max_overflow`）；`session_scope(immediate=True)` 改为事务级 `pg_advisory_xact_lock(2147480001)` |
| `database/memory_index.py` | 删除 FTS5 影子表与触发器；卡片表加 `tsvector` 表达式索引，检索用二元组 `to_tsquery` + `ts_rank_cd`；新增 mem0 同步任务入队 |
| `database/conversation_session_migration.py`、`preference_value_migration.py` | SQL 已是标准 `ALTER TABLE`/`CREATE INDEX`，PG 直接执行 |
| `requirements.txt` | 加 `psycopg[binary]`、`psycopg-pool`、`mem0ai==2.2.1`；移除 `PyMySQL` |
| `.env.example`、`README.md` | 更新连接串、安装步骤、PG 前置条件 |

```python
# shortcut: PG 用单库级 advisory lock 复刻 SQLite 单写者语义；
# 多用户高并发写入成为瓶颈时，改为按 student_id 哈希的细粒度锁。
```

`init_db()` 继续用 `Base.metadata.create_all` + 两个手写迁移，不引入 Alembic。

空库初始化不写迁移脚本：`create_all` 建表即可，旧 SQLite 文件移到 `.runtime/legacy-sqlite/` 留档，不参与运行。

## 4. LightRAG 硬切设计

### 4.1 存储绑定

`knowledge/lightrag/engine.build_rag()` 固定传：

```python
kv_storage="PGKVStorage",
vector_storage="PGVectorStorage",
graph_storage="PGTableGraphStorage",
doc_status_storage="PGDocStatusStorage",
```

不新增存储开关。`PGTableGraphStorage` 用普通表存图，不依赖 Apache AGE；`PGVectorStorage` 初始化时自动 `CREATE EXTENSION IF NOT EXISTS vector`。workspace 沿用现有 `deeptutor_426733019d24d665`，保证导入后 id 与引用身份一致。

### 4.2 文件依赖改走 PG

| 位置 | 硬切后 |
|---|---|
| `knowledge/fixed_book.py:193` 直读 `vdb_entities.json` | 初始化后从 PG 读取实体词表 |
| `knowledge/lightrag/retrieval.py:160` 校验 `index_files.json` | 校验 `lightrag_index_manifest` 表 |
| `knowledge/lightrag/storage.py` 用 JSON/`vdb_*` 判断就绪 | 查 `LIGHTRAG_DOC_STATUS` |
| `knowledge/lightrag/pipeline.py:204` 清点文件 | 清点 PG 表并写 manifest |
| `knowledge/lightrag/cache_reuse.py` | 读 `LIGHTRAG_LLM_CACHE` |
| `graph_viewer.py` | 查询 PG，页面与接口不变（改为需要数据库连接） |
| `scripts/check_lightrag_completion.py` | 查 PG 三类表 |

仍留在磁盘：`input/` 教材原文、`input_manifest.json`、`source_map.json`、`policy.json`、`meta.json`（release 身份）、`__parsed__/` sidecar。这些是教材素材与发布身份，不是可变存储。

### 4.3 一次性导入

新增 `scripts/import_lightrag_candidate_to_pg.py`，不调用 LLM：

1. 用 LightRAG 存储类建 11 张表；workspace 取 candidate `meta.json`；用 `HostEmbedding`（512 维）初始化。
2. KV：8 个 `kv_store_*` 按 namespace upsert。
3. 向量：解码 `vdb_chunks`/`vdb_entities`/`vdb_relationships` 的 NanoVectorDB base64 float32，按原 id、原向量写入。
4. 图：graphml 节点/边 → `upsert_node`/`upsert_edge`。
5. 在 `heart_rag` 写 `lightrag_index_manifest`：各 namespace 行数、id 集合 sha256、源 `index_files.json` 签名、导入时间。
6. 幂等：按 `(workspace, id)` upsert。

### 4.4 对照门禁（删文件分支前必须通过）

固定题集 `tests/data/native_lightrag_latency_cases.json`（10 题）：

- `mode=naive`：对比 session 设置 `SET LOCAL enable_indexscan=off`，强制精确扫描，比 chunk 命中集合。
- `mode=hybrid`：固定 `hl_keywords`/`ll_keywords`，比 chunk/entity/relationship 三类命中 id 集合。
- 通过条件：`chunk_id`、`document_id`、引文范围集合完全一致；排序差异允许。
- 同时核对：图节点/边数量、doc_status 行数与 `chunks_list`、实体词表条目数。
- 不通过则停在文件后端，不切 `.env`、不删分支。

## 5. 记忆层：账本 + 卡片 + mem0

### 5.1 三层职责

| 层 | 位置 | 职责 |
|---|---|---|
| 账本 | PG `conversations`/`evidence`/`learning_events` | 原始事实，只追加；记忆的唯一权威 |
| 卡片 | PG `memory_documents` | 规则从账本生成；带来源、`verification`、`content_hash`、`epoch`、`mem0_id` |
| 索引 | mem0（pgvector 表在 `heart_psychology`） | 卡片向量检索；`infer=False`，只存不算 |

### 5.2 mem0 配置

```python
config = {
    "history_db_path": os.environ.get("MEM0_HISTORY_PATH", ".runtime/mem0/history.sqlite"),
    "vector_store": {
        "provider": "pgvector",
        "config": {
            "connection_string": COURSE_DATABASE_URL,
            "collection_name": "student_memory",
            "embedding_model_dims": 512,
            "hnsw": True,
        },
    },
    "embedder": {
        "provider": "fastembed",
        "config": {"model": "BAAI/bge-small-zh-v1.5", "embedding_dims": 512},
    },
    "llm": {
        "provider": "openai",
        "config": {
            "model": os.environ["OPENAI_MODEL"],
            "api_key": os.environ["DEEPSEEK_API_KEY"],
            "openai_base_url": os.environ["OPENAI_BASE_URL"],
        },
    },
}
```

- `infer=False` 时不调用 LLM；仍显式指向 DeepSeek，避免回落到 OpenAI 默认配置。
- `history_db_path` 固定为 `.runtime/mem0/history.sqlite`。这是本轮唯一保留的 SQLite 文件，只记录 mem0 的变更历史，可由 PG 卡片表重建。
- 中文处理：embedding 用 bge-small-zh；卡片文本由现有 `memory_terms` 规则构造，不依赖 mem0 的中文提示词。

### 5.3 写入与检索

写入：

1. `MemoryIndexRepository.sync_memory_index` 仍从账本生成卡片，写 PG `memory_documents`（同事务）。
2. 事务提交后入队 `memory_jobs`；后台 worker 调 `mem0.add([{"role":"user","content":card}], user_id=student_id, infer=False, metadata={...})`，把返回的 `memory_id` 写回 `memory_documents.mem0_id`。
3. `metadata` 必含：`student_id`、`session_id`、`source_kind`、`source_id`、`verification`、`epoch`、`content_hash`。
4. 重复卡片按 `content_hash` 跳过；mem0 侧失败只重试，不影响回合。

检索：

1. PG 关键词检索（tsvector，二元组 OR）始终可用，是兜底。
2. mem0 检索带 `filters={"student_id": ..., "epoch": ...}`；按 `verification` 决定是否可作为"已证实"证据。
3. 两路结果按现有 RRF/预算逻辑融合；记忆永远不能当教材事实。

删除：

1. 写 `memory_exclusions`（来源黑名单），`memory_epoch` 递增。
2. 按 `source_id` 查 `memory_documents.mem0_id`，调 `mem0.delete(memory_id)`，删 PG 卡片行。
3. 重建索引时先查黑名单，删过的来源不再生成卡片；旧 epoch 的卡片检索不可见。

### 5.4 边界

- mem0 不得接受助教未核验的陈述作为卡片内容；卡片只由规则从账本生成。
- mem0 的 `history.sqlite` 不参与证据链，不参与备份一致性要求；丢失可重建。
- 现有 `MemoryManager` 对外 API 不变，替换的是 `MemoryIndexRepository` 内部实现。

## 6. 测试策略（PG-only）

新增 `tests/pg_support.py`：

- 读 `TEST_POSTGRES_URL`，为每次测试创建 `heart_test_<uuid>`，设置 `DATABASE_URL`/`COURSE_DATABASE_URL`/`POSTGRES_DATABASE`，用完 drop。
- LightRAG 夹具另建 `heart_rag_test_<uuid>`。
- mem0 单元测试用假 vector store；保留 1 个真实 mem0 + pgvector 集成测试。

改造范围：

- 硬编码 `sqlite:///` 的宿主业务库测试改走 `pg_support`。
- LightRAG 文件夹具测试（`test_lightrag_backend`、`test_lightrag_relocation`、`test_graph_viewer`、`test_fixed_book`、`test_native_course_kb_migration`、`test_output_speed`）改 PG 或纯函数。
- 记忆测试（`test_memory_management`、`test_memory_retrieval`、`test_memory_events`、`test_memory_jobs`、`test_unified_context_chain` 相关用例）改为 PG 卡片表 + mem0 适配层。
- vendor 的 SQLite 测试（`chat_history.db`、practice store、session store）不动。

## 7. 验收标准

1. 三个库建立完成；`SELECT extversion FROM pg_extension WHERE extname='vector'` 返回 0.8.7。
2. 空库启动：建表成功；旧 SQLite 已移出运行路径。
3. `/health` 的 `fixed_book.ready=true`；启动不读文件存储。
4. 真实教材问题 3 个、划选 1 个、图题 1 个、研究 1 个：回答带合法引用，引用可打开原 PDF 坐标。
5. 检索对照门禁通过（4.4）。
6. 记忆链路：生成卡片 → 异步写 mem0 → 跨会话检索命中 → 删除后不再召回 → epoch 递增后旧卡片不可见。
7. `pg_dump` 三库可备份；恢复到空实例后服务可启动。
8. 记录启动耗时与单题耗时；仅记录，不作迁移门槛。

## 8. 回滚

1. 代码回退到硬切前提交（文件存储分支仍在）。
2. 恢复原 `.env`。
3. 业务库回到空库或旧 SQLite 留档；LightRAG 回原 candidate 目录。
4. PG 三个库保留不删，作为对照资料。

因为"删文件存储分支"是最后一步，迁移、导入、门禁、切库期间任何失败都可以停在旧代码上。

## 9. 风险与限制

| 风险 | 处理 |
|---|---|
| pgvector 在 PG18 上编译失败 | 先做最小编译验证；失败改 Docker 镜像，连接串与代码不变 |
| LightRAG 导入后检索不一致 | 4.4 门禁阻断切换 |
| mem0 `history.sqlite` 与 PG-only 冲突 | 显式列为唯一例外，可重建，不进证据链 |
| mem0 依赖较新、快照库升级带来行为变化 | 钉 `mem0ai==2.2.1`；升级单独立项 |
| `infer=False` 不做语义去重，卡片重复 | 按 `content_hash` 在 PG 去重；mem0 只存已去重卡片 |
| 全局 advisory lock 限制写入并发 | 当前规模可接受；记录为可升级点 |
| 异步写 mem0 有短暂不一致 | PG 关键词检索兜底；卡片刻可见 |
| 旧数据全丢后无法演示历史 | 已确认接受；旧 SQLite 留档但不接入 |

## 10. 非目标

- LangGraph 接入（另有独立 spec）。
- vendor DeepTutor 的每用户 SQLite 迁移。
- `knowledge/rag_index.sqlite3` 本地教材向量索引（正在被 LightRAG 取代，本次不动）。
- JSON → JSONB、Alembic、连接池压测、远程 ECS 部署。
- mem0 的 `infer=True` 自动抽取与中文提示词优化（本轮只做 `infer=False`）。
