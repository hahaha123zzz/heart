# LightRAG 公共接入最终隔离验收与正式启用方案

验收跨2026-10-22—23；交付2026-10-23。被测业务提交 **2ae1e5fd9618ea80a999a22cb30339a153e15d0c**；全部修改已推送。本文更新此前1b1b573的失败结论，不改写原始失败记录。[逐项证据](LIGHTRAG_INTEGRATION_FINAL_EVIDENCE.json)给出实际调用、计数、哈希和路径。

**当前结论：代码接线和独立宿主运行已验证，本轮最终完整10组全部通过；此前练习引用异常已修复。回答体验的已验范围可受控启用，LightRAG可在明确批准采用当前候选的前提下启用。正式8000尚未由本窗口切换，不能说线上已经生效，也不能把候选使用等同教材正式发布。staging/ready=false、pending原图保持原样。**

## 修复及调研结论

- `practice_api.ai_parts`在教学质检通过后还会调用EvidenceBundle.references。缺引用、越界编号或版本失效会抛CitationGroundingError，旧实现让异常传到main SSE，缺done收据；模型没有通过引用核验的正文原本也未保存。
- 2ae1e5f仅在练习公共边界捕获该明确异常，返回已有quality_rejected，新增可选reason=citation_grounding_failed，quality.passed=false、来源为空、step_advanced=false。`help_question`和`explain_exercise`已有拒绝分支，直接复用，不写辅导/对话记录，不需要修改main、TaskService或前端。未知RuntimeError仍传播，不吞掉故障；不删除核验、不补编号、不增加重生成循环。浏览器夹具现在先保存原始SSE再断言，拒绝也可复核。
- 离线反例覆盖hint/explain无编号/越界、过期版本及未知异常；真实HTTP应用（Mock模型输出，明确不算真实模型）已经返回done/quality_rejected，辅导和assistant保存均0。见P/practice-rejection-protocol/result.json和rejected.sse。
- 本机只读调研D:/deeptutor，HEAD 6cf793bd868ba5ecbe64722936d4be8fab5a01df；按agent-reach GitHub CLI只读核对上游固定a31d82624c27d75f4e771d4fcb78dce16470b383。其[终态校验](https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/runtime/agentic/loop.py#L280)在接收最终结果前验证，失败给循环反馈；本项目已有拒绝契约更适合练习入口，未迁入第二套循环。
- 上游[LightRAG存储/发布选择](https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/services/rag/pipelines/lightrag/storage.py#L227)只选择native published版本，不能拿它的存储就绪标记替代本项目教材来源、版本和视觉审核。未复制D盘未提交代码、没有换SDK或重建图谱。

## 同一稳定提交的独立部署与完整验收

证据根 **P**：`E:/项目/heart/.runtime/response-portable-20261022`；完整运行 **F**：`P/proof-2ae1e5f-final`。代码从git archive 2ae1e5f导出至P/code-proof-2ae1e5f/project/integration/discrete-math-tutor，没有把主工作树未提交修改打包。完整宿主教材、现有Q2索引、独立候选、223个sidecar、17个独立缓存文件、独立.venv及隔离DB沿用已验证迁移方案，完整祖先含803db64/55f930a及LightRAG完整基础链。

- 最终5384个跟踪宿主文件与归档逐项相同；candidate/input严格325个material核验，活动宿主409个material含84个只审计附加文件，均不变。宿主基础快照457个文件，普通宿主运行另外生成12个非入图crops缓存，所以新清单共469个文件；不把这些裁图当作新教材或图谱证据。
- 候选7个核心文件、policy及Q2 rag_index.sqlite3与此前登记相同；冻结索引未重建。清单P/resource-manifest-2ae1e5f.json，核对P/integrity-2ae1e5f.json。实际sidecar读取仍由803db64生产适配完成。
- 模型官方https://api.deepseek.com、deepseek-flash；凭据只读ds.env并注入进程，不入Git/日志，不再发旧网关。依赖固定LightRAG1.5.7/openai3.36.1/CPU onnxruntime1.31.0，独立缓存不下载模型。
- 最终完整进程审计禁止旧worktree/旧候选读取，environment-final.json为forbidden_old_reads=[]、uri_test_hook=false。未替换来源校验或改写冻结URI。
- 联合164项通过（120.252秒，regression-2ae1e5f.log）；另补引用去重/版本/真实PDF专项32项通过（28.514秒，citation-negative-2ae1e5f.log，部分与联合覆盖重叠，不能相加宣称196项独立用例）。

完整真实命令：

```powershell
& 'E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe' -B 'E:/项目/heart/.runtime/response-portable-20261022/run_final.py'
```

该运行版本和10组结果固定在F/runs.json，exit0；不能覆盖重跑，复现需新输出目录。先native后普通/partial/Q5/PDF/media/practice/ask/native-edges/recovery，一次完整运行，不拼接Q5。native20.652秒、有效原文4条、实际官方LLM调用非零。首字按首次正文DOM绘制，结构化输出None，不假装模型首字；外层模型与原生查询分开统计。

| 案例 | 实际读取 | 首字/总耗时（秒） | 外层模型/原生查询 | 引用数；章节 |
|---|---|---|---|---|
| cross | lightrag | 61.047 / 66.059 | 7 / 2 | 5；[1, 2] |
| single | lightrag | 26.432 / 34.905 | 4 / 1 | 5；[2] |
| q5-plan | 结构化输出，无检索 | None / 2.374 | 0 / 0 | 0；[] |
| q5-confirm | q2_exact | 4.351 / 7.894 | 4 / 0 | 2；[1] |
| q5-cross | lightrag | 25.853 / 29.48 | 7 / 2 | 4；[1, 2] |
| q5-return | q2_exact | 1.767 / 10.397 | 6 / 0 | 3；[1] |
| q5-next | q2_exact | 6.797 / 12.15 | 5 / 0 | 1；[1] |
| pdf-explain | 选区原文 | 7.912 / 12.742 | 5 / 0 | 1；[1] |
| pdf-followup | 选区原文 | 5.319 / 9.334 | 5 / 0 | 1；[1] |
| media-tool | q2_exact | 15.761 / 24.78 | 4 / 0 | 2；[5] |
| ask-pause | 结构化输出，无检索 | None / 1.685 | 1 / 0 | 0；[] |
| ask-resume | lightrag | 23.743 / 30.086 | 4 / 1 | 2；[1] |
| partial | lightrag | 29.444 / 34.28 | 5 / 3 | 3；[1] |

- 原跨章题及Q5插问均covered、无fallback，双方最终引用对应原文逐字出现在实际模型工具输入。Q5插问6个关联候选有原文链接、evidence_eligible=false，图谱关系没有自动成为先修、考试重点或掌握依据。
- 缺一方真实partial：3次native、1次补查后明确“火星玄武岩晶体结构”缺证，只发布已有第一章证据，不编造另一方。
- Q5单session单次完整：计划→确认讲解→成功跨章插问→返回原目标→下一部分→刷新；插问前后整个学习状态一致，返回同目标，下一部分更换目标且未标掌握。讲解/返回/下一部分q2_exact是保留的精确读取，不计LightRAG查询成功。
- PDF两轮选区追问使用原选区及像素、刷新一致；不是LightRAG一般查询。ask_user同task恢复，revision增长，续答为LightRAG。原生取消/超时/晚到、断线恢复全部通过，实际结束时间见JSON/native-events，不靠UI停止判底层已停；取消/故障的学习状态与历史无误写。
- 图5-2生成和质检使用相同d713f3bae36f099e03fefaea8533fa84c0afae74e3b8891ca164087db43e0f75像素，官方请求成功。页面实际解码、点击返回第5章第3节、刷新同图，额外生成0，仍标pending。证据F/media/ui-pixels.json与image-visible.png。
- AI测试练习hint首字2.906/总6.065秒，explain首字3.578/总7.876秒，最终均answered、有有效引用；草稿/辅导刷新、AI标签与正式评分409均通过，正式提交0。原教材仍11章0题，3道AI测试题不冒充原题，正式启动档不加载测试题。
- 外层75次调用、212798 tokens；native SDK start16次（含取消/超时/晚到），不是单次回答成本。未假设单价计算费用。普通跨章66.059秒，无包装宿主另一次81.954秒，延迟仍偏高；没有同配置性能对照，不宣称UX0全部优化完成。

## 补齐TLS、旧来源及无测试包装证明

1. **本机真实TLS故障注入通过**，P/proof-2ae1e5f-tls-v2：原生LightRAG查询照常运行，仅native AsyncCompletions的实际连接使用本机不受信任自签名TLS服务及虚拟key，不发送真实官方key。3次工具检索×每次适配器最多3次=9次握手，实际HTTP正文0，最终rejected，无fallback、assistant历史0、Q5状态不变。客户端APIConnectionError→ConnectError证书不受信任，服务端SSL错误及实际native清理结束均留证。这证明该类证书故障有界，不代表所有代理/外部TLS故障。
2. 首次TLS夹具误把总SDK上限写成3而非按两层预算，断言失败，完整P/proof-2ae1e5f-tls保留。读config.py `_ADAPTER_MAX_ATTEMPTS=3`并分清工具预算后，修正仅测试断言，在新目录完整复跑通过；不改业务重试来配合脚本、不把失败改写成成功。
3. **旧来源页面负例通过**：只在浏览器内存将保存引用版本变为旧值，不改教材；实际citation-state返回stale，点击被阻止、PDF焦点不变、不升级版本、生成0。F/media/stale-source.json/png。真实PDF变更及重复原文范围去重另由上述32项测试验证。
4. **完整宿主无测试包装通过**：P/start-isolated-lightrag.py只有环境配置及正常import main/uvicorn，无SDK/query/来源替换，无测试路由。独立新DB以8012运行原跨章问题，covered、LightRAG、无回退、双方5条引用、页面/历史刷新成功。P/standalone-browser-2ae1e5f/verified.json、cross.sse、runtime.json。此正常档允许SDK正常缓存；不将它单独当“未命中缓存的真实native模型”证明，后者已在最终整套禁关键词缓存运行中验证。

实际调用仍为Q3/Q5共用`agents.course_search.shared_search→CoverageNavigator/ContextualRetrieveCourseTool→LightRagBackend`，精确目标保留Q2 read_target。未重写检索、未另建学习路径，原图/流式/上标/排版实现未重复开发。

## 运行切换与数据保护

发现已有P/approved-runtime.json记录537dfb4/local_llamaindex/PID80736，以及旧备份receipt；这是既有登记，非本轮隔离验收启动的服务，本窗口只读保留，不据此声称LightRAG正式运行。收尾检查8000和8012均未监听，不接管或停止身份不明服务。为避免覆盖登记，新启动器、日志、PID和备份均使用2ae1e5f独立名称。

正式DB在537dfb4与本轮2ae1e5f初始快照之间发生过变化；本轮2ae1e5f验收前后hash一致，见formal-db-observation-history.json，不谎称跨窗口整个时段文件始终未变。新建只读SQLite一致性备份P/backup-before-lightrag-2ae1e5f，两库PRAGMA integrity_check=ok，所有表计数与源相同（43/49表），备份期间源哈希不变；未恢复旧备份覆盖现有学习数据。

现有`LightRagBackend.validate`的启用门禁是显式allow_candidate及完整候选/来源哈希；`course_release.ready`另表示教材发布状态。不能把二者混为一个开关。因此技术上可明确批准使用当前候选检索，同时保留staging/pending；这仍不等于发布了审核完成的正式教材。未经这项明确采用，不自动给8000加候选开关。

**准备好但未执行**：P/start-lightrag-approved-2ae1e5f.py，固定setup-2ae1e5f.json和业务版本、独立依赖/缓存，使用现有正式DB；Q3=lightrag、Q5=1、LLM_MOCK=0，仅在显式双参数下允许当前候选。移除AI测试题输入，不改.env或ready、不切换到未知索引，8000占用即拒绝。执行前若又有学习写入，需重新生成新命名一致性备份并更新该运行档，不能用旧快照代替。

```powershell
# 本轮未执行；须明确批准8000采用本候选后才能运行。
& 'E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe' -B 'E:/项目/heart/.runtime/response-portable-20261022/start-lightrag-approved-2ae1e5f.py' --start-approved --activate-reviewed-candidate
```

启动器生成独立approved-lightrag-2ae1e5f-runtime.json，记录PID/启动时间/配置的release与backend/候选启用模式。启动后还需对8000实际问答及刷新检查backend/source_binding；health200不等于切换验收通过。本轮不执行正式启动，因为用户此前明确“本轮不自动修改正式服务、正式数据库或staging/ready=false”。

回滚：先只停登记的新服务，不能按Python进程名或旧PID批量杀进程；保留全部DB/WAL和候选。以下命令也未执行：

```powershell
@'
import json,psutil,subprocess
from pathlib import Path
r=json.loads(Path(r'E:/项目/heart/.runtime/response-portable-20261022/approved-lightrag-2ae1e5f-runtime.json').read_text(encoding='utf8'))
p=psutil.Process(r['pid'])
assert abs(p.create_time()-r['create_time'])<0.01
assert 'uvicorn' in p.cmdline() and 'main:app' in p.cmdline()
assert Path(p.cwd()).resolve()==Path(r['cwd']).resolve()
subprocess.run(['taskkill','/PID',str(p.pid),'/T'],check=True)
'@ | & 'E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe' -B -

# 如需回到已核实旧运行档：固定537dfb4/local_llamaindex，沿用最新学习库，绝不还原旧DB。
& 'E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe' -B 'E:/项目/heart/.runtime/response-portable-20261022/rollback-text-537dfb4.py' --start-approved
```

## 仍未宣称完成的范围

整套UX性能优化、全部格式边界、全书原图人工审核和教材正式发布未因此完成。此前100秒faulthandler转储时进程退出仍无原退出码/根因定论；现存日志保留，停止该可选观测后整套及正常宿主未再重现，不把它改写成SDK/模型根因。没有凭据阻塞、没有现存LightRAG原生检索失败需要换模型或重建全书；下一步为明确采用上述候选运行档后，执行正式启用与8000现场验收。
