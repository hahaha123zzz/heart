"""迁入 DeepTutor 6cf793bd… runtime/agentic/messages.py；Apache-2.0，许可见 llm/DEEPTUTOR_LICENSE。"""
from typing import Any

def with_transient_model_messages(
    messages: list[dict[str, Any]], transient: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Place model-only images after their tool result without mutating history."""
    if not transient:
        return messages
    anchored: dict[str, list[dict[str, Any]]] = {}
    for item in transient:
        tool_call_id = item.get("_after_tool_call_id")
        if not isinstance(tool_call_id, str) or not tool_call_id:
            continue
        anchored.setdefault(tool_call_id, []).append({"role": "user", "content": item["content"]})
    request_messages: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        request_messages.append(message)
        if message.get("role") == "tool":
            pending.extend(anchored.pop(str(message.get("tool_call_id") or ""), []))
            # Providers require all replies to one assistant tool-call batch
            # before another user message. Inject images after the batch.
            if index + 1 == len(messages) or messages[index + 1].get("role") != "tool":
                request_messages.extend(pending)
                pending.clear()
    return request_messages

def _transient_image_count(message: dict[str, Any]) -> int:
    content = message.get("content")
    if not isinstance(content, list):
        return 0
    return sum(1 for part in content if isinstance(part, dict) and part.get("type") == "image_url")

def extend_transient_model_messages(
    transient: list[dict[str, Any]], incoming: list[dict[str, Any]], *, max_images: int = 2
) -> None:
    """Keep the latest bounded source evidence across tool rounds."""
    transient.extend(incoming)
    while sum(_transient_image_count(item) for item in transient) > max_images:
        transient.pop(0)
