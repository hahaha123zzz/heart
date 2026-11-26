# 阶段 1 教材资产与干净打包报告

日期 2026-11-26
分支 `codex/phase1-textbook-assets-20261126`（从 `36f33867` 新建的隔离工作树）
计划 [2026-11-26 固定教材启动与回答延迟](../plans/2026-11-26-fixed-book-startup-and-answer-latency.md)

## 状态

已完成两项前置整改并做了实测：

1. 取消适配器对上游快照哈希的运行时依赖，干净提交可以打包并启动 worker；
2. 固定教材资产安装/加载（哈希表、冻结输入大小、来源映射）落地，启动只核对身份与文件大小。

旧 SQLite 索引退役、图表/词表预生成、候选部署对照还没做。

## 1. 上游快照检查

改动（`8d747746`）：

- `learning_binding_adapter.py`：保留“模块路径等于固定源码”“接口未被替换”的检查，删除
  `UPSTREAM_SNAPSHOT.json` 的逐文件哈希比对。
- `learning_tool_adapter.py`：保留工具工厂/题卡提交的模块来源与路径检查，删除快照哈希比对。
- 新增测试 `tests/test_learning_adapter_pin.py`：快照为空、哈希对不上时，适配器仍能安装。

验收：

- 隔离工作树（干净提交）直接启动 worker 到 18002：24 秒 `/health/ready`。
- 从该提交打包 `phase1-clean-20261126`，复制现有 Web 构建产物，`student_release.py verify` 通过；
  从该发行启动 worker 到 18002：15 秒 `/health/ready`，日志到 `worker.ready_to_listen` 23.2 秒。

## 2. 教材资产契约

新增（`825f5c4a`）：

- `knowledge/fixed_book_assets.py`
  - `install(root, textbook, candidate, release_id, source_map)`：完整执行冻结输入校验、教材 inventory、
    `verify_active` 和来源映射加载，生成并原子写入 `assets.json`；失败保留上一份。
  - `load(root, textbook, candidate)`：没有记录时返回 None（退回完整扫描）；记录存在但路径、控制文件摘要、
    教材/冻结输入文件大小不一致时抛 `AssetsMismatch`，消息统一“请重新安装教材资产”。
  - 记录内容：教材 release_id、候选路径、5 个控制文件摘要、教材 409 个文件的哈希与大小、
    冻结输入 325 个文件的哈希与大小、宿主额外文件指纹、已核验的 `source_map`。
- `scripts/install_textbook_assets.py`：显式安装入口，默认写到 `<DEEPTUTOR_HOME>/../textbook-assets`。
- `fixed_book.py`：启动先加载资产；有资产时跳过 `verify_active`、冻结输入逐文件校验和教材 inventory，
  用资产里的哈希表与来源映射；启动后仍用 `course_release.validate()` 的 release_id 核对绑定，不一致则
  固定教材未就绪并报“请重新安装教材资产”。
- `lightrag/retrieval.py`：`validate(..., assets=...)` 时冻结输入和正式教材只记安装来源，不再扫描。

实测（写入的是运行部署的 `private/textbook-assets`，不影响当前运行的旧发行）：

- 安装：release_id `e051f817145b…`，教材 409 个文件、冻结输入 325 个文件、来源映射 11 章。
- 加载：0.046 秒；与运行中宿主最近一次 `fixed_book.release` 的 release_id 完全一致。
- 对照：同一份教材的启动扫描在本轮样本中约 3.2 秒（正式教材）+ 1.9 秒（冻结输入）+ 3.1 秒（再次 inventory）。

测试：`test_fixed_book_assets.py` 6 项，覆盖安装、加载、教材缺失、索引变化、无记录回退、失败保留旧记录、
`validate` 不触发扫描；与启动/索引相关专项合计 52 项通过。

## 3. 还没做

| 项 | 状态 | 下一步 |
| --- | --- | --- |
| 候选部署对照 | 未做 | 用同一健康发行做基线，候选用本分支发行、独立端口/运行目录/账号/数据库命名空间；跑同一批用例 |
| 图表/检索词表预生成（第 6 项） | 未做 | 资产记录增加图表清单与词表；启动不再 `visual_inventory`/`load_figures` |
| 冻结输入整目录缺席（第 5 项验收） | 部分 | 启动已不读冻结输入做校验；`fixed_book.visual_map` 仍读候选 input，需随第 6 项迁移 |
| 旧 SQLite 索引退役（第 3 项） | 未做 | 10 处运行时调用按“问答/原文定位/启动预热”三类迁移，再在无旧索引的候选验收 |
| 旧索引预热与样例查询 | 未做 | 迁移后删除 `warmup.local_index`、`warmup.sample_query`，保留 LightRAG 自身就绪检查 |
| 原文页码与引用回归 | 未做 | 候选上验证引用跳页、图表、选区、练习、历史引用 |

## 4. 注意

- 当前运行的 8000 部署仍是旧发行，资产目录是新增的，不影响它；要看到收益必须让候选发行启动。
- 资产加载仍执行 `course_release.validate()`（约 0.35 秒）与 LightRAG 索引清单核对；这两项是版本绑定，
  不属于被取消的教材逐文件扫描。
- 资产绑定的 release_id 目前包含旧 SQLite 索引的摘要；旧索引退役后 release_id 会变化，需要重新安装资产。
