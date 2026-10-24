# Final answer publishing design

## Goal

Do not show a model draft to the student before the turn has passed its teaching and evidence checks. When accepted, keep a streamed presentation, but stream only the authoritative answer saved by the task service. If rejected, clear the empty draft state and show no unverified model text.

## Flow

1. Model token callbacks continue checking cancellation and task revision, but do not publish body text to SSE.
2. The tutoring loop evaluates its publication gate. A formative check at the end of the answer may omit a generic context preamble (for example, “睡眠与记忆的例子” shortened to “这个例子”) while preserving the same core question; normalize such presentation differences before rejecting.
3. After the task receipt is replay-validated and the saved result is `answered`, publish that saved reply in chunks, then send the authoritative full snapshot and saved state.
4. If the task is rejected, publish only the rejected state; the generated draft never leaves the server.

## Trade-off

The page starts rendering the answer after validation and persistence rather than while the model is still composing it. This prevents visible rollback while retaining chunked streaming for the final answer. The existing exact core check remains conservative so a different formative question is not silently accepted.


## 2026-10-24 提速集成时的决策更新

用户明确要求“看看 DeepTutor 怎么做，按照他的来”。核对固定上游 `6cf793bd868ba5ecbe64722936d4be8fab5a01df`：`agents/loop/pipeline.py::_capability_buffers_visible_output` 只缓冲协议载荷，明确普通 Mastery 教学实时流式；`agent_loop.py::_discard_deferred_output` 用回合身份撤回被拒绝的文字。故本设计上面的“保存后分块”在普通教学入口由该决策取代：实时候选正文保留未核验状态，核验/保存成功才为正式答案；探索及工具协议不冒充答案，被拒绝的教学修订轮按同一 round_id 撤回。引用、质检、幂等收据、取消与保存门禁不放宽。详见 OUTPUT_SPEED_EXECUTION.md 和来源台账。
