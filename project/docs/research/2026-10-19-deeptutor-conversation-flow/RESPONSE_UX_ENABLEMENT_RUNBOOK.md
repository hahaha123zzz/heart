# 回答体验启用准备与回滚

最新部署收尾（2026-10-22，已提交业务537dfb4）：启动器递归已修复；独立完整宿主/候选/依赖/缓存、157项回归及真实native、跨章、partial、单次完整Q5、PDF、同图像素/页面、ask_user、取消/超时/晚到与刷新已有证据。**最终整轮AI测试练习触发CitationGroundingError，保持失败；全入口和整计划未完成，正式LightRAG不切换，staging/ready=false不变。** 以[部署收尾报告](LIGHTRAG_DEPLOYMENT_CLOSEOUT_REPORT.md)及[逐项证据](LIGHTRAG_DEPLOYMENT_CLOSEOUT_EVIDENCE.json)为本轮事实，下方旧日期保留历史。

## 2026-10-22 当前可执行首批方案（准备完成，未启动）

业务 **421f871**；[收尾报告](RESPONSE_UX_REMAINING_CLOSEOUT.md)记录独立环境111项、真实一般检索/页面、固定代码/输入及只读备份。旧段落保留此前未就绪状态，不再作为当前仍缺独立环境或备份的结论。

| 项目 | 本次实际值 |
|---|---|
| 固定release | `E:\项目\heart\.runtime\response-release-20261022\code\project\integration\discrete-math-tutor`；导出421f871，5380项对账不变 |
| 独立Python | `E:\项目\heart\.runtime\response-release-20261022\.venv\Scripts\python.exe`；pip check通过，不借其他worktree包 |
| 教材输入 | 独立副本457项，逐项哈希相同；原文、索引没有重建 |
| 已验档 | Q3=1、Q5=0、local_llamaindex、CPU、官方DeepSeek、后台记忆/额外生成图关闭；不是LightRAG档 |
| 一般检索预演 | 独立8013/库，真实回答17.225秒，6引用，上标与刷新通过；服务已停 |
| 原库备份 | `E:\项目\heart\.runtime\response-release-20261022\backup-before-enable-verified`；两库完整性ok，源字节不变，哈希见证据JSON |
| 启动器 | 同目录上级`start-approved.py`已生成、仅语法检查；读取本机ds.env，不复制/打印key；只把主.env数据库位置带入已验运行档 |
| 当前8000 | 无监听；运行目录/SHA/backend为null，磁盘代码不代表生效 |

启动会使用正式学习库，**本轮没有执行**。启动前重新核对8000占用和备份后是否已有新学习记录；若已变化，重新做只读online backup，不覆盖现有备份。首批只启用上述已验档，新独立环境没有全量重跑PDF/图像/AI练习，Q5保持关闭。LightRAG不启用，不改staging/ready=false。

完成最终启用决定后，具体启动命令如下；它不会强停已有8000服务：

```powershell
$releaseHome = 'E:\项目\heart\.runtime\response-release-20261022'
$releasePython = Join-Path $releaseHome '.venv\Scripts\python.exe'
$launcher = Join-Path $releaseHome 'start-approved.py'
if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { throw '8000已占用，先核对身份' }
$launcherProcess = Start-Process -FilePath $releasePython -ArgumentList @('-B', $launcher) -WorkingDirectory $releaseHome -WindowStyle Hidden -PassThru
$launcherProcess.Id | Set-Content -LiteralPath (Join-Path $releaseHome 'approved-launcher.pid')
Invoke-RestMethod 'http://127.0.0.1:8000/health'
```

启动器会登记真正uvicorn PID至`approved-service.pid`，并把PID/创建时间/解释器/目录/SHA/backend写入`approved-runtime.json`，日志在`approved-service.log`。启动后除health外，还须核对PID/目录、实际retrieval_calls、保存/刷新；首次启动失败按下列命令只停本次已登记服务，不按名称杀全部Python，不恢复旧备份覆盖新学习数据：

```powershell
$releaseHome = 'E:\项目\heart\.runtime\response-release-20261022'
$runtimeRecord = Get-Content -LiteralPath (Join-Path $releaseHome 'approved-runtime.json') -Raw | ConvertFrom-Json
$serviceId = [int]$runtimeRecord.pid
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$serviceId"
if (-not $process -or $process.CommandLine -notlike '*uvicorn*main:app*--port*8000*' -or $process.ExecutablePath -ne (Join-Path $releaseHome '.venv\Scripts\python.exe')) { throw '服务PID身份不符，停止操作' }
$createdAt = ([DateTimeOffset]$process.CreationDate).ToUnixTimeSeconds()
if ([Math]::Abs($createdAt - [double]$runtimeRecord.create_time) -gt 2) { throw 'PID创建时间不符，停止操作' }
Stop-Process -Id $serviceId
```

PID复用须通过登记创建时间校验；当前未启动，所以还没有该运行记录。此前8000未运行，因此本次回滚基线是停止本次服务并保留学习数据。没有准备擅自恢复身份不明的旧版本。正式LightRAG的sidecar可迁移性和全部入口仍待验，这套文本首批启动方案不能代替其切换验收。

## 以下为此前准备过程与通用命令（历史记录）

2026-10-22增量：官方DeepSeek查询迁移已接通，原网关绑定不再阻塞，本机.env通过LIGHTRAG_QUERY_ENV_FILE引用ds.env；见[迁移与真实实证](DEEPSEEK_QUERY_MIGRATION.md)。本文件其余部分保留此前正式启用前准备方案；不因迁移通过就自动执行8000启动或正式LightRAG索引切换。

2026-10-21；业务版本 `be8daa73b60c7e47d6954b95d85a574b191ecc72`。本轮未执行正式启动、备份或LightRAG切换。[收尾矩阵](RESPONSE_UX_CLOSEOUT_MATRIX.md)分别记录代码、离线、模型、页面及阻塞。

## 当前运行实况

8000在20:30—20:31无监听、健康检查连接失败，提升权限只读进程查询无相关Python服务。**没有正在运行的目录/SHA/backend可报告**；磁盘HEAD不等于线上版本。

主目录 `E:\项目\heart\project\integration\discrete-math-tutor` 存在其他窗口未提交内容，不在这里reset/clean/stash或覆盖部署。仅核对公开配置，不显示key：

| 配置/环境 | 磁盘值或代码默认 | 尚未生效/缺口 |
|---|---|---|
| OPENAI_BASE_URL | https://api.deepseek.com | 官方key不发网关 |
| TUTOR_COURSE / LLM_MOCK | experimental-psychology-3 / 0 | 不是服务已启动 |
| LOCAL_AGENT_LOOP_ENABLED | 未设置，默认0 | 普通聊天不自动走Q3循环 |
| Q3_RETRIEVAL_MODE | 未设置，默认stub | 不等于LightRAG正式接通；精确目标q2_exact单列 |
| Q5_LEARNING_ENABLED | 未设置，默认0 | Q5未自动启用 |
| MEMORY_WORKER_ENABLED | 未设置，默认1 | 启动可能写后台任务；隔离/首次验证先设0 |
| VISUALIZATION_ON_DEMAND | 1 | 首次验证禁用无关生成图，教材原图独立 |
| 主.venv | openai/fitz有；llama_index/lightrag无 | 一般检索依赖不足 |

现有SQLite路径已只读核对：`ai_tutor.db`（3465216字节）、`ai_tutor.experimental-psychology-3.db`（3604480字节），都在主目录。操作前若配置变化，重新解析实际路径。没有核实到历史运行SHA，不杜撰旧服务回退目标。

## 固定运行来源与依赖前置条件

本轮已将be8daa7导出到独立目录并验证，未带主目录未提交worker/config。教材目录未跟踪，通过本机junction读取已有课程输入；未写教材或重建索引。新机器须按Q2输入清单取得授权输入并验哈希，不能只clone即认为有书。

```powershell
$repo = 'E:\项目\heart'
$app = Join-Path $repo 'project\integration\discrete-math-tutor'
$runDir = Join-Path $repo '.runtime\response-closeout-20261021'
$release = Join-Path $runDir 'committed\project\integration\discrete-math-tutor'
$revision = 'be8daa73b60c7e47d6954b95d85a574b191ecc72'
git -C $repo merge-base --is-ancestor $revision main
if ($LASTEXITCODE -ne 0) { throw '运行来源不在稳定main中' }
```

测试只读借用LightRAG窗口已有venv，该环境含llama_index/lightrag/fastembed/onnxruntime；**不能将借用环境当作独立正式部署**。正式启用前准备本项目独立Python环境，按已有requirements锁和匹配Python版本核对依赖、embedding/reranker/device及一般检索。安装/同步本轮未执行。不得以精确read_target或import成功替代一般检索验收。

## 正式启动前的备份命令（尚未执行）

主main导入会建表、恢复中断提交、清理过期账户；因此即使不改schema，正式启动前也需备份。先停止新请求并等待本服务任务收尾，再运行SQLite online backup，源只读，备份检查完整性；不要直接复制正在写入的db。不导入main做备份。

```powershell
$backupDir = Join-Path $repo ('.runtime\response-backups\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path -LiteralPath $backupDir) { throw '备份目录已存在，不覆盖' }
New-Item -ItemType Directory -Path $backupDir | Out-Null
$env:UX_BACKUP_APP = $app
$env:UX_BACKUP_DEST = $backupDir
$backupCode = @'
import hashlib,json,os,sqlite3
from pathlib import Path
root=Path(os.environ['UX_BACKUP_APP']); out=Path(os.environ['UX_BACKUP_DEST'])
records=[]
for name in ('ai_tutor.db','ai_tutor.experimental-psychology-3.db'):
    source=(root/name).resolve(strict=True); target=out/name
    if target.exists(): raise RuntimeError('备份文件已存在')
    src=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
    dst=sqlite3.connect(target)
    try:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise RuntimeError('备份完整性失败')
    finally: dst.close(); src.close()
    records.append({'file':name,'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
(out/'backup-manifest.json').write_text(json.dumps(records,indent=2),encoding='utf8')
print('SQLite backups verified:',len(records))
'@
$backupCode | & "$app\.venv\Scripts\python.exe" -
if ($LASTEXITCODE -ne 0) { throw '备份失败，停止启用' }
Remove-Item Env:UX_BACKUP_APP,Env:UX_BACKUP_DEST
```

以上文件名是本次核对配置；数据库类型/路径变化则先修改方案。备份留本机不进Git。本轮已将文档中的原Python片段用于2份隔离WAL库自检，完整性和已提交WAL记录通过，见`.runtime/response-closeout-20261021/preparation-checks.json`；未对正式库备份或改动。启动Python片段也仅编译检查，不表示启动通过。

## 启动准备命令（不在本轮执行8000启动）

先完成独立环境、一般本地检索/失败行为及代码完整性检查，在8012及独立DB预演。完整Q5跨章尚未验完，初次准备保持Q5=0；不切换LightRAG。下面只生成本机启动器，安全读取主.env注入子进程，不复制.env或打印key。`$release\.venv`是待准备的独立环境，不是当前已存在环境。

```powershell
$releasePython = Join-Path $release '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $releasePython)) { throw '独立运行环境未就绪' }
$launcher = Join-Path $runDir 'start-approved.py'
@'
import os,subprocess
from pathlib import Path
from dotenv import dotenv_values
app=Path(r'E:/项目/heart/project/integration/discrete-math-tutor')
release=Path(r'E:/项目/heart/.runtime/response-closeout-20261021/committed/project/integration/discrete-math-tutor')
env={**os.environ,**{k:v for k,v in dotenv_values(app/'.env').items() if v is not None}}
env.update(OPENAI_BASE_URL='https://api.deepseek.com',TUTOR_COURSE='experimental-psychology-3',LLM_MOCK='0',
    LOCAL_AGENT_LOOP_ENABLED='1',Q3_RETRIEVAL_MODE='local_llamaindex',Q5_LEARNING_ENABLED='0',
    MEMORY_WORKER_ENABLED='0',VISUALIZATION_ON_DEMAND='0',PYTHONDONTWRITEBYTECODE='1',
    DATABASE_URL='sqlite:///'+str(app/'ai_tutor.db'),
    COURSE_DATABASE_URL='sqlite:///'+str(app/'ai_tutor.experimental-psychology-3.db'))
env.pop('LIGHTRAG_CANDIDATE_PATH',None);env.pop('LIGHTRAG_ALLOW_CANDIDATE',None)
python=release/'.venv/Scripts/python.exe'
raise SystemExit(subprocess.run([str(python),'-B','-m','uvicorn','main:app','--host','127.0.0.1','--port','8000'],cwd=release,env=env).returncode)
'@ | Set-Content -LiteralPath $launcher -Encoding utf8
```

隔离预演必须将port换8012、两个DB换成新的独立文件，不能用正式学习库演练。官方key仅在本机进程内存继承，不能换URL试网关。LightRAG专用凭据另由安全配置注入后续隔离验收。

**只有前置验收、备份完成且具体启动获准后**才执行下列正式启动：

```powershell
if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { throw '8000已有服务，先核对身份，不强杀' }
$service = Start-Process -FilePath $releasePython -ArgumentList @('-B', $launcher) -WorkingDirectory $release -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runDir 'approved-service.out.log') -RedirectStandardError (Join-Path $runDir 'approved-service.err.log') -PassThru
$service.Id | Set-Content (Join-Path $runDir 'approved-launcher.pid')
Invoke-RestMethod 'http://127.0.0.1:8000/health'
```

/health版本0.8.0不含git SHA或真实查询backend，200不能证明新版本接通。需另存release SHA/哈希、PID/启动时间/目录/非敏感有效开关，执行实际问答/选区/来源失败检查，验证retrieval_calls、来源/引用/保存与刷新。精确q2_exact和一般local_llamaindex分别记账，失败不自动切LightRAG。

## 回滚命令与数据保护

当前8000原本未运行，无可核实的旧运行SHA。正式启用前登记真实旧release/配置；若是初次启用失败，仅停本次已登记服务，保留DB/证据，不启动身份不明的历史版本。

```powershell
$serviceId = [int](Get-Content (Join-Path $runDir 'approved-launcher.pid'))
$registered = Get-CimInstance Win32_Process -Filter "ProcessId=$serviceId"
if (-not $registered -or $registered.CommandLine -notlike '*start-approved.py*') { throw 'PID身份不符，停止操作' }
# 确认启动时间与登记记录一致后，仅停本次父子进程树；不删除文件：
taskkill /PID $serviceId /T
```

不得按进程名批量杀Python。代码回滚使用固定旧release与兼容配置，沿用当前学习DB；默认不恢复旧备份覆盖新学习数据。确需数据恢复时先备份当前库，再单独确认丢失范围与迁移兼容。不要删库、教材、索引或失败证据，不改ready=false，不清理其他窗口。

**回答体验**：已验入口可隔离使用；本轮暂不整体启用8000，仍缺独立环境、一般检索预演和备份。**LightRAG**：凭据及完整真实矩阵不足，不可正式切换。两者独立判断。
