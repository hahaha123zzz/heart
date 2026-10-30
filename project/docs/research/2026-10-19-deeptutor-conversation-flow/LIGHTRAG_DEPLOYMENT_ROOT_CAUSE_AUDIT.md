# LightRAG 部署阻塞根因核对（2026-10-22）

## 结论与范围

本次核对 main `55f930a80a03b71749339eda350f87228f3058af`、DeepTutor `6cf793bd868ba5ecbe64722936d4be8fab5a01df`、本机独立环境的 LightRAG SDK 1.5.7，以及 LightRAG 官方文档。只读调查业务代码、现有运行记录；另运行临时 SQLite/文件专项测试和不联网的函数复现。未修改业务代码、验收脚本、服务、候选或发布状态。

问题不等于图谱不能使用。两个原始部署失败是接入层混淆了冻结输入与完整宿主运行资源；此外，新独立验收脚本存在可实证复现的递归错误。已有目录修复不能代替部署验收。

## 1. 整目录相等校验误拒绝完整宿主

- 原始证据：仓库根 `.runtime/response-portable-20261022/superset-failure-native.log`。`LightRagBackend.validate → verify → actual != material_files(expected)` 报“教材输入已变化”。
- 校验位于本项目新增 `knowledge/lightrag/course_input.py`，不属于 LightRAG SDK 的目录要求。
- 当前提交 `55f930a` 已分开：冻结 `candidate/input` 仍用严格 `verify`；显式当前宿主 `source_root` 使用 `verify_active`，要求所有冻结文件逐项存在且哈希相同，允许宿主附加文件共存。附加文件审计为 `evidence_eligible=false`。
- 这允许现有 Q2 索引与公式等共存，不允许用不同原文冒充候选来源。额外文件不自动获得图谱覆盖身份。
- 84 个额外文件的分类见 `LIGHTRAG_PORTABLE_QUERY_INTERFACE.md`；本次没有重新全量计算其哈希，不能把该数字当成本轮新测结果。

## 2. 纯建图快照不是宿主部署包

- 原始证据：仓库根 `.runtime/response-portable-20261022/startup-missing-q2-server-all.log`。
- 实际堆栈：`main.py` 创建 `TutorOrchestrator` → `orchestrator.py:86` 无条件 `load_textbook()` → `knowledge/textbook.py:64` 缺 `rag_index.sqlite3`。
- 即便一般检索选择 LightRAG，宿主目前仍需要 Q2 教材块、精确目标读取、导航和引用。选择另一检索后端不会自动删除启动依赖。
- 正确最小部署方式：保留与当前教材绑定的现有完整宿主教材目录/已有 Q2 索引，另行提供 LightRAG 候选。仅因部署副本缺文件而重建正式索引没有依据。
- 若要彻底取消 Q2 依赖，应单独改造所有调用方；不是本次切换必须完成的工作。

## 3. sidecar 与 workspace 是两种路径身份

- DeepTutor `engine.workspace_for` 优先读取 `meta.json` 中固定 workspace，避免搬目录后重新计算路径哈希而打开空库。本项目已保留该逻辑，不需要再实现一套。
- DeepTutor `storage.py` 使用每 KB 的 `version-N` 作为存储根，查询经 `latest_published_root` 和 embedding binding 选择版本；`ingress.freeze_document/load_verified_bundle` 逐文档冻结和核验来源。
- DeepTutor `parser.py:83` 仍通过 SDK `sidecar_uri_for` 保存 `sidecar_location`；不能由 workspace 可迁移推断 sidecar 全部可迁移。
- 本机 SDK 1.5.7 `lightrag/utils_pipeline.py:1217` 对解析目录做 `resolve()`，编码为 file URI；resolver 读取 URI 路径。该行为依赖原绝对位置，且 Windows URI 需保持本项目现有兼容适配。
- 已查看的 DeepTutor 原生查询链没有与本项目 `bind_candidate_sidecars` 等价的迁移读取视图，不能宣称上游有完整现成的自动搬迁修复。
- `803db64` 已把适配放进业务查询边界：初始化后依据文档身份、当前候选和冻结 bundle 绑定本实例的单项/批量读取，不改冻结历史 URI。公共 `shared_search` 显式传当前 `PSYCHOLOGY_DIR`。这是当前项目的适配，仍需实际部署验证。

## 4. 新独立页面验收的递归错误：已复现

证据：仓库根 `.runtime/response-portable-20261022/server-all.log` 多次实际检索 `error_type=RecursionError`，并非 401 或版本拒绝。其验收启动器 `.runtime/response-portable-20261022/serve.py`：

```python
# 第20行保存原函数，fresh 在执行时读取模块全局 query。
query = engine.query_with_sources
async def fresh(rag, *args, **kwargs):
    rag.llm_response_cache.global_config['enable_llm_cache'] = False
    return await query(rag, *args, **kwargs)
engine.query_with_sources = fresh

# 第48行又把同一个全局 query 改成 fresh。
query = engine.query_with_sources
# measured_query 随后调用 query，即 fresh；fresh 再调用 query，即自己。
```

调用变为 `measured_query → fresh → fresh → …`，原 SDK 查询尚未执行便递归失败。它是测试仪表代码的全局变量重绑定问题，不是向量/图谱损坏。

本次用 AST 提取脚本原 `fresh` 函数，不导入启动器、不加载模型、不联网：`query=fresh` 实证触发 RecursionError；保持 `query` 指向原始异步替身后正常返回。该实验只证明上述递归机制，不代表完整部署通过。

最小修正：启动器只安装一次缓存/计时包装，使用不会再次赋值的原函数引用（例如单独命名 `original_native_query`）；故障注入分支和普通分支调用同一个保存的原函数。不要为修复测试脚本修改生产检索、SDK 或冻结数据。由于其他窗口仍负责该运行，本次未编辑它。

## 5. 官方依据与版本限制

通过 agent-reach 指定 Jina 网页读取方式获取官方原文：

1. [SDK 指南](https://github.com/HKUDS/LightRAG/blob/main/docs/ProgramingWithCore.md)：`working_dir`、workspace、存储初始化/释放、索引与查询 embedding 一致性。它没有规定本项目的 `rag_index.sqlite3`。
2. [Sidecar 格式](https://github.com/HKUDS/LightRAG/blob/main/docs/LightRAGSidecarFormat.md)：`*.parsed/`、结构块及图表资产文件；图像资源路径相对解析目录。资产内部相对路径不意味着外层 sidecar_location 会自动迁移。
3. [官方 README](https://github.com/HKUDS/LightRAG/blob/main/README.md)：当前 SDK/存储和相关文档入口。

以上是获取时官方 main 文档；具体 URI 行为另外核对了本机固定 SDK 1.5.7，未用最新文档替代版本实证。未升级依赖。

## 6. 验证与交付顺序

本次直接运行现有专项：

```powershell
# 工作目录：E:\项目\heart\project\integration\discrete-math-tutor
& 'E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe' -B -m unittest tests.test_lightrag_relocation -v
```

6 项通过，unittest 报告 5.705 秒，exit 0。覆盖单项/批量迁移读取、历史不变、缺块和 bundle 漂移、hardlink 拒绝、显式宿主根、额外 Q2 产物共存而冻结快照仍严格。它不覆盖验收启动器，因此不能发现该启动器的全局变量重绑定。

建议负责窗口按以下顺序完成：

1. 先修正独立启动器原查询引用，离线证明实际原函数恰调用一次，普通/超时/取消分支均不递归。
2. 以包含 `803db64`、`55f930a` 的最终稳定提交导出部署副本，保留完整宿主目录。已有 `.runtime/response-release-20261022/preparation.json` 标记旧 `421f871`，不能以旧快照验收新增修复；其他副本须分别登记 SHA。
3. SDK、模型缓存、宿主教材、候选和数据库分别登记，禁止读取旧候选/旧 worktree；仅使用计数、计时和故障注入，不再靠改写来源 URI 的临时 hook。
4. 新进程先做 1 次原生检索，再做跨章、Q5、PDF、图表、练习、ask_user、取消/刷新。分别标实际 LightRAG 与 Q2 精确读取；正常无证据与运行异常分开。
5. 核对原候选核心签名未改、宿主旧索引未重建、学习数据保留。正式运行切换与教材发布审核分别判断，不以文件存在自动改 ready。

尚未执行修正后的完整启动器、真实模型或浏览器验收；本报告不能作为正式切换通过证明。
