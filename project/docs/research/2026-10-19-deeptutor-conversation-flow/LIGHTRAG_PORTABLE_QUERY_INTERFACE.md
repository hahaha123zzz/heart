# LightRAG 查询迁移接口（2026-10-22）

基于8de37cd；仅修正本地查询的来源解析边界，不重写检索、不建图、不改staging/ready=false或冻结文件。独立环境真实联验待本批实现提交后执行，不能把本文件或单测当作部署通过。

## 旧目录依赖与处理

1. 冻结full_docs.sidecar_location是原候选目录下的绝对URI。`paths.bind_candidate_sidecars(rag, working)`在已初始化的查询实例中绑定读取视图：核对file_path、doc_id、parse_engine和历史URI对应同一文档，使用SDK parsed_artifact_dir_for定位当前候选的固定目录，验证原冻结bundle及sidecar路径。缺失、远程URI、跨文档、目录冲突、越界、symlink/reparse point/hardlink拒绝。原full_docs字典不改，不读旧路径，不写回新路径。SDK单项和批量读取均覆盖。
2. 冻结input_manifest.source_root保留为历史身份。`LightRagBackend(..., source_root=None)`新增可选关键字参数；省略时保持旧校验行为。Q3/Q5共同`shared_search`显式传入当前宿主PSYCHOLOGY_DIR；当前目录与候选input均按同一冻结files逐项核验，缺输入/新增或变更受保护文件仍失败。没有“旧路径不可用则跳过验证”的分支。

## 调用方和兼容性

- 实际接入点：`LightRagBackend.search`的worker job，initialize后、query_with_sources前。仅此查询实例安装读取视图；建图/抽取/发布路径不改。
- `agents/course_search.py::shared_search`为公共Q3/Q5提供active source_root，CourseSearch保持resolve、read_target与路径状态语义。
- backend结果/异常审计新增可选`source_binding`：indexed_source_root、active_source_root、sidecars.mode及实际访问文档名。CourseSearch.retrieval_calls和LightRagNavigator.backend_calls透传，便于验证确实使用迁移适配；不是教材事实或引用。
- `bind_result`、TaskContext.course_navigation、source_visuals、course_release、SourceRef、Q5位置、工具/循环及HTTP入参不改。现有直接调用backend的脚本可以继续省略source_root；新运行目录应显式传当前教材目录。
- 实现只使用SDK与现有ingress校验，不修改第三方包或其他worktree，不复制其未提交代码。所有原文/引用/像素/版本/保存门禁保留。

## 已完成检查与未验项

新增tests.test_lightrag_relocation，涵盖旧目录不存在时单项/批量本地读取且原数据不变、远程/跨文档/身份错误拒绝、缺块/冻结bundle漂移拒绝、hardlink拒绝、active输入核验及历史manifest不变。

定向命令：独立环境Python `-B -m unittest tests.test_lightrag_relocation tests.test_lightrag_backend tests.test_lightrag_deepseek_query tests.test_course_search_bridge tests.test_lightrag_q3_adapter tests.test_lightrag_coverage -q`；70项32.518秒通过。应用`.runtime/deepseek-query-20261021/relocation-tests.log`保留日志。

下一步在固定已提交代码、独立venv/输入/DB及候选副本中，移除旧验收initialize重写URI的临时hook，执行真实native与页面。需要分别核对普通聊天、Q5跨章接续、PDF选区、AI练习、ask_user、取消/刷新和原图像素；缺少真实证据的入口保留未完成。source_binding与原始API/模型输入用于区分实际LightRAG、Q2精确读取及缓存/回退。
