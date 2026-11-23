# PostgreSQL + mem0 迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把宿主业务库和 LightRAG 教材库全部迁到 PostgreSQL，并把记忆层的卡片索引接到 mem0；旧业务数据全部丢弃，空库起步。

**Architecture:** 一个本机 PostgreSQL 18 实例放三个库：`heart`（空库）、`heart_psychology`（账本 + 卡片 + mem0 向量）、`heart_rag`（LightRAG 的 11 张表）。宿主代码删除 SQLite 分支；LightRAG 硬切到 `PGKVStorage`/`PGVectorStorage`/`PGTableGraphStorage`/`PGDocStatusStorage`，存量索引用一次性脚本导入；mem0 以 `infer=False` 只存索引，卡片正文仍在 PG，异步同步、可重建。

**Tech Stack:** PostgreSQL 18、pgvector 0.8.7、psycopg 3.3、SQLAlchemy 2.1、lightrag-hku 1.5.7、mem0ai 2.2.1（fastembed + bge-small-zh-v1.5）、FastAPI、pytest。

**Spec:** `docs/superpowers/specs/2026-11-14-postgresql-storage-migration-design.md`

## Global Constraints

- 只支持 PostgreSQL；除 mem0 的 `history.sqlite` 外，运行路径不得再出现 SQLite。
- 旧业务数据不迁移；只导入教材文件与 LightRAG 索引。
- 不改 `project/vendor/DeepTutor`；vendor 自带的 SQLite 存储不在本轮范围。
- 版本钉死：`pgvector 0.8.7`、`lightrag-hku==1.5.7`、`mem0ai==2.2.1`、`psycopg>=3.3,<4`。
- 所有命令从 `project/integration/discrete-math-tutor` 运行，Python 用 `.venv-runtime/Scripts/python.exe`。
- 每个测试使用独立临时库，测试结束 drop；不得复用开发库。
- LightRAG 的 doc_id、chunk_id、workspace（`deeptutor_426733019d24d665`）、release 身份与引用坐标不得改变。
- 迁移期间保留旧 SQLite 文件与 candidate 目录，只读留档；不删除。

## Review Focus

- 连接串串库：业务库写成 `heart_rag`、或 LightRAG 写成 `heart_psychology`，服务能启动但读到错误数据。
- 中文全文检索：查询没切成二元组，`to_tsquery` 永远查不到 `index_text`。
- 异步索引滞后：刚写入的记忆在 mem0 跟上之前必须还能被 PG 关键词检索命中。
- 删除/epoch：删掉的卡片和旧 epoch 卡片不得再被 mem0 召回。
- 启动顺序：LightRAG 初始化仍读 `vdb_entities.json` 之类文件，导致硬切后启动崩溃。

---

### Task 1: 安装 PostgreSQL 18 与 pgvector

**Files:**
- Modify: `.env.example`
- Create: `docs/postgres-setup.md`

**Interfaces:**
- Produces: 本机 `127.0.0.1:5432` 可用，角色 `heart`，库 `heart`/`heart_psychology`/`heart_rag`，扩展 `vector 0.8.7`。

- [ ] **Step 1: 安装 PostgreSQL 18 并建角色与库**

用 EDB Windows 安装包安装，设置超级用户密码；在 `psql -U postgres` 执行：

```sql
CREATE ROLE heart LOGIN PASSWORD '<pw>' CREATEDB;
CREATE DATABASE heart OWNER heart;
CREATE DATABASE heart_psychology OWNER heart;
CREATE DATABASE heart_rag OWNER heart;
```

- [ ] **Step 2: 编译安装 pgvector 0.8.7**

在 “x64 Native Tools Command Prompt for VS” 以管理员运行：

```cmd
set "PGROOT=C:\Program Files\PostgreSQL\18"
cd %TEMP%
git clone --branch v0.8.7 https://github.com/pgvector/pgvector.git
cd pgvector
nmake /F Makefile.win
nmake /F Makefile.win install
```

- [ ] **Step 3: 验证扩展**

Run: `psql -U heart -d heart_rag -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extversion FROM pg_extension WHERE extname='vector';"`
Expected: `0.8.7`

- [ ] **Step 4: 写配置文档并提交**

`docs/postgres-setup.md` 记录安装步骤、三个库、备份命令 `pg_dump -U heart -Fc heart_psychology > ...`；`.env.example` 增加 spec 第 2 节的变量。

```bash
git add docs/postgres-setup.md .env.example
git commit -m "docs: PostgreSQL 18 与 pgvector 安装说明"
```

---

### Task 2: PG 测试夹具

**Files:**
- Create: `tests/pg_support.py`
- Test: `tests/test_pg_support.py`

**Interfaces:**
- Produces: `temp_databases(prefix: str = "heart_test") -> Iterator[dict]`，yield 含 `DATABASE_URL`、`COURSE_DATABASE_URL`、`TEST_POSTGRES_URL`、`POSTGRES_DATABASE`、`POSTGRES_HOST`、`POSTGRES_PORT`、`POSTGRES_USER`、`POSTGRES_PASSWORD` 的字典；`maintenance_url() -> str` 读 `TEST_POSTGRES_URL`（默认 `postgresql://heart:<pw>@127.0.0.1:5432/postgres`）。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_pg_support.py
import os, psycopg
from tests.pg_support import temp_databases

def test_temp_databases_are_isolated():
    with temp_databases() as env:
        assert env["COURSE_DATABASE_URL"].endswith("heart_test_")
        with psycopg.connect(env["COURSE_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")) as conn:
            assert conn.execute("select current_database()").fetchone()[0].startswith("heart_test_")
    with psycopg.connect(env["TEST_POSTGRES_URL"].replace("postgresql+psycopg://", "postgresql://")) as conn:
        names = [r[0] for r in conn.execute("select datname from pg_database where datname like 'heart_test_%'")]
    assert not names
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_pg_support.py -q`
Expected: `ModuleNotFoundError: tests.pg_support`

- [ ] **Step 3: 实现夹具**

`tests/pg_support.py`：用 psycopg 连维护库，`CREATE DATABASE <name> OWNER heart`，生成两个库名（业务 + rag），`finally` 里 `DROP DATABASE ... WITH (FORCE)`。URL 统一 `postgresql+psycopg://heart:<pw>@127.0.0.1:5432/<name>`，密码从 `TEST_POSTGRES_URL` 解析。

- [ ] **Step 4: 运行确认通过**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_pg_support.py -q`
Expected: `1 passed`

- [ ] **Step 5: 提交**

```bash
git add tests/pg_support.py tests/test_pg_support.py
git commit -m "test: 增加独立 PostgreSQL 测试库夹具"
```

---

### Task 3: 宿主数据库改 PostgreSQL

**Files:**
- Modify: `database/database.py`
- Modify: `requirements.txt`
- Test: `tests/test_postgres_database.py`

**Interfaces:**
- Produces: `engine`、`SessionLocal`、`init_db()`、`session_scope(immediate: bool)`、`course_database_url(url)` 行为不变；`DATABASE_URL` 只接受 `postgresql+psycopg://`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_postgres_database.py
import os
from tests.pg_support import temp_databases

def test_session_scope_immediate_serializes_writers():
    with temp_databases() as env:
        os.environ.update(DATABASE_URL=env["DATABASE_URL"], COURSE_DATABASE_URL=env["COURSE_DATABASE_URL"], TUTOR_COURSE="experimental-psychology-3")
        from database.database import init_db, session_scope, DATABASE_URL
        assert DATABASE_URL.startswith("postgresql+psycopg://")
        init_db()
        with session_scope(immediate=True) as s:
            assert s.bind.dialect.name == "postgresql"

def test_course_database_must_differ():
    import pytest
    from database.database import course_database_url
    with pytest.raises(ValueError):
        course_database_url("postgresql+psycopg://heart:pw@127.0.0.1:5432/heart_psychology")
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_postgres_database.py -q`
Expected: FAIL（`sqlite` 分支或连接失败）

- [ ] **Step 3: 实现**

- `database/database.py`：删除 `sqlite` 分支与 `PRAGMA` 事件；`create_engine` 加 `pool_size=5, max_overflow=5`；`session_scope(immediate=True)` 在 `session.bind.dialect.name == "postgresql"` 时执行 `session.execute(text("SELECT pg_advisory_xact_lock(2147480001)"))`。
- `course_database_url`：非 sqlite 时仍要求显式 `COURSE_DATABASE_URL`，且不得与 `DATABASE_URL` 相同。
- `requirements.txt`：加 `psycopg[binary]>=3.3,<4`、`psycopg-pool>=3.3,<4`、`mem0ai==2.2.1`；删除 `PyMySQL`。

```python
# shortcut: 单库级 advisory lock 复刻 SQLite 单写者语义；
# 多用户高并发写入成为瓶颈时改为按 student_id 哈希的细粒度锁。
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_postgres_database.py -q`
Expected: `2 passed`

- [ ] **Step 5: 提交**

```bash
git add database/database.py requirements.txt tests/test_postgres_database.py
git commit -m "feat: 宿主数据库只支持 PostgreSQL"
```

---

### Task 4: 记忆卡片表与 PG 全文检索

**Files:**
- Modify: `database/models.py`（`MemoryDocumentRow`）
- Modify: `database/memory_index.py`
- Test: `tests/test_memory_index_postgres.py`

**Interfaces:**
- Produces: `MemoryDocumentRow.active: bool`、`mem0_id: str|None`、`mem0_synced_hash: str|None`；`MemoryIndexRepository.memory_lexical(student_id, query, limit=40) -> (list[int], str)` 返回 `"postgres_tsvector"` 或 `"lexical_fallback"`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_memory_index_postgres.py
import os
from tests.pg_support import temp_databases

def test_chinese_bigram_search_hits_card():
    with temp_databases() as env:
        os.environ.update(DATABASE_URL=env["DATABASE_URL"], COURSE_DATABASE_URL=env["COURSE_DATABASE_URL"])
        from database.database import init_db, session_scope
        from database.models import MemoryDocumentRow
        from database.memory_index import MemoryIndexRepository, memory_terms
        init_db()
        with session_scope() as s:
            s.add(MemoryDocumentRow(student_id="s", source_kind="conversation", source_id="1",
                knowledge_point="自变量", content="学生分不清自变量和额外变量",
                index_text=" ".join(sorted(memory_terms("自变量 学生分不清自变量和额外变量"))),
                content_hash="h", source_metadata={}, embedding=[], embedding_model=""))
        ids, mode = MemoryIndexRepository().memory_lexical("s", "自变量是什么")
        assert mode == "postgres_tsvector" and ids
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_memory_index_postgres.py -q`
Expected: FAIL（`sqlite_master` 查询或返回空）

- [ ] **Step 3: 实现**

- `models.py`：`active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))`、`mem0_id`、`mem0_synced_hash`（nullable）。
- `memory_index.py`：删除 `_fts()` 与三个触发器；`init_db` 后建表达式索引
  `CREATE INDEX IF NOT EXISTS ix_memory_documents_tsv ON memory_documents USING gin (to_tsvector('simple', index_text))`。
- `memory_lexical`：`terms = sorted(memory_terms(query))[:48]`；`query = " | ".join(terms)`；
  `SELECT id FROM memory_documents WHERE student_id=:s AND active AND to_tsvector('simple', index_text) @@ to_tsquery('simple', :q) ORDER BY ts_rank_cd(...) DESC LIMIT :n`；无 terms 时走现有 `lexical_fallback`。
- `sync_memory_index`：缺失来源不 `session.delete`，改 `row.active=False`；重建时恢复 `active=True`；`content_hash` 的输入加入该知识点的 epoch（同一事务内先读 `MemoryControlRow.epoch` 到字典，无记录按 0），使 epoch 变化产生新卡片。

- [ ] **Step 4: 运行确认通过**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_memory_index_postgres.py -q`
Expected: `1 passed`

- [ ] **Step 5: 提交**

```bash
git add database/models.py database/memory_index.py tests/test_memory_index_postgres.py
git commit -m "feat: 记忆卡片迁 PostgreSQL 全文索引"
```

---

### Task 5: 现有宿主库测试改 PG

**Files:**
- Modify: `tests/test_clarification_tasks.py`、`test_interactive_practice.py`、`test_psychology_course.py`、`test_psychology_cutover.py`、`test_psychology_memory.py`、`test_psychology_pipeline.py`、`test_psychology_presets.py`、`test_psychology_retrieval_fixes.py`、`test_psychology_visualization.py`、`test_q3_entrypoint.py`、`test_q3_task_loop.py`、`test_q5_learning.py`、`test_task_api.py`、`test_unified_context_chain.py`、`test_memory_events.py`、`test_memory_jobs.py`、`test_memory_management.py`、`test_memory_retrieval.py`
- Test: 上述文件

**Interfaces:**
- Consumes: `tests.pg_support.temp_databases`

- [ ] **Step 1: 逐个替换 `sqlite:///` 与 `:memory:`**

对每处 `create_engine("sqlite:///...")`：改为在 `temp_databases()` 上下文里设置环境变量后 `from database.database import engine`；对子进程测试，把 `DATABASE_URL`/`COURSE_DATABASE_URL` 换成夹具生成的 URL。保留 `rag_index.sqlite3`、`chat_history.db` 等**非业务库** SQLite 引用不动。

- [ ] **Step 2: 运行记忆相关四个文件**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_memory_events.py tests/test_memory_jobs.py tests/test_memory_management.py tests/test_memory_retrieval.py -q`
Expected: 全部 PASS（断言内容可随软删除语义调整，但不得删除用例）

- [ ] **Step 3: 运行任务与课程相关文件**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_clarification_tasks.py tests/test_task_api.py tests/test_q3_task_loop.py tests/test_q5_learning.py tests/test_psychology_course.py tests/test_psychology_cutover.py -q`
Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
git add tests
git commit -m "test: 宿主库测试改用 PostgreSQL 临时库"
```

---

### Task 6: LightRAG 绑定 PG 存储

**Files:**
- Modify: `knowledge/lightrag/engine.py`（`build_rag`）
- Modify: `knowledge/fixed_book.py:193`（实体词表）
- Test: `tests/test_lightrag_pg_storage.py`

**Interfaces:**
- Consumes: `POSTGRES_HOST/PORT/USER/PASSWORD/DATABASE`
- Produces: `build_rag(...)` 构造的实例满足 `rag.kv_storage == "PGKVStorage"`、`rag.vector_storage == "PGVectorStorage"`、`rag.graph_storage == "PGTableGraphStorage"`、`rag.doc_status_storage == "PGDocStatusStorage"`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_lightrag_pg_storage.py
import os
from tests.pg_support import temp_databases
from knowledge.lightrag.engine import build_rag

def test_build_rag_uses_postgres_storages(tmp_path):
    with temp_databases() as env:
        os.environ.update(env)
        rag = build_rag(tmp_path, query_only=True)
        assert (rag.kv_storage, rag.vector_storage, rag.graph_storage, rag.doc_status_storage) == (
            "PGKVStorage", "PGVectorStorage", "PGTableGraphStorage", "PGDocStatusStorage")
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_lightrag_pg_storage.py -q`
Expected: FAIL（仍是 `JsonKVStorage`）

- [ ] **Step 3: 实现**

`build_rag` 的 `constructor` 增加四个 storage 字段（字面量，不做开关）；`fixed_book.start` 删除 `entity_file = ... vdb_entities.json`，改在 `await engine.initialize(self.rag)` 后从 `rag.chunk_entity_relation_graph.get_all_labels()` 取实体名。

- [ ] **Step 4: 运行确认通过**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_lightrag_pg_storage.py -q`
Expected: `1 passed`

- [ ] **Step 5: 提交**

```bash
git add knowledge/lightrag/engine.py knowledge/fixed_book.py tests/test_lightrag_pg_storage.py
git commit -m "feat: LightRAG 存储切到 PostgreSQL"
```

---

### Task 7: 就绪判断与 manifest 校验改 PG

**Files:**
- Modify: `knowledge/lightrag/storage.py`
- Modify: `knowledge/lightrag/retrieval.py:151-176`
- Modify: `knowledge/lightrag/pipeline.py:190-215`
- Test: `tests/test_lightrag_pg_manifest.py`

**Interfaces:**
- Produces: `storage.has_output(root) -> bool` 查 PG；`retrieval.LightRagBackend.validate()` 校验 `lightrag_index_manifest`；`manifest` 行字段 `namespace, row_count, id_sha256, source_signature`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_lightrag_pg_manifest.py
import os
from tests.pg_support import temp_databases
from knowledge.lightrag import storage

def test_has_output_reads_postgres(tmp_path):
    with temp_databases() as env:
        os.environ.update(env)
        assert storage.has_output(tmp_path) is False
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_lightrag_pg_manifest.py -q`
Expected: FAIL（读文件返回 False 但未连 PG，或异常）

- [ ] **Step 3: 实现**

- `storage.has_output`：用 `psycopg` 连 `POSTGRES_DATABASE`，`SELECT 1 FROM lightrag_doc_status WHERE workspace=%s AND status IN (...)`；连接失败抛错，不静默。
- `validate`：删除 `index_files` 逐文件哈希；改查 `lightrag_index_manifest` 与 `has_output`；`input/`、`source_map.json`、`policy.json` 仍核对文件。
- `pipeline` 完成清点：查 `LIGHTRAG_DOC_STATUS`/`LIGHTRAG_DOC_CHUNKS`/`LIGHTRAG_VDB_CHUNKS` 行数，写 manifest。

- [ ] **Step 4: 运行确认通过**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_lightrag_pg_manifest.py -q`
Expected: `1 passed`

- [ ] **Step 5: 提交**

```bash
git add knowledge/lightrag/storage.py knowledge/lightrag/retrieval.py knowledge/lightrag/pipeline.py tests/test_lightrag_pg_manifest.py
git commit -m "feat: LightRAG 就绪与 manifest 校验改查 PostgreSQL"
```

---

### Task 8: 存量索引一次性导入

**Files:**
- Create: `scripts/import_lightrag_candidate_to_pg.py`
- Test: `tests/test_lightrag_pg_import.py`

**Interfaces:**
- Produces: `import_candidate(candidate: Path, *, dry_run: bool = False) -> dict`，返回 `{"counts": {namespace: int}, "manifest": {...}}`；命令行 `python scripts/import_lightrag_candidate_to_pg.py --candidate <path>`。

- [ ] **Step 1: 写失败测试**

构造一个两文档的最小 candidate（复用 `tests/test_graph_viewer.py` 的 graphml/chunks 夹具），断言导入后三个计数相等且重复执行计数不变。

```python
# tests/test_lightrag_pg_import.py
import os
from tests.pg_support import temp_databases
from scripts.import_lightrag_candidate_to_pg import import_candidate

def test_import_is_idempotent(tmp_path):
    build_fixture_candidate(tmp_path)
    with temp_databases() as env:
        os.environ.update(env)
        first = import_candidate(tmp_path)
        second = import_candidate(tmp_path)
        assert first["counts"] == second["counts"]
        assert first["counts"]["LIGHTRAG_DOC_CHUNKS"] > 0
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_lightrag_pg_import.py -q`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: 实现**

读取 `meta.json` 的 `workspace`、8 个 `kv_store_*.json`、3 个 `vdb_*.json`（base64 float32 解码）、`graph_chunk_entity_relation.graphml`；用 `build_rag(..., query_only=True)` 初始化后调用各 storage 的 `upsert_*`；最后写 `lightrag_index_manifest`。不调用任何 LLM/embedding 函数。

- [ ] **Step 4: 运行确认通过**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_lightrag_pg_import.py -q`
Expected: `1 passed`

- [ ] **Step 5: 提交**

```bash
git add scripts/import_lightrag_candidate_to_pg.py tests/test_lightrag_pg_import.py
git commit -m "feat: 存量 LightRAG 索引导入 PostgreSQL"
```

---

### Task 9: 检索对照门禁

**Files:**
- Create: `scripts/check_lightrag_pg_parity.py`
- Test: `tests/test_lightrag_pg_parity.py`

**Interfaces:**
- Produces: `compare(question, mode, keywords) -> dict`，字段 `file_ids`、`pg_ids`、`equal`；命令行输出 JSON 报告到 `.runtime/lightrag-pg-parity/<run-id>/report.json`。

- [ ] **Step 1: 写失败测试**

用假 backend 返回固定 id 集合，断言 `equal` 计算正确、排序差异不影响结果。

- [ ] **Step 2: 运行确认失败**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_lightrag_pg_parity.py -q`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: 实现**

读 `tests/data/native_lightrag_latency_cases.json` 10 题；文件后端新建一个仅读文件的临时实例（在删分支前保留）；PG 后端连接 `POSTGRES_DATABASE`；`naive` 模式执行 `SET LOCAL enable_indexscan=off`；`hybrid` 固定 `hl_keywords/ll_keywords`；比较 chunk/document id 集合。

- [ ] **Step 4: 运行真实对照**

Run: `.venv-runtime/Scripts/python.exe scripts/check_lightrag_pg_parity.py --report-dir .runtime/lightrag-pg-parity`
Expected: 10/10 `equal=true`；否则停止后续任务。

- [ ] **Step 5: 提交**

```bash
git add scripts/check_lightrag_pg_parity.py tests/test_lightrag_pg_parity.py
git commit -m "test: LightRAG 文件与 PostgreSQL 检索对照门禁"
```

---

### Task 10: 删除 LightRAG 文件存储分支

**Files:**
- Modify: `knowledge/lightrag/cache_reuse.py`
- Modify: `graph_viewer.py`
- Modify: `scripts/check_lightrag_completion.py`
- Modify: `knowledge/lightrag/storage.py`、`pipeline.py`（删除残留文件读取）
- Modify: `tests/test_lightrag_backend.py`、`test_lightrag_relocation.py`、`test_graph_viewer.py`、`test_fixed_book.py`、`test_native_course_kb_migration.py`、`test_output_speed.py`
- Test: 上述文件

- [ ] **Step 1: 改 cache_reuse 与 graph_viewer**

`cache_reuse` 改查 `LIGHTRAG_LLM_CACHE`；`graph_viewer.GraphView` 改查 `lightrag_graph_nodes/edges` 与 `LIGHTRAG_DOC_CHUNKS`，HTTP 响应字段保持不变。

- [ ] **Step 2: 改完成检查脚本**

`check_lightrag_completion.py` 查 3 张 PG 表，输出格式不变。

- [ ] **Step 3: 更新测试**

文件夹具改为 PG 夹具；只测纯函数的用例保留。

- [ ] **Step 4: 运行相关回归**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_lightrag_backend.py tests/test_lightrag_relocation.py tests/test_graph_viewer.py tests/test_fixed_book.py tests/test_native_course_kb_migration.py tests/test_output_speed.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add knowledge graph_viewer.py scripts tests
git commit -m "refactor: 删除 LightRAG 文件存储读取路径"
```

---

### Task 11: mem0 存储适配层

**Files:**
- Create: `memory/mem0_store.py`
- Test: `tests/test_mem0_store.py`

**Interfaces:**
- Produces: `Mem0Store(enabled: bool)`；`add_card(student_id: str, card: dict) -> str`（`card` 必含 `card_id`、`content`、`source_id`、`epoch`，`card_id` 写入 metadata）；`search(student_id: str, query: str, epoch: int, limit: int = 20) -> list[dict]`，元素为 `{"memory_id": str, "card_id": int}`；`delete(memory_id: str) -> None`；`close() -> None`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_mem0_store.py
import os
from tests.pg_support import temp_databases
from memory.mem0_store import Mem0Store

def test_add_search_delete(tmp_path):
    with temp_databases() as env:
        os.environ.update(COURSE_DATABASE_URL=env["COURSE_DATABASE_URL"], MEM0_HISTORY_PATH=str(tmp_path/"h.sqlite"))
        store = Mem0Store(enabled=True)
        mid = store.add_card("s1", {"card_id": 7, "content": "学生分不清自变量和额外变量", "source_id": "c1", "epoch": 1})
        hits = store.search("s1", "自变量和额外变量", epoch=1, limit=5)
        assert {"memory_id": mid, "card_id": 7} in hits
        store.delete(mid)
        assert mid not in [h["memory_id"] for h in store.search("s1", "自变量", epoch=1)]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_mem0_store.py -q`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: 实现**

`Mem0Store` 用 spec 5.2 的配置构造 `Memory.from_config`；`add_card` 调 `add([{"role":"user","content":card["content"]}], user_id=student_id, infer=False, metadata={...})`；`search` 带 `filters={"student_id": student_id, "epoch": epoch}`；`enabled=False` 时所有方法返回空/None。

- [ ] **Step 4: 运行确认通过**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_mem0_store.py -q`
Expected: `1 passed`

- [ ] **Step 5: 提交**

```bash
git add memory/mem0_store.py tests/test_mem0_store.py requirements.txt
git commit -m "feat: 增加 mem0 存储适配层"
```

---

### Task 12: 卡片异步同步到 mem0

**Files:**
- Create: `memory/mem0_indexer.py`
- Modify: `memory/background_worker.py`（lifespan 启动独立 worker）
- Modify: `database/memory_index.py`（记录 `mem0_synced_hash`）
- Test: `tests/test_memory_mem0_sync.py`

**Interfaces:**
- Produces: `Mem0Indexer(repo, store, interval=2).run_once() -> bool`；处理条件 `active AND (mem0_synced_hash IS NULL OR mem0_synced_hash <> content_hash)`，成功写回 `mem0_id`、`mem0_synced_hash`；`active=False` 且 `mem0_id` 非空时先 `store.delete`。

- [ ] **Step 1: 写失败测试**

插入一条卡片；用假 store 记录调用；`run_once()` 后断言 `mem0_id` 写回、第二次 `run_once()` 不再调用。

- [ ] **Step 2: 运行确认失败**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_memory_mem0_sync.py -q`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: 实现**

`Mem0Indexer` 每次取 32 条；同步调用（mem0 OSS 是同步 API），由后台线程执行；`add_card` 的 `card` 取自 `memory_documents` 行（含 `card_id=row.id`）；失败只记录 `mem0_synced_hash` 不变，下轮重试。`memory_lifespan` 在 `MEM0_ENABLED=1` 时启动它，**不受 `native_enabled()` 限制**；现有 `MemoryWorker` 的启动条件不变。

- [ ] **Step 4: 运行确认通过**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_memory_mem0_sync.py -q`
Expected: `1 passed`

- [ ] **Step 5: 提交**

```bash
git add memory/mem0_indexer.py memory/background_worker.py database/memory_index.py tests/test_memory_mem0_sync.py
git commit -m "feat: 卡片异步同步到 mem0"
```

---

### Task 13: 检索接 mem0，保留 PG 兜底

**Files:**
- Modify: `memory/retrieval.py`（`MemoryRetriever.retrieve`）
- Test: `tests/test_memory_mem0_retrieval.py`

**Interfaces:**
- Consumes: `Mem0Store.search`
- Produces: dense 排序来源标记为 `mem0`；无 mem0 命中时仍返回 PG lexical/结构化结果；新增返回字段 `dense_status` 取值 `"mem0" | "unavailable" | "not_initialized"`。

- [ ] **Step 1: 写失败测试**

构造一条卡片不写 mem0；检索仍能通过 `memory_lexical` 命中；再写 mem0 后 `dense_status == "mem0"`。

- [ ] **Step 2: 运行确认失败**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_memory_mem0_retrieval.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

`retrieve()` 中当 `MEM0_ENABLED=1`：`dense = [h["card_id"] for h in store.search(student_id, query, epoch=current_epoch)]`，跳过现有 fastembed 循环与 `save_memory_vectors`；`MEM0_ENABLED=0` 时保留原 dense 逻辑。RRF 融合与预算逻辑不变。

- [ ] **Step 4: 运行确认通过**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_memory_mem0_retrieval.py -q`
Expected: `1 passed`

- [ ] **Step 5: 提交**

```bash
git add memory/retrieval.py tests/test_memory_mem0_retrieval.py
git commit -m "feat: 记忆检索优先走 mem0，PG 关键词兜底"
```

---

### Task 14: 删除与 epoch 传播

**Files:**
- Modify: `database/memory_index.py`（软删除与 epoch）
- Modify: `database/memory_management.py`
- Test: `tests/test_memory_delete_epoch.py`

**Interfaces:**
- Produces: `MemoryIndexRepository.expire_cards(student_id, point, epoch) -> int`；`sync_memory_index` 对不在来源集合的卡片置 `active=False`；`memory_documents` 只返回 `active=True`。

- [ ] **Step 1: 写失败测试**

生成卡片 → 写 exclusion → 重建 → 断言卡片 `active=False`；epoch 递增后旧卡片不可检索，新卡片 epoch 正确。

- [ ] **Step 2: 运行确认失败**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_memory_delete_epoch.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

`sync_memory_index` 末尾把 `old` 中未出现的行置 `active=False`；`memory_management` 在删除/epoch 变更后调用 `expire_cards`；`Mem0Indexer` 负责把 `active=False` 的 `mem0_id` 删除并清空。

- [ ] **Step 4: 运行确认通过**

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests/test_memory_delete_epoch.py -q`
Expected: `1 passed`

- [ ] **Step 5: 提交**

```bash
git add database/memory_index.py database/memory_management.py tests/test_memory_delete_epoch.py
git commit -m "feat: 记忆删除与 epoch 失效传播到 mem0"
```

---

### Task 15: 端到端验收与文档

**Files:**
- Create: `scripts/check_postgres_mem0.py`
- Modify: `README.md`
- Test: 手工验收 + 脚本

**Interfaces:**
- Produces: 脚本输出 `{"databases": {"business": "heart_psychology", "rag": "heart_rag"}, "vector": "0.8.7", "fixed_book_ready": true, "memory": {"add": true, "search": true, "delete": true}}`。

- [ ] **Step 1: 留档旧 SQLite 并跑全量测试**

把 `ai_tutor.db`、`ai_tutor.experimental-psychology-3.db` 移到 `.runtime/legacy-sqlite/`（只读留档，不接入运行）。确认运行路径不再引用它们后执行：

Run: `.venv-runtime/Scripts/python.exe -B -m pytest tests -x -q`
Expected: 全部 PASS；把未运行/跳过项列进验收记录。

- [ ] **Step 2: 启动服务与真实问答**

Run: `3-start-api.bat`
依次验证：3 个教材问题、1 个划选、1 个图题、1 个研究；引用可打开原 PDF 坐标。

- [ ] **Step 3: 记忆闭环**

同一学生两轮对话 → 卡片生成 → mem0 命中 → 删除一条记忆 → 不再召回 → epoch 递增后旧卡片不可见。

- [ ] **Step 4: 备份恢复**

Run: `pg_dump -U heart -Fc heart_psychology > .runtime/backup-psychology.dump`
Expected: 文件非空；在空库恢复后服务可启动。

- [ ] **Step 5: 更新 README 并提交**

记录 PG 前置条件、测试命令、`MEM0_ENABLED`、备份/恢复、旧 SQLite 留档位置。

```bash
git add README.md scripts/check_postgres_mem0.py
git commit -m "docs: PostgreSQL 与 mem0 运行与验收说明"
```
