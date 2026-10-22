# LightRAG 查询迁移接口（2026-10-22）

基于8de37cd；仅修正本地查询的来源解析边界，不重写检索、不建图、不改staging/ready=false或冻结文件。独立环境真实联验待本批实现提交后执行，不能把本文件或单测当作部署通过。

## 旧目录依赖与处理

1. 冻结full_docs.sidecar_location是原候选目录下的绝对URI。`paths.bind_candidate_sidecars(rag, working)`在已初始化的查询实例中绑定读取视图：核对file_path、doc_id、parse_engine和历史URI对应同一文档，使用SDK parsed_artifact_dir_for定位当前候选的固定目录，验证原冻结bundle及sidecar路径。缺失、远程URI、跨文档、目录冲突、越界、symlink/reparse point/hardlink拒绝。原full_docs字典不改，不读旧路径，不写回新路径。SDK单项和批量读取均覆盖。
2. 冻结input_manifest.source_root保留为历史身份。`LightRagBackend(..., source_root=None)`新增可选关键字参数；省略时保持旧校验行为。Q3/Q5共同`shared_search`显式传入当前宿主PSYCHOLOGY_DIR。候选input仍按原verify要求全量一致；当前宿主用verify_active逐项核对全部冻结原文，缺失/变化拒绝。宿主还需要自己的Q2索引与未入图产物，额外文件仅审计数量/哈希且evidence_eligible=false，不加入图谱证据。没有“旧路径不可用则跳过验证”的分支。

## 调用方和兼容性

- 实际接入点：`LightRagBackend.search`的worker job，initialize后、query_with_sources前。仅此查询实例安装读取视图；建图/抽取/发布路径不改。
- `agents/course_search.py::shared_search`为公共Q3/Q5提供active source_root，CourseSearch保持resolve、read_target与路径状态语义。
- backend结果/异常审计新增可选`source_binding`：indexed_source_root、active_source_root、sidecars.mode及实际访问文档名；显式宿主目录还含additional_host_files的count/sha256/evidence_eligible=false。CourseSearch.retrieval_calls和LightRagNavigator.backend_calls透传，便于验证确实使用迁移适配；不是教材事实或引用。
- `bind_result`、TaskContext.course_navigation、source_visuals、course_release、SourceRef、Q5位置、工具/循环及HTTP入参不改。现有直接调用backend的脚本可以继续省略source_root；新运行目录应显式传当前教材目录。
- 实现只使用SDK与现有ingress校验，不修改第三方包或其他worktree，不复制其未提交代码。所有原文/引用/像素/版本/保存门禁保留。

## 已完成检查与未验项

新增tests.test_lightrag_relocation，涵盖旧目录不存在时单项/批量本地读取且原数据不变、远程/跨文档/身份错误拒绝、缺块/冻结bundle漂移拒绝、hardlink拒绝、active输入核验及历史manifest不变。

定向命令：独立环境Python `-B -m unittest tests.test_lightrag_relocation tests.test_lightrag_backend tests.test_lightrag_deepseek_query tests.test_course_search_bridge tests.test_lightrag_q3_adapter tests.test_lightrag_coverage -q`；70项32.518秒通过。应用`.runtime/deepseek-query-20261021/relocation-tests.log`保留日志。

下一步在固定已提交代码、独立venv/输入/DB及候选副本中，移除旧验收initialize重写URI的临时hook，执行真实native与页面。需要分别核对普通聊天、Q5跨章接续、PDF选区、AI练习、ask_user、取消/刷新和原图像素；缺少真实证据的入口保留未完成。source_binding与原始API/模型输入用于区分实际LightRAG、Q2精确读取及缓存/回退。

首轮803db64真实native自变量成功、返回4条来源，sidecar指向新候选；直接“图5-2”检索no_evidence，未计成功。宿主启动暴露了纯建图快照没有Q2索引的问题；宿主副本相对冻结文件没有缺失/变更，额外84项为OMML、原始全书/前言及rag_index.sqlite3。原整目录严格比较误把两种输入域混为一谈，已改用上述双边界。旧verify及默认source_root不变，新增测试确保宿主额外Q2文件不入图、冻结快照仍拒绝新增、缺失/换版继续拒绝。71项3.923秒通过，应用`.runtime/deepseek-query-20261021/relocation-host-tests.log`。803db64的失败目录和日志保留；最终代码仍须重跑页面，不拼接为整体通过。

启动器递归专项：根据LIGHTRAG_DEPLOYMENT_ROOT_CAUSE_AUDIT.md复核，55f930a独立页面批次的fresh读取被再次赋值的query，出现RecursionError，并未进入原SDK查询。已保留`.runtime/response-portable-20261022/serve-recursion-failure.py`、`recursion-earliest-reproduced-traceback.txt`及`failure-recursion-55f930a`。仅修复验收层：`scripts/lightrag_acceptance_instrumentation.py::wrap_native_query`通过闭包绑定原函数，将禁缓存/计时/注入截止合为一次包装；启动器保存一次original_native_query，不再定义fresh。普通/异常/原函数取消/外部取消/本次SDK开始后的超时五项离线检查0.199秒通过，日志应用`.runtime/deepseek-query-20261021/launcher-selfcheck.log`。本批不改生产检索、SDK、冻结来源或图谱；真实部署须在该提交后重新导出资源并顺序执行，旧递归批次不算成功。
