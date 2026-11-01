# 输入理解层首批执行记录

日期：2026-10-30。**首批实现已形成可审查代码；完整计划未完成，默认关闭，未合入 main、未部署 8000。**

基线、端口、数据库与历史失败见 [INPUT_UNDERSTANDING_BASELINE.md](INPUT_UNDERSTANDING_BASELINE.md)。工作树为 `E:\项目\heart\.worktrees\input-understanding-v1`，分支 `codex/input-understanding-v1`，父提交 `816e78a`。

代码提交：`597b5c7`（协议与理解核心）→ `4e18c08`（公共接线、教学/页面修复与集成测试）→ `fba8d41`（否定切换话题不丢待答题）。文档及可复验脚本单独提交；工作区内的运行证据不进入 Git。

## 已实现行为

1. `InputEnvelope / ContextHeader / ObjectReference / TaskFrame / ScopedDirective / GroundedTurn` 使用严格 Pydantic 协议。保存原话和规范化位置；最多四个任务；校验依赖、引用、当前题目身份、长期确认及原话依据。禁止模型产生 approved 字段，拒绝同范围互斥指令被静默覆盖。
2. TaskService 在认领任务后、Q5/聊天分流前只生成一次理解；收据重放及重复认领在此前返回。理解前后核查 guard，取消后不执行后续回答或保存。当前任务的 task/revision/epoch 回写到快照，仍由原 guard/CAS 决定能否发布。
3. “先解释 X，再回原题”有两个 frame；关闭原 resume 快捷截断，先运行原 AgentLoop 讲解，成功后附回服务端保存的同一道题。失败不标完成，否定恢复不触发回题。
4. 阅读位置与活动待答题分开：有效 pending 优先保持教学目标，reader_location 作为阅读/检索背景；显式换目标和选区仍沿原入口处理。来源失效返回 reference_stale，不恢复失效题。
5. “我不选 B”“为什么 B 不对”“B 或 C”在辅助评估前确定性拦截，不依赖评估模型阻止误提交。选项解析直接调用既有 DeepTutor pending 工具，不复制第三套。
6. 本轮 no_questions 不删除原 pending，也不把本轮限制永久写成后续禁考。原 Q5 计划中只讲解不测验的会话设置保持原职责。
7. 长期偏好只生成待确认候选；沿现有前端确认卡展示，默认长期范围，刷新恢复；确认前不写画像，确认后调用原 API。当前实现缓存最近一个显式候选，不是新的画像数据库。
8. ask_user 保存原要求、已解析 frame 和 loop_state；恢复另存 reply_envelope，保留实际答复“第二个”，不把拼接的补充说明误存成学生原话。
9. 复杂解析端口最多一次 JSON 解析、一次有界格式修复；伪造 ID、原话依据或写权限立即拒绝。复杂解析已经调用模型时不再串行调用分类器；正式标签未配置时 annotations 为空。

首批不新增业务表、索引、AgentLoop 或模型依赖。理解快照随现有任务 TTL/删除/epoch 清理；没有暗中延长辅助题生命周期。

## 验证与失败

证据根目录：`E:\项目\heart\.runtime\input-understanding-implementation-20261030`。计数均指对应运行，不累加重复执行宣称覆盖率。

| 验证 | 结果 / 证据 |
| --- | --- |
| 最新理解/TaskService/教学/Q5/上下文相关回归 | `final3-regression.log`：187 项通过，74.045 秒 |
| 最新 Q3 AgentLoop 回归 | `q3-agent-current.log`：28 项通过；与上一行是分别运行 |
| 理解移到认领后、取消保护的定向回归 | `claimed-understanding-regression.log`：36 项通过；与其他行存在重叠，不累加为新覆盖 |
| 否定切换话题最终回归 | `negated-switch-regression.log`：37 项通过，覆盖输入规则、接线及原辅助教学；与其他行存在重叠 |
| 原生评估命令和授权 | 正确工作树导入后 `native-regression-host-tests.log`：20 项通过，426.146 秒；受控题目/教师夹具，不是模型命题验收 |
| 前端 | `node --check frontend/app.js`、`node --test tests/interaction-style.cjs` 通过；覆盖候选确认、冷却、刷新、学生/会话隔离 |
| 实际 HTTP | `active-final/http-results.json`：16 轮；含 ask_user 等待与 Q5 草稿这两轮 expected awaiting_clarification，其他 answered；逐条保存 SSE 和前后任务/绑定快照 |
| 真实浏览器 | `active-final/browser-results.json`、`browser-same-reader-results.json`：7 轮，跨章与同小节回题保持 question_id，刷新恢复，无 pageerror |
| 长期偏好页面 | `active-final/preference-browser.json`：确认前无 answer_length，默认长期，刷新后仍有确认卡；确认后 answer_length=1，无页面错误 |

上述 16 轮规则理解各自 model_calls=0。这仅表示没有额外的理解模型调用，不表示回答/检索/辅助命题不调用模型。复合请求真实 HTTP 2.840 秒；页面跨章/同小节分别 3.447/4.035 秒，都是单样本，不是 P95。

`active-release-check/http-check.log`、`http/ca545c761ecb.json`：最后作用域/协议修正后 16 轮真实 HTTP 的自动状态检查通过；`verified-results.json` 核对 7 轮浏览器、两个刷新、同一道 pending 及长期偏好确认，全部通过。仍只覆盖该批场景。

随后把理解移到任务认领后，再重启形成 `active-commit-smoke/http-smoke.json`：三轮实际出题→解释后回原题→恢复，耗时 10.609/2.688/0.267 秒；全部 answered，保存的任务身份与返回一致，三轮 question_id 相同。与此前两套浏览器证据不是同一次运行。

预热规则解析另测 30 条不同输入，`rule-timings.json`：P95 0.0876ms、最大 0.1201ms、额外理解模型调用 0。这里只量规则和协议校验，不含数据库、上下文读取、对象版本复核、检索或回答；不能用它宣称 IU2 全链绑定耗时或复杂解析 P95 达标。

### 保留失败

- 模型余额 402、启动前连接拒绝、用系统 Python 缺 fastembed 均保留，环境修正后新建运行；不覆盖为成功。
- 原生首次 20 项中 13 错误：导入了原工作区 vendor；另一次 PYTHONPATH 指向 vendor 后 tests 包被上游遮挡，两个导入错误。最后显式选择工作树 vendor 与宿主 tests 后 20 项通过，没有削弱固定源码检查。
- 复杂请求“先解释自变量，再比较自变量与因变量，最后总结，不要出题”连续三次：理解各用一次模型并给出三个 frame；回答阶段把 retrieve_course 输出成 DSML 正文，没有真实工具调用，导致 model_unavailable/quality_rejected。原始输出分别在 `active-final/semantic-http-failed-1.json`、`semantic-http-failed-2.json`、`semantic-http-reader.json`。**不计复杂请求整轮通过；复杂解析保持默认关闭。**
- 早期回归中的 `不给完整解释` 否定错误已在原工作区复现并修正；旧 RecentRepository 测试替身缺 navigation_recent，按已有接口补齐后通过。失败日志未删除。

## 阶段状态和剩余任务

| 阶段 | 当前状态 | 尚需完成 |
| --- | --- | --- |
| IU0 | 基线与独立宿主复现完成，验收数据部分完成 | 100 条独立标注和 20 组多轮场景尚未形成 |
| IU1 | 核心严格协议、旧记录兼容、分类只读端口已实现 | 独立 ExecutionDecision、完整版本上下文投影及所有动作适配尚未齐全 |
| IU2 | 已校验对象、pending、阅读/活动分离已实现 | 持久示例/实验/assistant_claim 引入记录、通用指代解析与结构化候选澄清未实现 |
| IU3 | 本批复合回题、否定提交、偏好 scope 修复已运行 | 未覆盖所有省略/条件/混合写入变体；不声称通用自然语言命令完备 |
| IU4 | 解析与分类接口、调用上限已实现 | 真实复杂整轮失败；正式多维标签未确定，标签质量未验收 |
| IU5 | Q3/旧路由/Q5/ask_user/偏好已接线并有真实验证 | 新输入层选区/原生/练习页面矩阵；复杂 frame 部分完成后的跨回合命令幂等；Q5 活动统一身份及完整切换适配 |
| IU6 | 专项、相关回归、部分真实 HTTP/浏览器通过 | E01—E16 全矩阵、100/20 标注规模、30 样本 P95、10 组受控性能对照未完成 |
| IU7 | off/shadow/active 开关就绪 | 全场景发布、旧判断收敛、正式回退演练未执行；没有更改正式服务 |

独立会话“刚才那个例子”目前由原回答链询问用户，未泄露其他会话内容，但不是本计划要求的结构化 reference clarification，不能标为 IU2/E07 完成。

`final_summary` 记录的是发布/执行状态，不是模型讲解内容的独立语义评分器；普通只读 frame answered 不代表每一个教学子要求已被人工验收。长期偏好确认沿用原 PUT 接口，值覆盖可重复，但该接口还没有本计划专用的命令收据；不能声称重复确认审计完全去重。

## 配置与复验

正式缺省：

```dotenv
INPUT_UNDERSTANDING_MODE=off
INPUT_UNDERSTANDING_SEMANTIC_ENABLED=0
```

`off` 沿原入口；`shadow` 保存理解但不改变业务动作；`active` 仅适合已验收场景的隔离测试。复杂解析单独为 0，分类器未配置不加载 BGE 或编造标签。不要直接把本机测试开关写进正式 .env。

在已启动的**隔离**服务上使用仓库内脚本，生成新测试账号和会话，结果写新文件；SQL 仅只读查询该隔离库：

```powershell
& .\.venv-runtime\Scripts\python.exe -B scripts/check_input_understanding.py `
  --base-url http://127.0.0.1:8147 `
  --database E:/项目/heart/.runtime/input-understanding-implementation-20261030/active-release-check/deep-course.sqlite3 `
  --report-dir E:/项目/heart/.runtime/input-understanding-implementation-20261030/active-release-check/http
```

原生环境若使用 root 的 editable 安装，需要在启动测试前显式设置本工作树 `project/vendor/DeepTutor` 为 PYTHONPATH，并选择宿主 tests 包，避免加载上游同名 tests；详见 `native-regression-host-tests.log` 对应运行。不要修改安装、拼接两套 site-packages 或跳过源码校验。

```powershell
# 在本工作树应用目录执行；显式选择宿主 tests，避免 vendor 同名包遮挡。
$env:PYTHONPATH=(Resolve-Path ../../vendor/DeepTutor).Path
& E:/项目/heart/project/integration/discrete-math-tutor/.venv-deeptutor/Scripts/python.exe -B -c "import pathlib,sys,types,unittest; p=pathlib.Path.cwd(); t=types.ModuleType('tests'); t.__path__=[str(p/'tests')]; sys.modules['tests']=t; unittest.main(module=None,argv=['unittest','tests.test_native_assessment_commands','tests.test_native_learning_authorization','-v'])"
```

回退关闭新开关，保留任务记录；已有新协议复杂待办未完成完整 off 恢复演练，不能声称随意开关完全无风险。用户需要旧 pending 时优先保留原隔离进程/协议，取消后完整重新提问。

## 复用和许可证

- 直接调用既有 `agents/deeptutor_learning/pending.py` 的选项解析；本轮未复制新的上游代码。此文件 SHA256：`be77c8004896b83d59d3def4334fa9a78d57eebaa4118976763928ac4ffdee2e`。
- 现有 DeepTutor 迁入及 Apache-2.0 说明沿用 `third_party/DeepTutor` 与 vendor 固定快照；没有更新上游版本、账户/会话/学习主库。
- OpenMAIC/OpenTutor 的对象引用、命令与诊断边界来自前期调研，固定版本和来源见本目录深度审计。本轮是宿主 Python 适配，没有复制 TS 运行时或引入新框架。

截至 2026-10-30 本执行窗口结束时，本分支代码尚未合入 main；原工作区未提交教材和其他窗口修改仍由原持有人处理。2026-10-31 的本机主线历史对账见下文。

收尾：本轮 8147 隔离测试服务已停止并确认 health 不再可访问；隔离数据库、候选快照及失败证据保留。正式服务及正式数据库未更新。

## 主线历史对账（2026-10-31）

- 更新核对：`codex/input-understanding-v1` 的 `25053a1` 已包含在本机 `main` / `origin/main` 当前引用 `a9725fb` 的提交历史中。此项仅核对本地 Git 引用，未执行 `fetch`，不代表已验证远端最新状态。
- `main` 中的代码默认仍是 `INPUT_UNDERSTANDING_MODE=off`、`INPUT_UNDERSTANDING_SEMANTIC_ENABLED=0`；本次没有检查或更改 8000 运行进程的环境变量。
- 六维分类器的当前本地扩展另见 `SEMANTIC_CLASSIFIER_COMPLETION_PLAN_20261031.md`；该代码与测试仍有未提交改动，不能和已合入的输入理解两批代码混称为同一稳定交付。
