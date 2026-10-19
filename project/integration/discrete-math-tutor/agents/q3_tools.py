"""Q3 tools: textbook retrieval boundary and same-task clarification."""
from __future__ import annotations

from typing import Any

from agents.ask_user_contract import AskUserPayload, build_ask_user_payload
from agents.tool_protocol import (
    BaseTool, ToolContext, ToolDefinition, ToolParameter, ToolResult,
)
from agents.q3_navigation import LearningTarget


class RetrieveCourseTool(BaseTool):
    """Q2-owned search, called only after Q3 resolved a learning target."""

    definition = ToolDefinition(
        name="retrieve_course",
        description="检索当前学习目标范围内的教材原文。先由系统确定学习目标，再调用本工具；返回带项目来源身份的摘录，引用时使用返回的[n]编号。",
        parameters=(
            ToolParameter("query", "string", "要在当前目标范围内查找的具体问题或关键词"),
            ToolParameter("limit", "integer", "返回片段数，默认6，最多10", required=False, default=6),
        ),
    )

    def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        target = context.state.get("learning_target")
        if not isinstance(target, LearningTarget):
            return ToolResult(content="尚未确定学习目标，不能检索教材。", success=False)
        query = str(arguments.get("query") or "").strip()
        if not query:
            return ToolResult(content="检索问题不能为空。", success=False)
        try:
            limit = int(arguments.get("limit", 6))
        except (TypeError, ValueError):
            limit = 6
        limit = max(1, min(10, limit))
        if context.navigation is None:
            return ToolResult(content="教材检索接口尚未接入（Q2 待完成）。", success=False,
                              metadata={"dependency": "Q2"})
        sources = context.navigation.search(target=target, query=query, limit=limit)
        if not sources:
            return ToolResult(content="当前学习目标的检索范围没有返回教材片段。", sources=[],
                              metadata={"target_id": target.target_id, "query": query})
        lines = []
        payload = []
        for index, source in enumerate(sources, 1):
            location = f"第{source.page}页" if source.page else ""
            lines.append(f"[{index}] {source.document_id} {location}\n{source.text}")
            payload.append(source.to_dict() | {"index": index,
                                                "stub": bool(source.location.get("stub"))})
        return ToolResult(content="\n\n".join(lines), sources=payload,
                          metadata={"target_id": target.target_id, "query": query,
                                    "stub": any(item["stub"] for item in payload)})


class AskUserTool(BaseTool):
    definition = ToolDefinition(
        name="ask_user",
        description="仅在缺少必要信息、无法继续原任务时，向学生提出一个到四个结构化问题。回答后会继续原任务；不要用它结束任务或重复询问已知信息。",
        raw_parameters={
            "type": "object",
            "properties": {
                "intro": {"type": "string", "description": "问题卡开头的一句话"},
                "questions": {
                    "type": "array", "minItems": 1, "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "prompt": {"type": "string"},
                            "header": {"type": "string"},
                            "multi_select": {"type": "boolean"},
                            "allow_free_text": {"type": "boolean"},
                            "options": {
                                "type": "array", "maxItems": 8,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string"},
                                        "description": {"type": "string"},
                                    },
                                    "required": ["label"],
                                },
                            },
                        },
                        "required": ["prompt"],
                    },
                },
            },
            "required": ["questions"],
        },
    )

    def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        payload, error = build_ask_user_payload(
            questions=arguments.get("questions"),
            intro=arguments.get("intro"),
            question=arguments.get("question"),
            options=arguments.get("options"),
        )
        if error:
            return ToolResult(content=error, success=False)
        assert isinstance(payload, AskUserPayload)
        return ToolResult(
            content="等待学生回答问题卡后继续原任务。",
            pause_for_user=payload.to_dict(),
            metadata={"ask_user": payload.to_dict()},
        )


def build_default_registry(navigation=None):
    from agents.tool_protocol import ToolRegistry

    registry = ToolRegistry()
    registry.register(RetrieveCourseTool())
    registry.register(AskUserTool())
    return registry


__all__ = ["AskUserTool", "RetrieveCourseTool", "build_default_registry"]
