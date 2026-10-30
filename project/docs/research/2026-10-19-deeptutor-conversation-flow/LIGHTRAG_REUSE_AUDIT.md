# DeepTutor LightRAG 接入源码复核（2026-10-20）

## 结论与范围

可以复用其原生 Python SDK 接入方式及主要实现。建议迁入 LightRAG 适配模块，替换模型、教材解析、权限、索引发布及证据接口。保留本项目 Q3 回答编排与 Q5 学习状态，不引入完整 DeepTutor 应用。本文为源码调查及候选设计，未安装、建图、修改业务代码或完成模型验收。

本机源码：`D:/deeptutor`，HEAD `6cf793bd868ba5ecbe64722936d4be8fab5a01df`。以下文件位于 `deeptutor/services/rag/pipelines/lightrag/`。实施前需记录实际迁入文件哈希及工作树差异，不能仅凭 HEAD 推断文件未修改。

## 实际接入链

1. `services/rag/factory.py::_build_pipeline` 按 provider=`lightrag` 创建 `LightRagPipeline`，与 `lightrag-server` HTTP 后端分开。
2. `pipeline.py::initialize/add_documents` 负责写入所有权、索引配置快照、版本目录、文档处理及发布；`_stage_documents` 调用其解析服务。
3. `ingress.py` 冻结原件、Markdown、结构块和资源到版本目录，保存摘要并核对路径、文件身份与内容，避免运行中读到变动的源文件。
4. `engine.py::_register_parser` 注册自定义 parser；`parser.py` 校验冻结数据，有结构块时经 `sidecar.py::build_ir` 转为原生 Sidecar IR，无结构块时走 RAW 内容。
5. `engine.py::build_rag` 构造 LightRAG 并适配 EXTRACT、KEYWORD、QUERY、VLM 及 embedding；原生 SDK 完成分块、实体关系抽取、图谱与向量处理。
6. `worker.py` 通过固定后台事件循环运行 SDK，桥接调用方模型回调和取消；`storage.py` 处理版本/就绪元数据及 embedding 兼容性。
7. `pipeline.py::search` 选择已发布版本，核对 embedding、解析查询角色，再调用 `engine.query_with_sources`。
8. `query_with_sources` 使用 `QueryParam(stream=False, include_references=True)` 调用 `rag.aquery_llm`，返回生成答案以及 chunk/entity/relationship/reference/query_metadata。它不是只返回原始块的检索接口。

## 版本与配置事实

- `pyproject.toml` 的 `rag-lightrag` 固定 `lightrag-hku==1.5.7`；`engine.py` 运行时严格校验同一版本。不能直接安装任意最新版再宣称兼容。
- 本地适配器支持 naive/local/global/hybrid/mix，默认 **hybrid**，不能把其他版本的默认 mix 套到这份源码上。
- EXTRACT/VLM 与 embedding 的身份随已接受索引任务固定；QUERY/KEYWORD 按查询角色解析。实际限制、超时及配置更新规则需按源码保留。
- VLM 可以禁用；文本、表格、公式处理与图片分析分别配置。不能将文字索引成功算作图片理解通过。
- `storage.py` 当前布局使用版本目录中的 KV、向量和图文件，需评估全书资源及并发，不能声称上游原生接入默认部署 Neo4j。
- DeepTutor 根 LICENSE 为 Apache-2.0；迁入保留其 LICENSE、适用 NOTICE 和修改记录，并核对 LightRAG 及其他依赖许可。

## 迁入边界

| 模块 | 复用方式 | 必要适配 |
| --- | --- | --- |
| engine/parser/sidecar | 保留原生 SDK 契约、结构转换、响应形状校验 | parser 注册路径、现有章/节/block/页码身份，以及宿主查询职责 |
| ingress/block_policy | 保留冻结、摘要校验、资源边界、布局块处理和审计 | 当前 document.json/原件/PDF 与上游 ParsedDocument/MinerU 字段不同，需转换；页坐标也要校准 |
| worker/write_lock/cache_reuse | 保留循环归属、取消、写入互斥、可安全复用的缓存 | 绑定 Q3 取消及任务生命周期，验证超时和重启边界 |
| storage/pipeline | 保留处理状态、兼容检查、版本布局及发布流程的可用逻辑 | 本项目课程发布、就绪与换版，不直接采用上游全局运行目录和 KB 管理器 |
| config/roles/indexing_policy | 保留角色分工、配置快照与签名语义 | 替换上游用户上下文、模型目录、访问控制、全局配置与 embedding 客户端 |
| 来源映射 | 保留结构化来源返回并分类 | chunk 映射到本项目原文；实体/关系摘要不能冒充精确引句；metadata 不作证据卡 |

## 必须检查的行为差异

1. **生成职责**：首选使用固定 SDK 经验证的结构化检索接口返回上下文，由 Q3 生成唯一正式回答。若复用现有 `aquery_llm` 保留内层答案，只能当工具背景，仍须用原文核验并记录额外模型开销。纯检索具体 API 尚未在 1.5.7 安装环境验证，不能写成已接通。
2. **精确导航**：Q2 的 read_target/真实目录定位继续处理明确章/节/点；LightRAG 增强概念及关系检索，知识图谱边不自动成为教学顺序。
3. **发布边界**：`_initialize_owned` 在 `has_output` 后调用发布函数，最终返回 `outcome.complete`。需要联查 `_run_indexing` 的异常路径和部分成功情况，不能仅凭返回布尔值认定绝不会发布不完整候选。本项目需实测“部分失败不替换正式教材版本”。
4. **取消及安全**：上游包含 symlink/路径/摘要防护，迁入不能裁掉；Windows junction/reparse point、跨进程写入及取消后无残留写入需本机验证。
5. **测试含义**：上游 `test_lightrag_native_smoke.py` 使用真实 SDK，但部分测试用 fake LLM 和固定向量；这种通过不证明教材实体关系抽取或真实检索质量。

## 推荐实施顺序

用户已于 2026-10-20 明确要求直接全书建图，取消单章试点；以下顺序以全 11 章为首批实际建图范围。全书任务可以分批排队和续跑，不以单章验收作为继续处理其余章节的前置条件。

1. 独立分支迁入模块与最小依赖闭包，固定 SDK 版本、来源和许可证；用宿主适配替换原应用依赖。不要从正在开发的 Q2/Q3 工作树直接覆盖文件。
2. 接既有全 11 章解析产物为结构化入口，核对正文、表格、公式、图片与来源映射；验证模型、embedding 及必要 VLM 可用性，登记全书文件清单与版本签名。
3. 直接构建全书独立候选图谱/向量索引，记录逐文档进度、失败、重试和恢复信息；限制并发并观察耗时、费用、内存。失败章节必须明确列出，不将部分成功标为全书完成；不覆盖当前正式索引。
4. 接入 Q2 knowledge 接口及 Q3 retrieve_course，测单概念、比较、跨章、章节概述、自然追问和无依据拒答；分别记录检索结果、目标选择与质量门禁失败原因。
5. 对全书逐章核查摄取完成状态，并验证实际抽取、检索、精确原文引用、删除/换版、取消和部分失败；对照当前检索，通过后切为主后端，再清理被替代的索引实现。Q3/Q5 的路径与教学循环继续推进，不把换检索引擎记为学习状态完成。

备选：直接导入整个上游 pipeline 的改动看似少，但会引入模型账户与 KB 管理依赖；外部 LightRAG Server 可隔离运行，却需要额外 HTTP 生命周期及来源协议。当前目标是复用源码，推荐上述本地模块迁入方案。
