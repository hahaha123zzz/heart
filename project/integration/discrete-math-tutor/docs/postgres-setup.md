# PostgreSQL 18 与 pgvector 安装记录（Windows）

日期：2026-11-16
适用：本项目本机开发与验收。远程 ECS 不在本记录范围。

## 已安装

- PostgreSQL 18.6（EDB 安装包 `postgresql-18.6-5-windows-x64.exe`），服务名 `postgresql-x64-18`，端口 5432。
- pgvector 0.8.7，用 Visual Studio 2019 的 `nmake /F Makefile.win` 编译并安装到 `C:\Program Files\PostgreSQL\18`。
- 超级用户密码：本机开发用 `heart_pg_admin`，只存在于本地 `.env`，不提交仓库。

## 角色与数据库

```sql
CREATE ROLE heart LOGIN PASSWORD '<pw>' CREATEDB;
CREATE DATABASE heart OWNER heart;
CREATE DATABASE heart_psychology OWNER heart;
CREATE DATABASE heart_rag OWNER heart;
```

| 库 | 用途 |
|---|---|
| `heart` | 旧课程业务库（空库） |
| `heart_psychology` | 当前心理学课程：账本、卡片、mem0 向量 |
| `heart_rag` | LightRAG 的 11 张表 |

扩展（superuser 执行，每个用到的库一次）：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

验证：

```bash
psql -U heart -d heart_rag -c "SELECT extversion FROM pg_extension WHERE extname='vector';"
# 0.8.7
```

## 重新编译 pgvector

需要 “x64 Native Tools Command Prompt for VS”：

```cmd
set "PGROOT=C:\Program Files\PostgreSQL\18"
cd <pgvector-0.8.7>
nmake /F Makefile.win
nmake /F Makefile.win install
```

## 备份与恢复

```bash
pg_dump -U heart -Fc heart_psychology > backup-psychology.dump
pg_dump -U heart -Fc heart_rag > backup-rag.dump
createdb -U heart heart_psychology_restore
pg_restore -U heart -d heart_psychology_restore backup-psychology.dump
```

`mem0` 的 `history.sqlite` 不属于 PG 备份范围，可从卡片表重建，不参与证据链。

## 本机中文路径

`E:\项目\...` 下的模型缓存和 candidate 在部分进程里会因编码/非 ASCII 路径解析失败。本机用一个 ASCII junction 规避：

```powershell
New-Item -ItemType Junction -Path E:\heart-runtime -Target E:\项目\heart\.runtime
```

`.env` 中的 `LIGHTRAG_CANDIDATE_PATH`、`FASTEMBED_CACHE_PATH`、`LIGHTRAG_EMBED_SNAPSHOT`、`RAG_RERANK_SNAPSHOT`、`DEEPTUTOR_HOME` 指向 `E:\heart-runtime\...`。`LIGHTRAG_QUERY_ENV_FILE` 指向一个只含官方 DeepSeek 地址与 key 的 `deepseek-query.env`；不要把它指向含代理地址的文件。

## 远程 ECS（未执行）

`deploy/provision_heart.sh` 目前仍是 SQLite 时代的安装脚本，不包含 PostgreSQL/pgvector。切远程前需要：

1. 安装 PostgreSQL 16+ 与 `postgresql-16-pgvector`（或源码编译）。
2. 创建 `heart`、`heart_psychology`、`heart_rag` 三个库，并在业务库与教材库执行 `CREATE EXTENSION vector`。
3. 把 `.env` 改为 `postgresql+psycopg://...`；模型缓存与 `DEEPTUTOR_HOME` 放到 ASCII 路径。
4. 用本机 `pg_dump` 导出 `heart_psychology` 与 `heart_rag`，远端 `pg_restore`。
5. 远端 2C2G 仍按 README 关闭固定教材/LightRAG；启用前需要升配。

以上步骤没有在远程执行，也没有改动 `provision_heart.sh`。
