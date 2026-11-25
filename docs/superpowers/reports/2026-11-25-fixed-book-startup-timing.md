# 固定教材启动分段计时报告

日期 2026-11-25
工作树 student-frontend-reuse-20261117
运行基线 lightrag-native-v4-20261124（宿主重排与 embedding 均为 CPU）

## 状态

本轮完成了分段计时、控制脚本并行探测、汇总报告器和首问采样器，代码与测试已提交。
真实启动采样按用户决定 **暂缓**：采样需要把本分支打成新发行并重启本机 18000/18001/8000，
而当前工作树另有会话在修改 textbook-prefetch 相关文件、且本机测试环境正在被使用。

因此本文只给出可复核的静态证据、计时口径和采样步骤；**没有实测数字被提前填入**。
采样完成后用 `deploy/startup_report.py` 生成本文第 5 节的表格，再补齐第 6 节三个结论。

现有基线（来自计划与既有记录，非本轮实测）：固定教材初始化 98.72 秒；另一次独立复跑中
第二次正式教材目录扫描 0.43 秒，旧本地检索样例查询 28.64 秒（含 28.30 秒原文重排）。

## 1. 计时口径

- 同一轮启动用 `STARTUP_ID` 关联控制脚本、宿主、worker 与首问采样器；每个进程单独写
  `<deployment>/private/startup-traces/<startup_id>/<service>-<pid>.jsonl`。
- 每条记录字段：`startup_id / service / pid / seq / stage / parent / seconds / status / at / fields`。
  `seconds` 在进程内用 `time.perf_counter()` 计算（Windows 的 `monotonic` 只有约 15.6 ms 分辨率）；
  `at` 是本机时区的墙钟时间，用于跨进程对齐。
- `/health` 的 `startup_seconds` 保持原有 `time.monotonic() - started` 口径，不受分项计时影响；
  另加 `fixed_book.startup_id` 供检索。
- 失败与取消：已走过的阶段按 `status=failed/cancelled` 记录并带异常类型；未执行的阶段不产生记录，
  不会以 0 秒出现。`FixedBookRuntime.start` 失败时另记 `fixed_book.start.failed`。
- 不记录教材原文、学生个人数据、API key、模型 endpoint；只记录阶段名、计数、字符数、模型名、
  设备、release/源签名、章节号。

## 2. 已布置的分段

| 分段 | 阶段名（`parent`） | 已有计数 / 说明 |
| --- | --- | --- |
| 控制脚本开始 | `control.begin` | label、cache_state、三个端口 |
| 各服务发行校验 | `control.release_verify` | 只计 `student_release.verify()`；release_id、文件数 |
| 服务进程创建 | `control.process_start` | pid、目标服务 |
| 顺序就绪检查 | `control.ready` | 目标服务、探测次数（会阻塞后续服务探测） |
| 并行辅助探测 | `probe.first_ok` / `probe.stopped` | 独立线程每 0.2 s 探测三个端口，单独文件 |
| 控制脚本总计 | `control.done` | 含失败状态；失败另记 `control.failed` |
| 宿主固定教材入口 | `fixed_book.entry` | 起点 |
| LightRAG 核验总计 | `lightrag.manifest`（parent `fixed_book`） | 输入文件数 |
| ├ 控制文件读取 | `lightrag.manifest.control_files` | 章数、complete 数 |
| ├ 索引清单核验 | `lightrag.index_manifest` | 命名空间数、源签名、源文件数 |
| │ ├ PostgreSQL 基线 | `lightrag.pg.baseline` | 清单命名空间数 |
| │ └ 表逐项核对 | `lightrag.pg.tables` | 表数、总行数 |
| ├ 冻结输入扫描 | `lightrag.manifest.frozen_input` | root=candidate_input、文件数 |
| ├ 正式教材扫描 | `lightrag.manifest.host_textbook` | root=host_textbook、文件数、额外文件数 |
| └ 控制文件摘要 | `lightrag.manifest.control_digest` | 摘要文件数 |
| 原文来源映射 | `lightrag.source_map`（parent `fixed_book`） | 章数、最慢章节与秒数 |
| └ 逐章映射校验 | `lightrag.source_map.chapter` | 章节号、块数 |
| 冻结图表目录 | `fixed_book.visual_map` | 视觉资产数 |
| 正式教材发布快照 | `fixed_book.release` | release_id、ready |
| 目录加载 | `fixed_book.outline` | 条目数 |
| 正式教材图表目录 | `fixed_book.visuals` | 视觉资产数 |
| 再次 inventory 建哈希表 | `fixed_book.hashes` | root=host_textbook、文件数 |
| 引用坐标 | `fixed_book.citation` | branch=fixed_path / version_cache / build |
| └ 新建引用索引 | `fixed_book.citation.build` | 构建与原子发布合计 |
| embedding 配置 | `lightrag.embedding.config` | model、dim |
| embedding 兼容检查 | `lightrag.embedding.compat` | — |
| 角色绑定 | `lightrag.roles` | 角色列表、binding 模式 |
| 常驻查询线程调度 | `lightrag.resident.schedule` | — |
| └ SDK 构建/初始化 | `lightrag.sdk.build` / `lightrag.sdk.initialize` | — |
| └ sidecar 绑定 | `lightrag.sidecars` | — |
| └ 逐章来源绑定 | `lightrag.provenance.chapter_XX` | 章号、块数、素材类数；聚合章数与最慢章 |
| │ ├ 入库包校验 | `lightrag.provenance.bundle` | — |
| │ ├ 文档元数据 | `lightrag.provenance.document` | — |
| │ └ 图表公式 sidecar | `lightrag.provenance.sidecar` | modality |
| 图谱标签装载 | `lightrag.labels` | 标签数、实体词数 |
| self.ready 赋值 | `fixed_book.ready_flag` | 相对入口秒数 |
| 旧索引加载 | `warmup.local_index` | — |
| 重排器会话 | `warmup.reranker` | device |
| 旧样例查询 | `warmup.sample_query` | 沿用 retrieve() 的 embedding/recall/rerank 秒数、语料数、设备 |
| 客户端池准备 | `warmup.client_pool` | model、mock |
| 图片词表 | `warmup.image_terms` | 图片数 |
| 固定教材完成 | `fixed_book.start.complete` | 总秒数 |
| `/health` 首次通过 | `host.health.first_ok` | fixed_ready、startup_seconds |
| worker 启动 | `worker.entry/vendor_import/app_import/warm_retrieval/warm_worker/listen` | 相对 worker 入口秒数 |
| 第一问 | `sample.login/connected/first_*/done/turn` | 事件类型、阶段、字符数、工具名、来源数 |

## 3. 已确认的重复工作（静态证据）

资产规模（只读计数，2026-11-25）：正式教材 material 文件 409 个（11 章 + 2 个 source 目录 + 4 个元数据）；
候选冻结输入 325 个文件；11 个 `source_map` 条目；当前发行清单 4919 个文件（三个服务各全量校验一次）。

1. **两次正式教材目录遍历是同一份工作。**
   `LightRagBackend.validate()` 里的 `verify_active(source_root, files)` 和
   `FixedBookRuntime.start()` 里的 `inventory(PSYCHOLOGY_DIR)` 调用同一个
   `knowledge/lightrag/course_input.inventory()`，根路径与 `material_files()` 过滤完全相同，都是 409 个文件。
   前者只返回“额外文件”，丢弃了完整哈希表；后者重新算一遍。共享哈希结果不会改变就绪条件。
   采样后可用 `lightrag.manifest.host_textbook` 与 `fixed_book.hashes` 的较小值作为可合并耗时上限。
2. **三个服务各自全量校验同一发行包。**
   `manage_student_local.py` 在同一个控制进程里对 host/worker/web 各调用一次
   `plan(..., timing=...)`，每次都执行 `student_release.verify()`（4919 个文件）。三次结果只用于
   release_id 一致性与启动环境；可由控制脚本校验一次后复用。
3. **图表/词表资产重复读取。**
   `visual_inventory(candidate/input)`（候选）、`load_visuals()`（宿主）、
   `course_release.snapshot()` 内的 `source_visuals.stats()`、以及 `load_figures()`（图片词表）
   分别读取目录或清单；各自用途不同（候选筛选、阅读定位、发行身份、图片检索词），
   但输入重叠。采样后按阶段名对比三者耗时，再判断能否共享解析结果。
4. **原文映射与逐章来源绑定读取不同文件。**
   `load_source_map()` 读 11 个 `document.json` 并逐个 SHA-256；`ResidentGraph.start()` 读每章的
   `blocks.json` 与 sidecar，不重复读 `document.json`。两者属于不同输入，暂不视为可合并。
5. **旧本地检索预热与线上 LightRAG 预热是两套栈。**
   `warmup.local_index` + `warmup.sample_query` 只服务旧快速路径；线上检索走
   `lightrag.resident.*`。旧索引退役计划会移除前者；在本轮报告中它们只作为耗时对比，不合并。
6. **跨线程等待与执行分开看。**
   `lightrag.resident.schedule` 包含 worker 线程启动；SDK 构建/初始化与逐章绑定是它的子阶段。
   父阶段与子阶段分别列出，同一墙钟区间只算一次。

## 4. 采样步骤（待执行）

前置：确认本机测试环境空闲、另一个会话已完成；本分支工作树没有未提交改动参与打包。

```powershell
$Worktree = "E:\项目\heart\.worktrees\student-frontend-reuse-20261117"
$Deploy   = "$Worktree\.runtime\student-release-20261122"
$Release  = "$Deploy\releases\fixed-book-startup-timing-20261125"
$Clean    = "C:\Users\free\AppData\Local\Temp\heart-startup-clean"
$Python   = "E:\项目\heart\.runtime\fixed-book-speed-20261025\standalone-venv\Scripts\python.exe"

# 1) 从本分支已提交快照打包，避免带上并发未提交改动
git -C $Worktree worktree add --detach $Clean HEAD
& $Python "$Clean\project\integration\discrete-math-tutor\deploy\student_release.py" bundle `
  --repo $Clean --output $Release --release-id fixed-book-startup-timing-20261125

# 2) 复用当前发行的 Next 构建产物（bundle 不含 .next）
$Prev = "$Deploy\releases\lightrag-native-v4-20261124\project\vendor\DeepTutor\web"
$Web  = "$Release\project\vendor\DeepTutor\web"
Copy-Item "$Prev\.next" "$Web\.next" -Recurse -Force
Copy-Item "$Prev\public" "$Web\public" -Recurse -Force

# 3) 校验并切换；上一版保留回退
& $Python "$Clean\project\integration\discrete-math-tutor\deploy\student_release.py" verify --release $Release
& $Python "$Clean\project\integration\discrete-math-tutor\deploy\student_release.py" select `
  --root $Deploy --release $Release --expected-current lightrag-native-v4-20261124

# 4) 用本分支的控制脚本与报告器覆盖 private/control
Copy-Item "$Worktree\project\integration\discrete-math-tutor\deploy\manage_student_local.py" "$Deploy\private\control\" -Force
Copy-Item "$Worktree\project\integration\discrete-math-tutor\deploy\run_student_release.py" "$Deploy\private\control\" -Force
Copy-Item "$Worktree\project\integration\discrete-math-tutor\deploy\startup_report.py" "$Deploy\private\control\" -Force

# 5) 至少三次进程重启；第一次标 process-cold，其余标 os-warm
& $Python "$Deploy\private\control\manage_student_local.py" restart --root $Deploy --label cold-1 --cache-state process-cold
& $Python "$Deploy\private\control\manage_student_local.py" restart --root $Deploy --label warm-1 --cache-state os-warm
& $Python "$Deploy\private\control\manage_student_local.py" restart --root $Deploy --label warm-2 --cache-state os-warm
```

每次 restart 的输出带 `startup_id` 与 `trace` 目录。随后跑同一道教材题两次（同一会话）：

```powershell
& $Python "$Worktree\project\integration\discrete-math-tutor\scripts\sample_startup_first_answer.py" `
  --base http://127.0.0.1:8000 --ws ws://127.0.0.1:8000/ws `
  --creds "$Deploy\private\worker-home\.runtime\review-accounts\vendor-accounts.txt" `
  --trace-dir "$Deploy\private\startup-traces\<startup_id>" --startup-id <startup_id> `
  --question "自变量是什么"
```

生成汇总（原始 JSONL 保留在同一目录）：

```powershell
& $Python "$Deploy\private\control\startup_report.py" --root $Deploy `
  --output "$Worktree\docs\superpowers\reports\2026-11-25-fixed-book-startup-timing.md"
```

回退：`student_release.py select --release <上一版> --expected-current fixed-book-startup-timing-20261125`，
再 `manage_student_local.py restart --root $Deploy`。若宿主无法就绪，按 `private/logs/host.log` 定位；
`fixed_book.start.failed` 的 `fields.error` 会给出失败类别。

采样注意：
- 第一次重启标为进程冷启动；未确认操作系统缓存的样本不要标 `os-warm`。
- 失败/取消场景：可先用一次错误配置（例如临时改坏 `LIGHTRAG_CANDIDATE_PATH` 的测试副本）验证
  `fixed_book.start.failed` 能定位最后阶段；不要改生产候选目录。
- 采集器开关对照：同一发行连续两次启动，一次设置 `STARTUP_TRACE_DIR`，一次不设置，核对调用次数、
  顺序和 `/health` 总秒数没有变化。

## 5. 汇总表（采样后自动生成）

采样完成后，`deploy/startup_report.py` 会输出：

1. 时间线：每个 startup_id 的缓存状态、控制脚本总计、固定教材初始化、`/health` 首次、第一问、第二问。
2. 顺序就绪与并行探测对照：区分“实际可用”与“控制脚本首次观测到可用”。
3. 阶段耗时：位置（service）、阶段、调用次数、中位数与范围（单样本列实测值）、占固定教材初始化比例。
4. 重复目录遍历：`verify_active` 与再次 inventory 的实测秒数、文件数和可合并上限。

## 6. 待采样后补写的三个结论

1. 耗时最大的三个阶段及多次样本的变化范围（以阶段汇总表为准）。
2. 可确认的重复工作、输入与耗时，以及是否影响就绪（静态证据见第 3 节；耗时范围待第 5 节）。
3. 就绪到首条教材回答的时间差，以及首问是否仍在加载或首次推理（看第一问的
   `sample.first_tool_call/first_text/done` 相对 `host.health.first_ok` 的差值；第二问同题对比缓存与常驻模型影响）。

对账要求：`fixed_book.entry` 到 `fixed_book.start.complete` 的总秒数应与串行子阶段之和一致；
若出现明显剩余，报告需补出未计时区间或注明来源（例如 `policy.json` 读取与阶段之间的 Python 开销）。
