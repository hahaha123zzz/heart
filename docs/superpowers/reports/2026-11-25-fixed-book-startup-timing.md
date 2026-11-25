# 固定教材启动分段计时报告

日期 2026-11-25
工作树 student-frontend-reuse-20261117
运行基线 lightrag-native-v4-20261124（宿主重排与 embedding 均为 CPU）

## 状态

分段计时、控制脚本并行探测、汇总报告器和首问采样器已完成，代码与测试已提交。

本机做了真实启动尝试，结论分三部分：

1. **3 次受控重启验收未完成**：干净计时发行在“先 host、后 worker”的现有控制顺序下，
   宿主在 60 秒内等不到 worker 就绪而退出。worker 的 `warm_retrieval` 单次 49.21 秒，
   冷启动实测 96.4 秒；同时控制脚本对三个服务各做一次发行包全量校验（2.61 / 16.09 / 18.26 秒）。
   这条失败轨迹本身已由分段记录定位（见第 5.1 节）。
2. **拿到一次可用的宿主单样本**：先把 worker 启动并就绪（96.4 秒），再由受控脚本启动 host/web；
   固定教材初始化 33.48 秒，分项见第 5 节。样本是 `os-warm`、`textbook-prefetch-20261125` 发行、
   且编排顺序与控制脚本默认不同，**不能当作 98.72 秒基线的同条件对照**。
3. **首问未采样**：采样器未运行，因此“就绪→首答”仍为空。

本机测试环境已恢复到采样前的 `textbook-prefetch-20261125` 发行并确认 `ready`。

现有基线（来自计划与既有记录，非本轮同条件对照）：固定教材初始化 98.72 秒；另一次独立复跑中
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
| 顺序就绪检查 | `control.ready` | 目标服务、探测次数、`elapsed_since_origin`（与并行探测同起点）；`seconds` 是本次等待时长 |
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
| │ ├ 原文块文件 | `lightrag.provenance.blocks` | 块数 |
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
| worker 启动 | `worker.entry/vendor_import/app_import/warm_retrieval/warm_worker/ready_to_listen` | 相对 worker 入口秒数；`ready_to_listen` 不代表端口已监听成功 |
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

# 4) 用本分支的控制脚本与报告器覆盖 control（注意目录是 control，不是 private/control）
Copy-Item "$Worktree\project\integration\discrete-math-tutor\deploy\manage_student_local.py" "$Deploy\control\" -Force
Copy-Item "$Worktree\project\integration\discrete-math-tutor\deploy\run_student_release.py" "$Deploy\control\" -Force
Copy-Item "$Worktree\project\integration\discrete-math-tutor\deploy\startup_report.py" "$Deploy\control\" -Force

# 5) 至少三次进程重启；第一次标 process-cold，其余标 os-warm
& $Python "$Deploy\control\manage_student_local.py" restart --root $Deploy --label cold-1 --cache-state process-cold
& $Python "$Deploy\control\manage_student_local.py" restart --root $Deploy --label warm-1 --cache-state os-warm
& $Python "$Deploy\control\manage_student_local.py" restart --root $Deploy --label warm-2 --cache-state os-warm
```

每次 restart 的输出带 `startup_id` 与 `trace` 目录。随后跑同一道教材题两次（同一会话）：

```powershell
& $Python "$Worktree\project\integration\discrete-math-tutor\scripts\sample_startup_first_answer.py" `
  --base http://127.0.0.1:8000 --ws ws://127.0.0.1:8000/ws `
  --creds "$Deploy\private\worker-home\.runtime\review-accounts\vendor-accounts.txt" `
  --trace-dir "$Deploy\private\startup-traces\<startup_id>" --startup-id <startup_id> `
  --question "自变量是什么"
```

生成汇总（原始 JSONL 保留在同一目录；表格写到单独文件，避免覆盖本文方法说明）：

```powershell
& $Python "$Deploy\control\startup_report.py" --root $Deploy `
  --output "$Worktree\docs\superpowers\reports\2026-11-25-fixed-book-startup-timing-tables.md"
```

再把 `-tables.md` 的时间线、阶段自身耗时、串行对账和重复遍历四张表粘回本文第 5 节。
阶段表只统计成功就绪的启动，先按 `startup_id` 汇总同名阶段，再对“自身耗时
（阶段总耗时 − 同启动内子阶段合计）”取中位数；总量与里程碑（`*.start.complete`、`*.ready_flag`、
`worker.*` 导入里程碑、`sample.*`、`probe.*`）不参与排名，避免总耗时冒充最慢阶段。

回退：`student_release.py select --release <上一版> --expected-current fixed-book-startup-timing-20261125`，
再 `manage_student_local.py restart --root $Deploy`。若宿主无法就绪，按 `private/logs/host.log` 定位；
`fixed_book.start.failed` 的 `fields.error` 会给出失败类别。

采样注意：
- 第一次重启标为进程冷启动；未确认操作系统缓存的样本不要标 `os-warm`。
- 失败/取消场景：可先用一次错误配置（例如临时改坏 `LIGHTRAG_CANDIDATE_PATH` 的测试副本）验证
  `fixed_book.start.failed` 能定位最后阶段；不要改生产候选目录。
- 采集器开关对照：同一发行连续两次启动，一次设置 `STARTUP_TRACE_DIR`，一次不设置，核对调用次数、
  顺序和 `/health` 总秒数没有变化。

## 5. 单次成功样本（非三次重启验收）

- 发行：`textbook-prefetch-20261125`（包含本次计时改动和并发会话的 prefetch 改动；不是干净计时发行）。
- 编排：先手动启动 worker 并等到 `/health/ready`（96.4 秒），再 `manage start` 启动 host/web。
  因此控制脚本的“顺序就绪”从 host 开始算，worker 的真实冷启动不在这一列的 41.78 秒内。
- 缓存：`os-warm`（worker 已就绪、模型已加载）。
- 原始记录：`.runtime/student-release-20261122/private/startup-traces/20261125T200344-26504/`
  （`host-36532.jsonl`、`control-26504.jsonl`、`probe-26504.jsonl`；worker 记录在 `recovery-worker/`）。
- 首问采样未运行。

### 时间线

| 启动 | 缓存状态 | 控制脚本总计 | 固定教材初始化 | health 首次（自模块初始化） | 就绪→首问 | 首问耗时 | 第二问 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 20261125T200344-26504 | os-warm | 51.79 | 33.48 | 41.09 | — | — | — |

顺序就绪（相对控制脚本起点）与并行探测对照：

| 启动 | 顺序 host | 顺序 worker | 顺序 web | 探测 host | 探测 worker | 探测 web |
| --- | --- | --- | --- | --- | --- | --- |
| 20261125T200344-26504 | 51.75 | 51.77 | 51.79 | 51.53 | 0.82 | 11.12 |

控制脚本分段（不参与宿主阶段排名）：

| 启动 | 发行校验合计 | 进程创建合计 | 顺序就绪等待合计 |
| --- | --- | --- | --- |
| 20261125T200344-26504 | 9.73 | 0.03 | 41.78 |

### 阶段自身耗时（前 12）

自身耗时 = 该阶段总耗时 − 同启动内子阶段合计；占比按固定教材初始化 33.48 秒计算。

| 位置 | 阶段 | 父阶段 | 调用 | 实测自身耗时 | 占固定教材 |
| --- | --- | --- | --- | --- | --- |
| host | warmup.sample_query | warmup | 1 | 11.88 | 35.5% |
| host | lightrag.manifest.host_textbook | lightrag.manifest | 1 | 6.35 | 19.0% |
| host | lightrag.manifest.frozen_input | lightrag.manifest | 1 | 5.94 | 17.7% |
| host | lightrag.provenance.bundle | lightrag.provenance.chapter_01 | 11 | 1.65 | 4.9% |
| host | warmup.local_index | warmup | 1 | 1.35 | 4.0% |
| host | lightrag.sdk.build | lightrag.resident.start | 1 | 0.87 | 2.6% |
| host | fixed_book.outline | fixed_book | 1 | 0.83 | 2.5% |
| host | fixed_book.hashes | fixed_book | 1 | 0.60 | 1.8% |
| host | fixed_book.release | fixed_book | 1 | 0.36 | 1.1% |
| host | lightrag.pg.tables | lightrag.index_manifest | 1 | 0.31 | 0.9% |
| host | lightrag.sdk.initialize | lightrag.resident.start | 1 | 0.31 | 0.9% |
| host | lightrag.resident.start | lightrag.resident.schedule | 1 | 0.29 | 0.9% |

注：该样本来自旧发行，`warmup.*` 的 `parent` 仍记为 `warmup`；干净发行已改为 `fixed_book`，
报告对两种写法都做对账。完整阶段表由 `startup_report.py` 生成。

### 串行阶段对账

| 启动 | 固定教材总耗时 | 顶层阶段合计 | 未计时剩余 |
| --- | --- | --- | --- |
| 20261125T200344-26504 | 33.48 | 32.27 | 1.21 |

### 重复目录遍历

| 启动 | verify_active | 再次 inventory | 文件数 | 可合并范围 |
| --- | --- | --- | --- | --- |
| 20261125T200344-26504 | 6.35 | 0.60 | 409 / 409 | 0.60 |

## 5.1 三次重启验收受阻（关键发现）

干净计时发行 `fixed-book-startup-timing-20261125` 连续三次 `restart` 均在宿主就绪处失败。
失败轨迹（`private/startup-traces/20261125T195101-36552` 等）：

- `control.release_verify`：2.61 / 16.09 / 18.26 秒（host / worker / web 各做一次全量发行校验）。
- worker 分段：`worker.entry` 0、`vendor_import` 0.24、`app_import` 2.16 后停在
  `install_native_bridge`，60 秒窗口内没有 `warm_retrieval` 记录。
- 宿主日志：`原生 worker 在 60 秒内未就绪`。`control.failed` 的 `target=host` 定位到最后阶段。
- 手工单跑 worker：`warm_retrieval` 49.21 秒，`ready_to_listen` 54.86 秒；另一次冷启动
  `/health/ready` 96.4 秒。

原因链：宿主先启动并硬编码等待 worker 60 秒；控制脚本对三个服务顺序做发行校验，worker 被推迟
数十秒才 spawn；worker 自身预热已接近或超过 60 秒。三者叠加时宿主必然超时。

要让三次重启验收可执行，需在下列方案中选一个（属于后续优化计划，不在本轮计时改动内）：
1. 控制脚本校验一次发行包并复用结果（第 3 节第 2 条，预计可省 2.6–18.3 秒 × 2）；
2. 改为 worker 先就绪、再启动 host；
3. 放宽宿主 60 秒的 worker 就绪预算，并说明对就绪定义的影响。

## 6. 三个结论（按现有证据）

1. **耗时最大的三个阶段**：单样本（os-warm、worker 先行）为
   `warmup.sample_query` 11.88 秒（35.5%）、`lightrag.manifest.host_textbook` 6.35 秒（19.0%）、
   `lightrag.manifest.frozen_input` 5.94 秒（17.7%）。多次样本的范围尚未取得；
   98.72 秒基线与本样本 33.48 秒不是同条件对照（发行、缓存、编排均不同）。
2. **可确认的重复工作**：同一 409 个正式教材文件的 `verify_active` 6.35 秒与再次 inventory 0.60 秒
   可共享结果，保守可合并范围 ≤0.60 秒/次启动；三个服务的发行包全量校验每次 2.61–18.26 秒，
   一次校验即可服务三个服务；图表/词表目录由候选、宿主、发行快照和图片词表分别读取。
   重复校验不仅耗时可观，还通过推迟 worker 启动**直接影响就绪**（第 5.1 节）。
3. **就绪到首条教材回答**：未测。固定教材的预热（旧索引、样例查询、图片词表）都在
   `fixed_book.ready_flag` 之后、`fixed_book.start.complete` 之前完成，因此不会推迟到第一问；
   第一问的剩余成本是模型与检索推理，需要采样器运行后才能给出时间差。

对账要求：`fixed_book.entry` 到 `fixed_book.start.complete` 的总秒数应与串行子阶段之和一致；
本例为 33.48 ≈ 32.27 + 1.21，剩余为 `policy.json` 读取与阶段之间的 Python 开销。
