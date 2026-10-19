# 心理学真实模型代表性黄金集

日期：2026-10-19。固定上游提交：`6cf793bd868ba5ecbe64722936d4be8fab5a01df`。

本阶段复用原 `/api/chat`、TaskService、教学策略、证据充分性、QualityChecker、精细引用索引和上游 Provider/Obsidian/课程/回合服务。沿用原五类验收的教材对象与公式选区，新增可重复执行的隔离验收入口；没有创建第二套教学流程。

## 最终结果

最终运行 `20261019T011227Z-4a5cb9`：9 类案例全部通过。

| 案例 | 结果 |
| --- | --- |
| 自变量概念 | 真实生成、教材引用、原质量检查通过 |
| 自变量/因变量/额外变量比较 | 真实检索、比较与引用通过 |
| 操作性/选择性自变量边界 | 正确保留选择性自变量，未把年龄/性别一概排除 |
| 被试间/被试内设计 | 正确比较每名被试接受的处理水平数 |
| 随机分配提示 | 仅提示任务约束与 give_hint 动作一致 |
| 教材文字选区 | 客户端伪造选区文字未进入模型，实际引用服务端原文 |
| DL 公式图片框选 | 原图实际送入模型，解释 St/PSE 参照点，引用通过 |
| 同会话简化追问 | 沿用当前自变量语境，未误解成回答助教检查题 |
| 未提供实验数据时拒答 | 原证据核验拒绝发布真实人数/p值，学习步骤未推进 |

本轮实际调用模型网关 43 次、知识库 10 次；其中 6 次成功模型调用携带教材图片。20 条引用均为 exact，已重新校验引句存在于原文、坐标对应的 PDF 文字及教材版本。不是把 HTTP 200 当作验收通过。

重复发送原 request_id 未新增模型调用，conversation_id 保持一致；原 API 的 sources/done 事件重放、其他学生访问拒绝均通过。测试 worker 已停止；9 个案例使用合成学生和独立数据库，裁图缓存也在运行目录内。

## 本轮发现并修正的问题

1. 路由器把“缺少实验数据”当成“任务不明”，返回通用任务澄清。已区分任务槽位与证据缺口，让明确请求进入原证据核验，再按缺失的数据拒答；没有添加按关键词伪造的拒答。
2. 初轮选区解释在忠实引用定义后，追加了教材不支持的排除结论。对照本章的选择性自变量分类后，在共用课程规则中限制从总括定义推断必要条件、唯一分类和互斥关系；生成器和原质检共用此规则。增加分类案例，最终选区回答未再排除选择性自变量。
3. 验收脚本起初将 TaskExecution.hint_only 当作序列化字段。实际它是从 learning_intents/answer_constraints 计算的属性；已直接复用 TaskExecution 解析，并同时检查教学动作为 give_hint。

初轮失败产物保留在本机，没有覆盖成成功；修复后重新运行了完整 9 类案例。最终结果还使用当前版本的验收函数再次核对。Codex 已逐条对照回答、引句和公式裁图；这不代表全教材、教师审核或所有模型输出均已验证。

## 回归检查与复现

专项 Python 回归共 96 项通过：黄金集判定 8、澄清事务 29、路由校验 10、证据充分性 22、心理学问答 9、任务 API 18。全量旧离散数学资源测试仍存在前阶段已记录的资源依赖问题，本阶段没有把全量测试宣称为通过。

在宿主目录执行：

```powershell
.venv-gpu/Scripts/python.exe -B scripts/check_deeptutor_golden.py
# 可单独复现；followup 会自动加入 concept 前置案例。
.venv-gpu/Scripts/python.exe -B scripts/check_deeptutor_golden.py --case hint --case refusal
.venv-gpu/Scripts/python.exe -B -m unittest discover -s tests -p test_deeptutor_golden.py -q
```

需要本机正式教材、模型配置、DeepTutor 独立环境，以及 `.runtime/deeptutor-generation-smoke/citation-index.sqlite3`；可通过 `--citation-index` 指定另一个已构建的引用索引。每次运行在 `.runtime/deeptutor-golden/<run>/` 新建运行目录、自动发布 Obsidian 知识库并启动/关闭独立 worker。模型默认超时 35 秒，单次运行限制最多 180 次网关生成调用。既有代码中显式配置的超时保持不变。

模型读取本机配置，本轮为 `deepseek-flash`。检索设备固定为 CPU，保留已有重排模型和阈值，避免与现有服务争用 GPU；未做生产并发或 CUDA 性能验收。关闭后台记忆 worker 和附加图解，只验收本阶段的核心教学与引用链路。

最终原始产物仅保留本机：

- `project/integration/discrete-math-tutor/.runtime/deeptutor-golden/20261019T011227Z-4a5cb9/report.json`
- 产物 SHA-256：`b3871f5c3fe007d81fd44edb4a74f36ee7b0236bf62afe60881e5461853935be`
- 引用索引 SHA-256：`8b3b6bad671f626d1f96017e4fe6c3cf5854ac647b16780dbefb18696ce4a666`

## 仍保留的范围

本次没有修改实际 `.env`、生产学习数据库或默认模型入口，也没有重启既有 8000 服务。后端提示规则需在部署新代码时生效。9 类是固定的代表性样本，未逐章穷尽整个教材。

完整 AgenticChatLoop、向量索引、Mermaid/代码主题/工作区附件，以及后续阅读批注、测评与记忆整块接入继续保留；B 整批和整个迁移尚未标为完成。默认切换还需结合后续接入与实际部署验证。
