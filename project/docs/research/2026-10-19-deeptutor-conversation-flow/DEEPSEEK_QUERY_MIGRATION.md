# LightRAG查询迁移至DeepSeek官方端点

2026-10-22。用户明确授权“改网关，改成deepseek”。从06585ec继续，保留其他窗口修改、正式服务与索引；不重建全书图，不修改staging/ready=false。

## 配置及最小适配

本机主项目.env只新增`LIGHTRAG_QUERY_ENV_FILE`指向用户已有`E:\项目\heart\ds.env`，未复制key或更改其他配置。该文件及.env均不进Git。现有Q3检索后端/候选启用开关不变，正式服务未切换。

`roles.resolve_query_roles`显式读取该文件，要求HTTPS官方DeepSeek地址、文件内非空key；不允许把官方key发送旧网关，也不在缺key时回退项目其他key。未设置该入口时维持原宿主配置。

`roles.query_binding`继续保留默认严格比较。仅显式选择官方文件、模型/思考/温度/输出等身份全部相同、差异只有endpoint时允许查询迁移。其他模型或参数变化仍拒绝。原candidate policy不改；结果与失败audit分别记录`indexed_extract`和实际`query/keyword`，不能伪称旧图由新端点建成。

`engine.build_rag`新增可选`query_only=False`参数；检索调用传True，禁止传建图快照，extract角色直接拒绝。原建图入口仍走indexing_snapshot和原有策略。embedding权重/维度、图谱文件、全书输入、来源版本和Q2引用门禁完整保留。查询缓存身份采用实际官方模型配置，不复用旧网关模型身份。

`config.Metrics`记录每次调用的实际endpoint；backend结果/失败及CourseSearch记录model_binding，Q3/Q5同一search边界继续使用，无新循环或静默fallback。

## 验证状态

65项离线检查通过：`tests.test_lightrag_deepseek_query tests.test_lightrag_backend tests.test_lightrag_q3_adapter tests.test_lightrag_coverage tests.test_course_search_bridge`。覆盖显式官方切换、无显式配置仍拒绝、模型/参数变化拒绝、非法地址/空key不回退、查询实例拒绝抽取/建图。日志应用目录`.runtime/deepseek-query-20261021/offline.log`，用已有native环境、-B、独立库和mock完成。

代码提交`99aadf2`已推送。最终65项复验3.660秒、exit0，日志`final-tests.log`；现有`scripts/serve_lightrag_acceptance.py`预加载也改为同一query_binding并启用query_only，避免验收入口仍按旧网关全等检查。后续提交的该调用点及文档不改变本次页面使用的业务代码。

## 真实native及同一次完整Q5页面验收

证据摘要：[DEEPSEEK_QUERY_EVIDENCE.json](DEEPSEEK_QUERY_EVIDENCE.json)。真实运行基于已提交99aadf2，使用用户ds.env、已有native环境（-B）、本项目候选副本、独立8012和host/course数据库。未在其他worktree运行SDK或写缓存，未切8000/正式索引。

- 直接native查询“什么是自变量？”：28.844秒、success，第2章4条真实来源。实际keyword调用`https://api.deepseek.com`返回200，0.890秒、690 tokens、finish_reason=stop。不是Q2精确读取或回退；未调用extract。
- 现有页面同一次运行：生成计划→确认并讲解→原跨章插问→返回原目标→下一部分→刷新。计划待确认，其余4轮均answered/已保存；脚本exit0。插问前后完整Q5状态相等，返回目标ID相同，下一部分切到“笛卡儿的哲学思想”、mastered=false，刷新一致。不是多次运行拼接。
- 原题“第一章的实验程序和第二章的自变量控制有哪些联系？”实际backend=lightrag，coverage=covered；2次检索、0补查、fallback=false。最终4条引用分别覆盖第1/2章；实际正文流请求包含双方原文，不只是检索器返回过。6个带本轮原文链接的关联候选进入同一实际模型请求，全部evidence_eligible=false。最终回答明确不据此断言先修/因果关系。
- 查询前后7项核心图/向量/文档/状态签名不变，policy原字节不变。查询缓存可新增，不重建全书图。sidecar绝对地址只在隔离SDK读取视图重定位，存储原文未改；这不是独立部署可迁移性通过。

| 本次页面步骤 | 总秒 | 首次正文秒 | 外层SDK调用 / total_tokens | 实际后端 |
|---|---:|---:|---:|---|
| 计划 | 1.369 | 无正文 | 0 / 0 | 结构化计划 |
| 确认与讲解 | 8.229 | 4.984 | 4 / 13220 | q2_exact |
| 跨章插问 | 28.443 | 25.303 | 7 / 13802 | lightrag，2次native检索 |
| 返回原目标 | 7.232 | 3.734 | 5 / 21437 | q2_exact |
| 下一部分 | 10.656 | 6.279 | 5 / 17406 | q2_exact |

外层合计21次SDK create、65865 tokens（含选证/语义/正文/质检）；跨章native另有2次官方keyword调用，分别684/686 tokens、0.969/0.531秒，未混入外层计数。按相邻请求开始时刻分段，避免边界容差重复计数。SDK计数不代表全部HTTP重试可观测；adapter最多3次、内部SDK重试0；没有金额，不估价，不以本次结果推断整体性能提升。

原始native结果和日志：应用`.runtime/deepseek-query-20261021/native-result.json`、native.log。页面SSE、flow.json、模型真实输入/usage、阶段记录、截图q5.png（已查看）及服务日志：应用`.runtime/response-experience/20261020/deepseek-query-q5`。运行结束停止本次服务。

## 剩余与启用结论

官方查询替代已实现且原native/跨章/关联候选消费/Q5固定序列已真实通过，**此前网关凭据/地址绑定阻塞已解除**。缺一方证据的真实partial、native取消/超时的实际退出与晚到不发布保存、独立生产环境/候选侧车迁移仍待验，不据此宣布UX5或整份计划完成。一次固定Q5序列通过不代表全书长期路径覆盖、正式评分或全部教学循环完成。

不自动切正式索引或修改ready=false。保留之前401、绑定失败等历史事实；它们不再代表当前官方查询不可用。
