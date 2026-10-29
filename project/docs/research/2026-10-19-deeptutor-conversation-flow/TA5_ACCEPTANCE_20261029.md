# TA5联合验收与发布门禁

日期：2026-10-29。基线：TA4 `c701670db775e4b12dde2ca761b126b964bd5a16`。

**结论：本轮完成联合验收工具和已定位问题的修复交付，TA5整阶段仍未通过，release_ready=false。工作分支推送不代表合入main或正式启用。**

## 本轮修复

1. “请复习……不出题”被当成practice，最终强制检查题而拒绝回答。先以实际失败问句和回归复现，补齐单字“不”、不必、无需、不得的否定识别；“请复习”识别为review。高提问偏好也不能覆盖明确的“不出题”。
2. 教材回顾在没有当前原文时被当成可直接回答的混合知识请求。复用原LoopRequest.requires_evidence与answer_ready约束，使其先取得实际原文；已有证据不重复检索，不新增Planner或AgentLoop。
3. 模型输出`<｜｜DSML｜｜ calls>`等变体时，旧检查只认识单个竖线，可能把内部协议保存为正文。扩展发布检查；没有证据时只允许一次实际结构化取证修复，有证据时只允许一次纯正文修订。仍失败则拒绝发布；不把模型正文中的协议解析执行。
4. 超时测试原先用30毫秒真实时钟，繁忙时可能在任务登记前到期，导致测试期望的失败收据不存在。改成在执行回调内明确让deadline过期；临时库建表前登记Q5模型，保持实际init_db的schema。未放宽生产时限或修改生产评分规则。

失败证据保留在应用`.runtime/ta5/`：`no-quiz-before.log`、`dsml-before.log`、`modes-live-before.json`、`modes-before-protocol-fix.json`、`navigation-live.json`及各轮回归日志。不会把失败文件改写成通过。

## 同一代码身份与自动回归

新增`scripts/check_ta5_acceptance.py`，明确HOST/NATIVE测试清单与TE01—TE18要求。运行时记录base_commit、源码摘要、UTC时间、实际模块/测试数和失败标识；执行中源码变化则拒绝作为稳定验收。单测全绿、旧版本证据、缺失或变更的artifact均不能自动通过发布门禁。

最终报告及逐项缺口以同目录`TA5_ACCEPTANCE_20261029.json`为准。以下命令在应用目录执行：

最终冻结代码：宿主209项、原生105项通过，分别见`.runtime/ta5/host-evidence.json/log`和`native-evidence.json/log`，源码摘要一致。模块存在共享/导入的测试夹具，不相加为314个独立教学案例。发布矩阵仍有缺口，因此release_ready=false。

```powershell
.venv-runtime/Scripts/python.exe -B scripts/check_ta5_acceptance.py --layer host --output .runtime/ta5/host-evidence.json
.venv-deeptutor/Scripts/python.exe -B scripts/check_ta5_acceptance.py --layer native --output .runtime/ta5/native-evidence.json
.venv-runtime/Scripts/python.exe -B scripts/check_ta5_acceptance.py --layer summary --reports .runtime/ta5/host-evidence.json .runtime/ta5/native-evidence.json --evidence .runtime/ta5/evidence.json --output .runtime/ta5/summary.json
```

summary退出码0表示完整满足清单，1表示执行错误，2表示发布证据不齐。**退出码2不是测试全绿或正式发布成功。** 两套Python环境沿用既有依赖，不安装新模型/库。

## 真实运行边界

- 隔离宿主8043运行实际main.app；8044用`integrations/deeptutor/worker.py`启动固定vendor的完整实际App，未替换AgentLoop、能力或模型。8045是仅用于核对实际SQLite的只读探针，不替换worker响应。
- 全新隔离host/course SQLite与原生home，教师批准及原题是受控验收输入；初始证据时间注入三天前构造到期。提示使用TA3实际模型生成后已保存的内容，不将读取缓存称作本轮新模型生成。
- 原生实际模型回合返回engine=agent_loop，19.844秒、2次模型调用，产生content/result/done。但它调用inspect_setup并在正文提到缺少embedding配置；这是独立原生home的配置/工具上下文缺口，不能算正式教材检索成功，更不能证明现有页面已接管到原生。
- 普通Q3最后冻结版本真实对照：直接讲解3.266秒/2引用，引导5.437秒/1引用，知识关系回顾7.828秒/4引用；回顾不出题、不增加正式掌握。记录于`modes-last.log`和`modes-live.json`。这些单次功能耗时不是旧版本提速对照，也不证明无缓存或无负载差异。
- 此前页面单问题ask_user/文字选区/连续追问16项通过，run `mvtl0na7`，`live/mvtl0na7-entrypoints-browser.json`。最后冻结版本另跑`mvtllcd0`时，模型返回两个问题，后端questions内有选项、顶层options为空；页面只读取顶层options，未显示多问题选项，测试等待按钮失败。这不是仅修改脚本就能消除的产品接线缺口，保留为未通过。未用鼠标拖选PDF，不宣称原始划选手势通过。
- 完整worker的原生复习页面曾有20项通过记录；后续更多历史/路径的最终复验，在完成请求立即重放处失败，同一请求随后HTTP重放200。第一次失败响应细节未完整采集，原因未核实，不把整轮标记稳定通过。后续应记录响应状态与耗时并排查历史卡片恢复/授权回查压力，不能靠重跑挑选成功记录。

## TE01—TE18对账

| 项目 | 本轮证据与缺口 |
| --- | --- |
| TE01 | 直接/引导真实模式不同；教学内容仍待人工抽查。 |
| TE02 | 普通解释无待答/正式掌握；查页/目录完整同版本对照仍需补齐。 |
| TE03 | 三级提示、完整解释及恢复自动回归；本轮完整实际页面三级流程未重新计证。 |
| TE04 | 文字选区换例子/求助通过；视觉区域及教材例子来源人工抽查未全完成。 |
| TE05 | 实际复习作答区分原始独立证据与提示后辅助证据；不把辅助答对算独立掌握。 |
| TE06 | 有权威推进/不加掌握的自动回归；最后实际章节流程仍因协议正文拒绝发布，失败后返回navigation_required。见navigation-after.log及navigation-live.json，未标通过。 |
| TE07 | 有原话来源、撤销及epoch回归；真实自然语言更正与内容人工抽查未全完成。 |
| TE08 | 临时/会话/长期偏好与隔离自动回归；完整实际页面清除矩阵待补。 |
| TE09 | 原生待答/插问状态自动回归；实际普通聊天与原生题卡统一接续仍依赖NT3。 |
| TE10 | 重试/并发/取消自动回归及实际重复操作部分通过；完成重放有上述保留失败。 |
| TE11 | 原生题卡、分步卡、刷新与窄屏已有实际证据；三类卡片完整键盘矩阵未全完成。 |
| TE12 | 到期/延后/评分/完成实际执行；最终立即重放不稳定，不能整项通过。 |
| TE13 | 换版、缺像素、答案修订/撤销自动回归；完整实际视觉/审核矩阵待补。 |
| TE14 | 宿主删除/epoch授权阻断已测；跨库删除传播与竞争仍依赖NT8。 |
| TE15 | 自评confidence与评分证据、未校准概率自动回归；真实高信心话语全入口待补。 |
| TE16 | 关系回顾真实返回4引用并区分教学分析；重点依据内容待人工抽查。 |
| TE17 | Q3、选区、单问题ask_user及原生题卡分链可运行；多问题ask_user选项页面未接；正式/api/chat仍是旧Q3，统一原生入口未实现，阻止发布。 |
| TE18 | 无新增必经Planner/LLM的自动回归；实际阶段计时已收集，严格同配置开关/版本性能对照未完成。 |

单元/接口、实际模型、浏览器和人工审核是不同证据层；矩阵中“自动回归通过”不等于整项通过。没有实际教师批准或长期学习效果验证。

## 发布与回退

本轮推送验收分支及必要修复，保留正式开关默认状态。不迁移/覆盖正式数据库，不重建正式索引，不改教材ready，不把临时服务当正式部署。公共原生入口迁入、NT8删除传播、上述不稳定重放和剩余人工/性能证据完成后，再执行TA5发布复验。回退应关闭原生入口并保留新增SQLite/原生证据，不用旧库覆盖新成绩。

当前优先顺序：先对章节场景采集提供方原始tool_calls/finish_reason与宿主接收结果，定位为什么仍输出协议正文；对完成重放采集首次失败响应和历史恢复并发度；再接NT3公共入口与NT8删除契约，完成TE矩阵和同配置性能对照。不得仅增加重试或绕开来源门禁来“通过”。

多问题ask_user应按既有questions契约接实际表单与答复映射，保留任务/问题身份、单选/多选、自由文本与刷新恢复；不能丢弃额外问题或把第一组强行投影为单组选择来冒充通过。

## 保留的执行失败

- 初版测试清单误纳入离散数学“关系闭包”，与教材知识关系不同；已修正清单，保留`.runtime/ta5-host.log`，未通过修改数学业务测试消除失败。
- 多轮回归期间修复了实际问题，工具按设计拒绝把源码变化中的运行标成稳定通过。保留native-final/native-delivery/native-accepted/native-ready-final等日志，不拼接成最终同次全绿。
- 浏览器复用脚本最初引用旧坐标fixture文件名导致ENOENT；修正为当前教材坐标fixture后重跑，未冒充产品异常或成功。
- 一次原生新路径准备复用了全局题号，被原生存储正确拒绝；后续使用全局唯一题号，没有覆盖旧成绩。
- 自动审批曾因额度限制未执行重启，恢复后重新核对端口/进程并执行；没有绕过审批，也未停止其他窗口进程。
