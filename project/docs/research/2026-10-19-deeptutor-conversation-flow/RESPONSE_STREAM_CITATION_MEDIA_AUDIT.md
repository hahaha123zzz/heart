# 回答流式输出、行内引用、教材图表与排版调研

日期：2026-10-20。状态：源码调研与隔离验证；未修改业务代码、数据库或运行服务。

## 1. 结论

四项问题需要在模型调用、Q3 循环、任务/SSE、证据协议和前端共同处理。当前已有 SSE、Markdown、引用定位和教材原图模块，可在这些接口上补齐，不需要重建聊天应用，也不以 LightRAG 建图完成作为前置条件。

建议来源分工：

| 问题 | 优先复用 | 本项目需要适配 |
|---|---|---|
| 真正流式正文 | DeepTutor 的工具调用增量累积、正文/思考分流、回合撤回；参考 OpenTutor 的 content/replace 事件 | OpenAI SDK → Q3 → TaskService → SSE → 页面；保留质检、落库、恢复 |
| 隐藏底部引用列表、文字旁上标 | 已迁入的 DeepTutor 引用解析与消息内定位；参考 OpenMAIC 的按需展开交互 | 上标直接绑定本条回答的来源；不能依赖被删除的底部按钮 |
| 回答中使用教材图表 | DeepTutor 的精确原图/页码/区域检索与多模态消息；复用本地 source_visuals、PDF 原文资源接口 | Q3 图表工具入口、图片送模、质检、正文显示和历史恢复 |
| 公式/表格/段落及回答结构 | 保留现有 DeepTutor Markdown 管线；参考 OpenMAIC 的流式 Markdown、中文强调和公式处理 | 宿主适配、样式、流式生命周期、按任务调整回答结构约束 |

## 2. 核对的版本

| 仓库 | 本机目录 | HEAD | 根许可证 |
|---|---|---|---|
| 当前项目 | `E:\项目\heart` | `2b5d5d6aa6080588ed9ba927a59d568984e4bb7a` | 沿用本项目约定 |
| DeepTutor | `D:\deeptutor` | `6cf793bd868ba5ecbe64722936d4be8fab5a01df` | Apache-2.0 |
| OpenMAIC | `F:\openmaic\OpenMAIC` | `d128ef67c920571a86ce8a7c0430185689ab3d45` | MIT |
| OpenTutor | `F:\opentutor\OpenTutor` | `a890519f3632efa14cf24449b366b3b9d901eecf` | MIT |

用户后续更正备选仓库在 F 盘。研究本地源码，不依赖网上其他版本。文件哈希与定位见同目录 `RESPONSE_STREAM_CITATION_MEDIA_SOURCES.json`。HEAD 不代表工作树一定无改动，以实际读取文件哈希为依据。

## 3. 问题一：已有 SSE，为什么仍等完整答案

### 本项目

- `main.py::chat_stream` 推送 `progress`、完整 `answer`、最终 `done`，没有模型正文 delta。
- `llm/client.py::chat_with_tools` 调用 `chat.completions.create` 时未设置 `stream=True`，随后读取完整 `choice.message`。
- `agents/agent_loop.py` 的探索轮和强制收尾调用都等待完整结果；最终正文经过发布门禁后才返回。
- `agents/agent_loop_service.py` 把循环事件映射为短进度说明，没有独立正文通道。
- `frontend/chat-transport.js` 只消费 progress/answer/done/error；`frontend/app.js` 接收完整结果后替换回答。
- TaskService 的 answer_ready 用于已保存文字先展示、再准备辅助图解，并不是 token 回调。

静态调用链说明等待来自检索、模型多轮调用、核验和保存等阶段；本轮没有测真实模型各阶段耗时，不能给出哪一阶段占比最高或提速百分比。

### DeepTutor

`deeptutor/agents/loop/agent_loop.py::_call_llm` 使用 `stream=True`，逐块处理 `delta.content`、思考片段、工具调用片段和 usage。`ToolCallAccumulator` 按工具 index 分组，完整 id/name 使用赋值，arguments 使用拼接，避免重复字段导致工具名称损坏。

通过 StreamBus 发布正文，调用元数据关联到具体模型轮。`_discard_deferred_output` 对已展示但被拒绝的轮设置 `answer_visible=False`、`finish_rejected=True`，前端据此移出正式答案。

不能仅复制流式 SDK 调用而丢掉：取消、流中断、工具参数拼接、质检修订、暂停恢复、最终来源编号和保存失败语义。也不建议整套复制上游 WebSocket/账户运行时；本项目已有 SSE。

### OpenTutor

`apps/api/services/llm/providers/openai_client.py::stream_chat` 支持实际模型增量；前端 `lib/api/chat.ts` 和 `store/chat.ts` 支持 content 追加、replace 替换。后端 orchestrator 在 verifier/reflection 改变正文后发送 replace。

但 ReAct function-call 轮仍调用非流式 chat_with_tools；无工具时可能直接一次返回完整 last_text，有工具后另做一轮流式生成。它不是所有轮都逐字输出的现成替换件，也可能增加生成调用。

### 最小落地要求

沿用 SSE 增加正文追加与正文替换事件（具体名称实施时定）。每段关联 task/revision/round，区分生成中、核验中和已保存。工具参数和内部思考不混入正文。质检拒绝或修订后替换相应草稿；done 的正式结果和历史记录一致。断线恢复不重复提交任务，不把旧 revision 的片段追加到新回答。

指标分别记录：提交→首条进度、检索完成、首个可见正文、生成结束、核验结束、保存完成。流式改善开始阅读的时间，不保证降低检索和模型本身的计算耗时。

## 4. 问题二：引用改成文字右上角标

### 现状与关联风险

`frontend/app.js::renderChatReferences` 渲染底部来源按钮、原文摘录、定位状态、选区/裁图。底部较长既有来源条目数量的因素，也有每条展开内容较多的因素。

现有 `reader/src/tutor/index.tsx` 会把正文引用点击转发给同条消息底部 `.message-source[data-source-index]` 按钮。直接停止渲染底部列表会造成正文引用失去点击目标。

DeepTutor 已迁入的 `SimpleMarkdownRenderer` 使用 `.citation-group`，是缩小的行内方括号链接，本身不是用户要求的上标。当前 CSS 只改变字号，没有上标定位。

### 可复用范围

- 保留 DeepTutor 的 Markdown 引用解析、代码/公式保护、消息内作用域。
- 将可核验的 `[n]` 渲染成可键盘操作的上标按钮/链接；点击按该消息的 pdf_references/evidence 直接定位或展示详情。
- 正文下不再展开来源清单。来源原文、版本和页码可在上标点击后按需显示；后台来源和核验记录继续保存。
- 历史来源失效时，上标明确不可用或提示失效，不能悄悄定位到新版本后声称是旧证据。
- 相同来源仍允许在不同结论旁重复使用同一编号；不能只保留第一次上标，导致其他结论丢失出处。

OpenMAIC 的 `components/ai-elements/inline-citation.tsx` 提供 HoverCard/Badge/Carousel 组件，但源码搜索只找到组件自身定义，不能据此声称当前主聊天已接通。它默认显示 URL 域名徽章，也不是数字上标；适合参考按需展示详情，不值得为这一个效果迁入整个组件依赖树。

OpenTutor 提示词反而要求 `[Source: filename]` 加 Sources footer，不符合此次隐藏底部来源的需求。

## 5. 问题三：正文里的教材插图和表格

### 本项目已有与缺失

已有 `knowledge/source_visuals.py` 保存原图 ID、图表类别、章节、块、审核状态和本地 `/api/figures/{id}/image`。已有正文外图片区和 PDF 选区图片显示；这些基础可复用。

普通 Q3 聊天仍有断点：

1. retrieve_course 只接受 query/limit，没有精确图号、asset_id、来源页或区域参数。
2. `q3_navigation.source_from_chunk` 构造 SourceRef 时没有补入图片关联，虽然 SourceRef 定义了 image_refs。
3. `tool_dispatch` 收集 `ToolResult.model_message` 到 `model_messages`，但 `agent_loop` 接收调度结果后只追加 tool_messages，没有追加 model_messages。接口字段存在不等于像素已送到下一轮模型。
4. Q3 发布门禁调用 QualityChecker 时没有传入 figure_images，视觉事实核验仍需接线。
5. `reader/src/tutor/markdown.tsx` 对图片 src 返回空，img 被替换为 `[图片：说明]`；不能靠模型输出 Markdown 图片地址实现正文原图。
6. `_map_result` 和保存/历史链路需要保留被实际选用的媒体及其来源身份，不能仅在当前内存中展示。

### DeepTutor 的完整做法

`tools/builtin/__init__.py::RAGTool` 支持 source_path、asset_id、figure、page、region、source_hash。普通语义检索与精确视觉检索共用工具入口；出现明确图表标签或精确参数时进入 retrieve_visual。

`services/rag/source_visuals.py`：

- 区分 figure/table，歧义图号要求补充来源或页码，不用相似图替代。
- 原始像素来自受控文件或 PDF 页面/区域，核对源文件身份，限制区域、文件和输出大小。
- 同时提供出处、图题、附近正文、结构化表格和原图 URL。
- `VisualEvidence.model_message()` 把原图送入支持视觉的模型；不支持时明确仅能依据文字。
- 工具调度在完整配对的工具回复之后附加图片消息；对跨轮累计图片数量/大小有限制。
- 前端 Markdown img 真正显示图片，支持延迟加载。

建议复用精确检索和证据结构，适配本项目的 source_visuals/版本接口，不再建第二份图库。模型能看图与学生能看到图要分别验收。

简单表格可用有来源的 Markdown 表格；合并单元格、多层表头、密集公式等采用原表图/PDF 裁图。展示原图与根据图得出专业结论是两项能力；待审核资源保留 pending，不冒充教师审核通过。

## 6. 问题四：格式既包含渲染，也包含回答组织

### 隔离检查结果

用 Playwright 加载当前已构建的 `frontend/tutor-markdown/tutor-markdown.js`，只输入合成样本，不调用模型、不发送聊天请求：

| 样本 | 当前输出 |
|---|---|
| 标准标题、加粗 | 能生成 h2/strong |
| Markdown 表格 | 能生成 table |
| 标准 LaTeX 公式 | 能生成 KaTeX |
| 正文 `[1]` | 能生成 citation-group；不是 sup |
| Markdown 图片 | 无 img，只有图片说明 |
| HTML 表格 | 无 table，原样显示 HTML 文本 |
| 未闭合的加粗/公式 | 没有独立 streaming 标志，尚不能据此保证流式显示稳定 |

因此不能将所有排版问题归因于“没有 Markdown”。标准样本可用；具体用户失败回答仍需保留原始模型输出与截图对照，区分模型格式错误、流式半成品、适配层限制和 CSS。

当前 `reader/vite.chat.config.js` 已直接打包 vendor/DeepTutor 的 SimpleMarkdownRenderer、latex/markdown-display，接入 remark-gfm/remark-math/rehype-katex；无需再次迁一套相同引擎。现有宿主又明确禁止原始 HTML，不能为表格直接打开任意 HTML。

### OpenMAIC 更值得借鉴的部分

`components/workbench/chat/text-block.tsx` 使用 Streamdown，按 streaming 开启 `parseIncompleteMarkdown`；中文强调插件置于 GFM 前，公式插件与流式未闭合处理单独配置。`text-block-lifecycle.test.ts` 检查 streaming→完成→历史重放的渲染一致性。

`lib/workbench/markdown-math.ts` 以同一个 tokenizer 识别单美元公式，区分钱、shell 变量与公式；`lib/markdown/safe-math-plugin.ts` 隔离每次公式宏状态。它的 StreamBuffer 则带逐字符展示节奏，不能为追求快而照搬后再人为延迟展示。

优先保留现有 DeepTutor 管线并补 streaming 生命周期及来源/图片适配。若真实增量样本证明现有渲染器仍无法稳定处理半成品，再最小迁入 OpenMAIC TextBlock 所用的 Streamdown 与数学配置，删去课程导航、课堂样式和其他无关依赖。锁文件标明 Streamdown 2.5 支持 React 18/19，但这不是本项目已构建运行的证据；本轮未安装新包。

OpenTutor 的 MarkdownRenderer 有数学和 Mermaid 降级，但读取的该组件未启用 remark-gfm，不能因为定义了 table 组件就认定能正常解析 GFM 表格。它对本次表格修复不比现有管线完整。

### 回答结构约束也需要调整

当前心理学 RESPONSE 要求“最多三小段”，Q3 loop_prompt 又要求尽量 400 字、不要扩展。这会影响用户期望的分阶段教学规划、对比表、完整步骤。格式调优必须同步检查生成提示、预算与质量检查：简短问答保持简短，规划/比较/推导允许匹配任务的标题、列表、表格和长度。不能仅换前端渲染器就宣称详细教学规划已解决。

## 7. 推荐实施顺序与完整范围

1. **引用与静态排版**：去掉底部展开列表；上标直接定位证据；保留版本检查；验证公式、列表、表格、中文强调、长内容和历史恢复。
2. **真正流式**：同时贯通 SDK、Q3 探索/强制收尾、TaskService、SSE、transport、页面；实现追加/替换/完成，验证核验失败、断线、取消、ask_user 恢复。按真实阶段计时，不靠打字动画冒充流式。
3. **教材图表**：精确图表入口→原图选择→完整工具回复后的像素消息→视觉核验→正文图片→点击回原文→历史恢复。保持同一本书/同一版本，缺图和歧义明确反馈。
4. **联合验收**：普通问答、Q5 计划/讲解、PDF 选区、练习帮助的入口分别核对。后面几个入口仍有独立旧链，普通 Q3 通过不代表它们通过。

必要验收：正文出现时模型请求尚未结束；无工具参数/思考泄露；拒绝草稿不会作为最终答案留下；上标能点且跨消息不串号；无底部来源大列表；图表不是占位图；刷新前后正文/来源/媒体一致；流式完成与历史排版一致。保留来源失效、无图、图号歧义、模型无视觉能力等失败记录。

## 8. 本轮证据与限制

- 本地 SSE 传输测试：`node --test tests/chat-transport.cjs`，8 项通过。验证的是现有进度/完整回答/恢复协议，不能当成正文流式已经通过。
- 隔离浏览器渲染样本：`.runtime/response-ux-audit/render-probe.json`，7 类样本，结果见第 6 节；不是用户真实回答的端到端验收。
- DeepTutor 工具调用增量累积与 StreamBus：23 项通过，1.42 秒，日志 `.runtime/response-ux-audit/deeptutor-core-tests.log`。包含图表模块的 38 项组合运行超过五分钟后停止，未取得完整报告；日志保留失败标记，不计为通过。对图表来源边界案例单独复验，失败在创建 symlink 测试文件时，Windows 返回 WinError 1314（缺少创建符号链接权限），尚未进入该部分边界断言，见 `visual-boundary.log`；不能据此声称来源边界测试通过或认定生产代码存在漏洞。未停止当前应用服务。最初尝试还遇到项目虚拟环境缺少 pytest、测试临时目录父目录不存在，随后改用本机已安装 pytest 的 Python 并创建独立目录。
- OpenMAIC/OpenTutor 为源码与根许可证审查；未启动两套应用，OpenMAIC 无本地 node_modules，本轮未安装依赖或声称它们的界面在本机通过。
- 当前 8000 服务未改动。没有更换 RAG、模型或正式配置，没有合并其他窗口代码。
