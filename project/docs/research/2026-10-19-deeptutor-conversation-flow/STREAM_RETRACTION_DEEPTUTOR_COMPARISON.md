# 草稿撤回、长等待与失败：流式链路对照调查

日期：2026-10-23。宿主源码 `974617de0d385fe945106e337ddc856351d6df6d`；DeepTutor `6cf793bd868ba5ecbe64722936d4be8fab5a01df`。本次业务代码只读，读取正式SQLite使用mode=ro；另执行不联网的流协议测试和替身流复现。不启动服务、不调用真实模型、不改学习库或索引。

## 1. 用户截图已对应到真实任务

按截图原句匹配到课程库learning_tasks：

| 任务 | 观察事实 |
|---|---|
| 66539384-a2ca-4bce-9b43-975e50f3c9d8；“给我解释一下图1-4，我有点看不懂” | quality_rejected；2轮模型/1次工具；LightRAG一次39.860秒，no_evidence；原图0；目标是第一章第二节 |
| 51fd9986-76f1-4b4c-9d50-0b0b44d3751f；“请解释我选中的这段内容。” | answered；上下文有第三节pdf_selection；无Q3检索调用记录；image_refs=0。正文声明不能由该截图确认原图细节，与用户截图相符 |
| d923fb1e-fc4e-4f69-b632-014d008274df；随后“我想学一下图1-4” | answered；目标变为第三节；LightRAG49.609秒；工具调用到结果60.802秒；3条来源、1张原图。不能由一次成功推断提速 |

第一项持久化事件：探索开始1792758046.898，工具调用1792758047.707，工具结果1792758087.568，最终拒绝1792758089.388。总跨度42.490秒，与页面约43秒相符；39.860秒检索约占事件跨度94%。不是模型已生成好答案后被前端藏了40秒。

图1-4在第三节。直接问题仍绑定第二节，而圈选显式携带第三节来源，故两条证据路径不同。图像不存在的判断不成立：稍后同库任务取到原图；前次资产核对也验证image-01-0006存在。

局限：本次没有该用户请求的原始浏览器SSE，不能还原截图草稿每一片段的时间；旧检索阶段审计不全，不能量化每个候选在哪层被淘汰。上述来源范围缺陷已有先前调查和离线复现，不代表排除了其他召回因素。

## 2. 运行版本与修复状态要分开

本机运行登记 `.runtime/response-portable-20261022/approved-lightrag-2ae1e5f-runtime.json` 指向code-proof-2ae1e5f；这是登记记录，本次未用PID/启动时间重新确认当前监听进程。

最新main已有：e34ce01把中间撤回改为retrieving，c3b86f6修正小节范围/点名原图读取，974617d记录隔离真实模型/页面验收。`DIALOGUE_RETRIEVAL_FIX_ACCEPTANCE.md`明确8000当次未更新；不能以main已修复证明截图运行版本已生效。

该隔离报告中“图1-4”q2_figure约18.976秒、“被试反应”LightRAG约35.353秒；这些是另一次环境的记录，不是本次重测，也不是严格前后性能对照。它仍记录跨章51.645秒、首次草稿2.355秒，证明“早有草稿”与“取证后答案就绪”相隔很久的问题并未由文案修复根治。

## 3. 我们当前的真实流式流程

```text
每轮answer_kwargs → AnswerEvents.begin
  ├─ 清空上一轮正文、generating
  └─ SDK增量直接成为同一消息的content
       ├─ 最后发现tool_calls → retract清空 → retrieving → 检索/选证/视觉读取
       └─ 无工具 → checking → 引用/事实/视觉门禁
                         ├─ 通过 → 保存 → 最终快照替换 → saved
                         ├─ 可修订 → 下一轮begin再次清空 → 再生成/核验
                         └─ 拒绝 → 清空未保存正文 → rejected
```

关键源码：llm/client.py::_stream_call、llm/answer_events.py::begin/retract/finish、agents/agent_loop.py::_loop/_forced_finish、agents/agent_loop_service.py::_publish_gate、frontend/chat-transport.js::applyDraft。

当前确实是真SDK增量，不是人为打字动画。finish_reason、工具参数不作为正文、取消/保存guard和最终快照校正已有价值，应保留。

## 4. 与 DeepTutor 的实际差异

### 4.1 普通工具轮不应等同于被拒绝的正文

DeepTutor `agents/loop/agent_loop.py`：

- `_call_llm`为每次调用生成call_id；通过call_role区分narration/finish，answer_visible单独决定正文可见性。
- 普通工具轮文字默认保留；工具轮的output_policy只有明确discard时才调用`_discard_deferred_output`。进度说明不因出现tool_calls就被全部撤回。
- 明确被能力拒绝的轮次通过同call_id标answer_visible=false、finish_rejected=true，转入折叠trace；不是清空整条消息。
- 强制工具选择的轮次不展示普通正文；内部思考仅进trace，DSML/工具参数过滤。

本项目无条件`if round_result.tool_calls: retract()`，而下一轮`begin()`又清空，无法区分“我先查看原图”与“没有取证却先讲图意”。这是两者不同的输出所有权策略，不是前端随机吞字。

不能照搬“所有工具前文字都保留为正式回答”：我们有教材事实发布门禁，模型探索轮可能含未支持结论。适合复用调用/片段身份、进度与答案分离、定点撤回；不应原样放行未核验事实。

### 4.2 部分流中断后的自动收尾处理较弱

DeepTutor有`LLMProviderTransportError.partial_response`。已输出文字/思考后中断，不进入普通自动重试或收尾，避免新旧答案混接；尚无输出时才允许有限恢复。它会保留可重放assistant状态并发出明确失败元数据。

本项目_stream_call把所有异常包装为普通LLMError；LocalAgentLoop仅按result.rounds判断：首轮失败直接结束，已有轮次后统一调用_forced_finish。没有partial_response标志，出错流的result.text也没有作为该轮结果返回。

**本次替身SDK实证**：第一轮工具调用，第二轮先显示文字再抛模拟transport错误；随后第三次模型调用强制收尾。第二轮可见文字不在收尾messages里，累计3次空替换，状态为generating→retrieving→generating→generating→checking。输出保存在应用`.runtime/stream-retraction-audit-20261023/partial_failure_probe.json`。这是协议复现，不证明截图当次发生了网络错误。

### 4.3 先有证据再解释的流程未稳定保证

DeepTutor `_retrieve_kb_seed_block` 在普通配置允许时先取最多3个KB、有界原文作为seed；还可强制首轮工具。不代表上游总是预检索，也不保证零撤回或全范围覆盖。

我们主要依靠提示“先retrieve_course”，实际LoopRequest不设置tool_choice，首轮可能无来源先回答。门禁发现后才要求补检索，前面的正文已显示。这增加一轮无效生成及清空。

可复用seed/强制工具轮思路，但只能二选一并共享已有结果：明确图号优先现有q2_figure，明确导航优先q2_exact，其余走统一检索。不能为了预取再重复查询LightRAG，不可把所有闲聊/画像请求强制检索。

### 4.4 取证/核验存在多次串行模型调用

撤回到正式回答之间可能包括：原生关键词模型、图谱/向量读取、Q2 choose_evidence、跨对象semantic_selection、外层回答和QualityChecker，有时再加补查/格式修订。不能只量正文模型首字。

当前choose_evidence和semantic_selection传retries=0，但没有显式timeout；普通心理学QualityChecker的chat_json调用只有proof_required分支明确timeout25/retries0。默认OpenAI客户端没有本项目设定的统一预算，chat_json默认还有最多一次重试。Q3正文单次timeout90也不是整轮截止预算，且不覆盖所有内部调用。

这证明调用预算不统一，不能由源码单独断言每个用户长等待都来自SDK重试。截图当次已实测主要耗在检索；后续应逐阶段计时，再有证据地减少重复选择与调用。

## 5. 已有修复的价值与未解决部分

e34ce01的retrieving修正了“仍在工作却显示拒绝”的错误状态；c3b86f6修正了当前截图涉及的重要取证路径。它们应先作为部署基线采用。

尚未解决：每轮覆盖同一正文、普通工具轮全量清空、无证据先生成、部分流中断统一重做、缺少贯穿取证/回答/核验的时间预算。这些不能仅靠换状态文字解决。

不能采用的快捷方式：取消引用/事实门禁、把空检索当成功解释、原样留下未核验草稿、前端假打字、每次失败重做整轮或无限重试。严格零撤回与始终即时展示未完成模型答案存在取舍，需向用户解释。

## 6. 建议后续改造顺序（本次未实施）

1. 核对实际运行SHA/后端；先采用已验的范围与点名图读取修复，确认同原句实际获得原文/像素，而非仅改main。
2. 取证阶段只展示真实进度说明；明确需要工具的轮次不把潜在事实正文立即塞进答案。取得证据后正常流式讲解，避免一开始生成注定撤回的答案。
3. 复用上游call_id/call_role/answer_visible的思想，以现有answer_id/round_id扩展必要的片段身份；进度与可核验答案分开，修订只替换对应未发布答案。不要迁入整个StreamBus/账户系统。
4. 增加已输出状态的异常契约。显示部分正文后中断不自动透明重做；明确标未完成、不落正式历史。未输出且已有工具成果才允许有界收尾。显式用户重试继续沿用收据/新请求语义。
5. 统一连接/流空闲/工具内部模型/选证/质检与整轮预算；截止后正确退出和保存拦截。阶段心跳反映正在做什么，不泄露思考。不要只加大timeout。
6. 最终矩阵：工具前文字、延迟工具调用、首轮无取证、质量修订、首轮/后续流中断、长取证超时、ask_user恢复、取消与刷新。分别记录首个进度、首次未核验正文、取证后正文、保存时刻、撤回次数及失败原因。

## 7. 验证范围

本次`tests.test_answer_stream tests.test_q3_agent_loop`：32项通过，0.273秒，exit0；这些检查证明现有协议行为，不能当上述体验问题已修复。另有替身流探测与截图任务只读核对。没有新跑真实模型/浏览器；未修改生产代码或正式服务。

上游源码可借鉴，但现有SSE/原生JavaScript聊天页与上游React/StreamBus事件不同，须适配而非整类复制。此前上游流中断测试还存在事件消费时序问题记录，不能因引用上游就默认所有细节已无缺陷。
