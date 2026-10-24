# New conversation design

## Goal

Let the same learner start a clean tutor conversation without creating a new demo learner or deleting existing chat and learning records.

## Chosen approach

- Treat the existing per-tab `session_id` as the conversation thread identifier.
- Add a “＋ 新对话” control in the chat header. It creates a fresh session ID, clears only the current chat presentation and unsent draft, and keeps the learner ID and durable learning memory unchanged.
- Persist the session ID on conversation rows and filter chat-history reads by it. The tutor's task context and PDF-selection context must use the same session boundary.
- Keep the history API's unfiltered mode for the learning-records page. Existing rows remain untouched and continue to appear there; their `session_id` stays `NULL` because their former thread boundaries were never stored.
- Apply an idempotent schema migration on startup to add the nullable field and index. No history is deleted or reassigned.

## Consequences

- A new chat is blank after refresh and does not send prior thread messages as conversational history.
- Course-wide learning memory, preferences, mastery, and learning records remain associated with the same learner.
- Old messages are preserved and remain accessible in “学习记录” → “近期对话”; they cannot be reconstructed as separate old threads because the former schema did not store thread IDs.
- Opening a new chat does not cancel a request already in flight; the action is refused while the tutor is generating.

## Verification

Check Python and JavaScript syntax, inspect the schema/history filters, and verify the running app health and UI. Do not run the full test suite unless requested.
