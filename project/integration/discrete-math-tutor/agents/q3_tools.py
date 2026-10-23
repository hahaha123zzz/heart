"""Q3 tools: textbook retrieval boundary and same-task clarification."""
from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any

from agents.ask_user_contract import AskUserPayload, build_ask_user_payload
from agents.tool_protocol import (
    BaseTool, ToolContext, ToolDefinition, ToolParameter, ToolResult,
)
from agents.q3_navigation import LearningTarget

# Retrieval calls may run in parallel inside one assistant tool batch. Reserve
# citation numbers under one lock so [n] never means two different sources.
_RETRIEVE_LOCK = RLock()


class RetrieveCourseTool(BaseTool):
    """Q2-owned search, called only after Q3 resolved a learning target."""

    definition = ToolDefinition(
        name="retrieve_course",
        description="检索教材原文。系统保留当前学习目标和路径；用户显式跨章插问时按问题范围检索。引用时使用返回的[n]编号。关联候选不是独立事实或先修关系。",
        parameters=(
            ToolParameter("query", "string", "要在当前目标范围内查找的具体问题或关键词"),
            ToolParameter("limit", "integer", "返回片段数，默认6，最多10", required=False, default=6),
            ToolParameter("asset_id", "string", "仅使用工具返回过或用户指定的教材原图ID", required=False),
        ),
    )

    def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        with _RETRIEVE_LOCK:
            return self._run(arguments, context)

    def _run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
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
        offset = max(0, int(context.state.get("source_offset", 0) or 0))
        max_sources = max(1, int(context.state.get("max_sources", 24) or 24))
        if offset >= max_sources:
            return ToolResult(
                content=("本轮教材检索预算已用完。请停止检索，直接基于已经取得的证据回答；"
                         "如果仍不足，明确说明缺少什么，不要继续调用 retrieve_course。"),
                success=False,
                metadata={"target_id": target.target_id, "query": query,
                          "source_budget_exhausted": True},
            )
        limit = min(limit, max_sources - offset)
        if context.navigation is None:
            return ToolResult(content="教材检索接口尚未接入（Q2 待完成）。", success=False,
                              metadata={"dependency": "Q2"})
        sources = context.navigation.search(target=target, query=query, limit=limit)
        if not sources:
            return ToolResult(content="本轮问题没有返回可核验原文。请按检索记录区分指定图号缺失/歧义与证据不足；不能据此断言整本教材没有，也不要重复相同查询。", sources=[],
                              metadata={"target_id": target.target_id, "query": query})
        seen = context.state.setdefault("seen_source_ids", set())
        fresh = []
        for source in sources:
            source_id = str(getattr(source, "source_id", "") or "")
            if not source_id:
                source_id = f"{source.document_id}:{hash(source.text)}"
            if source_id in seen:
                continue
            seen.add(source_id)
            fresh.append(source)
        if not fresh:
            return ToolResult(
                content=("本轮已经返回过相同教材片段，引用编号保持不变。"
                         "请停止重复检索，直接使用已有编号回答。"),
                success=False,
                metadata={"target_id": target.target_id, "query": query,
                          "duplicate_retrieval": True},
            )
        lines = []
        payload = []
        # Number citations across the whole turn, not per tool call: the model
        # may retrieve more than once, and [1] must keep the same meaning in
        # every tool result, the final answer and the quality gate.
        for position, source in enumerate(fresh, 1):
            index = offset + position
            location = f"第{source.page}页" if source.page else ""
            lines.append(f"[{index}] {source.document_id} {location}\n{source.text}")
            payload.append(source.to_dict() | {"index": index,
                                                "image_refs": [],
                                                "stub": bool(source.location.get("stub"))})
        context.state["source_offset"] = offset + len(payload)
        from knowledge.answer_media import selected_media, model_message
        media = selected_media(query, payload, asset_id=arguments.get('asset_id'))
        for item in media:
            source = next(s for s in payload if (s['chapter_id'], s['section_id']) == (item['chapter_id'], item['section_id']))
            source.setdefault('image_refs', []).append(item)
        visual_message = model_message(media)
        if media:
            import json
            lines.append('有效教材原图（身份已核对，审核状态仍按原记录；未收到像素时只依据文字）：\n'
                         + json.dumps(media, ensure_ascii=False))
        from agents.course_search import association_context
        relations = [] if hasattr(context.navigation, 'tool_context') else association_context(context.navigation, fresh)
        if relations:
            import json
            lines.append('关联候选（图谱描述，仅供查找联系；不得据此推断先修、重点或掌握，'
                         '只有所链接原文支持的事实可用原文编号引用）：\n' + json.dumps(relations, ensure_ascii=False))
        return ToolResult(content="\n\n".join(lines), sources=payload, model_message=visual_message,
                          metadata={"target_id": target.target_id, "query": query,
                                    "retrieval": list(getattr(context.navigation, 'calls', []))[-1:],
                                    "association_candidates": len(relations),
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


def build_registry(*, workspace_root: str | Path | None = None,
                   skills_root: str | Path | None = None,
                   allow_workspace: bool = False,
                   allow_skills: bool = True,
                   extra_tools: tuple[Any, ...] = (),
                   extra_scopes: tuple[str, ...] = ()):
    """Build the per-turn authorized registry used by the Q3 loop.

    Q3 owns the tool protocol; Q4 owns the process catalogue, lazy built-ins,
    grant/scope checks and the per-turn authorized view.  Only tools granted
    for this turn are visible to the model, and the same grant is checked
    again at execution time.
    """
    from agents.tools.local_specs import LOCAL_TOOL_SPECS, TOOL_ALIASES
    from agents.tools.registry import ScopedToolRegistry, ToolRegistry
    from agents.tools.scope import Allowlist, ToolGrant

    base = ToolRegistry(aliases=TOOL_ALIASES)
    base.load_builtins(LOCAL_TOOL_SPECS)
    overlay = [RetrieveCourseTool(), AskUserTool(), *extra_tools]
    names = {"retrieve_course", "ask_user"} | {
        tool.definition.name for tool in extra_tools
    }
    scopes: set[str] = set(extra_scopes)
    workspace = Path(workspace_root).resolve() if workspace_root else None
    skills = Path(skills_root).resolve() if skills_root else None
    if allow_workspace and workspace is not None:
        names.update({"workspace_list", "workspace_read", "workspace_search"})
        scopes.add("workspace:read")
    if allow_skills and skills is not None:
        names.add("read_skill")
        scopes.add("skills:read")
    grant = ToolGrant(
        tools=Allowlist.of(names),
        scopes=frozenset(scopes),
        workspace_root=workspace,
        skills_root=skills,
    )
    return ScopedToolRegistry(
        base=base, overlay=overlay, grant=grant, selected=names,
    )


def build_default_registry(navigation=None):
    """Compatibility entry point for callers/tests without task resources."""
    return build_registry(allow_workspace=False, allow_skills=False)


__all__ = ["AskUserTool", "RetrieveCourseTool", "build_default_registry",
           "build_registry"]
