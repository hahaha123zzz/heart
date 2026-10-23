# LightRAG 8000运行切换记录

2026-10-23；用户明确“确认”后执行。**8000已运行LightRAG候选检索与Q5，现场问答及完整Q5接续/刷新通过；这次不再只是隔离接通。** 仍保留staging/ready=false和pending，不将候选使用宣称为教材正式发布。

- 当前业务提交：2ae1e5fd9618ea80a999a22cb30339a153e15d0c。后续仅文档提交，不改变运行代码。
- 页面：http://127.0.0.1:8000 。实际监听PID **43028**，固定目录 `E:/项目/heart/.runtime/response-portable-20261022/code-proof-2ae1e5f/project/integration/discrete-math-tutor`。
- 登记的venv子进程PID69688，其实际服务子进程为43028，父子关系、创建时间与目录已核实。外层隐藏启动器64212。Windows venv使用基础Python子进程并不表示改用了其他worktree环境。
- 实际进程白名单配置：Q3_RETRIEVAL_MODE=lightrag、Q5_LEARNING_ENABLED=1、LOCAL_AGENT_LOOP_ENABLED=1、LLM_MOCK=0、LIGHTRAG_ALLOW_CANDIDATE=1，候选是 `.runtime/response-portable-20261022/candidate`，实际端点为官方DeepSeek。本机凭据仅进程读取，未输出/写Git。
- 健康检查ok/mock_mode=false；最终仍确认8000由43028监听。健康响应的应用版本0.8.0不是Git版本，实际版本由固定导出/哈希和进程登记核对。

## 启动前校验与数据保护

证据根 **S**：`E:/项目/heart/.runtime/response-portable-20261022/switch-2ae1e5f-20261023`。结构化证据：[LIGHTRAG_RUNTIME_SWITCH_EVIDENCE.json](LIGHTRAG_RUNTIME_SWITCH_EVIDENCE.json)。

1. 启动器用socket确认8000未占用，不接管其他服务。5384个代码文件逐个与git archive一致，候选7个核心文件、policy及两份一致性备份核验通过。全量校验耗时较长，最终正常exit0，不曾跳过哈希校验；后续辅助诊断发现主进程已退出，未终止它，辅助缺脚本日志保留为preflight-v2.log，不能误作业务启动失败。
2. 使用用户批准的 `start-lightrag-approved-2ae1e5f.py --start-approved --activate-reviewed-candidate` 隐藏后台启动，仅读正式DB位置与本机ds.env；保留正式学习库，不迁移/重建/覆盖。未覆盖旧approved-runtime.json/旧备份登记，采用单独approved-lightrag-2ae1e5f-runtime.json和日志。
3. 启动前备份目录 `.runtime/response-portable-20261022/backup-before-lightrag-2ae1e5f`：两库integrity_check=ok、全部表计数一致、源哈希与备份时登记一致。正式切换后只读检查原有每一行和主键：全部仍在、内容未变。
4. 本次两个新验收账号均为account_type=test，数据库新增59行（旧课程库0，心理学学习库59），没有删除验收记录或已有数据。S/data-integrity-after.json给逐表对账；测试账号和新记录与用户原有记录分开标识。
5. 切换后候选核心/policy哈希不变，Q2 rag_index.sqlite3不变，未重建索引。正常检索缓存及部署副本的裁图可正常生成，不将缓存变化说成冻结图谱重建。

## 8000现场验收

没有向正式服务安装SDK、查询、来源替换或测试路由。浏览器脚本直接访问公开页面/接口；Q5前后快照通过只读SQLite筛选新验收账号，不修改学习状态来配合测试。

| 检查 | 实际结果 |
|---|---|
| 原跨章题“第一章的实验程序和第二章的自变量控制有哪些联系？” | answered/covered；实际backend=lightrag；两对象均覆盖，双方有效上标共3条；2次检索、0补查、无fallback；保存/刷新一致 |
| 上述首次现场请求 | 首次正文210.218秒，总221.377秒；检索覆盖阶段197.688秒。显著偏慢，保留为性能限制，不因功能通过说延迟已优化 |
| Q5计划→确认讲解 | 8.301秒awaiting_clarification→11.739秒answered；实际Q2精确目标读取保留 |
| Q5跨章插问 | 29.643秒answered/covered，实际LightRAG，双方引用有效；跨章前后路径/模块/目标/进度整个SQL快照相同，step_advanced=false |
| 返回原目标 | 17.943秒answered，目标与确认后相同 |
| 我懂了，下一部分 | 14.895秒answered，换到下一目标，mastered=false |
| 刷新恢复 | 普通问答及同次完整Q5最终正文一致，无第二次生成 |

Q5为一个新session中一次完整五步，并非拼接多次运行。独立验收此前10组全通过、TLS故障/版本失效/同图像素等证据仍以[接入报告](LIGHTRAG_INTEGRATION_FINAL_REPORT.md)为准；本次正式现场只追加普通问答与Q5，不冒充重新验了全部媒体负例。

命令（已执行；原始输出目录拒绝覆盖）：

```powershell
& 'E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe' -B 'E:/项目/heart/.runtime/response-portable-20261022/switch-2ae1e5f-20261023/run_smoke.py'
& 'E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe' -B 'E:/项目/heart/.runtime/response-portable-20261022/switch-2ae1e5f-20261023/check_data_after.py'
```

两项exit0。原始SSE/截图/逐步Q5快照：S/ordinary、S/q5；实际进程和开关：S/actual-runtime.json；最后存活检查：S/health-final.json。默认沙箱端口查询及Schannel无密钥探测不可靠，授权环境重查代理7890正常，官方无密钥探测预期401；业务实际请求200/answered，不把辅助探测失败归为凭据故障。

## 运行与回滚

当前已经运行，不要重复执行启动命令。之后主工作树的新提交不会自动生效：8000跑固定2ae1e5f副本，无热重载；下一次更新需重新导出、验收、做新一致性备份并受控切换。当前未配置开机自启。

回滚档仍可使用[启用方案](LIGHTRAG_INTEGRATION_FINAL_REPORT.md)中已准备的 `rollback-text-537dfb4.py`，但必须先核对新登记的PID/创建时间/命令/目录，仅停本次树。恢复旧代码时沿用最新学习库，不还原旧备份覆盖切换后的学习记录；不按python进程名批量杀进程。此轮没有执行回滚或停止新服务。

**回答体验运行版本：已启用并现场通过普通问答/Q5/刷新。LightRAG：已被8000实际使用，采用的是明确批准的候选模式；教材正式发布、全书人工审核仍未完成。** 原教材0题/测试题不冒充原题、pending图仍待审核。首个请求高延迟、长时运行/全部性能边界及开机自启不在本次完成结论内。
