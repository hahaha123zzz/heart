"""所有宿主提示词使用上游 PromptBlock 与统一渲染器。"""
from agents.context_runtime.protocol import PromptBlock
from agents.context_runtime.prompt_blocks import LoopPromptAssembler


def render_blocks(blocks, *, language="zh", allow_user_override=True):
    return LoopPromptAssembler(prompts={}, language=language).render(
        blocks, allow_user_override=allow_user_override)


__all__ = ["PromptBlock", "render_blocks"]
