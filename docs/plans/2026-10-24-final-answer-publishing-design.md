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
