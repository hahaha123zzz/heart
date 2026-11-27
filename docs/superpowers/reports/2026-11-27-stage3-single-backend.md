# 阶段 3 · 统一 Heart 后端（2026-11-27）

对应计划 [2026-11-26 固定教材启动与回答延迟](../plans/2026-11-26-fixed-book-startup-and-answer-latency.md)
阶段 3。候选发行 `phase1-candidate-20261126w`，端口 28000（后端）+ 28002（Web）。
`HEART_SINGLE_BACKEND=1`。

## 1. 结构

```
Web 28002 ──► 28000  main:asgi = SingleBackend
                        ├─ 宿主 FastAPI：教材、检索、图/表、练习、`/internal/*`、`/health`
                        └─ DeepTutor 原生应用（同进程同循环）：`/ws`、`/api/auth`、会话、模型、设置、RAG 工具
```

- `worker.py` 的主装配置抽成 `build_app(home, port, *, chdir)`，独立进程与单进程共用。
  `main()` 只负责 uvicorn。
- `single_backend.py` 新增组合应用：宿主优先；浏览器今天走 worker 的表面
  （`/ws`、`/api/auth`、`/api/sessions`、`/api/models` 等）列在 `WORKER_FIRST`；
  `/api/chat`、`/api/chat/stream` 仍回宿主的 410 退役响应。
  宿主与 worker 的 lifespan 顺序启动、逆序关闭；启动失败回 `lifespan.startup.failed`。
- 教材检索改服务内调用：`client._post_async` 在单进程模式下走
  `httpx.ASGITransport`，不再经过本机端口。
- 部署：`HEART_SINGLE_BACKEND=1` 时控制脚本只起 host 与 web，Web 的
  `DEEPTUTOR_API_BASE_URL`、`DEEPTUTOR_BACKEND_URL` 都指向宿主端口；host 走 `main:asgi`。
  回退只需把该变量改回 0 并重启（两步进程路径在同一发行里验证过）。

## 2. 验收（发行 w，28002）

| 项 | 结果 |
| --- | --- |
| 启动 | `/health` 200，固定教材 8.0s 就绪；28001 无监听，只剩 host+web 两个进程 |
| 路由 | `GET /api/sessions` → 401（worker 路由）；`GET /api/figures/...` → 404/图片（宿主路由） |
| 登录 + WS 流式 | 浏览器登录 `heart-review-02`，提问「图9-19 …原图」正常流式完成 |
| 教材检索 + 原图 | 回答 7.6s、首正文 2.4s、2 次工具调用、3 处引用，`/api/figures/image-09-0021/image` 显示 628×537 |
| 会话恢复 | 重新登录后左栏列出既有会话 |
| 练习页 | `/learning/practice` 正常加载（复习区可见） |
| 账号隔离 | 各账号独立 `chat_history.db`；按标题核对不可靠（两个账号都有同名历史），未发现跨账号数据 |
| 后台任务 | 启动无 assessment/attachment 报错，仅 spaCy 缺模型警告（与本阶段无关） |
| 资源关闭 | 连续重启后旧进程全部退出，端口由新进程接管 |
| `/api/graph/release`、`/api/figures` 经 28002 | 有鉴权时正常（无 cookie 401，符合预期） |

## 3. 桥接成本对比

同一 `usage.stages` 口径：`worker.host_roundtrip − host.backend`。

| 形态 | 每次检索的桥接开销 | 同回合问答 |
| --- | --- | --- |
| 两进程（发行 u） | 0.24s / 0.56s / 0.06s / 0.01s | 16.2s，首正文 3.1s |
| 单进程（发行 w） | 0.027s | 7.6s，首正文 2.4s |

两组问题不同，总时长只作方向参考；桥接开销本身是同一口径的 10–20 倍下降。

## 4. 未做 / 风险

- 同步桥接（native start/status/events 等）仍是本机环回 HTTP，只是同进程同端口；
  只有异步教材检索改成了服务内调用。
- `WORKER_FIRST` 是白名单：vendor 新增浏览器面路由若与宿主同名，会被宿主抢走，
  需要按需补进白名单。
- 引用缺失（短 ID 被整段删掉）仍是既有问题，未在本阶段处理。
- 线上 8000 未更新；本阶段只在候选。
