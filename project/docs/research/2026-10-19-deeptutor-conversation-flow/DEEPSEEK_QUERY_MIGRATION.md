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

真实native查询与页面证据待本批提交后隔离验证；此处不把离线通过当作LightRAG检索接通。已有候选副本在本项目.runtime中使用，不能在其他worktree直接运行SDK写缓存。旧绝对sidecar地址的副本读取视图重定位须如实记录；不改原文件或冒充独立部署就绪。
