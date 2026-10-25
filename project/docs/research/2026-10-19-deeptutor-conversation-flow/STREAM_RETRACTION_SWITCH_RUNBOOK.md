# 流式撤回交付、复验与切换手册

日期：2026-10-24；本轮仅隔离交付，未切换正式服务。

## 1. 集成窗口采用方式

分支`codex/stream-retraction`，基线`9d5f5f6a49c7fda01932c63bef22d84e9d003641`；按本分支顺序采用基线之后的提交，不复制其他窗口工作树。运行功能固定`a693dfb3934a985720cb3d5b265a7b86d5d5025a`；`fb4f3ae`只增加断线测试，后续文档不改变功能。稳定交付SHA以`git rev-parse codex/stream-retraction`为准，完整提交列表见执行记录及git log。

最初核心`42407ed`之后的修复必须一起采用，特别是`f50ac6c`澄清工具、`1182985`执行器watchdog、`f8c9beb`取消兼容、`4cb2064`空答一次恢复、`7a44ef6`旧入口中断收据和`a693dfb`版本快照。不要只挑核心提交上线。

共享文件包括agent_loop/service、TaskService、质量和检索边界、frontend/app.js、chat-transport.js、practice.js。当前main已继续前进，集成窗口须对照最新Q5/图像返回位置/回答体验改动逐项解决冲突；不要整文件覆盖。main.py、reader和Q5内部实现无本窗口改动。没有数据库迁移、新业务表或新依赖。

## 2. 接口契约

- 原answer_id/task_id/task_revision/round_id/seq继续有效；可选`role=progress|answer`，探索增量不进入正文。
- `answer_replace`带`target_round_id`/reason，只清对应未发布答案；begin不 blanket clear。未知字段旧消费方仍可读最终快照，但必须同版部署前端才能获得完整体验。
- 原`answer`/`done`最终快照权威；中断结果`answer_status=answer_interrupted`，截断`incomplete_answer`，超时`active_timeout`，首轮模型不可用`model_unavailable`。`unpublished_draft`仅转义纯文本展示，不激活引用/图片，不进正式对话历史和学习状态。
- 取消继续兼容`task_conflict`，识别额外`task_state=cancelled`；DELETE既有响应`task_cancelled`不变。取消/删除后收据可以410，不能绕过保护复活草稿。
- `execution_metrics`仅包含阶段、时间、允许的后端诊断和可得usage。保存前收据快照与最终SSE保存完成时间不同，不能据此重复相加成本。
- 同轮预算默认120秒，消息显式含比较/联系/区别/分别/跨章180秒；暂停序列化`execution_policy.active_limit_seconds`，不持久化monotonic时钟。人工等待不累计，恢复新建活动预算。
- `aquery_data`及现有Q2 SourceRef/引用分配保持原调用。点名图actual_backend可能为`q2_figure`，不是LightRAG fallback；检索失败不能宣称切换成功。

## 3. 本机可复验的隔离环境

代码/数据库/候选原件：`C:/Users/free/AppData/Local/Temp/sr24`；固定哈希和运行身份见manifest.json、final-integrity.json及各runtime.json。小体积证据镜像：`E:/项目/heart/.runtime/stream-retraction-20261023/final-evidence`；原运行数据仍保留。临时路径不是长期发布目录，集成交付时需把代码、模型缓存、冻结教材、候选和可复验脚本安置在持久release路径并重新核哈希。

模型读取本机既有`E:/项目/heart/ds.env`；没有把密钥写入交付物。Python复用`E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe`；deepseek-flash；LightRAG1.5.7；CPU embedding/rerank，各2线程。无需安装或升级依赖。

以下命令仅用于本机已保留的隔离布局。先确认对应18986/18987/18988端口空闲，不占用其他窗口端口；不要同时起两套全量RAG宿主。

```powershell
$py='E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe'
$root='C:/Users/free/AppData/Local/Temp/sr24'
# 普通真实模型宿主：独立host.db/course.db，18986
& $py "$root/serve.py" modified
# 故障专用宿主：18987，含显式测试钩子，绝不作为正式服务启动器
& $py "$root/fault-serve.py" fault
# AI测试练习宿主：18988，明确未审核，禁止正式评分
& $py "$root/practice-serve.py" practice
```

上述三条按需要单独启动并记录PID/cwd。serve.py已有端口占用检查；fault-serve.py的GET `/_sr/probes`须显示test_hooks与请求scenario一致，测试脚本会在POST前检查。运行器及注入源码已镜像归档并列SHA256；这不是正式业务路由。

浏览器复验使用安装的Playwright和可见Edge（runner需要写自己的临时脚本权限）：

```powershell
$env:SR_URL='http://127.0.0.1:18986'
$env:SR_OUTPUT='C:/Users/free/AppData/Local/Temp/sr24/new-review-01'
$env:SR_CASES='[["concept","请解释教材里的自变量，不要出题。"],["figure14","给我解释一下图1-4，我有点看不懂"]]'
node C:/Users/free/.agents/skills/playwright/run.js E:/项目/heart-worktrees/stream-retraction/project/integration/discrete-math-tutor/tests/browser/stream-retraction.cjs
# 指向18987才能注入：SR_SCENARIO=connect|partial|length|slow|repair|stale|asset-label|ask
# ask可设置SR_REUSE_SESSION=1，输入两步；正常案例必须清除SR_SCENARIO。
# SR_DROP_FINAL=1模拟丢失最终done事件，只应POST一次，随后GET原收据。
```

每次使用新输出目录，不覆盖旧尝试。SR_CASES未列为强断言的场景仍需核对report、SSE、收据、截图及模型probes；脚本退出0不代表矩阵全部通过。故障行中的SDK注入和真实模型要分别标明。

回归命令（独立进程/正确课程，测试使用自己的临时库）：

```powershell
Set-Location E:/项目/heart-worktrees/stream-retraction/project/integration/discrete-math-tutor
$env:TUTOR_COURSE='experimental-psychology-3'
& $py -m unittest tests.test_stream_retraction tests.test_answer_stream tests.test_answer_media tests.test_q3_agent_loop -q
& $py -m unittest tests.test_q5_learning tests.test_task_service_context -q
$env:TUTOR_COURSE='discrete-math'
& $py -m unittest tests.test_task_context tests.test_quality_guard tests.test_quality_parallel -q
node tests/chat-transport.cjs
node --check frontend/app.js
node --check frontend/practice.js
```

## 4. 正式切换前检查与回退

当前不满足无条件切换：冷启动概念120秒超时，旧收据缺快照问题虽已修复并在最终慢工具/选区流中复验，但最终新进程冷启动整轮尚需重测；R03真实延迟工具、R10真人多标签页仍有覆盖缺口；R08已实等121.010秒恢复成功，R12真实零证据问题已明确拒绝。旧澄清单测已有基线失败。不能删质量门禁来换绿灯。

集成窗口先在最新稳定宿主导出统一release、核教材515文件及索引7个核心哈希、确认模型配置与staging状态不变，再使用新隔离端口/数据库跑完整矩阵。普通成功案例至少同时检查：actual_backend/fallback、来源版本、像素标记、正文无工具导致全清、收据200且刷新一致；失败不进入正式历史/推进。health200只能证明服务可达。

具体切换动作仅在取得对应release的明确授权后执行：

1. 登记当前8000监听PID、cwd、启动时间、代码/static哈希及原启动配置引用；保留原release、冻结索引和模型缓存。
2. 新release前后端一起发布；配置引用现有合法教材/候选和模型配置。正式学生库继续按宿主既有授权方式使用，不用隔离测试库覆盖，不复制回测试数据。
3. 受控停止登记的旧实例，在原端口用新release既有启动方式启动；不自动改教材发布状态，不重建索引。
4. 用专门测试账户执行原图、概念、收据刷新、取消与失败案例，复核进程/static身份及实际后台；原题在正式服务验收前不得称生效。
5. 若身份、像素/来源、收据或门禁不符：停止本次新实例，按登记配置恢复原release；保留新实例日志。没有业务表迁移，回退不覆盖当前学生数据。旧索引始终保留。

同步IO不能硬杀；超时只停止后续调用和提交，已发起网络请求可能仍产生费用。保留partial意味着未保存诊断仍可能含模型错误，页面已去掉可点击教材证据语义。正式费用未返回，不能承诺预算金额。
