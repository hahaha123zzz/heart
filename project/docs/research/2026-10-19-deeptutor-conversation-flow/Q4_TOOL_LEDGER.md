# Q4 工具与循环扩展迁入台账

日期：2026-10-19。固定源码：`6cf793bd868ba5ecbe64722936d4be8fab5a01df`（D:\deeptutor）。本台账由 `scripts/audit_q4_tools.py` 从 SOURCE_AUDIT.json、LOCAL_MIGRATION_MAP.json 和当前运行目录生成；100 个工具与 14 个扩展逐项保留。

状态口径：**已可运行（隔离验证）**表示本项目已有迁入实现并在隔离资源上通过测试，不等于已接入 Q3 生产任务；**缺配置**表示实现依赖外部服务/凭据/数据；**待接业务**表示依赖尚未建立的 Q2/Q3/Q5/Q6 业务接口；**不适用**表示上游产品面与本项目部署冲突或平台不可用，保留台账但不以空实现冒充完成。

## 汇总

| 状态 | 工具 | 扩展 |
| --- | ---: | ---: |
| 已可运行（隔离验证） | 4 | 0 |
| 缺配置 | 27 | 3 |
| 待接业务 | 53 | 7 |
| 不适用 | 16 | 4 |
| **合计** | **100** | **14** |

## 已迁入文件与验证入口

- `agents/tools/protocol.py`：工具 schema/结果/查找协议（上游 `core/tool_protocol.py` 适配）。
- `agents/tools/registry.py`：惰性注册、别名、动态 entry point、进程注册表与按授权视图。
- `agents/tools/scope.py`：`Allowlist`、`ToolGrant`、`ToolScope`，由授权代理在 `run` 再次校验。
- `agents/tools/validation.py`：JSON 解析、必填/类型/枚举/未知参数检查和有限类型归一。
- `agents/tools/loader.py`：deferred schema 动态加载、同轮 live schema、会话持久化回调。
- `agents/tools/mounting.py`：按场景/上下文/扩展挂载，避免把全部工具强开给通用循环。
- `agents/tools/extensions.py`：14 个扩展的激活条件、owned tools 与阶段。
- `agents/tools/dispatch.py`：Q3 `tool_dispatch` 的薄桥接；Q4 不再实现第二套调度器。
- `agents/tools/workspace_tools.py`、`skill_tools.py`：已迁入的只读工具。
- `tests/test_q4_tool_foundation.py`：45 项隔离测试（未合并 Q3 时 1 项自动跳过）；另用 Q3 实际协议与调度做过联调。

复现（在集成目录、已激活本项目虚拟环境）：

```powershell
$env:PYTHONPATH=(Get-Location).Path
python -B -m unittest tests.test_q4_tool_foundation -v
```

## 100 个内置工具

### 已可运行（隔离验证）（4）

| 工具 | 阶段 | 来源与依据 | 依赖/下一步 |
| --- | --- | --- | --- |
| `read_skill` | Q4 | `deeptutor/tools/builtin/__init__.py:1714`；源文件存在；类名匹配；审计行 1714/2095；已迁入并用临时技能包及项目真实 visualization/skills 完成读取、名称校验和路径逃逸拒绝测试。 | agents/tools/skill_tools.py; tests/test_q4_tool_foundation.py; scope skills:read；Q3 注入任务技能根；真实 visualization/skills 已做只读验证。 |
| `workspace_list` | Q4 | `deeptutor/tools/workspace.py:25`；源文件存在；类名匹配；审计行 25/336；已迁入并用手工创建的隔离工作区完成列表/读取/搜索、路径逃逸与二进制拒绝测试。 | agents/tools/workspace_tools.py; tests/test_q4_tool_foundation.py; scope workspace:read；Q3 在任务上下文中注入 per-task workspace root；未绑定即失败关闭。 |
| `workspace_read` | Q4 | `deeptutor/tools/workspace.py:73`；源文件存在；类名匹配；审计行 73/336；已迁入并用手工创建的隔离工作区完成列表/读取/搜索、路径逃逸与二进制拒绝测试。 | agents/tools/workspace_tools.py; tests/test_q4_tool_foundation.py; scope workspace:read；Q3 在任务上下文中注入 per-task workspace root；未绑定即失败关闭。 |
| `workspace_search` | Q4 | `deeptutor/tools/workspace.py:116`；源文件存在；类名匹配；审计行 116/336；已迁入并用手工创建的隔离工作区完成列表/读取/搜索、路径逃逸与二进制拒绝测试。 | agents/tools/workspace_tools.py; tests/test_q4_tool_foundation.py; scope workspace:read；Q3 在任务上下文中注入 per-task workspace root；未绑定即失败关闭。 |

### 缺配置（27）

| 工具 | 阶段 | 来源与依据 | 依赖/下一步 |
| --- | --- | --- | --- |
| `web_search` | Q4 | `deeptutor/tools/builtin/__init__.py:483`；源文件存在；类名匹配；审计行 483/2095；需要搜索服务商与 API key；项目未配置 deeptutor/services/search 或 model_catalog 搜索 provider。 | services/search/*; SEARCH_API_KEY_ENV; data/user/settings/model_catalog.json；Q4 配置搜索 provider 后接 WebSearchTool；无凭据时保持缺配置。 |
| `paper_search` | Q4 | `deeptutor/tools/builtin/__init__.py:561`；源文件存在；类名匹配；审计行 561/2095；需要 arXiv 网络出口；当前没有工具级网络策略与 arXiv 客户端迁移。 | tools/paper_search_tool.py; arXiv API; 网络出口策略；Q4 接 arXiv 客户端与出口白名单，验证超时/限流。 |
| `zotero_search` | Q4 | `deeptutor/tools/builtin/__init__.py:641`；源文件存在；类名匹配；审计行 641/2095；需要 Zotero 用户 ID 与 API key；项目没有 Zotero 凭据。 | tools/zotero_search.py; Zotero Web API v3; Zotero-API-Key；Q4 读取服务端 Zotero 配置并做 401/429/超时验证。 |
| `web_fetch` | Q4 | `deeptutor/tools/builtin/__init__.py:1100`；源文件存在；类名匹配；审计行 1100/2095；需要受控 HTTP 出口与 HTML 抽取；项目尚未定义 URL 白名单/内网拦截策略。 | tools/web_fetch.py; services/web_source/html_extractor; httpx；Q4 增加 SSRF/内网地址拦截、大小与重定向限制后再开放。 |
| `github` | Q4 | `deeptutor/tools/builtin/__init__.py:1507`；源文件存在；类名匹配；审计行 1507/2095；依赖服务器安装 gh CLI 及认证；未验证本机 gh 可用性。 | tools/github_query.py; gh CLI; GitHub token；Q4 验证 gh 安装/登录；只读动作先行，写入不自动授权。 |
| `geogebra_analysis` | Q4 | `deeptutor/tools/builtin/__init__.py:764`；源文件存在；类名匹配；审计行 764/2095；需要可用的视觉模型与图像输入；当前仅配置聊天模型，未验证视觉端点。 | VisionSolverAgent; deeptutor.services.llm.config; image_base64；Q4 配置视觉模型并用真实图像验证，失败不得返回空命令。 |
| `preprint` | Q4 | `deeptutor/tools/research_tools.py:117`；源文件存在；类名匹配；审计行 117/391；需要 ResearchClient、arXiv 网络出口、缓存与可选 GitHub token；未配置。 | services/research/primitives; path_service parse cache; github token；Q4 接研究客户端并验证 PDF/页码；失败不得伪造阅读。 |
| `research_audit` | Q4 | `deeptutor/tools/research_tools.py:219`；源文件存在；类名匹配；审计行 219/391；需要 ResearchClient、arXiv/GitHub 出口与固定 commit 读取；未配置。 | services/research/primitives; github_source/_token; ResearchClient；Q4 接研究客户端；不执行仓库代码，只做静态证据核对。 |
| `research_lit` | Q4 | `deeptutor/tools/research_tools.py:297`；源文件存在；类名匹配；审计行 297/391；需要 ResearchClient 与 arXiv 检索出口；未配置。 | services/research/primitives; arXiv API; ResearchClient；Q4 接文献检索并保留来源/摘要证据等级。 |
| `exec` | Q4 | `deeptutor/tools/exec_tool.py:36`；源文件存在；类名匹配；审计行 36/386；依赖统一沙箱、资源限制与挂载；项目没有等价沙箱服务。 | tools/exec_tool.py; services/sandbox/ExecRequest; ResourceLimits; mounts；Q4 接受控沙箱并验证命令拒绝、超时、资源限制；不得裸执行。 |
| `imagegen` | Q4 | `deeptutor/tools/media_gen_tool.py:135`；源文件存在；类名匹配；审计行 135/308；需要 imagegen 生成服务/模型目录配置；项目只配置了聊天模型。 | services/imagegen; model_catalog imagegen; media_gen_tool.py；Q4 配置生成服务并验证产物落盘；未配置时明确拒绝。 |
| `videogen` | Q4 | `deeptutor/tools/media_gen_tool.py:217`；源文件存在；类名匹配；审计行 217/308；需要 videogen 生成服务/模型目录配置；项目未配置视频生成。 | services/videogen; model_catalog videogen; media_gen_tool.py；Q4 配置生成服务并验证渲染/下载；未配置时明确拒绝。 |
| `obsidian_search` | Q4 | `deeptutor/capabilities/obsidian/tools.py:108`；源文件存在；类名匹配；审计行 108/399；需要已绑定的 Obsidian vault；本项目当前没有 vault 绑定。 | capabilities/obsidian/vault.py; vault_for_turn; vault path；Q4 接 vault 绑定；先只读工具，再单独授权写入工具。 |
| `obsidian_read` | Q4 | `deeptutor/capabilities/obsidian/tools.py:140`；源文件存在；类名匹配；审计行 140/399；需要已绑定的 Obsidian vault；本项目当前没有 vault 绑定。 | capabilities/obsidian/vault.py; vault_for_turn; vault path；Q4 接 vault 绑定；先只读工具，再单独授权写入工具。 |
| `obsidian_list` | Q4 | `deeptutor/capabilities/obsidian/tools.py:167`；源文件存在；类名匹配；审计行 167/399；需要已绑定的 Obsidian vault；本项目当前没有 vault 绑定。 | capabilities/obsidian/vault.py; vault_for_turn; vault path；Q4 接 vault 绑定；先只读工具，再单独授权写入工具。 |
| `obsidian_backlinks` | Q4 | `deeptutor/capabilities/obsidian/tools.py:200`；源文件存在；类名匹配；审计行 200/399；需要已绑定的 Obsidian vault；本项目当前没有 vault 绑定。 | capabilities/obsidian/vault.py; vault_for_turn; vault path；Q4 接 vault 绑定；先只读工具，再单独授权写入工具。 |
| `obsidian_links` | Q4 | `deeptutor/capabilities/obsidian/tools.py:224`；源文件存在；类名匹配；审计行 224/399；需要已绑定的 Obsidian vault；本项目当前没有 vault 绑定。 | capabilities/obsidian/vault.py; vault_for_turn; vault path；Q4 接 vault 绑定；先只读工具，再单独授权写入工具。 |
| `obsidian_tags` | Q4 | `deeptutor/capabilities/obsidian/tools.py:247`；源文件存在；类名匹配；审计行 247/399；需要已绑定的 Obsidian vault；本项目当前没有 vault 绑定。 | capabilities/obsidian/vault.py; vault_for_turn; vault path；Q4 接 vault 绑定；先只读工具，再单独授权写入工具。 |
| `obsidian_create_note` | Q4 | `deeptutor/capabilities/obsidian/tools.py:274`；源文件存在；类名匹配；审计行 274/399；需要已绑定的 Obsidian vault；本项目当前没有 vault 绑定。 | capabilities/obsidian/vault.py; vault_for_turn; vault path；Q4 接 vault 绑定；先只读工具，再单独授权写入工具。 |
| `obsidian_append` | Q4 | `deeptutor/capabilities/obsidian/tools.py:323`；源文件存在；类名匹配；审计行 323/399；需要已绑定的 Obsidian vault；本项目当前没有 vault 绑定。 | capabilities/obsidian/vault.py; vault_for_turn; vault path；Q4 接 vault 绑定；先只读工具，再单独授权写入工具。 |
| `obsidian_set_property` | Q4 | `deeptutor/capabilities/obsidian/tools.py:347`；源文件存在；类名匹配；审计行 347/399；需要已绑定的 Obsidian vault；本项目当前没有 vault 绑定。 | capabilities/obsidian/vault.py; vault_for_turn; vault path；Q4 接 vault 绑定；先只读工具，再单独授权写入工具。 |
| `consult_subagent` | Q4 | `deeptutor/capabilities/subagent/tools.py:43`；源文件存在；类名匹配；审计行 43/254；需要已配置的外部 Agent 运行器与连接；本项目未安装/登录任何外部 Agent。 | capabilities/subagent/tools.py; services/subagent/get_backend; connection registry；Q4 配置连接后验证预算、超时和真实就绪状态。 |
| `ima_list` | Q4 | `deeptutor/capabilities/ima/tools.py:119`；源文件存在；类名匹配；审计行 119/476；需要腾讯 IMA 知识库绑定与有效凭据；本项目未配置 IMA。 | capabilities/ima/binding; services/rag/pipelines/ima; IMA credentials；Q4 接 IMA 绑定；查询与写入分别授权，写入不自动执行。 |
| `ima_read` | Q4 | `deeptutor/capabilities/ima/tools.py:184`；源文件存在；类名匹配；审计行 184/476；需要腾讯 IMA 知识库绑定与有效凭据；本项目未配置 IMA。 | capabilities/ima/binding; services/rag/pipelines/ima; IMA credentials；Q4 接 IMA 绑定；查询与写入分别授权，写入不自动执行。 |
| `ima_note_search` | Q4 | `deeptutor/capabilities/ima/tools.py:232`；源文件存在；类名匹配；审计行 232/476；需要腾讯 IMA 知识库绑定与有效凭据；本项目未配置 IMA。 | capabilities/ima/binding; services/rag/pipelines/ima; IMA credentials；Q4 接 IMA 绑定；查询与写入分别授权，写入不自动执行。 |
| `ima_add_url` | Q4 | `deeptutor/capabilities/ima/tools.py:298`；源文件存在；类名匹配；审计行 298/476；需要腾讯 IMA 知识库绑定与有效凭据；本项目未配置 IMA。 | capabilities/ima/binding; services/rag/pipelines/ima; IMA credentials；Q4 接 IMA 绑定；查询与写入分别授权，写入不自动执行。 |
| `ima_write_note` | Q4 | `deeptutor/capabilities/ima/tools.py:354`；源文件存在；类名匹配；审计行 354/476；需要腾讯 IMA 知识库绑定与有效凭据；本项目未配置 IMA。 | capabilities/ima/binding; services/rag/pipelines/ima; IMA credentials；Q4 接 IMA 绑定；查询与写入分别授权，写入不自动执行。 |

### 待接业务（53）

| 工具 | 阶段 | 来源与依据 | 依赖/下一步 |
| --- | --- | --- | --- |
| `brainstorm` | Q4 | `deeptutor/tools/builtin/__init__.py:33`；源文件存在；类名匹配；审计行 33/2095；依赖项目 LLMClient 与 Q3 工具调用协议；Q3 契约已建立，工具适配尚未迁移。 | llm/client.py; Q3 tool protocol; tools/brainstorm.py；按 Q3 契约接模型/工具协议后迁入；保留多方案与理由输出。 |
| `rag` | Q2 | `deeptutor/tools/builtin/__init__.py:105`；源文件存在；类名匹配；审计行 105/2095；Q2 已有本地混合检索/重排模块，但尚未提供工具侧检索、来源映射和证据返回接口。 | knowledge/hybrid_retrieval.py; knowledge/psychology_retrieval.py; Q2 source/evidence mapping；Q2 暴露检索接口后接 RAGTool；不得把上游 node_id 冒充本项目 chunk_id。 |
| `kb_files` | Q2 | `deeptutor/tools/builtin/__init__.py:304`；源文件存在；类名匹配；审计行 304/2095；依赖 Q2 教材清单/版本发布接口；当前没有工具侧知识库枚举。 | knowledge/course.py; Q2 manifest/publish; knowledge_frontier；Q2 发布清单就绪后接只读枚举。 |
| `knowledge_frontier` | Q2 | `deeptutor/tools/builtin/__init__.py:400`；源文件存在；类名匹配；审计行 400/2095；依赖 Q2 知识库清单与 frontier 服务；当前只有本地检索模块。 | knowledge/course.py; tools/knowledge_frontier.py; Q2 manifest；Q2 接清单/探索接口并验证空库与未命中。 |
| `reason` | Q4 | `deeptutor/tools/builtin/__init__.py:523`；源文件存在；类名匹配；审计行 523/2095；依赖项目推理模型配置与 Q3 工具调用协议；Q3 契约已建立，尚未迁移适配。 | llm/client.py; model config; tools/reason.py；按 Q3 契约接模型/工具协议后迁入；无专用推理模型时明确降级/拒绝。 |
| `read_source` | Q3 | `deeptutor/tools/builtin/__init__.py:898`；源文件存在；类名匹配；审计行 898/2095；依赖 Q3 source_index 与来源读取协议；Q3 契约已建立，来源读取尚未接本项目任务。 | Q3 source_index; read_source binding; task context；按 Q3 契约接来源身份后做只读读取；普通回答循环不得无条件挂载。 |
| `read_memory` | Q5 | `deeptutor/tools/builtin/__init__.py:965`；源文件存在；类名匹配；审计行 965/2095；依赖 Q5 记忆/笔记/题库/学习日志业务与删除语义；Q5 未开始。 | memory/; database/; memory_api.py; Q5 deletion/epoch；Q5 接项目数据仓库与删除/遗忘语义，不复制上游账户存储。 |
| `write_memory` | Q5 | `deeptutor/tools/builtin/__init__.py:995`；源文件存在；类名匹配；审计行 995/2095；依赖 Q5 记忆/笔记/题库/学习日志业务与删除语义；Q5 未开始。 | memory/; database/; memory_api.py; Q5 deletion/epoch；Q5 接项目数据仓库与删除/遗忘语义，不复制上游账户存储。 |
| `load_tools` | Q4 | `deeptutor/tools/builtin/__init__.py:1808`；源文件存在；类名匹配；审计行 1808/2095；加载器、同轮 schema 追加和 Q3 registry 挂载已用替身 deferred tool 验证；尚无真实 MCP/CLI provider，不能标为动态外部工具可用。 | agents/tools/loader.py; agents/tools/skill_tools.py; ScopedToolRegistry.mount_tool; entry points heart.tools；Q4 配置真实 MCP/CLI provider 后做端到端验证；当前不冒充。 |
| `list_notebook` | Q5 | `deeptutor/tools/builtin/__init__.py:1164`；源文件存在；类名匹配；审计行 1164/2095；依赖 Q5 记忆/笔记/题库/学习日志业务与删除语义；Q5 未开始。 | memory/; database/; memory_api.py; Q5 deletion/epoch；Q5 接项目数据仓库与删除/遗忘语义，不复制上游账户存储。 |
| `write_note` | Q5 | `deeptutor/tools/builtin/__init__.py:1381`；源文件存在；类名匹配；审计行 1381/2095；依赖 Q5 记忆/笔记/题库/学习日志业务与删除语义；Q5 未开始。 | memory/; database/; memory_api.py; Q5 deletion/epoch；Q5 接项目数据仓库与删除/遗忘语义，不复制上游账户存储。 |
| `question_bank` | Q5 | `deeptutor/tools/builtin/__init__.py:1214`；源文件存在；类名匹配；审计行 1214/2095；依赖 Q5 记忆/笔记/题库/学习日志业务与删除语义；Q5 未开始。 | memory/; database/; memory_api.py; Q5 deletion/epoch；Q5 接项目数据仓库与删除/遗忘语义，不复制上游账户存储。 |
| `ask_user` | Q3 | `deeptutor/tools/builtin/__init__.py:1570`；源文件存在；类名匹配；审计行 1570/2095；依赖 Q3 问题卡、任务/修订/命令身份和答复续跑；Q3 契约已建立，尚未接本项目任务链路。 | Q3 task identity; ask_user payload; SSE; reply/cancel commands；按 Q3 契约接任务链路；刷新/重复答复不得重复执行。 |
| `cron` | Q4 | `deeptutor/tools/builtin/__init__.py:1866`；源文件存在；类名匹配；审计行 1866/2095；依赖项目定时任务存储、所有者范围和结果投递；当前没有等价调度服务。 | services/cron equivalent; task store; delivery/SSE；Q4/Q5 建所有者隔离的调度存储后再开放；外发/定时执行需显式授权。 |
| `learning_status` | Q5 | `deeptutor/tools/learning_journal_tools.py:16`；源文件存在；类名匹配；审计行 16/173；依赖 Q5 记忆/笔记/题库/学习日志业务与删除语义；Q5 未开始。 | memory/; database/; memory_api.py; Q5 deletion/epoch；Q5 接项目数据仓库与删除/遗忘语义，不复制上游账户存储。 |
| `learning_update` | Q5 | `deeptutor/tools/learning_journal_tools.py:47`；源文件存在；类名匹配；审计行 47/173；依赖 Q5 记忆/笔记/题库/学习日志业务与删除语义；Q5 未开始。 | memory/; database/; memory_api.py; Q5 deletion/epoch；Q5 接项目数据仓库与删除/遗忘语义，不复制上游账户存储。 |
| `workspace_present` | Q4 | `deeptutor/tools/workspace.py:156`；源文件存在；类名匹配；审计行 156/336；依赖 Q3 任务事件/UI 预览与工作区发布协议；当前只有只读工作区工具。 | Q3 event protocol; workspace publish service; reader/UI；Q3 事件接通后做真实卡片呈现，不以一段文本冒充预览。 |
| `workspace_export` | Q4 | `deeptutor/tools/workspace.py:219`；源文件存在；类名匹配；审计行 219/336；依赖 Q3 ask_user 一次性授权与导出执行；当前没有授权卡片/写入通道。 | Q3 ask_user; workspace export service; authorization record；Q3 接通后只执行用户批准的精确复制；不自动授权外发/覆盖。 |
| `submit_visualization` | Q6 | `deeptutor/visualizers/tool.py:22`；源文件存在；类名匹配；审计行 22/150；依赖 Q6 可视化载荷校验、Viewer 和产物处理；Q6 未开始。 | visualization/; visualization-client/; Q6 payload validator；Q6 接载荷校验与 Viewer；无效载荷不得空画布冒充成功。 |
| `mastery_topics` | Q5 | `deeptutor/tools/mastery_nav.py:206`；源文件存在；类名匹配；审计行 206/500；依赖 Q5 掌握学习状态、attempt/evidence、题卡与评分；Q5 未开始。 | agents/learning; database; practice_api; Q5 attempt/evidence；Q5 接掌握状态与题卡；每次作答只记一次事实。 |
| `mastery_sessions` | Q5 | `deeptutor/tools/mastery_nav.py:255`；源文件存在；类名匹配；审计行 255/500；依赖 Q5 掌握学习状态、attempt/evidence、题卡与评分；Q5 未开始。 | agents/learning; database; practice_api; Q5 attempt/evidence；Q5 接掌握状态与题卡；每次作答只记一次事实。 |
| `mastery_open_session` | Q5 | `deeptutor/tools/mastery_nav.py:306`；源文件存在；类名匹配；审计行 306/500；依赖 Q5 掌握学习状态、attempt/evidence、题卡与评分；Q5 未开始。 | agents/learning; database; practice_api; Q5 attempt/evidence；Q5 接掌握状态与题卡；每次作答只记一次事实。 |
| `mastery_new_session` | Q5 | `deeptutor/tools/mastery_nav.py:405`；源文件存在；类名匹配；审计行 405/500；依赖 Q5 掌握学习状态、attempt/evidence、题卡与评分；Q5 未开始。 | agents/learning; database; practice_api; Q5 attempt/evidence；Q5 接掌握状态与题卡；每次作答只记一次事实。 |
| `mastery_status` | Q5 | `deeptutor/capabilities/mastery/tools.py:704`；源文件存在；类名匹配；审计行 704/2886；依赖 Q5 掌握学习状态、attempt/evidence、题卡与评分；Q5 未开始。 | agents/learning; database; practice_api; Q5 attempt/evidence；Q5 接掌握状态与题卡；每次作答只记一次事实。 |
| `mastery_quiz` | Q5 | `deeptutor/capabilities/mastery/tools.py:885`；源文件存在；类名匹配；审计行 885/2886；依赖 Q5 掌握学习状态、attempt/evidence、题卡与评分；Q5 未开始。 | agents/learning; database; practice_api; Q5 attempt/evidence；Q5 接掌握状态与题卡；每次作答只记一次事实。 |
| `mastery_note_explained` | Q5 | `deeptutor/capabilities/mastery/tools.py:826`；源文件存在；类名匹配；审计行 826/2886；依赖 Q5 掌握学习状态、attempt/evidence、题卡与评分；Q5 未开始。 | agents/learning; database; practice_api; Q5 attempt/evidence；Q5 接掌握状态与题卡；每次作答只记一次事实。 |
| `mastery_grade` | Q5 | `deeptutor/capabilities/mastery/tools.py:1185`；源文件存在；类名匹配；审计行 1185/2886；依赖 Q5 掌握学习状态、attempt/evidence、题卡与评分；Q5 未开始。 | agents/learning; database; practice_api; Q5 attempt/evidence；Q5 接掌握状态与题卡；每次作答只记一次事实。 |
| `mastery_skip_question` | Q5 | `deeptutor/capabilities/mastery/tools.py:1528`；源文件存在；类名匹配；审计行 1528/2886；依赖 Q5 掌握学习状态、attempt/evidence、题卡与评分；Q5 未开始。 | agents/learning; database; practice_api; Q5 attempt/evidence；Q5 接掌握状态与题卡；每次作答只记一次事实。 |
| `mastery_repair_question` | Q5 | `deeptutor/capabilities/mastery/tools.py:1576`；源文件存在；类名匹配；审计行 1576/2886；依赖 Q5 掌握学习状态、attempt/evidence、题卡与评分；Q5 未开始。 | agents/learning; database; practice_api; Q5 attempt/evidence；Q5 接掌握状态与题卡；每次作答只记一次事实。 |
| `mastery_defer_objective` | Q5 | `deeptutor/capabilities/mastery/tools.py:1693`；源文件存在；类名匹配；审计行 1693/2886；依赖 Q5 掌握学习状态、attempt/evidence、题卡与评分；Q5 未开始。 | agents/learning; database; practice_api; Q5 attempt/evidence；Q5 接掌握状态与题卡；每次作答只记一次事实。 |
| `mastery_assess` | Q5 | `deeptutor/capabilities/mastery/tools.py:1421`；源文件存在；类名匹配；审计行 1421/2886；依赖 Q5 掌握学习状态、attempt/evidence、题卡与评分；Q5 未开始。 | agents/learning; database; practice_api; Q5 attempt/evidence；Q5 接掌握状态与题卡；每次作答只记一次事实。 |
| `mastery_build` | Q5 | `deeptutor/capabilities/mastery/tools.py:1761`；源文件存在；类名匹配；审计行 1761/2886；依赖 Q5 掌握学习状态、attempt/evidence、题卡与评分；Q5 未开始。 | agents/learning; database; practice_api; Q5 attempt/evidence；Q5 接掌握状态与题卡；每次作答只记一次事实。 |
| `mastery_mode` | Q5 | `deeptutor/capabilities/mastery/tools.py:1919`；源文件存在；类名匹配；审计行 1919/2886；依赖 Q5 掌握学习状态、attempt/evidence、题卡与评分；Q5 未开始。 | agents/learning; database; practice_api; Q5 attempt/evidence；Q5 接掌握状态与题卡；每次作答只记一次事实。 |
| `mastery_profile` | Q5 | `deeptutor/capabilities/mastery/tools.py:2013`；源文件存在；类名匹配；审计行 2013/2886；依赖 Q5 掌握学习状态、attempt/evidence、题卡与评分；Q5 未开始。 | agents/learning; database; practice_api; Q5 attempt/evidence；Q5 接掌握状态与题卡；每次作答只记一次事实。 |
| `mastery_revise` | Q5 | `deeptutor/capabilities/mastery/tools.py:2147`；源文件存在；类名匹配；审计行 2147/2886；依赖 Q5 掌握学习状态、attempt/evidence、题卡与评分；Q5 未开始。 | agents/learning; database; practice_api; Q5 attempt/evidence；Q5 接掌握状态与题卡；每次作答只记一次事实。 |
| `mastery_paths` | Q5 | `deeptutor/capabilities/mastery/tools.py:2343`；源文件存在；类名匹配；审计行 2343/2886；依赖 Q5 掌握学习状态、attempt/evidence、题卡与评分；Q5 未开始。 | agents/learning; database; practice_api; Q5 attempt/evidence；Q5 接掌握状态与题卡；每次作答只记一次事实。 |
| `mastery_switch` | Q5 | `deeptutor/capabilities/mastery/tools.py:2384`；源文件存在；类名匹配；审计行 2384/2886；依赖 Q5 掌握学习状态、attempt/evidence、题卡与评分；Q5 未开始。 | agents/learning; database; practice_api; Q5 attempt/evidence；Q5 接掌握状态与题卡；每次作答只记一次事实。 |
| `mastery_leave` | Q5 | `deeptutor/capabilities/mastery/tools.py:2447`；源文件存在；类名匹配；审计行 2447/2886；依赖 Q5 掌握学习状态、attempt/evidence、题卡与评分；Q5 未开始。 | agents/learning; database; practice_api; Q5 attempt/evidence；Q5 接掌握状态与题卡；每次作答只记一次事实。 |
| `solve_plan` | Q6 | `deeptutor/capabilities/solve/tools.py:77`；源文件存在；类名匹配；审计行 77/291；依赖 Q5/Q6 解题引擎状态与 Q3 循环；当前没有 solve 状态工具。 | capabilities/solve; Q3 loop; Q5/Q6 solve engine；Q5/Q6 接计划/步骤/重规划预算；模型文字不得替代状态门槛。 |
| `solve_finish_step` | Q6 | `deeptutor/capabilities/solve/tools.py:139`；源文件存在；类名匹配；审计行 139/291；依赖 solve 计划状态与步骤核验；当前没有 solve 引擎。 | capabilities/solve; Q3 loop; Q5/Q6 solve engine；Q5/Q6 接步骤完成校验；不能跳过状态门槛。 |
| `solve_replan` | Q6 | `deeptutor/capabilities/solve/tools.py:206`；源文件存在；类名匹配；审计行 206/291；依赖 solve 预算与重规划状态；当前没有 solve 引擎。 | capabilities/solve; Q3 loop; Q5/Q6 solve engine；Q5/Q6 接受限重规划，失败保留真实状态。 |
| `reading_list_tabs` | Q5 | `deeptutor/capabilities/reading/tools.py:67`；源文件存在；类名匹配；审计行 67/680；依赖 Q5 阅读器目录/原图/跳转/批注与当前材料绑定；Q5 未开始。 | reader/; knowledge/pdf_reader.py; Q5 reading state；Q5 接现有阅读器；空材料/失效 revision 不得伪造内容。 |
| `reading_switch_tab` | Q5 | `deeptutor/capabilities/reading/tools.py:120`；源文件存在；类名匹配；审计行 120/680；依赖 Q5 阅读器目录/原图/跳转/批注与当前材料绑定；Q5 未开始。 | reader/; knowledge/pdf_reader.py; Q5 reading state；Q5 接现有阅读器；空材料/失效 revision 不得伪造内容。 |
| `material_outline` | Q5 | `deeptutor/capabilities/reading/tools.py:171`；源文件存在；类名匹配；审计行 171/680；依赖 Q5 阅读器目录/原图/跳转/批注与当前材料绑定；Q5 未开始。 | reader/; knowledge/pdf_reader.py; Q5 reading state；Q5 接现有阅读器；空材料/失效 revision 不得伪造内容。 |
| `search_material` | Q5 | `deeptutor/capabilities/reading/tools.py:199`；源文件存在；类名匹配；审计行 199/680；依赖 Q5 阅读器目录/原图/跳转/批注与当前材料绑定；Q5 未开始。 | reader/; knowledge/pdf_reader.py; Q5 reading state；Q5 接现有阅读器；空材料/失效 revision 不得伪造内容。 |
| `read_material` | Q5 | `deeptutor/capabilities/reading/tools.py:311`；源文件存在；类名匹配；审计行 311/680；依赖 Q5 阅读器目录/原图/跳转/批注与当前材料绑定；Q5 未开始。 | reader/; knowledge/pdf_reader.py; Q5 reading state；Q5 接现有阅读器；空材料/失效 revision 不得伪造内容。 |
| `view_figure` | Q5 | `deeptutor/capabilities/reading/figure_view.py:31`；源文件存在；类名匹配；审计行 31/180；依赖 Q5 阅读器目录/原图/跳转/批注与当前材料绑定；Q5 未开始。 | reader/; knowledge/pdf_reader.py; Q5 reading state；Q5 接现有阅读器；空材料/失效 revision 不得伪造内容。 |
| `reader_goto` | Q5 | `deeptutor/capabilities/reading/tools.py:405`；源文件存在；类名匹配；审计行 405/680；依赖 Q5 阅读器目录/原图/跳转/批注与当前材料绑定；Q5 未开始。 | reader/; knowledge/pdf_reader.py; Q5 reading state；Q5 接现有阅读器；空材料/失效 revision 不得伪造内容。 |
| `reader_annotate` | Q5 | `deeptutor/capabilities/reading/tools.py:491`；源文件存在；类名匹配；审计行 491/680；依赖 Q5 阅读器目录/原图/跳转/批注与当前材料绑定；Q5 未开始。 | reader/; knowledge/pdf_reader.py; Q5 reading state；Q5 接现有阅读器；空材料/失效 revision 不得伪造内容。 |
| `course_overview` | Q5 | `deeptutor/capabilities/course_study/tools.py:560`；源文件存在；类名匹配；审计行 560/786；依赖 Q5 课程绑定、课程状态与学习入口；Q5 未开始。 | knowledge/course.py; Q5 course binding; reader/learning UI；Q5 接课程状态与可操作交接；无课程时明确缺口。 |
| `course_material` | Q5 | `deeptutor/capabilities/course_study/tools.py:577`；源文件存在；类名匹配；审计行 577/786；依赖 Q5 课程绑定、课程状态与学习入口；Q5 未开始。 | knowledge/course.py; Q5 course binding; reader/learning UI；Q5 接课程状态与可操作交接；无课程时明确缺口。 |
| `course_edit` | Q5 | `deeptutor/capabilities/course_study/tools.py:603`；源文件存在；类名匹配；审计行 603/786；依赖 Q5 课程绑定、课程状态与学习入口；Q5 未开始。 | knowledge/course.py; Q5 course binding; reader/learning UI；Q5 接课程状态与可操作交接；无课程时明确缺口。 |
| `course_handoff` | Q5 | `deeptutor/capabilities/course_study/tools.py:716`；源文件存在；类名匹配；审计行 716/786；依赖 Q5 课程绑定、课程状态与学习入口；Q5 未开始。 | knowledge/course.py; Q5 course binding; reader/learning UI；Q5 接课程状态与可操作交接；无课程时明确缺口。 |

### 不适用（16）

| 工具 | 阶段 | 来源与依据 | 依赖/下一步 |
| --- | --- | --- | --- |
| `marginnote_search` | Q4 | `deeptutor/capabilities/marginnote4/tools.py:98`；源文件存在；类名匹配；审计行 98/329；MarginNote 4 是 macOS/iOS 本地应用；当前 Windows 部署没有本地库或绑定。 | capabilities/marginnote4/store; MarginNote local library；保留台账；平台不适用，不以空实现冒充可用。 |
| `marginnote_read` | Q4 | `deeptutor/capabilities/marginnote4/tools.py:144`；源文件存在；类名匹配；审计行 144/329；MarginNote 4 是 macOS/iOS 本地应用；当前 Windows 部署没有本地库或绑定。 | capabilities/marginnote4/store; MarginNote local library；保留台账；平台不适用，不以空实现冒充可用。 |
| `marginnote_list` | Q4 | `deeptutor/capabilities/marginnote4/tools.py:175`；源文件存在；类名匹配；审计行 175/329；MarginNote 4 是 macOS/iOS 本地应用；当前 Windows 部署没有本地库或绑定。 | capabilities/marginnote4/store; MarginNote local library；保留台账；平台不适用，不以空实现冒充可用。 |
| `marginnote_documents` | Q4 | `deeptutor/capabilities/marginnote4/tools.py:217`；源文件存在；类名匹配；审计行 217/329；MarginNote 4 是 macOS/iOS 本地应用；当前 Windows 部署没有本地库或绑定。 | capabilities/marginnote4/store; MarginNote local library；保留台账；平台不适用，不以空实现冒充可用。 |
| `marginnote_links` | Q4 | `deeptutor/capabilities/marginnote4/tools.py:236`；源文件存在；类名匹配；审计行 236/329；MarginNote 4 是 macOS/iOS 本地应用；当前 Windows 部署没有本地库或绑定。 | capabilities/marginnote4/store; MarginNote local library；保留台账；平台不适用，不以空实现冒充可用。 |
| `marginnote_tags` | Q4 | `deeptutor/capabilities/marginnote4/tools.py:265`；源文件存在；类名匹配；审计行 265/329；MarginNote 4 是 macOS/iOS 本地应用；当前 Windows 部署没有本地库或绑定。 | capabilities/marginnote4/store; MarginNote local library；保留台账；平台不适用，不以空实现冒充可用。 |
| `marginnote_cards` | Q4 | `deeptutor/capabilities/marginnote4/tools.py:291`；源文件存在；类名匹配；审计行 291/329；MarginNote 4 是 macOS/iOS 本地应用；当前 Windows 部署没有本地库或绑定。 | capabilities/marginnote4/store; MarginNote local library；保留台账；平台不适用，不以空实现冒充可用。 |
| `inspect_setup` | Q4 | `deeptutor/capabilities/setup/tools.py:66`；源文件存在；类名匹配；审计行 66/345；本项目已有 .env/管理员配置权威；上游设置 UI 与凭据采集会形成第二套配置权威。 | capabilities/setup/*; data/user/settings; credential UI；保留台账；如未来需要只读设置检查，另做项目设置适配，不迁入凭据写入。 |
| `apply_setting` | Q4 | `deeptutor/capabilities/setup/tools.py:161`；源文件存在；类名匹配；审计行 161/345；本项目已有 .env/管理员配置权威；上游设置 UI 与凭据采集会形成第二套配置权威。 | capabilities/setup/*; data/user/settings; credential UI；保留台账；如未来需要只读设置检查，另做项目设置适配，不迁入凭据写入。 |
| `request_credential` | Q4 | `deeptutor/capabilities/setup/tools.py:213`；源文件存在；类名匹配；审计行 213/345；本项目已有 .env/管理员配置权威；上游设置 UI 与凭据采集会形成第二套配置权威。 | capabilities/setup/*; data/user/settings; credential UI；保留台账；如未来需要只读设置检查，另做项目设置适配，不迁入凭据写入。 |
| `run_setup_job` | Q4 | `deeptutor/capabilities/setup/tools.py:273`；源文件存在；类名匹配；审计行 273/345；本项目已有 .env/管理员配置权威；上游设置 UI 与凭据采集会形成第二套配置权威。 | capabilities/setup/*; data/user/settings; credential UI；保留台账；如未来需要只读设置检查，另做项目设置适配，不迁入凭据写入。 |
| `propose_partner` | Q4 | `deeptutor/capabilities/partner_authoring/tools.py:14`；源文件存在；类名匹配；审计行 14/83；本项目已有 .env/管理员配置权威；上游设置 UI 与凭据采集会形成第二套配置权威。 | capabilities/setup/*; data/user/settings; credential UI；保留台账；如未来需要只读设置检查，另做项目设置适配，不迁入凭据写入。 |
| `invoke_other` | Q4 | `deeptutor/capabilities/partner_group/tools.py:14`；源文件存在；类名匹配；审计行 14/162；本项目已有 .env/管理员配置权威；上游设置 UI 与凭据采集会形成第二套配置权威。 | capabilities/setup/*; data/user/settings; credential UI；保留台账；如未来需要只读设置检查，另做项目设置适配，不迁入凭据写入。 |
| `partner_read` | Q4 | `deeptutor/tools/partner_memory.py:87`；源文件存在；类名匹配；审计行 87/315；本项目没有伙伴/IM 账户与会话产品面；迁入会复制第二套账户/会话存储。 | services/partners/*; partner sessions; partner memory；保留台账；不迁入伙伴账户/IM 连接器。 |
| `partner_memorize` | Q4 | `deeptutor/tools/partner_memory.py:127`；源文件存在；类名匹配；审计行 127/315；本项目没有伙伴/IM 账户与会话产品面；迁入会复制第二套账户/会话存储。 | services/partners/*; partner sessions; partner memory；保留台账；不迁入伙伴账户/IM 连接器。 |
| `partner_search` | Q4 | `deeptutor/tools/partner_memory.py:222`；源文件存在；类名匹配；审计行 222/315；本项目没有伙伴/IM 账户与会话产品面；迁入会复制第二套账户/会话存储。 | services/partners/*; partner sessions; partner memory；保留台账；不迁入伙伴账户/IM 连接器。 |

## 14 个循环扩展

| 扩展 | 阶段 | 状态 | 激活条件 | owned tools | 依据/下一步 |
| --- | --- | --- | --- | --- | --- |
| `ask_questions` | Q3 | 待接业务 | ask_questions_mode 或 ask_questions 场景 |  | `deeptutor/capabilities/ask_questions/loop.py:12`；源文件存在；类名匹配；审计行 12/53；依赖 Q3 ask_user 问题卡、答复续跑和任务身份。；Q3 建立接口后接问题策略与恢复。 |
| `mastery` | Q5 | 待接业务 | mastery_mode 或 mastery_path 场景 | `mastery_status`, `mastery_quiz`, `mastery_note_explained`, `mastery_grade`, `mastery_skip_question`, `mastery_repair_question`, `mastery_defer_objective`, `mastery_assess`, `mastery_build`, `mastery_mode`, `mastery_profile`, `mastery_revise`, `mastery_paths`, `mastery_switch`, `mastery_leave`, `read_source` | `deeptutor/capabilities/mastery/loop.py:175`；源文件存在；类名匹配；审计行 175/607；依赖 Q5 掌握状态、题卡、评分和完成门槛。；Q5 接状态与题卡；重复作答不重复推进。 |
| `solve` | Q6 | 待接业务 | solve_mode 或 deep_solve 场景 | `solve_plan`, `solve_finish_step`, `solve_replan` | `deeptutor/capabilities/solve/loop.py:22`；源文件存在；类名匹配；审计行 22/83；依赖 Q5/Q6 solve 引擎与 Q3 循环。；Q5/Q6 接计划/重规划预算。 |
| `obsidian` | Q4 | 缺配置 | 本轮存在绑定的 Obsidian vault | `obsidian_search`, `obsidian_read`, `obsidian_list`, `obsidian_backlinks`, `obsidian_links`, `obsidian_tags`, `obsidian_create_note`, `obsidian_append`, `obsidian_set_property` | `deeptutor/capabilities/obsidian/capability.py:25`；源文件存在；类名匹配；审计行 25/82；需要已绑定的 Obsidian vault；本项目无 vault 配置。；Q4 接 vault 绑定；先只读，再单独授权写入。 |
| `marginnote4` | Q4 | 不适用 | 本轮存在可访问的 MarginNote 4 绑定 | `marginnote_search`, `marginnote_read`, `marginnote_list`, `marginnote_documents`, `marginnote_links`, `marginnote_tags`, `marginnote_cards` | `deeptutor/capabilities/marginnote4/capability.py:28`；源文件存在；类名匹配；审计行 28/80；MarginNote 4 是 macOS/iOS 本地应用；当前 Windows 部署没有本地库或绑定。；保留台账；平台不适用，不以空实现冒充可用。 |
| `subagent` | Q4 | 缺配置 | 本轮存在外部 Agent 连接 | `consult_subagent` | `deeptutor/capabilities/subagent/capability.py:32`；源文件存在；类名匹配；审计行 32/251；需要外部 Agent 运行器与连接；本项目未配置。；Q4 配置后验证预算、超时与真实就绪状态。 |
| `ima` | Q4 | 缺配置 | 本轮存在 IMA 知识库绑定 | `ima_list`, `ima_read`, `ima_note_search`, `ima_add_url`, `ima_write_note` | `deeptutor/capabilities/ima/capability.py:35`；源文件存在；类名匹配；审计行 35/92；需要腾讯 IMA 知识库绑定与凭据；未配置。；Q4 接绑定；查询/写入分权。 |
| `immersive_reading` | Q5 | 待接业务 | 已打开材料/阅读工作区，或显式阅读模式 | `reading_list_tabs`, `reading_switch_tab`, `material_outline`, `search_material`, `read_material`, `view_figure`, `reader_goto`, `reader_annotate` | `deeptutor/capabilities/reading/capability.py:112`；源文件存在；类名匹配；审计行 112/497；依赖 Q5 阅读器材料/视口/原图状态。；Q5 接现有阅读器与阅读交接。 |
| `course_study` | Q5 | 待接业务 | course_study 场景且课程 ID 可解析 | `course_overview`, `course_material`, `course_edit`, `course_handoff` | `deeptutor/capabilities/course_study/capability.py:380`；源文件存在；类名匹配；审计行 380/532；依赖 Q5 课程绑定与学习入口。；Q5 接课程状态与交接。 |
| `explore_context` | Q3 | 待接业务 | source_index 非空 |  | `deeptutor/capabilities/explore_context/capability.py:82`；源文件存在；类名匹配；审计行 82/144；依赖 Q3 source_index 与只读来源调查；Q3 未开始。；Q3 接入后按来源存在条件激活。 |
| `setup` | Q4 | 不适用 | 仅设置引导上下文 | `inspect_setup`, `apply_setting`, `request_credential`, `run_setup_job` | `deeptutor/capabilities/setup/capability.py:39`；源文件存在；类名匹配；审计行 39/108；本项目已有 .env/管理员配置权威；上游设置 UI 与凭据采集会形成第二套配置权威。；保留台账；如未来需要只读设置检查，另做项目设置适配，不迁入凭据写入。 |
| `partner_authoring` | Q4 | 不适用 | 仅伙伴创建上下文 | `propose_partner` | `deeptutor/capabilities/partner_authoring/capability.py:18`；源文件存在；类名匹配；审计行 18/71；本项目没有伙伴/IM 账户与会话产品面；迁入会复制第二套账户/会话存储。；保留台账；不迁入伙伴账户/IM 连接器。 |
| `partner_group` | Q4 | 不适用 | 存在 partner_group 字典上下文 | `invoke_other` | `deeptutor/capabilities/partner_group/capability.py:18`；源文件存在；类名匹配；审计行 18/229；本项目没有伙伴/IM 账户与会话产品面；迁入会复制第二套账户/会话存储。；保留台账；不迁入伙伴账户/IM 连接器。 |
| `visualization_generation` | Q6 | 待接业务 | 已设置可视化生成模式 | `submit_visualization` | `deeptutor/visualizers/loop_capability.py:18`；源文件存在；类名匹配；审计行 18/125；依赖 Q6 可视化载荷校验、Viewer 与产物。；Q6 接载荷校验与画布产物。 |

## 明确未完成 / 不冒充项

- 已可运行工具只在隔离工作区/技能库上验证；Q3 生产任务根、技能根和事件 sink 尚未接入。
- `load_tools` 的加载器、同轮 schema 追加和 registry 挂载已用替身 deferred tool 验证；没有真实 MCP/CLI provider，因此本台账不把“动态外部工具可用”标为通过。
- 外部搜索、Zotero、arXiv/GitHub、Obsidian、IMA、外部 Agent、媒体生成、视觉和沙箱均未配置；没有执行外发、发布或第三方写入来证明功能。
- 未实现第二套 AgentLoop；Q3 契约已建立，dispatch 只执行单批工具调用，不决定循环轮数。
- 上游工具描述/行号来自固定源码审计；本台账不把注册名、文件存在或模拟返回当作能力验收。
