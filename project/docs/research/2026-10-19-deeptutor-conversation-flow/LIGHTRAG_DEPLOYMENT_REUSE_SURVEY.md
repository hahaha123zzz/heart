# LightRAG 部署现成方案调研（2026-10-22）

## 结论

有可借鉴的现成方案，优先级是：沿用当前原生接入，参考官方部署把路径和资源固定；继续复用 DeepTutor 的版本与生命周期；必要时再采用 DeepTutor 的 HTTP 检索客户端。没有查证到能直接搬入、同时自动修复本项目 325 项冻结输入、完整宿主 Q2 索引、Windows 历史 sidecar URI 和验收脚本递归的整套项目。

本次仅调研，不安装依赖、不引入新后端、不启动容器、不改正式索引。参见前置根因报告 `LIGHTRAG_DEPLOYMENT_ROOT_CAUSE_AUDIT.md`。

## 核对项目

| 项目 | 核对时提交 | 许可证 | 适合复用的部分 |
|---|---|---|---|
| HKUDS/LightRAG | aaebfe1bb8d55deb6a4304d357a3bf4c92fcd40a | MIT | 数据目录分离、固定运行路径、SDK 生命周期、结构化检索 API |
| D:\deeptutor | 6cf793bd868ba5ecbe64722936d4be8fab5a01df | Apache-2.0 | 已发布知识库绑定、固定 workspace、原生适配；另有 HTTP 客户端及探测 |
| HKUDS/RAG-Anything | afb67c43d391b1b1008a6fee9f020a232067b9e5 | MIT | 已有 LightRAG 实例注入、初始化锁、配置继承 |
| dadastory/dify-plugin-lightrag | 566079ca6b6d1de4679e3ebca50e3730d113d518 | API 未识别，未核实授权 | 仅参考 HTTP 集成思路；不直接迁入 |

远端 SHA 与许可证通过 GitHub API 核对；网络源码阅读来自当时默认分支，正式摘取前须针对固定 SHA 再核对文件和哈希。已知本机 SDK 为 1.5.7，不把远端 main 当作可无条件升级版本。

## 1. 官方 LightRAG：部署布局最值得借鉴

实际读取 `docker-compose.yml`：分别挂载 `data/rag_storage`、`data/inputs`、`data/prompts`，容器通过 WORKING_DIR、INPUT_DIR、PROMPT_DIR 显式指定固定路径；模型配置单独提供。

适用本项目的思路是分清资源职责：

```text
固定提交的应用代码
完整宿主教材目录（含既有 Q2 索引、导航和原图）
LightRAG 候选（图谱、向量、workspace、bundle、sidecar）
模型缓存
学生数据库
私有模型配置
```

这些资源独立登记和挂载，不能以建图 input 快照替代宿主全部运行资源。部署代码更新不应隐式挪动或重建数据。

限制：官方 Compose 示例用 latest，若实际采用必须固定兼容版本/镜像摘要。Linux 固定挂载点不能自动解析旧 Windows E: 盘绝对 URI，仍需现有迁移适配；容器可重复部署也不等于来源绑定已经正确。

可参考配置和目录约定，不建议为修复当前少数问题立即引入 Docker 并改变操作系统路径语义。

来源：[Compose](https://github.com/HKUDS/LightRAG/blob/aaebfe1bb8d55deb6a4304d357a3bf4c92fcd40a/docker-compose.yml)、[部署文档](https://github.com/HKUDS/LightRAG/blob/aaebfe1bb8d55deb6a4304d357a3bf4c92fcd40a/docs/DockerDeployment.md)。

## 2. DeepTutor：原生与服务两种接入都已存在

### 原生方式

`deeptutor/services/rag/pipelines/lightrag/engine.py` 的 workspace_for、initialize、finalize；storage.py 的 latest_published_root 和 embedding 兼容检查；ingress.py 的逐文档冻结与核验。本项目已经复用较多，不需要再次迁入完整知识库管理应用。

它避免“搬目录后 workspace 变了”，但 parser.py 仍保存 sidecar URI，不能声称完整解决了所有目录搬迁问题。

### HTTP 检索服务方式

新增核对到的现成文件：

- `D:\deeptutor\deeptutor\services\rag\pipelines\lightrag_server\client.py`
- 同目录 `probe.py`、`config.py`、`pipeline.py`

`LightRagServerClient` 是只依赖 httpx 的薄异步客户端，支持注入 transport。query_context 调用 POST /query，带 only_need_context=true，不让服务端再次生成答案。probe_server 分开检查可达性、LightRAG 服务身份、认证要求和 key 是否有效，避免把各种失败都叫作“密钥错误”。这些错误分类和只读探测值得参考。

限制：当前客户端映射 references 主要保留 reference_id/file_path，不能满足本项目块级证据、字符范围、版本、媒体和关系来源链。不能用它直接替换当前 SourceRef 发布链。

若后续确需把 native 依赖移出宿主，可参考它的 HTTP/配置/探测部分，并使用兼容版本的结构化检索接口，把现有 source_map、attach_provenance、Q2 引用门禁保留。原生 API 的来源字段是否完整仍需验证；特别是 SDK sidecar 指针不能仅凭接口名假定存在。

官方当前 query_routes.py 提供结构化检索实现，作为服务化候选的核对入口，而非本轮已验证替代品：[API 源码](https://github.com/HKUDS/LightRAG/blob/aaebfe1bb8d55deb6a4304d357a3bf4c92fcd40a/lightrag/api/routers/query_routes.py)。

## 3. RAG-Anything：复用已有实例，无需重建

README 的 Loading Existing LightRAG Instance 示例创建指向既有存储的 LightRAG，初始化后传给 RAGAnything(lightrag=...)。raganything.py 的 _ensure_lightrag_initialized/_initialize_lightrag 使用初始化锁，已有实例分支继承模型与 embedding 并按状态初始化存储。

值得借鉴：初始化入口唯一、传递明确实例、避免配置和生命周期重复管理。本项目不需要为了采用这个思路安装整套 RAG-Anything。

不能直接解决：本项目教材冻结清单、Q2 索引启动依赖、旧 sidecar URI、验收脚本 query 全局重绑定。现有 LightRAG 版本已集成部分多模态功能，新增框架还会扩大依赖和验证范围。

来源：[已有实例示例](https://github.com/HKUDS/RAG-Anything/blob/afb67c43d391b1b1008a6fee9f020a232067b9e5/README.md)、[实际初始化源码](https://github.com/HKUDS/RAG-Anything/blob/afb67c43d391b1b1008a6fee9f020a232067b9e5/raganything/raganything.py)。

## 4. Dify 插件：不适合作为当前替换方案

核对 models/llm/llm.py：通过 httpx 请求 /query 和 /query/stream，主要把 response 文本转换为 Dify LLMResult/LLMResultChunk。它面向把 LightRAG 当作回答模型，当前需要的检索数据、块级原文和引用核验不能由该文本转发承担。

该项目没有从 API 核实到许可证；本轮不推荐直接复制。即使解决授权，迁入 Dify SDK 和 LLMResult 类型也增加无关依赖。

来源：[插件源码](https://github.com/dadastory/dify-plugin-lightrag/blob/566079ca6b6d1de4679e3ebca50e3730d113d518/models/llm/llm.py)。

## 推荐执行顺序

1. 先修复已实证的验收启动器递归，唯一原函数引用；不靠换框架掩盖它。
2. 保留现有原生 LightRAG 接入和 Q2 证据链；以最新稳定提交、完整宿主资源、候选副本完成独立部署。
3. 借鉴官方布局，登记代码、宿主教材、图谱、模型缓存、数据库各自身份；借鉴 DeepTutor 区分连接/认证/存储/来源失败。
4. 验收通过后再考虑服务化。只有原生依赖/运行隔离仍有实际维护问题时，采用 DeepTutor HTTP 客户端的必要部分，继续保留结构化来源适配，不并行引入第二套回答链。

本轮查阅源码和文档，没有运行上述远端项目、容器或迁入代码；“可参考/可摘取”不等于与当前候选兼容已通过。agent-reach CLI 本机不可用，按技能指定的 GitHub CLI 与 Jina 网页读取方式完成资料获取。
