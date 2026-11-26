# 学生新版切换与回退操作单

本文件和源码包不构成正式重启授权。先确定目标、维护窗口、上一版可启动整包、域名/端口和独立的环境/数据路径，再执行切换。当前旧 deploy_heart.py 采用覆盖目录与旧壳配置，不用于这次新版切换。

## 可审阅发行物

`student_release.py bundle --repo <repo> --output <deployment>/releases/<id> --release-id <id>` 冻结 H、厂家后端、网页源码及许可证；`verify --release <path>` 逐项核对 SHA-256。源码包包含 knowledge Python 模块及发布元数据；不包含 .env、密码、厂家 home、数据库或教材正文/PDF/图库资产。它是源码快照，不能把 Windows node_modules/standalone 当作 Linux 已验收运行包。

目标需准备 Python 3.12/3.13、Node 24.15.0、独立的依赖环境，并在目标 OS 执行 web 的 npm ci、契约检查、类型检查与 npm run build；复制 .next/static 和 public 到 standalone 对应目录。H、厂家、网页三层必须来自同一个快照。Python 依赖应按目标系统验证；本仓库 Windows lock 不能作为 Linux lock 使用。

## 持久资源与绑定

部署之外固定保存厂家 DEEPTUTOR_HOME（含身份、会话、练习、路径及附件）、H 业务 PG、课程 PG（含长期记忆）、共享 LightRAG PG、教材目录和发布清单。HEART_MODEL_ENCRYPTION_KEY 与厂家 auth secret 随私密环境配置备份并恢复，不能每次发布重新生成。模型生成必须使用学生个人 Key，公共建库配置不下放学生页。

H 监听 127.0.0.1:8000；厂家 worker 监听 127.0.0.1:18001；Next 监听 127.0.0.1:3782。worker 经 integrations/deeptutor/worker.py 启动，Next 使用目标系统构建的 standalone/server.js。`run_student_release.py --root <deployment> --service host|worker|web --check` 核验路径、环境与构建；`--run` 才启动进程。`heart-student@.service` 是可审阅的 Linux systemd 模板，安装前须按目标确认控制解释器路径。三个实例由同一个 active-release.json 选择代码：相应 WorkingDirectory 与 PYTHONPATH 指向 release_path 下的 project 目录，所有数据目录指向上述部署外位置。不能只换前端而保留另一版 H/worker。

HEART_PUBLIC_SITE 必须设置为实际站点。Student.Caddyfile 将请求统一送入 Next；SSE 禁止缓冲、长响应等待 30 分钟，WebSocket 由反代升级。切换前用目标 Caddy 执行 validate，保留当前实际代理配置副本；验证 _next 静态资源、登录、WS、引用 PDF 后才能开放。公网只公开代理端口，不公开 8000/18001/3782；不增加 IP 白名单或共享口令。

## 切换窗口

1. 在具体新旧运行整包、依赖和代理配置可审阅后取得本次重启授权。停止新请求；确认没有活动回合或说明中断影响。暂停 H、worker 与相关写入器。
2. 同一静止窗口备份完整厂家 home、业务/课程/LightRAG 的 pg_dump custom、私密环境与教材发布/资产哈希；保存当前 release_id、代理配置及完整旧运行环境。备份存储目录需受控权限。仅有数据库转储不等于两处备份。
3. 恢复到随机目标库与新 home，验证账号、解密个人配置、聊天继续、练习/证据、教材 PDF 哈希和来源一致性。恢复演练绝不覆盖正式学生库。
4. verify 新整包，执行 select --root <deployment> --release <new> --expected-current <old-id>。该命令只原子修改部署选择文件，不自动重启、加载代理或修改数据。服务管理器按选择文件启动三服务，确认绑定的仍是相同持久资源。加载已验证的新代理；公网旧 HTML/JS 壳不再提供，不做新旧双活。
5. 验证默认聊天、阅读提问、图谱学习、路径辅导、记忆、练习、设置；检查默认评估、队列、个人 Key 隔离、退出和匿名拒绝。失败则在同一维护窗口回退。

## 回退与重新上线

verify 上一版完整运行包；select --release <old> --expected-current <new-id>，受控重启上一版三服务并恢复保存的真实旧代理配置。只回滚代码和配置，不还原学生数据库/home，不删除新记录。旧版看不到的新记录保留；修复并切回新版后应仍可读取。回退所需实际耗时、活动回合和可接受窗口必须在正式目标确定后实测，不能用文件选择测试代替进程和代理切换。

## 已验证与待执行

隔离 PG 与新厂家 home 的真实 pg_dump/pg_restore、账号与个人配置恢复、教材不变以及恢复后继续原聊天已跑通。文件选择与回退的新记录保留由独立回归核验。真实目标的上一版运行整包、Linux 依赖/Caddy 验证、三服务和公网切换仍须完成；不能将这份操作单或源码快照标作已经部署。

公网访问仅依赖十个独立强随机密码，无额外 IP 门禁或共享口令，这是已确认的访问风险。账号本身永久有效，登录 token 仍正常过期和退出。初始密码只通过 worker 受控本地文件交付，不进日志、网页公开资源或本报告。

私密运行参数放 <deployment>/private/runtime.env（Linux 0600），Python 依赖环境放 <deployment>/environments/<release_id>，HEART_RUNTIME_NODE 指向目标系统 Node 绝对路径。启动器要求所有持久资源在 releases 之外；网页进程仅继承必要代理参数，不继承 PG URL、模型加密密钥或项目模型 Key。目标预检缺失时拒绝启动。先完成三个 --check，再执行经授权的 systemctl restart heart-student@host heart-student@worker heart-student@web。

启动器还要求已准备 enabled=true 的本地认证、已有账号表和原 auth_secret，禁止未初始化身份时自动打开注册/匿名入口。后台 auth 的 enabled 环境显式开启，保留既有 token secret；mem0 本地历史文件固定到部署外的厂家 home。

## 本轮目标更新（2026-11-22）

用户指定先在本机 8000 测试，测试完成后再进入线上。本轮使用 HEART_WEB_PORT=8000、HEART_HOST_PORT=18000、HEART_WORKER_PORT=18001，均绑定 127.0.0.1，公网/ECS 不切换。HEART_RUNTIME_PYTHON 与 HEART_RUNTIME_EXTRA_PATHS 可明确复用本机已验证依赖环境；线上仍需目标 OS 的依赖与构建。后续线上切换另行决定。

2026-11-26 本机 Web 入口改为 800（HEART_WEB_PORT=800），host 18000、worker 18001 不变；只改部署 `private/runtime.env` 并重启，安装脚本的新装默认仍为 8000，避免非 root 的 Linux 目标绑定低端口。

本机实际控制程序位于部署根的 control 目录，版本与应用发行快照分别登记。Python 服务工作目录固定到外部 DEEPTUTOR_HOME，PYTHONPATH 指向所选 H/厂家源码；教材坐标缓存、mem0 历史等相对运行文件因此保留在数据目录，不写入发行源码。此处复用的是已验证的 Windows 依赖与生产构建，不宣称已验证 Linux 线上部署。

## 本机控制脚本与重排设备（2026-11-26）

control 目录中的 `manage_student_local.py`、`run_student_release.py`、`student_release.py`、`startup_report.py`
必须一起更新：`run_student_release.py` 导入 `student_release.py` 的 `active_release` 与 `inspect`，只覆盖前两个会在导入阶段让所有服务失败。启动顺序改为 worker 先就绪、再启动 host 与 Web；一次启动只解析一次 `active-release.json`，三个服务共用同一发行。

本机重排设备由 `setup_student_local.py` 在安装时探测目标解释器：具备 `CUDAExecutionProvider` 时写 `RAG_RERANK_DEVICE=cuda`，并把 `CUDA_CACHE_PATH` 固定到 `<deployment>/private/cuda-cache`，不允许 ONNX JIT 缓存写进发行目录。该探测只证明 onnxruntime 构建包含 CUDA；安装后必须打开 `http://127.0.0.1:18000/health`，确认 `rag_runtime.sessions.reranker.providers` 含 `CUDAExecutionProvider`，否则按设备校验错误处理，不要静默按 CPU 使用。

