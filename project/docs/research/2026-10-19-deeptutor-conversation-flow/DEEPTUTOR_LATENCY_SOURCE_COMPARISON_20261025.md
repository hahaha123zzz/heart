# DeepTutor 与 8137 慢请求的源码对照

## 核对范围

- 上游：`D:\deeptutor`，提交 `6cf793bd868ba5ecbe64722936d4be8fab5a01df`；本次查看的 RAG、AgentLoop、工具源码无本地改动。
- 本项目：8137 实际运行的 `.worktrees/integration-main-20261025/project/integration/discrete-math-tutor`。
- 耗时依据：同页面用户最近三条完成请求，见 `LATENCY_8137_REAL_REQUESTS_20261025.md`。本次没有运行 DeepTutor 对照测速，不能据此声称其实际快多少秒。

## 结论

最值得借鉴的是“发布版本身份与具体资源读取分开处理”和“图片按需读取、复用已验证的图片字节”。我们的全书重复校验、全书图片目录重载是额外开销，并非 LightRAG 查询必需步骤。

必须纠正一个容易混淆的判断：DeepTutor 本地 LightRAG **没有跨查询常驻实例缓存**；其常驻的是 worker event loop。它的 LlamaIndex 后端才有显式索引缓存。不能把 LlamaIndex 的缓存当成 LightRAG 已有能力直接宣传。

## 1. 教材与索引版本校验

### DeepTutor

- `deeptutor/services/rag/pipelines/lightrag/pipeline.py:609`：选择已发布版本，绑定当前用户的向量配置，然后执行查询。
- `.../lightrag/storage.py:180`：通过元数据中的 provider、schema、published state 和输出文件存在性识别已发布版本。
- `.../lightrag/storage.py:258`：比较当前 embedding signature 与发布元数据。
- `.../lightrag/ingress.py:184`：摄取时生成不可变、带摘要的文档 bundle。
- `.../lightrag/ingress.py:304`：读取指定 bundle 时验证其文件摘要。它仍保留路径与数据身份检查，不能描述为“没有任何校验”。

本地 `search()` 没有我们这种每次查询前后扫描候选索引、冻结教材、宿主教材全目录的显式逻辑。

### 本项目

`knowledge/lightrag/retrieval.py:144` 的 `validate()` 计算候选索引摘要，并遍历冻结教材和宿主教材；`search()` 在查询前后各执行一次。最近三轮前后合计分别为 **20.970、10.031、9.703 秒**。

适配方向：完整验收放到加载/发布版本的边界；运行时查询绑定明确版本，只核验所用资源及必要控制身份。需要同时定义换版、异常改写和并发失效机制，不能直接永久缓存校验结果或只用 mtime 当作来源真实性证明。

## 2. LightRAG 实例与索引加载

### DeepTutor 本地 LightRAG

`.../lightrag/pipeline.py:635` 的每个查询 job 都调用：

```text
build_rag → initialize → query_with_sources → finalize
```

`.../lightrag/worker.py:34` 复用进程级 event loop，解决共享 asyncio 锁归属；不等于复用图谱/向量实例。`RAGService._pipelines` 缓存的也是 pipeline 外壳，不能据此推导底层 rag 实例常驻。

本项目已使用同类 worker 方案，也每轮构建/释放实例，最近 `engine.build` 为 **5.953–6.484 秒**。直接再复制上游同一段不会解决该耗时。

### 可借鉴的其他路径

- `.../llamaindex/storage.py:198`：显式缓存已加载索引，最多 2 项、空闲 10 分钟淘汰；按目录、文件 freshness token、scoped embedding 配置身份区分，加载与校验在 miss 时完成。这是可参考的缓存生命周期，但对象及校验规则不能直接用于 LightRAG。
- `.../lightrag_server/pipeline.py:76` 与 `client.py:80`：独立服务查询，`POST /query` 使用 `only_need_context=True`，聊天侧不加载本地图谱。这个连接器可复用适配，但上游连接器本身不证明服务器实例常驻、不证明本项目候选可直接部署或来源映射兼容；仍需独立部署验收。

若保持当前本地方案，应在已有同一 worker loop 中实现有限的版本实例生命周期，处理模型/凭据身份、取消、并发查询和关闭；不能把跨请求 owner/bridge 随旧实例复用。这个增强不是 DeepTutor 此版本现成实现。

## 3. 图片读取与重复全书计算

### DeepTutor

- `deeptutor/tools/builtin/__init__.py:103` 的 `RAGTool` 按 asset_id、figure、page、region 等参数选择精确视觉读取；正常语义问题走文本检索。语义结果确实携带图片资源且模型支持视觉时，也可附带原图。
- `deeptutor/services/rag/source_visuals.py:203` 的 `retrieve_visual()` 先按清单筛选指定资源；`source_state()` 校验对应源文档，`VisualAssetStore.read()` 校验实际图片尺寸/类型/摘要。
- `.../visual_assets.py:342` 返回 `(record, bytes)`；`VisualEvidence.model_message()` 直接复用已读字节构建图片消息。
- 没有发现与我们 `Figure.public() → binding() → refresh → 全书 snapshot` 对应的必经步骤。

### 本项目

- `knowledge/lightrag/retrieval.py` 对所有查询执行 `visual_inventory()`；`course_input.py:48` 每次创建独立模块，重新加载全书视觉目录，即使最终没有附图。这部分缺独立计时，不能把所有未分段时间都算给它。
- `knowledge/figures.py:48` 的 `public()` 调用 `course_release.binding()`；后者每次 `validate(refresh=True)` 清空缓存、重算全书发布身份。
- `knowledge/answer_media.py:51` 的 `current_media()` 为检查 version/document_id，对同一图调用两次 `public()`；均满足前置条件时会重复执行全书发布计算。
- 最近带图轮次 `media_selection` 为 2.906 秒、`media_payload` 为 4.282 秒。

复用建议：借鉴上游“读取一次得到身份与字节、同轮复用”的数据流；先消除同图重复元数据计算，再把全书版本重算移出图片元数据 getter。保留图片使用前的具体资源身份验证及失效返回。

## 4. 回答生成与发布检查

DeepTutor 的普通循环在 `deeptutor/agents/loop/agent_loop.py:1178` 逐段发送正文，正常结束在约 657 行调用 `_finalize_finish()`；后者清理文本并返回结果。此默认路径未见对应我们“再次调用 QualityChecker 模型审稿”的通用步骤。

但它也不是完全没有门槛：`agents/loop/pipeline.py:879` 的 capability finish hook 可拒绝尚未执行必要工具的结束；AgentLoop 最多进行一次对应的重定向。特定协议场景可缓冲/撤回输出，不能宣称 DeepTutor 从不撤回草稿或绝不重新生成。

8137 最近三条请求均只用一轮回答，已没有原先教学步骤拒绝后重写、第二次模型质检。仍有 `publish_integrity` 来源/引用核验，分别耗时 3.891、2.985、3.484 秒，其中存在发布身份重复计算。下一步应减少这里的重复 I/O，而非再次删除一个已经不在本轮执行的模型审稿步骤。

## 5. 不宜直接复制的生成路径

- DeepTutor 本地 `.../lightrag/engine.py:487` 调用 `aquery_llm()`，拿到内部生成的 content，再交给聊天循环；不能假设它只查不生成。
- 本项目 `knowledge/lightrag/engine.py` 已调用 `aquery_data()`，由宿主统一生成回答。这个边界应该保留，直接复制本地上游查询函数可能引入额外生成。
- DeepTutor 外部服务器连接器使用 `only_need_context=True`，与我们的检索/回答职责分离更接近。

## 6. 并行与 GPU

- `agents/loop/pipeline.py` 的 `_retrieve_kb_seed_block()` 用 `asyncio.gather` 并行查询多个独立知识库。
- 不应把本轮“前校验→读取→后校验”机械并行，这会改变一致性语义，也不能解决重复扫描本身。
- 8137 当前 embedding/reranker 已为 CUDA，GPU 重排约 0.45–0.56 秒。文件读取、哈希、JSON/GraphML 解析并不是把 device 改成 cuda 就会加速的部分。

## 建议实施顺序与复用边界

| 优先级 | 工作 | 上游可用内容 | 需本项目适配 |
|---|---|---|---|
| P0 | 同图元数据只计算一次；同轮复用已核验字节 | `VisualEvidence`、`VisualAssetStore.read` 数据流 | Q2 document/version/release、页面 URL、410 行为 |
| P0 | 发布版本与逐请求资源校验分开 | published root、embedding signature、冻结 bundle | 当前 staging 候选、Q2 发布身份、变更失效机制 |
| P1 | LightRAG 避免逐次全量加载 | worker 已存在；LlamaIndex 缓存生命周期可参考 | 本地 rag 实例池或独立服务；内存、owner bridge、取消与关闭 |
| P1 | 图片清单避免逐查询重载 | 精确视觉工具、按需资源读取 | 保留语义问题按需附图与图号歧义处理 |
| P1 | 来源发布重复 I/O 去重并补全分段指标 | 普通回答直接完成；无通用二次模型审稿 | 当前证据编号、原文/版本核验、刷新恢复 |

本次仅做源码调研并写入本记录，没有修改业务代码或重启服务。以上是可核对的实现差异，不是已完成的优化；需用用户原页面会话复验首字、完整耗时、图片、旧版本失效和刷新恢复。
