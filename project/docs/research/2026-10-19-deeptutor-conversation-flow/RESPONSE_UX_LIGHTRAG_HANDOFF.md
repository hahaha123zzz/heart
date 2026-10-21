# 回答体验与 LightRAG 公共接线交付（2026-10-21）

本批基于 `b7c00f9`，以合并提交 `a3b653e` 接收已提交候选 `d3d6a76`。只把它作为接口兼容基线；跨章覆盖尚未通过，不切换正式检索。没有读取其他 worktree 的未提交代码来实现本批功能；旧验收 JSON 只读回放，不在那里运行 SDK、写缓存或改索引。

## 实际调用点与接口

| 调用点 | 行为与兼容性 |
|---|---|
| `agents/agent_loop_service.py::run_agent_loop_turn` | Q5Navigator 继续负责 resolve、目标、路径和状态；Q3/Q5 的 search 共同经过 `agents/course_search.py`。传入 navigator 的 search 不再被 Q5 默认 search 覆盖。 |
| `CourseSearch.search` | 精确 `chN:sN:bN` 仍由 Q2 read_target 读取；目标失效报错，不伪装成语义检索成功。显式跨章只修改本次搜索范围，不修改原目标/路径。 |
| `shared_search` | 显式 `Q3_RETRIEVAL_MODE=lightrag` 时需要 `LIGHTRAG_CANDIDATE_PATH`；未发布候选还需显式 `LIGHTRAG_ALLOW_CANDIDATE=1`。本批未改 `.env` 或默认正式配置。缺索引/依赖不静默 fallback。 |
| 日志与响应 | `course_search` JSON 日志和最终 `retrieval_calls` 记录 actual_backend、fallback、来源 ID、耗时；LightRAG 带 input_signature/index_identity，Q2 精确读取带 document_identity，本地成功检索带索引路径/哈希。失败保留所选后端与错误类型，不捏造索引成功身份。 |
| `RetrieveCourseTool` | 增加可选 asset_id，旧 query/limit 调用兼容。原文经现有 choose_evidence 核验再编号，发布使用同一 EvidenceBundle；图谱描述为独立关联候选，最多8项/6000字符，带本轮原文 ID、document/version、quote、block，不生成独立引用证据。无有效原文链接的关系不传入模型。 |
| `_publish_gate` | 保留引用格式、事实质检、来源发布和保存门禁；显式多章问题缺章时拒绝发布。章节齐全仍不代表主题和完整关系覆盖通过。没有实现另一套跨章补检索。 |
| `llm/answer_events.py`、TaskService | 流式每个增量检查任务身份/revision/取消；模型轮开始、checking 和保存仍执行完整来源/版本检查。避免每个 token 全书重算哈希，不把草稿当正式事实。旧 bind 调用兼容。 |
| `agents/transient_messages.py` | 原样迁入固定 DeepTutor `6cf793bd868ba5ecbe64722936d4be8fab5a01df` 的三个临时消息函数；Apache-2.0 见 `llm/DEEPTUTOR_LICENSE`。完整工具回复批次结束后追加图片；累计最多2张，单图沿用8MB上限；正式 loop_state/历史不存 base64。 |
| `knowledge/answer_media.py` | 复用 Q2 source_visuals/figures，不建第二图库。检查 asset/document/version/sha256，只有实际像素送模后才标 model_saw_pixels；同图进入现有 QualityChecker。重启/ask_user 恢复重新验证文件身份。 |
| 图片 API、历史 API、正文 | 图片 URL 增加可选 sha256/version/document_id；旧接口仍兼容，新图片绑定不符返回410。历史恢复保存时的媒体记录，不按旧ID查询新版后升级。正文仅接受本条媒体集合内 `media:ID`，未知图和外链不加载；旧无版本图片保留文字，不伪升级。 |

教材图返回的是实际章节/小节；没有图像区域坐标时 `location_status=section`、rects为空，界面明确无精确原图区域。pending 表示未教师审核，不能据此冒充 approved，也不能把确实已提供的清晰像素误判为缺图。`course_release` 仍是 staging/ready=false，未修改其含义、教材原件、全书输入或正式索引。

普通“用表格比较”不再自动附整节原图。实际发现 `image-05-0002` 是二维码却被标为图5-7，按已核对哈希加入既有装饰图过滤；不改原资产。当前运行时目录为178个 pending/45个已过滤装饰项（原记录179/44保留历史意义），不是把待审图升为 approved 或补造缺图。复杂原表、精确页/区域检索和全部同号歧义仍未验完。

## 分层证据

证据根目录：应用 `.runtime/response-experience/20261020/`。日期沿用原基线，每个阶段独立隔离 host.db/course.db、8012端口；测试完成后停止本次子进程。未操作8000正式服务。

| 项目 | 代码已接入 | 真实模型 | 浏览器 |
|---|---|---|---|
| Q3精确教材讲解/流式 | 是 | `ux4-q3-guard` 已核验保存 | 实际页面在流关闭前出现正文，刷新内容一致 |
| 上标、隐藏底部引用、排版 | 是 | 当前保存回复保留原文引用 | 图5-2真实历史页面上标可打开原文、无底部清单；增量格式/公式/窄屏及生命周期夹具通过 |
| 教材图5-2正文展示 | 是 | `ux4-media-retry` 生成与质检收到同一原图SHA256；质检后修订一次，保存成功 | 实际375px页面原图、pending、返回第五章第三节、错误哈希410、刷新恢复且0额外生成请求均通过 |
| Q3/Q5共用LightRAG选择 | 是，含实际run_agent_loop_turn的Q5入口夹具 | 未重跑完整LightRAG检索；精确Q2成功不计作LR成功 | 待新稳定候选后联合验收 |
| 图谱关联候选 | 工具结果已传入有界独立区块 | 未取得真实LR外层模型消费证据 | 未验 |
| PDF选区、实际练习、Q5路径讲解/插问返回 | 公共入口沿用UX3接线 | 本批未完成独立真实模型验收；心理学习题目录为空 | 不用普通聊天或渲染夹具替代 |
| ask_user恢复、取消、断线 | 临时图片恢复、事件/任务门禁接入 | 完整真实模型页面组合仍待验 | 生命周期/任务夹具通过，不能据此宣称全部真实入口通过 |

### 实际耗时与失败

| 案例 | 请求总秒 | 首次正文秒 | SDK create数 / 返回total_tokens | 结果 |
|---|---:|---:|---:|---|
| Q3同题修复前 `ux4-q3-final` | 183.106 | 12.915 | 4 / 7963 | 保存，但正文流被重复全书哈希严重拖慢 |
| 修复后 `ux4-q3-guard` | 12.488 | 7.635 | 4 / 8009 | 核验保存，页面领先正文流关闭约1.10秒 |
| 图5-2 `ux4-real-media` | 46.096 | 29.390 | 5 / 11469 | 像素生成/质检一致，保存；当时未内嵌 |
| 内嵌复验 `ux4-media-retry` | 18.265 | 8.589 | 8 / 20424 | 修订一次后保存；页面内嵌及真实历史联验通过 |

单次对照不能推断全场景性能改善。金额API未返回，不估算费用。保留 `ux4-exact` 的240秒超时、`ux4-q3-final` 慢运行和原先空检索失败；实际发现 `.venv` 缺 llama_index，已移除将该导入失败静默当作空Stub检索的分支，未擅自安装/替换其他窗口环境。

内嵌首轮 `ux4-real-media-inline` 被充分性核验误以“pending无法展示”拒绝（8.901秒，无正式答案），修正规则后再验；没有删充分性核验。历史页首验发现 API 丢失原绑定，已修复；后续发现返回教材按钮消息键缺 `message:` 前缀并修复。移动端测试第一次未切到“对话”页导致隐藏元素超时，修正操作后再验。失败没有折算为通过。

### 旧 LightRAG 长度失败复验

只读旧有效第二轮原始草稿及来源，在当前 `_publish_gate` 和真实 QualityChecker 中回放，使用独立 `ux4-latest-gate` 数据库；没有重新检索、保存草稿或升级历史证据。

- synonym：原尝试 `f8696b37-7fd3-4b0d-b80a-1bab8cb04c18`，313字，旧260门禁失败；当前800/任务预算门禁及真实事实质检通过。
- first_chapter：`87c5eea2-73fb-414a-9419-9da1185fd981`，339字，同样通过当前门禁。
- cross_chapter：`3c5afcfa-2ea7-4b1b-ad93-72dd1293b07c`，207字，只有第2章。初次回放暴露模型质检会放过缺章，新增确定性缺章门禁后明确拒绝“跨章问题缺少原文依据：第1章”。仍未通过覆盖验收。

输入哈希/结果见 `ux4-latest-gate/report.json`、执行日志 `ux4-latest-gate-v2.log`。这是当前宿主对旧输出的门禁复验，不是新LightRAG全链路验收或正式接通证明。

## 复核命令与剩余门槛

167项后端组合通过（`ux4-final-v3-backend.log`）；新增Q5入口夹具后 `tests.test_course_search_bridge` 7项通过（`ux4-q5-boundary-final-v2.log`）。命令：

```powershell
.venv/Scripts/python.exe -m unittest tests.test_course_search_bridge tests.test_answer_media tests.test_answer_stream tests.test_q3_agent_loop tests.test_q3_task_loop tests.test_q3_entrypoint tests.test_reply_budget tests.test_quality_guard tests.test_task_api tests.test_response_citations tests.test_source_visuals tests.test_q5_learning tests.test_context_sufficiency -q
node --test tests/chat-transport.cjs
node --check frontend/app.js
```

Node transport 9项通过。实际Edge：`tests/browser/chat-lifecycle.cjs` 全部检查通过；`response-format.cjs` 8种标准格式通过逐字符增量/公式/375px检查；`answer-media.cjs` 5组受控渲染检查通过。真实服务历史 `response-media-live.cjs` 5组通过，`ux4-media-retry/media-live.json`、`media-live.png` 已查看。渲染夹具与真实服务结果分开，前者不证明模型实际收到像素。媒体构建产物558.02kB/gzip172.60kB，无新增依赖或数据库表。

切换前保持现有默认后端：先接收新稳定SHA及接口，确认完整输入/索引/embedding身份及staging含义；在独立环境/库验证普通聊天、Q5路径、跨章插问后返回、PDF选区、练习、ask_user、取消/刷新，各入口单独通过后才评估切换。当前不增加单章构图前置条件，也不重建全书索引。回退只恢复本批代码/配置，保留学习数据和索引，不清库。

本批未宣布 UX3—UX5、完整教学循环或Q2整阶段完成。Q5长期路径/正式评分仍归既有Q5接口，LightRAG内部检索与跨章补查归检索窗口。
