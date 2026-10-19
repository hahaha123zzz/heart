"""Prompt assembly for the Q3 local loop."""
from __future__ import annotations

from agents.prompt_blocks import PromptBlock, render_blocks
from agents.q3_navigation import LearningTarget
from agents.tool_protocol import ToolDefinition
from knowledge.course_config import PSYCHOLOGY


def _tool_manifest(definitions: list[ToolDefinition]) -> str:
    lines = []
    for definition in definitions:
        parameters = "，".join(
            f"{p.name}:{p.type}{'' if p.required else '?'}" for p in definition.parameters
        )
        lines.append(f"- {definition.name}（{parameters}）：{definition.description}")
    return "\n".join(lines)


def build_loop_system_prompt(*, target: LearningTarget | None,
                             definitions: list[ToolDefinition],
                             course_prompt: str | None = None) -> str:
    base = course_prompt
    if base is None:
        if PSYCHOLOGY:
            from agents.course_prompts import RESPONSE
            base = RESPONSE
        else:
            base = "你是基于教材的课程助教。只依据本轮提供的教材证据陈述教材内容。"
    target_text = "尚未确定" if target is None else (
        f"{target.name}（目标ID：{target.target_id}；章节：{target.chapter_id or '-'}；"
        f"小节：{target.section_id or '-'}）")
    protocol = """本轮在一个循环内完成：你可以调用工具，也可以直接回答。
- 需要教材事实时先调用 retrieve_course；工具返回的 [1][2] 是本轮可引用编号。
- 只有缺少必要信息、无法继续原任务时才调用 ask_user；一次问全，回答后继续原任务，不要只回复确认。
- 不存在的工具不能调用；不要声称未执行的工具成功。
- 没有工具调用的回复就是最终回答。先直接回答，再补充必要解释；不要输出内部推理或工具协议。
- 教材证据不足时明确说明，不编造数据、页码、定理编号或来源。
- 只回答学生明确询问的对象；不主动扩展未问的变量、分类或比较。回答尽量控制在400字内。
- 当前学习目标由系统确定；不要把“下一知识点”原句当作检索目标，也不要在没有路径时猜下一目标。"""
    blocks = [
        PromptBlock("course_policy", base),
        PromptBlock("loop_protocol", protocol),
        PromptBlock("learning_target", target_text),
        PromptBlock("tools", _tool_manifest(definitions)),
    ]
    return render_blocks(blocks, language="zh")


__all__ = ["build_loop_system_prompt"]
