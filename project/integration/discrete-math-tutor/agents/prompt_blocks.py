"""Named prompt blocks for the project's single-turn and loop prompts.

Ported in spirit from DeepTutor ``agents/loop/prompt_blocks.py``. The project
does not yet mount loop tools, so only the shared rendering contract is reused:
stable named blocks are assembled once, empty blocks are omitted, and one
language directive closes the rendered system prompt.
"""

from __future__ import annotations

from dataclasses import dataclass

from agents.prompt_language import append_language_directive


@dataclass(frozen=True)
class PromptBlock:
    name: str
    content: str


def render_blocks(
    blocks: list[PromptBlock],
    *,
    language: str = "zh",
    allow_user_override: bool = True,
) -> str:
    """Render non-empty blocks in order and append the language contract."""

    joined = "\n\n---\n\n".join(
        f"## {block.name}\n{block.content.strip()}"
        for block in blocks
        if block.content and block.content.strip()
    )
    return append_language_directive(
        joined, language, allow_user_override=allow_user_override
    )


__all__ = ["PromptBlock", "render_blocks"]
