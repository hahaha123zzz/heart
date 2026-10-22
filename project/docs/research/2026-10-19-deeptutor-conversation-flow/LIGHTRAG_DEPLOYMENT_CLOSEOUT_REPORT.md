# LightRAG 独立部署收尾（2026-10-22）

**递归与部署路径问题已修复，并通过独立原生/跨章检索。最终整轮10组中9组通过，AI测试练习触发引用门禁异常，保持失败。回答体验已验文本范围可准备受控启用，整体全入口仍有失败；LightRAG可继续隔离使用，不可切换正式索引，staging/ready=false不变。**

## 版本、实现与资源

- 被测 main `537dfb42d523b7f56e2b2ccb68ea1ffde8cbf748`。已核对803db64、55f930a、e3b7073、2b79ddc、31adf968、8bce4ee均为祖先；完整LightRAG此前基础链、公共6a8b0f7/be8daa7与官方查询迁移99aadf2/取消修复421f871保留，没有单独摘取最后三个交付提交。递归修复及本报告为本窗口交付，其他窗口改动未复制。
- 803db64是业务查询实例的sidecar迁移读取视图和active source_root；55f930a分开冻结input严格校验与完整宿主附加文件审计。没有在验收脚本重写URI或替换来源校验。
- 537dfb4仅新增验收包装、5个自检与接口说明。serve.py只保存一次original_native_query，普通/超时/取消调用同一个闭包引用；缓存控制、计时与故障注入合并，不再有fresh全局重绑定。未为启动器修复修改SDK、生产检索或冻结图谱。
- 原有4个修改、4455个教材相关删除和未跟踪教材保留，未修改其他worktree；本批不碰main.py、TaskService和前端。根因调查文档仍为原窗口文件，本次未暂存。

证据根 **P**：`E:/项目/heart/.runtime/response-portable-20261022`；最终完整运行 **F**：`P/proof-537dfb4-final`。

| 资源 | 当前部署与核验 |
|---|---|
| 已提交宿主 | P/code-proof-537dfb4/project/integration/discrete-math-tutor；git archive导出，5384个宿主文件逐个哈希相同 |
| 完整教材 | 457个文件，409个material；325个冻结内容相同，84个附加material只审计且evidence_eligible=false |
| 现有Q2索引 | 原文件和副本均SHA256 2a052d6d90624119c7bb10d445bcfb7c0a82306021f2af55ed29c71d23b0e7ef；不重建 |
| 独立候选 | P/candidate；workspace deeptutor_426733019d24d665；input_signature 0a6096dc43a8829d48776cbcd0c583b6dc779bd6b450614b4bd20bd1d7f0e5ce |
| 候选完整性 | 部署前后7个核心文件和policy哈希不变；来源映射、冻结input、223个sidecar逐文件另列清单 |
| 独立依赖 | 同级response-release-20261022/.venv；Python3.12.14、LightRAG1.5.7、openai3.36.1、fastembed0.8.1、CPU onnxruntime1.31.0、llama-index-core0.14.25 |
| 模型缓存 | 17个文件复制到P/model-cache/fastembed，最终整轮使用此目录，HF离线，不下载/重建模型 |
| 数据库 | F/all/course.db等新隔离库；正式两个学习库前后哈希未变 |
| 凭据 | 仅进程读取本机ds.env，实际端点https://api.deepseek.com；旧网关仅是冻结历史身份，没有请求旧网关 |

完整资源/启动器哈希：P/resource-manifest-final.json；5384个代码与候选核心对账：P/integrity-537dfb4.json。上述环境仍需本机基础Python，不宣称ZIP可在无Python的空白机器直接运行。

运行审计主动拒绝旧heart-worktrees整树、旧候选目录的open/scandir/listdir。F/environment-final.json中forbidden_old_reads=[]、uri_test_hook=false；source_binding确实访问新候选sidecar与当前宿主原文，不靠原路径仍存在通过。

## 命令及实际结果

最终整轮命令（本轮已执行，仅8012和隔离库）：

```powershell
& 'E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe' -B 'E:/项目/heart/.runtime/response-portable-20261022/run_final.py'
```

runner固定新输出目录，拒绝覆盖既有运行。复现需登记新输出名，不能删除失败后冒充首跑。最终exit=1，因为练习失败；server-exit.json的runner_terminated=true表示测试结束主动停止，非意外退出。

离线：包装5项通过；最终归档宿主157项通过，78.854秒，P/regression-proof-537dfb4.log。工作目录为归档宿主，命令：

```powershell
& 'E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe' -B -m unittest tests.test_lightrag_acceptance_instrumentation tests.test_lightrag_relocation tests.test_q3_task_loop tests.test_q3_entrypoint tests.test_task_service_context tests.test_course_search_bridge tests.test_q5_learning tests.test_lightrag_backend tests.test_lightrag_coverage tests.test_lightrag_q3_adapter tests.test_lightrag_deepseek_query tests.test_answer_media tests.test_answer_stream tests.test_response_citations -q
```

真实native查询13.078秒成功、4个有效来源，官方LLM实际调用非零。下面均为同一F：首字是首次正文DOM绘制，None表示结构化输出没有模型正文首字；外层模型次数不含native异步SDK，原生查询次数单列。

| 案例 | 实际读取 | 首字/总耗时（秒） | 外层模型/原生查询 | 最终引用数；章节 |
|---|---|---|---|---|
| cross | lightrag | 28.141 / 31.878 | 7 / 2 | 5；[1, 2] |
| single | lightrag | 12.298 / 15.635 | 4 / 1 | 3；[2] |
| q5-plan | 结构化计划/问卡，无检索 | None / 0.848 | 0 / 0 | 0；[] |
| q5-confirm | q2_exact | 3.587 / 6.856 | 4 / 0 | 2；[1] |
| q5-cross | lightrag | 25.174 / 28.288 | 7 / 2 | 4；[1, 2] |
| q5-return | q2_exact | 3.774 / 7.723 | 4 / 0 | 3；[1] |
| q5-next | q2_exact | 8.036 / 12.349 | 6 / 0 | 1；[1] |
| pdf-explain | 选区原文 | 4.927 / 7.916 | 5 / 0 | 2；[1] |
| pdf-followup | 选区原文 | 4.597 / 7.208 | 5 / 0 | 1；[1] |
| media-tool | q2_exact | 6.231 / 10.742 | 4 / 0 | 2；[5] |
| ask-pause | 结构化计划/问卡，无检索 | None / 1.335 | 1 / 0 | 0；[] |
| ask-resume | lightrag | 10.603 / 14.004 | 4 / 1 | 2；[1] |
| partial | lightrag | 27.52 / 30.47 | 5 / 3 | 3；[1] |

- 普通原跨章题及Q5插问均covered，双方有效上标，无fallback。Q5双方原文逐字匹配实际模型工具输入，6个有原文链接的关联候选实际进入模型；图谱描述和原文分开，候选evidence_eligible=false、linked_candidate_requires_claim_check，不自动成为先修、重点或掌握依据。
- 缺一方使用“第二章的火星玄武岩晶体结构”，真实3次native/1次补查后partial，正文明确缺失；未伪造检索结果。
- Q5五步同一session单次完整完成：插问前后整个学习状态相同，返回同目标、下一部分到不同目标且mastered=false、刷新一致。讲解/返回/下一部分用q2_exact，插问用LightRAG，不拼接不同运行。
- PDF两次连续追问读取选区原文和裁图，不计LightRAG通过。ask_user恢复同task_id、revision增加，续答实际LightRAG，刷新一致。
- 图5-2生成/质检请求均含SHA256 d713f3bae36f099e03fefaea8533fa84c0afae74e3b8891ca164087db43e0f75像素，官方响应成功。页面实际解码、点击返回第5章第3节、刷新同图，额外生成请求0；F/media/ui-pixels.json、image-visible.png、image-source.png。图仍标待审核，不把pending变approved；成功发送像素不等于所有视觉理解均正确。
- native取消5.552秒，SDK实际结束1792677417.863252，backend结束1792677417.866550（取消后约0.083秒）。超时为明确50ms故障注入、3次有界查询，SDK均CancelledError，13.424秒总耗时，不能当正常服务超时SLA。late在真实返回8个来源后暂停，再取消/放行，backend于1792677447.678432结束。三分支历史0、Q5状态未变，原始事件见F/native-edges/edges.json。
- 断线刷新经收据恢复，不重复生成/保存；该入口精确读取，不计LightRAG成功。真实TLS故障与来源失效页面负例本轮未重放，离线专项不替代真实负例。
- 外层71次模型调用/193407 tokens，native SDK start15次（含故障分支）。SDK内部传输重试数不可从本计数还原，未假设单价计算费用。同机同配置UX0性能对照未补全，不能宣称所有性能目标已完成。

## 失败与最早完整堆栈

1. 旧完整宿主被整目录相等拒绝：P/superset-failure-native.log；纯建图快照缺Q2索引：P/startup-missing-q2-server-all.log。803db64/55f930a业务修复已验证，不删附加文件。
2. 旧launcher递归：原文件serve-recursion-failure.py及failure-recursion-55f930a整轮保留；AST最小复现完整堆栈P/recursion-earliest-reproduced-traceback.txt。537dfb4后真实native成功，无递归。
3. 首轮proof-537dfb4：native和普通跨章通过，partial期间进程退出；server.log第394行起100秒faulthandler转储，末尾截断于networkx._clear_cache。未捕获原退出码，现存完整日志及earliest-runner-traceback.txt保留。停用可选定时转储后后续整轮未重现，**不能据此断言已证明退出根因**；未改NetworkX/SDK，不笼统归因密钥或模型。
4. nodump浏览器写技能目录EPERM；授权执行后继续。nodump2前两组页面初始化waitForFunction超时（含异常长墙钟间隔，原因未证实），Q5等通过；remaining补验两组通过。最终F从新进程完整重跑，普通/partial/Q5等通过，旧超时保留。
5. **最终F/practice失败**：模型无有效引用，quality后grounded_bundle.references抛CitationGroundingError，SSE没有done收据。最早完整宿主堆栈：F/practice/earliest-host-traceback.txt；browser.log保留“缺少最终收据”。实际537dfb4，调用链main._run_turn→TaskService→exercise_task_tutor.explain_exercise→practice_api.ai_parts:240→grounded_citations.references:97。save-gate.json只读验证failed/revision3、assistant_messages=0、exercise_help_rows=0，未保存不合格正文。这是练习引用门禁异常传播，不是LightRAG/凭据问题。nodump2历史同代码练习成功不能抵销最终失败。

原教材11章0题事实保留；3道测试题均标AI生成/测试用/未人工审核/非教材原题。最终提示→讲解→刷新未完成，不能用历史成功宣布全入口通过。下一步应单独处理练习无引用时的受控拒绝/收据，再基于修复提交重跑；不删除核验、不强插编号、不反复重试凑成功。

## 切换/回滚准备（本轮不执行正式切换）

8000/8012收尾时均未监听。P/start-text-approved-537dfb4.py已准备并通过语法检查，未正式启动；由既有启动器最小更新，固定537dfb4、独立依赖/缓存、local_llamaindex、Q5=0，移除LightRAG候选允许开关和AI测试题目录。仅读本机官方凭据与实际DB配置；无--start-approved不启动，8000占用即拒绝。

先处理练习失败或明确限定已验文本启用范围；启动前核对.env实际SQLite路径与两份现有库位置，按[既有备份与回滚规程](RESPONSE_UX_ENABLEMENT_RUNBOOK.md)使用SQLite backup API新建一致性备份，输出目录改P/backup-before-enable-verified。此目录本轮未创建，启动器要求两份备份存在；旧备份不能代替新备份，不复制WAL中的裸db冒充一致性备份。

```powershell
# 准备命令，本轮不执行：完成上述门槛及新备份后再采用。
& 'E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe' -B 'E:/项目/heart/.runtime/response-portable-20261022/start-text-approved-537dfb4.py' --start-approved
```

启动器登记P/approved-runtime.json的PID/create_time/release/revision/backend。正式启动后还需实际问答验证backend、保存和刷新，health200不算接通。回滚命令先核对登记进程身份，仅停本次树；不按Python名称批量杀进程：

```powershell
@'
import json,psutil,subprocess
from pathlib import Path
r=json.loads(Path(r'E:/项目/heart/.runtime/response-portable-20261022/approved-runtime.json').read_text(encoding='utf8'))
p=psutil.Process(r['pid'])
assert abs(p.create_time()-r['create_time'])<0.01
assert 'uvicorn' in p.cmdline() and 'main:app' in p.cmdline()
assert Path(p.cwd()).resolve()==Path(r['cwd']).resolve()
subprocess.run(['taskkill','/PID',str(p.pid),'/T'],check=True)
'@ | & 'E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe' -B -
```

保留全部学习DB/WAL、教材、候选和失败记录；代码回旧release沿用最新学习库，不用旧备份覆盖新学习数据。无已核实旧8000服务时只停本次，不启动身份不明版本。LightRAG正式切换另需发布门禁与完整入口验收；此方案不给8000设置LIGHTRAG_ALLOW_CANDIDATE=1，也不改staging/ready=false。
