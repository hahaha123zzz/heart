# 教学 Agent 与实验心理学教材 AI 助教

本仓库包含原教学平台与 Agent 模块抽取版，以及实验心理学教材 AI 助教（学生端）。

- [Agent 模块说明](project/README.md)：辅导、出题和教学决策代码；完整平台的部分依赖不在本仓库。
- [实验心理学 AI 助教](project/integration/discrete-math-tutor/README.md)：宿主 API、学生状态、教学规划、记忆/图谱、前端与部署脚本。
- [DeepTutor 上游源码](project/vendor/DeepTutor)：工作台前端、上游 Agent runtime、worker 与测试（含本地补丁 `LOCAL_PATCHES/`）。

> 本机 8000 端口的学生端是「宿主 API + 上游 worker + Next 工作台」三服务，由源码快照 + 外部数据/密钥组合而成。
> **克隆后不能直接得到同样的体验**：构建产物、教材资产、数据库、账号、模型缓存和密钥都不在 Git 里。下面按顺序列出需要补的东西。

## 仓库里没有的东西

| 缺少项 | 位置 / 说明 |
| --- | --- |
| 前端构建产物 `.next/`、`node_modules` | `project/vendor/DeepTutor/.gitignore` 排除，必须自己 `npm ci && npm run build` |
| 教材资产（阅读版 PDF、插图、正文切分、题库） | `knowledge/courses/experimental-psychology-3/` 约 2793 文件 / 147 MB，不入库；仓库只带 `kc_registry.json` |
| PostgreSQL 数据 | `heart`（旧业务空库）、`heart_psychology`（账本/卡片/mem0）、`heart_rag`（LightRAG 11 张表，11 文档 / 1239 chunks） |
| 厂家 `DEEPTUTOR_HOME` | 身份、会话、练习、路径、附件；含 `data/system/auth/users.json` 与 `auth_secret` |
| 密钥与运行配置 | `.env`、`private/runtime.env`：模型 Key、PG 口令、`HEART_MODEL_ENCRYPTION_KEY`、`DEEPTUTOR_BRIDGE_TOKEN`、auth 口令哈希 |
| 本地推理模型缓存 | fastembed / rerank 权重（离线模式 `HF_HUB_OFFLINE`、`TRANSFORMERS_OFFLINE`） |
| WSL 沙箱 | 代码执行工具依赖 `HEART_WSL_SANDBOX_DISTRO`（本机为 Ubuntu） |
| 账号 | 复核账号由脚本生成，初始密码只写在 `private/` 的凭据文件里 |

## 1. 系统依赖

- Python 3.13（本机验证版本）或目标系统对应版本
- Node **24.15.0**（本机已验证；构建与 `.next/standalone/server.js` 运行都用它）
- PostgreSQL **18 + pgvector**，建库与扩展见 [`docs/postgres-setup.md`](project/integration/discrete-math-tutor/docs/postgres-setup.md)
- 可选：WSL Ubuntu（代码执行沙箱）；不启用时相关工具不可用
- 首次启动要加载教材与本地 embedding/rerank 模型，约 2 分钟

## 2. Python 依赖

在 `project/integration/discrete-math-tutor` 下：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pip install -r requirements-local-rag.txt   # 教材词法/BM25 检索
.venv/Scripts/python.exe -m pip install -r requirements-lightrag.txt    # 需要 LightRAG 图检索时
python scripts/setup_deeptutor.py     # 另建 .venv-deeptutor 装上游 worker 依赖
```

GPU 推理另用 `requirements-gpu-runtime.txt` 装到独立 `.venv-gpu`（onnxruntime-gpu/CUDA），纯 CPU 跳过。`requirements-deeptutor-win32-py313.lock.txt` 等 lock 都是 Windows 下生成的；Linux/macOS 需重新安装并按目标系统重新验收，不能直接复用。

## 3. 前端构建（必做）

```powershell
cd project/vendor/DeepTutor/web
npm ci
npm run build
```

三服务模式用的是构建后的 `.next/standalone/server.js` 与 `.next/static`，源码不能直接当运行包。

## 4. 教材资产

仓库不含教材正文。把完整资产目录（阅读版 PDF、插图、正文切分、题库）放到任意外部路径，用 `TUTOR_PSYCHOLOGY_DIR` 指向它；`setup_student_local.py --assets` 也接这个路径。缺失时阅读、引用、图谱和题库页面为空。

## 5. PostgreSQL

按 `docs/postgres-setup.md` 创建角色 `heart`、三个库，并在用到的库上执行 `CREATE EXTENSION vector`。然后配置：

```ini
DATABASE_URL=postgresql+psycopg://heart:<pw>@127.0.0.1:5432/heart_psychology
COURSE_DATABASE_URL=postgresql+psycopg://heart:<pw>@127.0.0.1:5432/heart_psychology
TEST_POSTGRES_URL=...
TEST_POSTGRES_ADMIN_URL=...
```

`heart_rag` 的 LightRAG 索引要单独重建（重跑教材建库）或从备份恢复；只有表结构没有索引时，回答里的引用检索不可用。

方式 A 直接连这三个库；方式 B 的 `setup_student_local.py` 会另建一对 `heart_local8000_*` 隔离库，只需要给它一个可建库的管理连接（`TEST_POSTGRES_ADMIN_URL`）。

## 6. `.env` 与密钥

```powershell
cd project/integration/discrete-math-tutor
Copy-Item .env.example .env
```

至少补齐：

- `DEEPSEEK_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL`（真实模型；`LLM_MOCK=1` 可先跑通链路）
- `DEEPTUTOR_BRIDGE_TOKEN`：≥32 字符随机值，`python -c "import secrets;print(secrets.token_hex(32))"`
- `HEART_MODEL_ENCRYPTION_KEY`：Fernet 密钥，`python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`
- 登录账号由部署脚本写进 `DEEPTUTOR_HOME`（`data/system/auth/`），不要手填密码哈希；三服务启动器会强制认证开启

密钥不要提交。学生个人模型 Key 用 `HEART_MODEL_ENCRYPTION_KEY` 加密存储，**换 key 后旧密文解不开**，只能让学生重新填。

## 7. 启动方式 A：单服务 Demo（最快看到页面）

```powershell
cd project/integration/discrete-math-tutor
.venv/Scripts/python.exe -X utf8 -m scripts.start_server --port 8000
```

或双击 `3-start-api.bat`。这是宿主 API + SSE + 原页面，没有 Next 工作台、没有上游 worker；功能与 8000 学生端不完全一致。

## 8. 启动方式 B：本机 8000 三服务（与现有体验一致的结构）

在 `project/integration/discrete-math-tutor` 下，用可运行部署脚本的解释器（需 `psycopg`、`cryptography`、`psutil`、`filelock`、`httpx`）：

```powershell
# 1) 打源码快照并校验（不含 .env、密码、数据库、教材资产）
python deploy/student_release.py bundle --repo <repo> --output <deploy>/releases/<id> --release-id <id>
python deploy/student_release.py verify --release <deploy>/releases/<id>

# 2) 初始化部署：建独立 PG 库、写 private/runtime.env、建复核账号并授权教材章节
python deploy/setup_student_local.py --root <deploy> --project-env .env `
    --assets <教材目录> --python <python.exe> --node <node.exe>

# 3) 预检 + 起三服务（就绪后才返回）
python deploy/run_student_release.py --root <deploy> --service host   --check
python deploy/run_student_release.py --root <deploy> --service worker --check
python deploy/run_student_release.py --root <deploy> --service web    --check
python deploy/manage_student_local.py start --root <deploy>

# 4) 日常操作
python deploy/manage_student_local.py status|restart|stop --root <deploy>
```

默认端口：Next 工作台 `8000`、宿主 `18000`、worker `18001`（`HEART_WEB_PORT` / `HEART_HOST_PORT` / `HEART_WORKER_PORT`，均绑定 `127.0.0.1`）。账号密码、日志、`services.json` 都在 `<deploy>/private`，不会进网页资源或 Git。

`setup_student_local.py` 只写基础项；检索相关还要在 `<deploy>/private/runtime.env` 补原值（`LIGHTRAG_QUERY_ENV_FILE`、`LIGHTRAG_CANDIDATE_PATH`、`LIGHTRAG_EMBED_SNAPSHOT`、`RAG_RERANK_MODEL`、`FASTEMBED_CACHE_PATH` 等），否则阅读引用、候选检索会退化或不可用。

## 9. 想复现「和本机 8000 完全一样」还要恢复

按 [`deploy/STUDENT_CUTOVER.md`](project/integration/discrete-math-tutor/deploy/STUDENT_CUTOVER.md) 的顺序做备份/恢复：

1. `heart_psychology`、`heart_rag` 的 `pg_dump -Fc`（会话、掌握度、记忆、LightRAG 索引）
2. 厂家 `DEEPTUTOR_HOME` 整目录（身份、会话、练习、附件、`auth_secret`）
3. 教材资产目录及发布清单哈希
4. `private/runtime.env` 原值（尤其 `HEART_MODEL_ENCRYPTION_KEY`、`DEEPTUTOR_BRIDGE_TOKEN`、PG 口令）
5. embedding / rerank 模型缓存与离线开关
6. WSL 发行版、LightRAG 查询 env 文件等本机路径

只恢复代码不恢复这些，能起服务，但登录、对话历史、阅读引用、图谱、记忆都是空的。账号是永久账号，密码只在备份里。

## 10. 提交边界

不要提交：`.env`、`private/`、`data/`（含 `auth.json` 的 password_hash）、`.runtime/`、`node_modules`、`.next`、`*.sqlite`、PostgreSQL 转储、账号凭据文件。`.gitignore` 已覆盖其中大部分，其余靠提交前检查。

## 文档

- 部署、切换与回退：[`deploy/STUDENT_CUTOVER.md`](project/integration/discrete-math-tutor/deploy/STUDENT_CUTOVER.md)
- PostgreSQL 安装：[`docs/postgres-setup.md`](project/integration/discrete-math-tutor/docs/postgres-setup.md)
- 功能、接口与验收历史：[`project/integration/discrete-math-tutor/README.md`](project/integration/discrete-math-tutor/README.md)
- DeepTutor 接入计划与执行记录：[实施计划](project/docs/research/2026-10-18-deeptutor-full-reuse/IMPLEMENTATION_PLAN.md)
