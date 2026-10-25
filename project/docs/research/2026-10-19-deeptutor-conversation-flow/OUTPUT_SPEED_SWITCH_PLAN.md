# 输出速度运行版本切换与回滚准备

收尾更新：2026-10-25。业务验收提交：`073f814f77689a87e11c9aa7dc51ad80e59bd384`。本窗口未切换8000，也未迁移正式数据库。

## 实际运行与门槛

只读进程核对发现8000已由并行Q4窗口切到`E:\项目\heart\.runtime\q4-switch-20261024\release`，监听PID49972，发布记录`release.json`为`e8edcf458fa1b76625952250671f35d5a78c1ccd`。实际cwd、命令和开关记录在`.runtime/output-speed-20261024/formal-readonly-audit.json`；PID仅代表核对时点，执行时必须重新核对创建时间/cwd/命令。不可沿用旧2ae1e5f或17f8944当作当前回滚目标。

该Q4分支与main的共同祖先仍为be7cc9c，本提速分支没有擅自合入它。因此正式启用前必须由集成负责人对账Q4完整提交链（含滚轮阅读器），防止替换时丢失现网工具/阅读器成果。代码合入main不等于可替换现网。

两个正式库的conversations均没有session_id；心理学库q5_learning_bindings缺少session_plan。新主线启动会运行会话列增量迁移，Q5本次安排也需要显式增量迁移。速度专项原计划不包含业务表迁移，故本窗口仅给出依赖，不自动ALTER，不运行新代码连接正式库。使用现有database/conversation_session_migration.py及database/session_plan_migration.py，由迁移交付核对后执行，不自行重写。

此外，部分性能类别未达20%，PDF真实流程出现一次反问门禁拒绝；未通过项见验收矩阵。以上门槛解决前维持现有8000。

## 准备固定导出（仅在门槛解决后执行）

1. 固定最终集成SHA，使用git archive导出，不能复制未提交主工作区。示例（目录已存在则停止，不能覆盖旧发布）：

```powershell
$repoPath = 'E:\项目\heart'
$releaseSha = '073f814f77689a87e11c9aa7dc51ad80e59bd384' # Q4联合后应替换为复验过的最终SHA
$deployPath = Join-Path $repoPath ('.runtime/output-speed-deploy-' + $releaseSha.Substring(0,7))
if (Test-Path -LiteralPath $deployPath) { throw '发布目录已存在，拒绝覆盖' }
New-Item -ItemType Directory -Path $deployPath | Out-Null
git -C $repoPath archive --format=tar --output="$deployPath/source.tar" $releaseSha project/integration/discrete-math-tutor
tar -xf "$deployPath/source.tar" -C $deployPath
```

2. 完整宿主教材取当前Q4发布使用的教材输入，包含现有rag_index.sqlite3和宿主附加文件；冻结部分逐文件内容哈希一致。纯candidate/input不能替代完整宿主。复制教材不代表授权建图或重建索引。
3. 正式LightRAG路径保持`E:\项目\heart\.runtime\response-portable-20261022\candidate`，不切到C盘隔离候选；7个核心文件哈希继续与setup.json相同。ready=false/staging/pending全部保留。
4. 沿用现有venv和模型缓存；仅从本机ds.env注入官方DeepSeek配置，不复制密钥进命令行、报告、Git或发布副本。验收故障头、观测包装不能进入生产启动器。
5. 数据库保持当前两个绝对文件，不采用发布目录默认库。先审核迁移前/后schema、旧历史session_id=NULL的访问策略和回滚兼容；禁止通过整库替换解决迁移。

## 备份与启动

先为两个实际库执行sqlite3.Connection.backup，目标使用全新日期目录；拒绝覆盖。必须在迁移和停服前保存备份及表行数。下列代码是操作模板，尚未运行：

```python
from pathlib import Path
from datetime import datetime
import sqlite3
root = Path(r'E:\项目\heart')
backup = root / '.runtime' / ('output-speed-backup-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(exist_ok=False)
for name in ('ai_tutor.db', 'ai_tutor.experimental-psychology-3.db'):
    source = root / 'project/integration/discrete-math-tutor' / name
    with sqlite3.connect('file:' + str(source) + '?mode=ro', uri=True) as src:
        with sqlite3.connect(backup / name) as dst:
            src.backup(dst)
```

核对8000监听进程的PID、创建时间、cwd和uvicorn命令，再由正式切换步骤停止准确进程。端口身份变化即停止操作，不杀旧登记PID。新启动使用固定导出app为WorkingDirectory，命令为现有venv `python -B -m uvicorn main:app --host 127.0.0.1 --port 8000`；由安全启动档提供审核后的原索引/原数据库环境，后台Start-Process必须WindowStyle Hidden。登记实际子进程身份和代码/前端哈希，健康检查后还需普通、跨章、图像、Q5、选区和刷新真实冒烟，才能标为启用。

## 回滚至本轮实际现网Q4

停止新进程时做同样的身份核对，保留新产生的学习数据和候选。若本轮核对的Q4仍是切换前版本，可执行其既有live启动档：

```powershell
$pythonPath = 'E:\项目\heart\.runtime\response-release-20261022\.venv\Scripts\python.exe'
$launcherPath = 'E:\项目\heart\.runtime\q4-switch-20261024\launch.py'
Start-Process -FilePath $pythonPath -ArgumentList @('-B', ('"' + $launcherPath + '"'), 'live') -WorkingDirectory 'E:\项目\heart\.runtime\q4-switch-20261024' -WindowStyle Hidden
```

注意该启动档的`rollback`参数会进一步回到stream-switch旧版本，所以本轮恢复Q4应使用`live`，而不是`rollback`。如果其他窗口再次发布，先更新本文件的回滚目标。重启自然关闭传输池并清空进程内缓存；不得覆盖最新学习库、删除候选或重建索引。
