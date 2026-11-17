# 学生前端整组复用 · 任务 0 基线冻结

日期：2026-11-16
计划：`docs/superpowers/plans/2026-11-13-student-frontend-reuse.md`（任务 0）
范围：只记录事实与缺口，不改业务代码。

## 1. 版本与工作区

| 项 | 值 | 证据 |
|---|---|---|
| 仓库 HEAD | `d32e400`（fix: 研究正文引用锚点兜底与格式归一） | `git log -1` |
| 当前分支 | `codex/ta5-acceptance-20261029`（非 main） | `git branch --show-current` |
| 未提交改动 | 77 个已跟踪修改 + 153 个未跟踪 | `git status --porcelain` |
| V/web 上游 | HKUDS/DeepTutor `6cf793bd868ba5ecbe64722936d4be8fab5a01df`（2026-10-18 快照） | `project/vendor/DeepTutor/UPSTREAM_SNAPSHOT.json` |
| V 本地补丁 | 7 个（llm-config-adapter、windows-private-mode、reuse-scoped-path-service、knowledge-base-preference-inheritance、learning-evidence-qualification、mermaid-render-recovery、visualization-fullscreen-scope） | `project/vendor/DeepTutor/LOCAL_PATCHES/` |
| V/web 构建 | 已安装 942 包，`next build` 退出码 0（2026-11-13） | `.runtime/npm-build-web.log`；`.next` 存在，仅 `next-env.d.ts` 更新 |
| Node / npm | v24.15.0 / 11.12.1 | `node -v` |
| 数据库 | PostgreSQL 18 + pgvector 0.8.7 | 2026-11-16 计划 Task 15 账本 |
| 关键 Python 依赖 | lightrag-hku 1.5.7、mem0ai 2.2.1、psycopg[binary] 3.3 | `requirements.txt` |

### 1.1 未提交改动的性质

77 个已跟踪修改集中在四块，均属本次前后端改造的既有成果，不属“无关任务”：

- H 后端：`web_api.py`、`review_api.py`、`memory_api.py`、`learning_cards_api.py`、`integrations/deeptutor/*`（12 个）、`knowledge/*`（8 个）、`agents/agent_loop_service.py`、`database/repository.py`。
- H 前端（旧壳）：`frontend/*`（16 个，含 `app.js`、`chat-transport.js`、`native/*`、`workspace*.css`）与 `frontend/vendor/deeptutor-renderers/*`（生成物，单文件体积最大，占 diff 的主要行数）。
- V vendor：`deeptutor/agents/question/pipeline.py`、`app/container.py`、`app/service.py`、`plugins/registry.py`、`runtime/coordination/memory.py` 及对应测试；`web/components/Mermaid.tsx`、`web/components/visualize/VisualizationViewer.tsx`。这些与 `LOCAL_PATCHES` 中的补丁一一对应，属“补丁已应用但尚未提交”。
- 文档与脚本：`docs/superpowers/plans/*`、`project/docs/research/*`、`scripts/check_native_*`、`scripts/build_native_renderers.cjs`、`3-start-api.bat`。

153 个未跟踪文件：133 个在 H 下（多为 `.runtime` 之外的验收脚本/快照/临时产物），其余为仓库根目录的散落 `.pdf`/`.docx` 与 `data/` 等。**本次执行不 reset、不 clean；新产物只写入 `.runtime/` 与 `.superpowers/`。**

### 1.2 运行时仍是 SQLite 的部分（与“全部 PG”的预期不同）

PG 迁移刻意不动 vendor，因此以下仍是 SQLite，备份与回退必须一并考虑：

- `DEEPTUTOR_HOME=E:\heart-runtime\deeptutor` 下的 `heart-bridge/bindings.sqlite3`：H 会话 → 原生会话/工作区的绑定表（`integrations/deeptutor/session_bridge.py:28`）。
- 原生会话库：上游 `get_session_store().db_path`，`learning_binding_adapter.py:26-35` 直接 `ATTACH DATABASE`。
- `MEM0_HISTORY_PATH=.runtime/mem0/history.sqlite`（mem0 自己的历史，计划允许）。

## 2. 身份与作用域（当前实现）

调用链：浏览器 → H（`student_id` 来自请求体/URL）→ 内部桥（Bearer 令牌）→ DeepTutor 用户（由 student_id 派生）。

| 环节 | 现状 | 证据 |
|---|---|---|
| 浏览器身份 | **没有任何会话**；`main.py` 每个接口都直接收 `student_id` | `main.py:79,145,161-181,371` |
| 登录页 | 只有 `GET /login` 返回静态 `login.html`；无认证接口 | `main.py:101-103` |
| 账号存储 | PG 无 accounts / auth_sessions / provider_credentials 表 | `heart_psychology` 45 表清单 |
| 测试账号 | 仅 `create_test_account(student_id, ttl_hours=24)`，无密码 | `orchestrator.py:129` |
| H → 原生桥 | `/internal/heart/native/*` 全部要求 bridge token | `native_authorization.py:13`、`session_bridge.py:102` |
| 学生 → 原生用户 | `heart_native_<sha256(student_id)>`，首次自动建号、随机密码哈希、强制 role=user | `native_bridge.py:128-137` |
| 原生数据作用域 | `user_scope(user_id)` → `scope_for_user(user_id).root`；工作区按 `(user_id, course_id)` 存在 `native_courses` | `native_bridge.py:95-105,183-199` |
| memory worker | 当前关闭 | `GET /health` → `memory_worker.enabled=false` |
| AgentLoop → mem0 桥接 | 未实现（PG 计划 Task 15e 已记录） | 同上账本 |

结论：**越权面是“任何调用方可以自报 student_id”**。5.0 的会话隔离尚未存在，登录方案仍待用户在任务 2 前拍板。

## 3. 端口、代理与回退

| 项 | 现状 | 影响 |
|---|---|---|
| H 监听 | 8000（`scripts/start_server`，systemd `heart-tutor`） | — |
| V/web 默认端口 | `npm run dev` 实际监听 **3000**（`scripts/dev.mjs`，Turbopack）；`system.json` 的 `frontend_port: 3782` 不参与 dev 启动 | 计划文档里的 3782 不准 |
| V/web 后端地址 | `web/data/user/settings/system.json` 的 `backend_port: 8001`，`next_public_api_base` 为空 | 直接启动会连不上 H；本轮用 `BACKEND_PORT=8000` 覆盖 |
| 实测结果 | `http://127.0.0.1:3000/` → 302 到 `/chat`，外壳（侧栏/设置/首页）渲染正常；`/api/auth/status`、`/api/sessions` 等全部 404 | 说明 V/web 期望的 API 形状与 H 现有接口不一致，接线是适配工作，不是改端口 |
| 代理规则 | `web/next.config.js` 读取 `data/user/settings/system.json` 与 `auth.json`，`BACKEND_PORT` 默认 8001 | 同源代理是配置项，不是硬编码 |
| 公网部署 | `deploy/deploy_heart.py` 上传 `app.tar.gz` 解压覆盖 `/opt/heart/app`；Caddy 监听 80，provision 时备份 Caddyfile | 无 releases 目录、无自动回退 |
| 回退包 | 本地 `artifacts/archive/` 只有 2026-10-15 的旧目录，无近期上线包 | **任务 10 前必须建立“保留上一版 tar 包”的规程** |
| 部署脚本数据库 | `deploy_heart.py:41` 仍写 `DATABASE_URL=sqlite:///./ai_tutor.db` | 与 PG-only 代码不兼容，当前无法部署 |

## 4. 旧入口基线状态

2026-11-16 实测（`.venv-runtime`，4 个文件）：

```
16 failed, 20 passed in 148s
```

归因：

- `ModuleNotFoundError: No module named 'deeptutor'`（2 个文件）：`.venv-runtime` 未安装 vendor 包，属解释器/环境不匹配。
- `AttributeError: 'types.SimpleNamespace' object has no attribute 'llm'`（6 例，`agents/task_service.py:397`）：测试替身未跟上 `input_understanding` 参数，属**失效测试**。
- `ImportError: cannot import name 'requests_supplementary_proof'`（`test_quality_guard`）：测试引用已删除符号。
- `AssertionError: 'ready' != 'clarify'`（`test_course_navigation`）：行为漂移，待逐例归因。

因此**现阶段没有可信的旧基线**。任务 2 前必须先修正测试替身或明确排除，不能把 16 个失败当作“已知问题”一笔带过。

## 5. 页面 → 接口调用链

完整表见 `.superpowers/sdd/2026-11-13-student-frontend-reuse/task0-vweb-surface.md`（260 行，两表：流/路由、HTTP 端点）。

三个决定实施方式的结论：

1. **代理机制**：`web/proxy.ts` 第 1 步把 `/api/*`、`/ws/*` rewrite 到 `resolveBackendApiBase()`（默认 `http://127.0.0.1:8001`，`next.config.js` 只有 redirects 没有 rewrites）；第 2 步才是 `dt_token` JWT 门禁，默认关闭。因此后端必须提供 **v2 WebSocket 之外的全部 REST 形状**，并转发未知 cookie。
2. **对话是 v2 WebSocket**：`features/chat/ChatRuntimeProvider.tsx`、`TurnRuntimeClient.ts:133`，含 seq 缺口重放、resume、ask_user 重挂；与 H 的 SSE 事件流不是同一协议。
3. **设置是管理员实例配置**：普通用户在 UI 上能看到 llm/connections，保存却走 `/api/settings/apply/*` 且后端逐个 `_require_settings_admin()` → 学生 403；单份 `data/user/settings/*.json`，没有“每人一套模型”的契约。

其余已明确的形状：`GET /api/sessions`（分页）、`/api/auth/status|login|logout|is_first_user`、会话级 WS。


## 6. 旧页面可用功能（浏览器实测）

后端按 `3-start-api.bat` 等价命令重启后（`.venv-runtime`，warmup 21s + fixed book），登录页 `/login` 用 `admin/123456` 进入 `http://127.0.0.1:8000/`，标题“实验心理学学习平台”。

可用视图（点击 `data-view` 均能切换，无 JS 崩溃）：

| 视图 | 内容 |
|---|---|
| 学习 `/ course` | 左侧教材目录 + 阅读区 + “去练习”；右侧对话面板、教材版、布局比例菜单 |
| 练习与复习 `quiz` | 章节选择、题库、教材练习、讲解面板 |
| 学习记录 `learning` | 三个页签：学习概览、掌握路径、待复习 + 历史对话 |
| 设置 `settings` | 偏好设置、学习记忆、系统状态、测试账户（24 小时过期） |
| 学习者 `learner` | 学习档案、知识掌握、掌握路径、学习证据 |

控制台错误仅 3 个 404，对应心理学模式未挂载的 `/api/relations`、`/api/truth-tables`、`/api/visualizations`（与 PG 计划 Task 15e 记录一致）。

登录页副标题仍是“离散数学 AI 助教”，属旧文案残留，记录待清理。

**截图未取得**：`browser.screenshot` 要求桌面应用窗口可见，本轮环境不满足；已用可访问性快照与视图切换代替，截图留待窗口可见时补。

## 7. 结论：任务 0 的可用性判定

- 可复用：V/web 构建、PG 数据、LightRAG 图谱、旧页面功能清单。
- 仍需在任务 2 前补齐：登录方案（待用户选择）、旧基线测试归因、部署脚本 PG 步骤。
- 不阻塞任务 1：白灰截图可以在 V/web 连上 H 之后补拍。


## 8. 2026-11-17 厂家接管验证（方案 B）

已完成并联调通过的三步：

1. **厂家认证打开**：`scripts/enable_vendor_auth.py` → `auth.json` 的 `enabled=true, cookie_secure=false`。设置目录 `E:\项目\heart\.runtime\deeptutor\data\user\settings`。
2. **账号**：`scripts/init_vendor_accounts.py`（用 `.venv-deeptutor`，bcrypt 只装在该环境）建 1 个 `admin` + 10 个 `student01..10`，幂等；明文只写 `.runtime/vendor-accounts.txt`。用户库真实路径：`.runtime/deeptutor/data/system/auth/users.json`（不带 `DEEPTUTOR_HOME` 运行会误写到 `H/data/system/auth/users.json`，脚本已打印 `users_store` 以便核对）。
3. **代理与模型**：`V/web/lib/backend-forward.ts` 转发时注入 `x-heart-bridge-token`（补丁 `LOCAL_PATCHES/heart-bridge-token-forward.patch`）；V/web 以 `DEEPTUTOR_API_BASE_URL=http://127.0.0.1:18001` 启动。`scripts/assign_vendor_model.py` 把宿主 `heart-host` profile 授予 10 个学生（学生自带 Key 接入前的过渡，决定 29）。

验收证据（`scripts/check_vendor_ws.py`，经 `:3000` 代理）：

```
login(student01) -> dt_token
WS /ws start_turn -> done status=completed
events 984；types: content, thinking, tool_call, tool_result, progress, session, stage_start, stage_end, result, done
content_chars 816；usage total_tokens 20870
```

已知缺口：

- `learning_policy` 目前为 null（`learner` preset 没有下发教材白名单），固定教材/禁上传尚未生效。
- 学生仍用共享的宿主模型；自带 Key 的自建设置页未做。
- 生产环境 Next 不支持 WS 升级，`/ws` 与 `/api/*` 必须由 Caddy 直接转给 18001。
- 未做两个账号的并发隔离与浏览器 UI 视觉验收。

## 9. 2026-11-17 固定教材与白灰主题

- 厂家阅读材料按用户隔离，材料本体去重共享：admin 上传 `textbook.docx` 得到 `f0ed04bd1d9c43d9`（132 节、396783 字、render_mode=text、extractor=docx）。
- `scripts/provision_student_reading.py`：逐账号登录 → 若库里无同名材料则**临时**放开上传 → 导入 → 立刻收回，并把该账号的 `learning_policy.reading.material_ids` 写成自己的 material id。10 个账号全部 `policy_changed=True`。
- 验收：student01 的 `/api/auth/status` 返回 `reading: {allow_upload:false, material_ids:["f0ed04bd1d9c43d9"]}`；`/api/reading/library/materials` 返回该教材（status=ready）。政策生效后重跑 `check_vendor_ws.py` 仍 `done/completed`（984 事件、816 字符）。
- 白灰主题：默认主题是 `.theme-snow`（不是 `:root`）。已把其 `--background #f7f8f9`、`--primary #2f3437`、`--border #e3e5e8`、`--ring #9aa0a6`，`:root` 同步；浏览器计算值已确认 `#f7f8f9 / #2f3437 / #e3e5e8`。这是品牌差异，不随上游合并，故不写入 LOCAL_PATCHES。

## 10. 2026-11-17 路由裁剪（任务 3）

- 删除：`(admin)`、`(workspace)/{partners,kanban,co-writer,whisper}`、`(auth)/register`、`(utility)/{agents,space,session-handoff}`、`features/co-writer`。
- 导航收敛为 `/chat` + `/learning`，`/settings` 保留；登录页去掉注册跳转与链接。
- 验证：`npm run typecheck` EXIT=0；`npm run build` EXIT=0，路由表只剩 `chat / learning/** / login / memory/** / notebooks / profile / settings`。
- 被删地址实测 404：`/partners`、`/register`、`/space`、`/kanban`、`/agents`、`/session-handoff`；`/` 仍 307 到 `/chat`，`/login`、`/chat`、`/learning`、`/settings` 均 200。
- 测试：删除 7 个测已删路由的 spec；`learner-navigation`、`sidebar-defaults`、`sidebar-lazy-history` 更新为新导航后 13/13 通过。全量 vitest 在并行下大量 5–16s 超时（同一批单独跑全过），改用 `--no-file-parallelism` 作为门禁。
- 死代码保留：`components/partners`、`lib/partners-api.ts`、`components/space`（79/51 处引用，牵涉 memory 与 hooks），不再有可访问路由。

## 11. 2026-11-17 账号隔离验收

`scripts/check_account_isolation.py`（经 `:3000` 代理，两个真实学生账号）：

```
created=unified_1794878685345_8f665d7c
student01 sees it: True (n=2)
student02 sees it: False (n=0)
student02 GET session -> 404
ISOLATION_OK
```

## 12. 2026-11-17 学生自带模型 Key

- 后端：`integrations/deeptutor/heart_model_api.py`，由 worker 挂载为 `/api/heart/model`（GET/PUT/DELETE，走厂家 `require_auth`）。
- 存储：`<home>/data/system/heart-model/<user_id>.json`，Key 为 Fernet 密文（密钥 `.secret`，同目录）；读取只返回末四位。
- 校验：`https` + 非回环/私网/链路本地/保留地址，且 URL 不含凭据。`http://127.0.0.1:11434` → 400。
- 生效方式：保存时把 `heart-student-<user_id 前 12 位>` profile 写进 `model_catalog.json`，并把该学生 grant 的 `models.llm` **只**指向它；删除时移除 profile 与授权。
- 前端：`/settings/model`，侧栏“我的模型”入口（学生可见）。
- 验收（经 `:3000`）：`before {"configured":false}` → PUT `{"configured":true,"api_key_masked":"••••1234"}` → GET 返回 base_url/model/updated_at → DELETE `{"configured":false}`；catalog 出现 `heart-student-u_8186fbcaed` 且 grant 指向它。
- 取舍：删除 Key 后按决定 29 不回退共享 Key；本机为继续演示已重新授予宿主 profile（`assign_vendor_model.py`），学生一旦配置自己的 Key，其 grant 会被替换为个人 profile。

## 13. 2026-11-17 记忆页改造（决定 30/31）

- 后端：`integrations/deeptutor/heart_memory_api.py`，worker 挂载 `/api/heart/memory`：
  - `GET` 返回 `{preferences, profile}`，只取 L3 的 `preferences` 与 `profile` 条目；
  - `POST /preference` 走引擎 `write_preference(op="add")`（自带去重与原子写），ref 用合法的短名 `chat`；
  - `DELETE /{kind}/{entry_id}` 只允许 `preference|profile` 两类。
- 前端：`/memory` 改为 `features/heart/StudentMemory.tsx`（自然语言卡片、添加偏好、逐条删除）；删除 `/memory/{l1,l2,l3,graph,resolve}`，内部层级不可达。
- 验收：
  - `GET` → `{"preferences":[],"profile":[]}`；
  - 添加“讲题时多举例子，先给结论再展开” → 写入 `…/memory/L3/preferences.md`（中文完整，`[^1]: chat`）；
  - 重复添加返回同一 `entry_id`（去重生效）；
  - 删除 → 列表回空；
  - `/memory` 200，`/memory/l1` 404。
- 备注：PowerShell 5.1 直接发中文 JSON 会按 Latin-1 编码变成 `?`，验收时改用 UTF-8 字节；测试残留已删除。
- 未做：记忆页尚未接入“设置里的偏好唯一来源”核对（任务 7 的剩余项）。

## 14. 2026-11-17 教材知识图谱（决定 32 的第一步）

- 宿主接口：`graph_api.py` → `GET /api/graph/subgraph?chapter=&q=&limit=`（limit ≤ 200），只读 `heart_rag` 的 `lightrag_graph_nodes/edges`，按 `properties->>'file_path' = chapter_NN.generated.pdf` 限定章节，返回节点（id/type/description/chapter）、边（source/target/weight/description）与 `truncated`。
- 鉴权：校验厂家 `dt_token`（HS256，标准库实现，密钥读 `<home>/data/system/auth/auth_secret`）；匿名 401。不返回任何学生成绩。
- 代理：`web/proxy.ts` 把 `/api/graph/*` 直接 rewrite 到 `HEART_API_BASE_URL`（默认 `http://127.0.0.1:8000`），其余 `/api/*` 仍走厂家。
- 前端：`/learning/graph`（`features/heart/KnowledgeGraph.tsx`，cytoscape，章节选择、搜索、节点详情、截断提示）；侧栏“知识图谱”入口；节点详情显示实体类型与教材描述，并提供“去学习/去练习”，掌握状态明确写“尚未评估”。
- 验收（经 `:3000`）：匿名 401；`chapter=8&limit=40` → 40 节点 / 36 边 / `truncated=true`；节点带 `type` 与中文描述。
- 未做：实体↔知识点映射（需人工确认候选）与掌握状态叠加；这两项依赖“结果同步”，否则图谱只能显示教材结构。
