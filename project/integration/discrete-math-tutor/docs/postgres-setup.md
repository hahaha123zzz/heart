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
