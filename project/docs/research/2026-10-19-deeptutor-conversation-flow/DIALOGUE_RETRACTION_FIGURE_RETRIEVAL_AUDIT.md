# 草稿撤回、图号未命中与检索范围根因调查

日期：2026-10-23。性质：已完成只读调查与上游源码调研，尚未实施修复或切换服务。

## 结论

截图三次请求实际都走了 LightRAG，没有回退。共同缺陷是把阅读器当前小节作为普通提问的硬检索范围：用户在第一章第二节，却询问第三节的图和概念。全量改用 LightRAG 不能解除这个外层约束；取消 Q2 原文核验也不能解决定位与像素获取问题。

应继续以 LightRAG 承担语义/关联召回，保留 Q2 精确原文读取、资产身份及来源核验；将“学习路径当前位置”和“本轮问题检索范围”分开。图号问题先按全书资产目录确定对象，再读取对应原文及原图，不先赌语义检索能召回图注。

DeepTutor 可直接迁入图像点名读取的工具主体、媒体目录提示和相关测试模式；须适配本项目 SourceVisual/SourceRef、临时图片消息与发布门禁。无需搬第二套 AgentLoop、ReadingStore 或检索服务。

## 实际版本和调查方法

- main：`9f2b01c`，调查阶段未改业务代码。
- 当前宿主基底：`.runtime/response-portable-20261022/code-proof-2ae1e5f/`；阅读器另有已登记的滚轮构建覆盖。后端核对的是该实际运行副本，不用 main 代替运行版本。
- 正式课程库通过 SQLite `mode=ro` 读取，按截图原句定位到三个任务；没有创建对话、调用模型、修改学习位置或恢复数据库。
- 原始私有证据留在 `.runtime/response-dialogue-audit-20261023/`，不提交整段会话/系统提示词。`root-cause-evidence.json` 给出任务结果、检索调用、原图身份、代码哈希和四项离线核对。

复核命令：

```powershell
& 'E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe' -B 'E:/项目/heart/.runtime/response-dialogue-audit-20261023/check_root_causes.py'
```

结果：exit 0，4 项核对通过，模型调用 0，数据库只读。它验证缺陷存在，不是修复回归通过，也不是重新完成真实模型/浏览器验收。

## 三次请求逐项对账

| 请求/任务 | 已持久化的实际结果 | 检索与时间 |
| --- | --- | --- |
| “图1-4讲的是什么”；a7a367f8-d192-4ee8-ba61-a0e64319b4be | answered；保存了“本次片段不含该图”的答复；本轮原图数 0 | LightRAG 2 次，无 fallback；各 48.937 / 28.578 秒；首末 loop event 间 87.378 秒，与截图约 88 秒对应 |
| “给我解释一下被试反应”；e8fc330e-aeef-421c-ac4f-977f761711da | quality_rejected，sources=0，未发布讲解 | LightRAG 1 次，33.391 秒，无 fallback；首末 event 间 38.662 秒，与截图约 39 秒对应 |
| 同句重试；27502adb-5ba8-426f-919c-5d66d319b2e7 | 调查时最终也为 quality_rejected，sources=0 | LightRAG 1 次，13.063 秒，无 fallback；首末 event 间 17.425 秒。截图 7 秒是当时尚未结束的画面，不能当最终失败耗时 |

以上时间是服务器持久化事件跨度，不冒充浏览器首字时间；本轮未取得这三次请求的浏览器原始 SSE，无法还原每一条 answer_state 的准确时间。

### A. 当前小节错误限制了新问题

三个任务均保存了：目标 `kp:第二节 实验心理学的产生与发展`，chapter_id=1、section_id=2，reason=页面当前目标。

实际链路：

1. `agents/agent_loop_service.py:_target_from_context` 从页面 section 对象构建 LearningTarget。
2. `agents/course_search.py:CourseSearch.search` 仅用“第×章”识别显式跨章；不满足条件时保留旧 target 的 section_id。
3. `knowledge/lightrag/q3_adapter.py:LightRagNavigator.search` 将目标 chapter/section 传给 backend。
4. `knowledge/lightrag/retrieval.py:LightRagBackend.search` 在原文映射后执行严格 `scope_filter`。底层即使召回全书内容，也只能保留第一章第二节。

离线使用真实共享边界和观测型 backend，三句原话均仍传出 chapter=1、section=2、side_question=false，已复现范围错误。

第一章“被试反应”字面相关原文至少在第三节块 322、327，第二章也有相关解释；图 1-4 同样在第三节。阅读器位置可以帮助理解上下文，但不能无条件否决用户的新问题。后续扩大本轮检索不能推进或修改原学习路径。

**证据限制**：这两次零结果的持久化 retrieval_trace 只有 tool_output，没有保留 native_recall/original_mapping/scope_filter 详情。日志可确认底层曾取回候选 chunks、最终宿主结果为空；无法逐块证明这两次各有多少在映射、范围过滤或其他阶段丢弃。已确认的范围缺陷不等于排除了所有其他召回缺陷。

### B. 图 1-4 存在，但图号读取被文字召回绑住

运行副本中原图登记：

- ID：`image-01-0006`；第一章第三节；块 212；pending。
- SHA256：`cefa9fbd5b5cd0a4629c129b82f8f883674beeb6f42d5e33d50ab8fd84177d56`。
- 图注（块 213）：图1-4 科学研究过程：从研究思想到结果报告。
- 文件存在、哈希一致，实际 `get_figure` 能返回且 `is_valid()` 为真。因此不是教材原图缺失。

`RetrieveCourseTool` 在没有文字 sources 时直接返回，未进入找图；有 sources 时，`selected_media` 又要求原图与 sources 章/节相同。当前 sources 全在第二节，第三节原图因此不能绑定。图号解析器已有精确编号能力，但被调用顺序和范围约束挡住。

此次模型两次检索的 query 都混入当前“产生与发展”主题，第二次又加入冯特/莱比锡，进一步偏离图 1-4。最终保存答复的引用来自不相关的历史人物片段，图像数为 0。不能说模型看到了原图后拒绝解释。

发布门禁确认了引用真实性和答复未编造图意，但没有将“指定图号必须取得该图或明确查图失败分类”作为单对象覆盖要求。这是对象覆盖不足，不应通过允许无依据解释修复。

### C. “草稿已撤回”有两种语义

`llm/answer_events.py` 中，`begin()` 进入下一回合时、`retract()` 清空本回合临时内容时，以及 `finish()` 最终未通过时，都可能发送 state=rejected。`agents/agent_loop.py` 遇到工具调用会执行 retract，随后工具仍正常运行。

前端 `renderProgress` 在 pending 时把 rejected 显示为“本轮草稿已撤回”。因此截图的“转圈 + retrieve_course + 撤回”可以是正常取证中的中间态，不代表用户取消或网络断开。

这两次概念问答另有真实终态失败：第一回合模型未先检索，门禁要求补取依据；随后 retrieve_course 返回 0 来源，最终被 `_publish_gate` 的无来源检查拒绝。门禁应保留；需要修复范围及证据不足的有界恢复，并让界面区分“继续检索/修订”与“最终未发布”。

### D. 单对象诊断和补查仍有缺口

`CoverageNavigator` 无多对象 requirements 时走 passthrough：固定报告 retrieval_calls=1、supplemental_calls=0、missing=[]。即使未取到来源，missing 仍为空，且它不是整轮工具调用总数。图 1-4 实际有两次调用，末次 coverage 仍只报告一次。

`_capture_graph` 遍历并标记 backend trace，但没有将其追加到自己的 trace。三个任务持久化记录缺少原生阶段，导致只能看到“没找到”，不能定位逐层淘汰原因。应保留阶段审计和每次调用，而不是无限增加重试。

## DeepTutor 调研与直接复用清单

本机 `D:/deeptutor`：`6cf793bd868ba5ecbe64722936d4be8fab5a01df`。GitHub 当前 main 固定为 `a31d82624c27d75f4e771d4fcb78dce16470b383`，使用 agent-reach 的 gh 后端下载六份相关源码及测试；六份与本机内容一致。下载哈希见私有证据 `upstream-manifest.json`。一次猜测的 read_tools.py 路径返回 404，随后按实际 tools.py 核对；不把失败路径当已调研模块。

| 上游实现 | 实际解决方式 | 复用决策 |
| --- | --- | --- |
| [reading/tools.py](https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/capabilities/reading/tools.py) | search_material 查具体材料；read_material 按页/节 locator 精确读原文，附媒体列表 | 复用“查对象→读原文”的工具契约与有界定位参数；存储层接现有教材目录/PDF/Q2，不搬 ReadingStore |
| [reading/figure_view.py](https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/capabilities/reading/figure_view.py) | view_figure 按登记文件名找图；不存在时列最多 20 个候选；检查文件/大小；视觉读取有超时；无视觉能力明确仅提供图注 | 可迁工具主体的查找、失败分类、限额和测试；名称改用资产 ID，绑定 Q2 文档版本/哈希。像素仍走现有临时消息和同图质检，不新增一套视觉回答发布链 |
| [reading/media_notes.py](https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/capabilities/reading/media_notes.py) | 把图片名称、所在页和 caption 提供给模型；caption 限 300 字、最多 20 行，截断说明遗漏 | 可迁有界目录提示的格式化代码，改为本项目资产身份、图号、可靠页码/状态。上游 caption 可能由模型生成，迁入时必须区别原书图注和机器描述，不能当核验教材事实 |
| [runtime/agentic/loop.py](https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/runtime/agentic/loop.py) | 终态前 validate_terminal；违规后追加修订消息继续，受 max_iterations 限制；避免实时正文重复 emit_final | 复用既有循环中的有界恢复策略和测试思路；本项目已有对应机制，不整体覆盖循环。上游不保证内容永远无需修订，也不能拿协议核验替代教材事实核验 |
| [services/rag/smart_retriever.py](https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/deeptutor/services/rag/smart_retriever.py) | 默认生成最多 3 个 query 并发检索后聚合 | 仅适合迁入有界 query 变体模式。现实现会跳过异常、再生成摘要，来源仅 query/provider；不可直接替换本项目发布证据链。传入 query_hints 的数量也未在此切片，不把默认 3 误当强制预算 |
| [tests/reading/test_view_figure.py](https://github.com/HKUDS/DeepTutor/blob/a31d82624c27d75f4e771d4fcb78dce16470b383/tests/reading/test_view_figure.py) | 验证实际发送图片字节、无视觉能力明确未读取、缺图不调模型 | 可迁对应行为用例并替换 fixture，追加版本失效、图号歧义、同图质检和学习路径不变断言 |

本机 pyproject 声明 Apache-2.0。实施迁入时核对 LICENSE/NOTICE 并保留来源；本轮未复制上游业务代码到宿主。上游工具依赖其 _ReadingToolBase、ReadingStore、LLM client、ToolResult，不能零适配粘贴。上游也没有提供可直接替换本项目 rejected 状态的现成前端补丁。

## 建议实施顺序（待执行）

1. **先补可观测性和失败分类**：完整保留每次原生召回、映射、过滤、重排、证据选择及对象覆盖；统计全轮调用与补查，不记录密钥/像素。用截图原句写回归。
2. **修本轮检索范围**：区分继续学习与新概念/指定对象提问。当前小节作为默认偏好；必要时在授权课程内有界扩大到章/全书。Q2 精确学习目标读取不改，插问不推进/改写路径。
3. **接入确定性图号读取**：复用资产目录和 DeepTutor view_figure/read_material 模式，图号→资产/原文→像素；图不唯一只澄清必要信息。已存在的原图不要求学生重新上传；无法读像素、缺原件、缺图注分别报告。
4. **分开草稿中间态与终态**：保留追加/替换和撤回能力，检索中不显示为最终失败；核验失败有清楚原因。证据不足的补查/修订必须有总预算，晚到结果不得保存或推进。
5. **联合验收**：第一章第二节页面问图 1-4、问被试反应均取得对应真实来源；生成/质检使用同图；新问题后学习位置不变；返回原图定位遵循 `TEXTBOOK_IMAGE_RETURN_LOCATION_PLAN.md`；真正缺图/证据不足受控失败；连续追问、取消、刷新及重复点击不回归。

每阶段单独提交/push，最终同一稳定提交做隔离真实模型和浏览器验证，再准备运行版本更新。不得为了减少撤回而隐藏最终失败、删除门禁、把 pending 改 approved、重建候选或切换正式数据库。

## 本轮未完成与风险

本轮只证明了根因链中的范围缺陷、媒体进入条件、状态复用及审计缺口，未重放真实模型检索或修复后浏览器流程。原始阶段 trace 缺失，旧请求逐块丢弃原因不可补造。调查中的离线 backend 是观测夹具，不能算 LightRAG 检索通过。

“回答已保存”目前只说明该答复通过当前门禁并被保存，不能保证问题得到实质解答；截图中图号请求就是保存了证据不足的答复。后续必须单独检验指定对象是否被找到和解释，不能以 saved 图标代替效果验收。
