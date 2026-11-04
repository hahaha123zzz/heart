# 会话并行与生成状态标记 · 设计

日期：2026-11-04
范围：`project/integration/discrete-math-tutor`

## 目标

1. 会话 A 生成回答时，可以切到会话 B 并直接提问；两个会话各自独立生成、独立渲染。
2. 左侧会话列表每行右侧显示状态：
   - 生成中：转圈圆环。
   - 离开该会话期间完成：醒目的红点。
   - 点击该行（含点）即打开会话，同时清掉点。
3. 用户正停在该会话里看它生成完，不显示点。

## 现状与约束

- `frontend/app.js` 的 `switchConversation()` 被全局 `state.sending` 拦截，无法在生成时切换。
- 流式事件直接写全局 `state.chat` 并立即 `renderChat()`，没有会话维度。
- 后端 `main.py` 的 `/api/chat/stream` 用按 `student_id` 哈希的 `_turn_locks` 串行化同一学生的所有提问。任务状态本身按 `(student_id, session_id)` 存储，不存在数据冲突。
- 服务端会话列表 `/api/students/{id}/conversation-sessions` 只返回标题，不返回生成状态；状态标记是纯前端行为。

## 前端设计

### 状态模型（`frontend/app.js`）

| 名称 | 类型 | 含义 |
|---|---|---|
| `busySessions` | `Set<sessionId>` | 正在生成或执行短操作的会话 |
| `doneSessions` | `Map<sessionId, 'done'\|'failed'>` | 离开期间完成、尚未查看的结果 |
| `sessionChats` | `Map<sessionId, messages[]>` | 生成中会话的实时消息数组 |
| `sessionLabels` | `Map<sessionId, string>` | 服务端列表滞后时的标题兜底 |

- 删除 `state.sending`，改为 `busy(session = tabSessionId)` 判定当前会话是否忙碌；写入处统一 `markBusy(value, session)`。
- `markBusy` 只在该会话是当前会话时同步发送按钮。
- `syncComposer()`：按 `busy()` 设置 `.chat-input button` 的 `disabled`。切换会话后必须调用。

### 发送流程（`sendMessage`）

- 函数开头记录 `session = tabSessionId`；`await taskSessionReady` 后若 `session !== tabSessionId` 则放弃本次发送。
- 固定 `chat = state.chat`、`style = styleControl(session)`、`readerLocation` 快照；payload 的 `session_id` 用 `session`。
- 流式回调、进度、草稿事件**始终**写入 `pending` 消息对象；只有 `session === tabSessionId` 时调用 `renderChat()`。
- 完成时 `session !== tabSessionId`：
  - `doneSessions.set(session, pending.failed ? 'failed' : 'done')`
  - 不更新 `state.clarification`、`state.sessionPlan`、`state.clarificationObject`
  - 不执行阅读器跳页动作
  - `finally` 中删除 `sessionChats` 的该会话条目（下次切回走历史接口）
- 完成时在当前会话：保持现有行为，且不产生点。

### 切换流程（`switchConversation`）

- 去掉 `busy()` 拦截，保留 `switchingConversation` / `initializing` 拦截。
- 切走前：若当前会话 `busy()`，`sessionChats.set(oldSession, state.chat)`。
- 切到目标会话：
  - `doneSessions.delete(target)`。
  - 若目标 `busy()` 且 `sessionChats` 有实时数组：直接使用该数组渲染，跳过历史加载与 `restore*`（生成中的服务端状态不完整）。
  - 否则走现有历史加载 + `restoreLearningCards` / `restoreClarification` / `restoreGraphs`。
- 切换完成后 `syncComposer()`。

### 提示卡/风格/澄清

- `styleControl(session = tabSessionId)` 增加可选会话参数；生成任务在完成时用所属会话读写 `consume` / `observe`，避免覆盖其他会话的临时风格。
- `cancelClarification(task = state.clarification, session = tabSessionId)` 参数化；只有目标会话是当前会话时才改 `state.clarification` 并重绘。
- 后台完成产生的风格建议不即时展示；切回会话后由现有恢复逻辑处理。

### 列表渲染（`renderConversationList`）

- 行结构：`<button data-session-id><span class="conversation-label">title</span><span class="conversation-status ..."></span></button>`。
- 行集合 = 服务端会话 ∪ 当前会话 ∪ `busySessions` ∪ `doneSessions`；缺失标题用 `sessionLabels`，再退回“新对话”。
- `sessionLabels` 来源：`refreshConversations()` 的服务端标题；发送开始时用提问文本前 40 字兜底。
- 状态类：
  - `is-thinking`：12px 缺口圆环，0.8s 线性旋转。
  - `is-done`：8px 红点 + 3px 淡红光晕。
  - `is-failed`：橙色点。
- 状态标记带 `aria-label`（“正在生成”“有新回答”“回答失败”）。
- 点击行沿用现有 `[data-session-id]` 委托，不需要额外处理器。

### 样式（`frontend/workspace-layout.css`）

- `.conversation-list button` 改为 `display:flex; align-items:center; gap:8px`。
- `.conversation-label` 承担 `flex:1; min-width:0` 与省略号。
- 新增 `conversation-spin` 关键帧；`prefers-reduced-motion: reduce` 下停止旋转。

## 后端设计

`main.py` `_run_turn` 的锁索引改为按 `student_id + session_id`：

```python
identity = f"{request.student_id}:{request.session_id or 'legacy'}"
index = int.from_bytes(hashlib.sha256(identity.encode()).digest()[:2], "big") % len(_turn_locks)
```

同一会话仍串行，不同会话可并发。加一行注释说明意图。

## 明确不做

- 不把生成状态持久化到服务端；刷新页面后转圈/红点消失。
- 不做多标签页之间的状态同步（BroadcastChannel 只保留现有的会话编号认领）。
- 不新增接口、不新增依赖。
- 不改任务 revision、澄清、学习计划的服务端语义。

## 验证

1. `pytest` 现有与 `/api/chat/stream`、会话相关测试通过。
2. 8000 端口 Playwright 真实流程：
   - A 发送后立即切 B，B 发送成功；
   - 两个会话行同时出现转圈；
   - A 在后台完成后，B 中看到 A 的红点；
   - 点 A：红点消失，答案完整、无重复；
   - 在 A 生成完时停留在 A：不出现红点。
3. 服务端日志无 SQLite 锁冲突、无 task 冲突；两个会话的回答各自保存。
4. 前端无未捕获异常（浏览器 console）。
