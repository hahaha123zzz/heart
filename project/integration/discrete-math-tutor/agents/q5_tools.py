"""Q5 first-batch tools mounted through the Q3 protocol and Q4 authorization.

The tool names follow the DeepTutor mastery surface where the first batch has a
matching operation.  Formal quiz/grade/assess/review tools are intentionally
not included yet; they remain follow-up Q5 work.
"""
from __future__ import annotations

import json
from typing import Any

from agents.q5_learning import (
    LearningScope,
    ObjectiveDraft,
    PlanDraft,
    Q5LearningService,
)
from agents.tool_protocol import (
    BaseTool,
    ToolContext,
    ToolDefinition,
    ToolParameter,
    ToolResult,
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _command(context: ToolContext, suffix: str) -> str:
    base = context.request_id or context.task_id or context.session_id or "q5"
    return f"{base}:{suffix}"


class _Q5Tool(BaseTool):
    def __init__(self, service: Q5LearningService, scope: LearningScope) -> None:
        self.service = service
        self.scope = scope

    def _result(self, value: dict[str, Any]) -> ToolResult:
        return ToolResult(content=_json(value), metadata={"q5": value})

    def _failure(self, exc: Exception) -> ToolResult:
        code = str(exc) or type(exc).__name__
        return ToolResult(content=code, success=False, metadata={"error": code})


class MasteryStatusTool(_Q5Tool):
    definition = ToolDefinition(
        name="mastery_status",
        description="读取当前学习路径、当前/下一目标、已讲解/已理解状态和模式。每轮先读取；不要猜下一目标。",
        parameters=(),
    )
    scopes = ("learning:read",)

    def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            from agents.session_study_service import SessionStudyService
            current=SessionStudyService(self.scope).current()
            staged=context.state.get('session_study_plan')
            if staged and current and (staged['plan_id'],staged['revision'])==(current['plan_id'],current['revision']):
                current=staged
            return self._result(dict(self.service.status(self.scope), session_plan=current))
        except Exception as exc:
            return self._failure(exc)


class MasteryBuildTool(_Q5Tool):
    definition = ToolDefinition(
        name="mastery_build",
        description="把已设计好的模块/知识点保存为草稿路径。每个目标必须带可用 source_refs；保存后先展示，确认后才开始学习。",
        parameters=(
            ToolParameter(
                name="modules",
                type="array",
                description="模块数组：{name, objective, objectives:[{name,type,source_refs,...}]}",
                items={"type": "object"},
            ),
            ToolParameter(
                name="goal", type="string", description="学习目标", required=False
            ),
            ToolParameter(
                name="path_name", type="string", description="路径名称", required=False
            ),
        ),
    )
    scopes = ("learning:plan:write",)

    def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            draft = PlanDraft.from_mapping(
                {
                    "modules": arguments.get("modules") or [],
                    "name": arguments.get("path_name") or "",
                },
                goal=str(arguments.get("goal") or ""),
            )
            result = self.service.create_plan(
                self.scope, draft, command_id=_command(context, "build")
            )
            return self._result(result)
        except Exception as exc:
            return self._failure(exc)


class MasteryNoteExplainedTool(_Q5Tool):
    definition = ToolDefinition(
        name="mastery_note_explained",
        description="记录本轮实际讲解的目标和摘要。只记录已讲解，不授予掌握、不推进正式门槛。",
        parameters=(
            ToolParameter(
                name="knowledge_point_id",
                type="string",
                description="当前目标 ID（来自 mastery_status）",
            ),
            ToolParameter(
                name="summary", type="string", description="本轮实际讲解的摘要"
            ),
        ),
    )
    scopes = ("learning:explain:write",)

    def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            result = self.service.record_explained(
                self.scope,
                str(arguments.get("knowledge_point_id") or ""),
                summary=str(arguments.get("summary") or ""),
                command_id=_command(context, "explained"),
            )
            return self._result(result)
        except Exception as exc:
            return self._failure(exc)


class MasteryUnderstoodTool(_Q5Tool):
    definition = ToolDefinition(
        name="mastery_understood",
        description="仅当学生明确表示“我懂了/下一部分”时，推进当前教学位置到下一目标；不产生掌握分、不替代正式评估。",
        parameters=(),
    )
    scopes = ("learning:position:write",)

    def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            status = self.service.status(self.scope)
            return self._result(
                self.service.mark_understood(
                    self.scope,
                    command_id=_command(context, "understood"),
                    base_revision=int(status.get("path_revision") or 0) or None,
                )
            )
        except Exception as exc:
            return self._failure(exc)


class MasteryModeTool(_Q5Tool):
    definition = ToolDefinition(
        name="mastery_mode",
        description="切换 outline/study/review；study 需要计划已确认。切换会持久化，并告知学生。",
        parameters=(
            ToolParameter(
                name="mode",
                type="string",
                description="outline|study|review",
                enum=["outline", "study", "review"],
            ),
            ToolParameter(
                name="confirm",
                type="boolean",
                description="切到 study 且计划还是草稿时，学生已明确认可计划后传 true",
                required=False,
            ),
            ToolParameter(name="reason", type="string", required=False),
        ),
    )
    scopes = ("learning:mode:write",)

    def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            result = self.service.set_mode(
                self.scope,
                str(arguments.get("mode") or ""),
                command_id=_command(context, "mode"),
                confirm=bool(arguments.get("confirm")),
            )
            if arguments.get("reason"):
                result["reason"] = str(arguments["reason"])[:200]
            return self._result(result)
        except Exception as exc:
            return self._failure(exc)


class MasteryPathsTool(_Q5Tool):
    definition = ToolDefinition(
        name="mastery_paths",
        description="列出当前学生的学习路径及当前目标；切换前先读取。",
        parameters=(),
    )
    scopes = ("learning:read",)

    def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            return self._result({"paths": self.service.list_paths(self.scope)})
        except Exception as exc:
            return self._failure(exc)


class MasterySwitchTool(_Q5Tool):
    definition = ToolDefinition(
        name="mastery_switch",
        description="把当前会话切到学生已有路径；路径进度保留，失败保持原路径。",
        parameters=(
            ToolParameter(name="path_id", type="string", description="路径 ID"),
        ),
    )
    scopes = ("learning:path:write",)

    def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            result = self.service.switch_path(
                self.scope,
                str(arguments.get("path_id") or ""),
                command_id=_command(context, "switch"),
            )
            return self._result(result)
        except Exception as exc:
            return self._failure(exc)


class MasteryLeaveTool(_Q5Tool):
    definition = ToolDefinition(
        name="mastery_leave",
        description="当前会话离开活动路径；路径进度保留，可恢复。",
        parameters=(),
    )
    scopes = ("learning:path:write",)

    def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            return self._result(
                self.service.leave_path(
                    self.scope, command_id=_command(context, "leave")
                )
            )
        except Exception as exc:
            return self._failure(exc)


class MasteryReviseTool(_Q5Tool):
    definition = ToolDefinition(
        name="mastery_revise",
        description="在 outline 模式局部修改一个目标名称；已讲解/已理解目标受保护。",
        parameters=(
            ToolParameter(name="objective_id", type="string"),
            ToolParameter(name="name", type="string"),
        ),
    )
    scopes = ("learning:plan:write",)

    def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            status = self.service.status(self.scope)
            if not status.get("path_id"):
                raise ValueError("path_not_found")
            result = self.service.revise_objective(
                self.scope,
                str(status["path_id"]),
                str(arguments.get("objective_id") or ""),
                str(arguments.get("name") or ""),
                base_revision=int(status.get("path_revision") or 0),
                command_id=_command(context, "revise"),
            )
            return self._result(result)
        except Exception as exc:
            return self._failure(exc)


def q5_tool_instances(service: Q5LearningService,
                      scope: LearningScope) -> list[BaseTool]:
    return [
        MasteryStatusTool(service, scope),
        MasteryBuildTool(service, scope),
        MasteryNoteExplainedTool(service, scope),
        MasteryUnderstoodTool(service, scope),
        MasteryModeTool(service, scope),
        MasteryPathsTool(service, scope),
        MasterySwitchTool(service, scope),
        MasteryLeaveTool(service, scope),
        MasteryReviseTool(service, scope),
    ]


def build_q5_registry(service: Q5LearningService, scope: LearningScope):
    """Build the per-turn Q4 authorized registry containing Q5's first tools."""
    from agents.tools.registry import ScopedToolRegistry, ToolRegistry
    from agents.tools.scope import Allowlist, ToolGrant

    overlay = q5_tool_instances(service, scope)
    names = {tool.definition.name for tool in overlay}
    grant = ToolGrant(
        tools=Allowlist.of(names),
        scopes=frozenset(
            {
                "learning:read",
                "learning:plan:write",
                "learning:explain:write",
                "learning:position:write",
                "learning:mode:write",
                "learning:path:write",
            }
        ),
    )
    return ScopedToolRegistry(
        base=ToolRegistry(),
        overlay=overlay,
        grant=grant,
        selected=names,
    )


__all__ = [
    "MasteryBuildTool",
    "MasteryLeaveTool",
    "MasteryModeTool",
    "MasteryNoteExplainedTool",
    "MasteryPathsTool",
    "MasteryReviseTool",
    "MasteryStatusTool",
    "MasterySwitchTool",
    "MasteryUnderstoodTool",
    "build_q5_registry",
    "q5_tool_instances",
]
