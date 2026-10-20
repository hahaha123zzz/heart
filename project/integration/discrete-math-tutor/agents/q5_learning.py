"""Q5 first-batch learning-path service.

The persistence model is adapted from DeepTutor ``learning/models.py`` and the
decision semantics from ``learning/policy.py`` at commit
``6cf793bd868ba5ecbe64722936d4be8fab5a01df`` (Apache-2.0).  This module keeps
only the first-batch chain: generate a draft plan, confirm it, explain an
objective, mark teaching position understood, switch/leave/resume.  Formal
questions, mastery gates, review scheduling and teacher review are intentionally
not implemented here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable
from uuid import uuid4

from sqlalchemy import select

from database.database import session_scope
from database.q5_learning import (
    Q5BindingRow,
    Q5CommandRow,
    Q5ModuleRow,
    Q5ObjectiveRow,
    Q5PathRow,
    Q5ProgressRow,
)

KNOWLEDGE_TYPES = frozenset({"memory", "procedure", "concept", "design"})
MODES = frozenset({"outline", "study", "review"})
INTAKE_FIELDS: tuple[tuple[str, str], ...] = (
    ("prior_knowledge", "你已经会什么？"),
    ("target_level", "对你来说学到什么程度算完成？"),
    ("time_budget", "你大概有多少时间？"),
    ("preferences", "你希望怎么教？"),
)


def intake_gaps(profile: dict[str, Any] | None) -> list[dict[str, str]]:
    """Return only empty intake fields; ask at most once, never re-ask known values."""
    profile = profile or {}
    questions: list[dict[str, str]] = []
    for field, prompt in INTAKE_FIELDS:
        value = profile.get(field)
        if isinstance(value, str) and value.strip():
            continue
        questions.append(
            {
                "id": field,
                "prompt": prompt,
                "allow_free_text": True,
            }
        )
    return questions[:4]


@dataclass(frozen=True)
class LearningScope:
    student_id: str
    session_id: str
    course_id: str = ""
    actor: str = "student"


@dataclass(frozen=True)
class ObjectiveDraft:
    name: str
    knowledge_type: str = "concept"
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    prerequisite_ids: list[str] = field(default_factory=list)
    required_visual_tasks: list[str] = field(default_factory=list)


@dataclass
class PlanDraft:
    goal: str
    modules: list[tuple[str, str, list[ObjectiveDraft]]]
    name: str = ""
    source_scope: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: dict[str, Any], *, goal: str = "") -> "PlanDraft":
        modules: list[tuple[str, str, list[ObjectiveDraft]]] = []
        for module in data.get("modules") or []:
            if not isinstance(module, dict):
                continue
            objectives: list[ObjectiveDraft] = []
            raw_objectives = module.get("objectives") or module.get("knowledge_points") or []
            for item in raw_objectives:
                if not isinstance(item, dict):
                    continue
                refs = item.get("source_refs") or item.get("topic_source_refs") or []
                objectives.append(
                    ObjectiveDraft(
                        name=str(item.get("name") or "").strip(),
                        knowledge_type=str(
                            item.get("knowledge_type") or item.get("type") or "concept"
                        ).strip(),
                        source_refs=[dict(ref) for ref in refs if isinstance(ref, dict)],
                        prerequisite_ids=[
                            str(value)
                            for value in (item.get("prerequisite_ids") or [])
                            if str(value).strip()
                        ],
                        required_visual_tasks=[
                            str(value)
                            for value in (item.get("required_visual_tasks") or [])
                            if str(value).strip()
                        ],
                    )
                )
            modules.append(
                (
                    str(module.get("name") or "").strip(),
                    str(module.get("objective") or "").strip(),
                    objectives,
                )
            )
        return cls(
            goal=str(data.get("goal") or goal or "").strip(),
            name=str(data.get("name") or data.get("path_name") or "").strip(),
            modules=modules,
            source_scope=dict(data.get("source_scope") or {}),
        )


class Q5LearningService:
    def __init__(
        self,
        *,
        source_validator: Callable[[dict[str, Any]], bool] | None = None,
        generator: Any = None,
    ) -> None:
        self._source_validator = source_validator or _default_source_valid
        self._generator = generator

    # -- commands -----------------------------------------------------
    def generate_plan(
        self,
        scope: LearningScope,
        *,
        goal: str,
        materials: Iterable[dict[str, Any]],
        profile: dict[str, Any] | None,
        command_id: str,
        generator: Any = None,
        path_name: str = "",
    ) -> dict[str, Any]:
        if not command_id:
            raise ValueError("command_id_required")
        replayed = self._replay(scope, command_id)
        if replayed is not None:
            return replayed
        source = generator or self._generator
        if source is None or not hasattr(source, "generate"):
            raise ValueError("plan_generator_unavailable")
        draft = source.generate(
            goal=goal,
            materials=list(materials),
            profile=dict(profile or {}),
        )
        if not isinstance(draft, PlanDraft):
            raise ValueError("plan_generator_invalid")
        if path_name:
            draft.name = path_name
        return self._persist_draft(scope, draft, command_id, command_type="generate_plan")

    def create_plan(
        self, scope: LearningScope, draft: PlanDraft, *, command_id: str
    ) -> dict[str, Any]:
        """Persist a caller/model-authored draft after validation (tool path)."""
        return self._persist_draft(
            scope, draft, command_id, command_type="mastery_build"
        )

    def bind_textbook_target(
        self,
        scope: LearningScope,
        target: dict[str, Any],
        *,
        command_id: str,
    ) -> dict[str, Any]:
        """Project the current Q2 navigation target into Q5 without a local cursor.

        Q2 remains authoritative for textbook order.  This method stores only
        the current target/source version, so a later Q2 ``next`` call replaces
        the current objective; Q5 never computes a competing directory next.
        """
        if not isinstance(target, dict):
            raise ValueError("navigation_target_required")
        unit_id = str(
            target.get("unit_id") or target.get("id") or target.get("target_id") or ""
        ).strip()
        version = str(
            target.get("version") or target.get("source_version") or ""
        ).strip()
        if not unit_id or not version:
            raise ValueError("navigation_target_unavailable")
        title = str(target.get("title") or target.get("name") or unit_id).strip()
        ref = {
            "source_kind": "q2_navigation",
            "unit_id": unit_id,
            "version": version,
            "document_id": str(
                target.get("document_id") or target.get("source") or ""
            ),
            "chapter_id": target.get("chapter_id"),
            "section_id": target.get("section_id"),
            "page": target.get("page"),
            "title": title[:200],
            "release_id": str(target.get("release_id") or ""),
            "source_version": str(target.get("source_version") or ""),
        }
        replayed = self._replay(scope, command_id)
        if replayed is not None:
            return replayed
        with session_scope(immediate=True) as session:
            replay = self._command(session, scope, command_id)
            if replay is not None:
                return replay
            binding = self._ensure_binding(session, scope)
            path = self._binding_path(session, scope, binding, for_update=True)
            if path is None or path.kind != "textbook_navigation":
                path = Q5PathRow(
                    path_id=uuid4().hex,
                    student_id=scope.student_id,
                    course_id=scope.course_id,
                    kind="textbook_navigation",
                    name="教材目录导学",
                    goal="沿教材目录学习",
                    status="active",
                    revision=1,
                    plan_confirmed=True,
                    teaching_complete=False,
                    source_scope={"q2_cursor": dict(target)},
                )
                session.add(path)
                session.flush()
                module = Q5ModuleRow(
                    module_id=uuid4().hex,
                    path_id=path.path_id,
                    position=0,
                    name="教材导航",
                    objective="沿 Q2 当前教材目标学习",
                )
                session.add(module)
                session.flush()
                path.current_module_id = module.module_id
            else:
                module = session.get(Q5ModuleRow, path.current_module_id)
                if module is None:
                    module = session.scalars(
                        select(Q5ModuleRow)
                        .where(Q5ModuleRow.path_id == path.path_id)
                        .order_by(Q5ModuleRow.position)
                    ).first()
                if module is None:
                    module = Q5ModuleRow(
                        module_id=uuid4().hex,
                        path_id=path.path_id,
                        position=0,
                        name="教材导航",
                        objective="沿 Q2 当前教材目标学习",
                    )
                    session.add(module)
                    session.flush()
                path.source_scope = {"q2_cursor": dict(target)}
                path.updated_at = _now()
            objective = next(
                (
                    row
                    for row in self._ordered_objectives(session, path.path_id)
                    if any(
                        isinstance(source, dict)
                        and str(source.get("unit_id") or "") == unit_id
                        and str(source.get("version") or "") == version
                        for source in (row.source_refs or [])
                    )
                ),
                None,
            )
            if objective is None:
                position = len(
                    [
                        row
                        for row in self._ordered_objectives(session, path.path_id)
                        if row.module_id == module.module_id
                    ]
                )
                objective = Q5ObjectiveRow(
                    objective_id=uuid4().hex,
                    path_id=path.path_id,
                    module_id=module.module_id,
                    position=position,
                    name=title,
                    knowledge_type="concept",
                    source_refs=[ref],
                )
                session.add(objective)
                session.flush()
                session.add(
                    Q5ProgressRow(
                        path_id=path.path_id, objective_id=objective.objective_id
                    )
                )
            path.current_objective_id = objective.objective_id
            path.current_module_id = objective.module_id
            path.revision += 1
            path.updated_at = _now()
            binding.active_path_id = path.path_id
            binding.mode = "study"
            binding.revision += 1
            binding.updated_at = _now()
            result = {
                "status": "navigation_bound",
                "path_id": path.path_id,
                "path_revision": path.revision,
                "objective_id": objective.objective_id,
                "target_id": unit_id,
                "path_kind": path.kind,
            }
            self._save_command(
                session, scope, command_id, "bind_textbook_target", result
            )
            return result

    def bind_selection(
        self,
        scope: LearningScope,
        selection: dict[str, Any],
        *,
        goal: str,
        command_id: str,
        path_id: str = "",
        path_name: str = "",
    ) -> dict[str, Any]:
        """Create or bind a path from a Q2-resolved selection without re-selecting.

        ``selection`` is the server-resolved selection (document/version/
        chapter/section/page/text), never raw client coordinates alone.  With a
        path id, an objective whose source matches is selected; otherwise a
        one-objective draft is created around the selected source.
        """
        ref = selection_source_ref(selection)
        if path_id:
            replayed = self._replay(scope, command_id)
            if replayed is not None:
                return replayed
            with session_scope(immediate=True) as session:
                replay = self._command(session, scope, command_id)
                if replay is not None:
                    return replay
                path = self._owned_path(session, scope, path_id, for_update=True)
                ordered = self._ordered_objectives(session, path.path_id)
                target = next(
                    (
                        row
                        for row in ordered
                        if _selection_matches_refs(row.source_refs or [], ref)
                    ),
                    None,
                )
                if target is None:
                    raise ValueError("selection_not_in_path")
                path.current_objective_id = target.objective_id
                path.current_module_id = target.module_id
                path.revision += 1
                path.updated_at = _now()
                binding = self._ensure_binding(session, scope)
                binding.active_path_id = path.path_id
                binding.mode = "study" if path.plan_confirmed else "outline"
                binding.revision += 1
                binding.updated_at = _now()
                result = {
                    "status": "selection_bound",
                    "path_id": path.path_id,
                    "path_revision": path.revision,
                    "objective_id": target.objective_id,
                }
                self._save_command(
                    session, scope, command_id, "bind_selection", result
                )
                return result
        title = str(selection.get("title") or selection.get("section_title") or "").strip()
        text = str(selection.get("text") or selection.get("quote") or "").strip()
        objective_name = (title or text[:80] or goal or "圈选内容").strip()
        draft = PlanDraft(
            goal=goal or objective_name,
            name=path_name or f"圈选学习：{objective_name[:60]}",
            modules=[
                (
                    "圈选内容",
                    f"能解释并应用：{objective_name[:120]}",
                    [ObjectiveDraft(objective_name, "concept", [ref])],
                )
            ],
        )
        return self._persist_draft(
            scope, draft, command_id, command_type="bind_selection"
        )

    def confirm_plan(
        self,
        scope: LearningScope,
        path_id: str,
        *,
        base_revision: int,
        command_id: str,
    ) -> dict[str, Any]:
        replayed = self._replay(scope, command_id)
        if replayed is not None:
            return replayed
        with session_scope(immediate=True) as session:
            replay = self._command(session, scope, command_id)
            if replay is not None:
                return replay
            path = self._owned_path(session, scope, path_id, for_update=True)
            if path.revision != int(base_revision):
                raise ValueError("path_conflict")
            objectives = session.scalars(
                select(Q5ObjectiveRow).where(Q5ObjectiveRow.path_id == path_id)
            ).all()
            if not objectives:
                raise ValueError("plan_has_no_objectives")
            path.plan_confirmed = True
            path.status = "active"
            path.revision += 1
            path.updated_at = _now()
            binding = self._ensure_binding(session, scope)
            binding.active_path_id = path_id
            binding.mode = "outline"
            binding.revision += 1
            binding.updated_at = _now()
            result = {
                "status": "active",
                "path_id": path_id,
                "path_revision": path.revision,
                "plan_confirmed": True,
                "mode": binding.mode,
            }
            self._save_command(session, scope, command_id, "confirm_plan", result)
            return result

    def set_mode(
        self,
        scope: LearningScope,
        mode: str,
        *,
        command_id: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        if mode not in MODES:
            raise ValueError("invalid_mode")
        replayed = self._replay(scope, command_id)
        if replayed is not None:
            return replayed
        with session_scope(immediate=True) as session:
            replay = self._command(session, scope, command_id)
            if replay is not None:
                return replay
            binding = self._ensure_binding(session, scope)
            path = self._binding_path(session, scope, binding, for_update=True)
            if mode == "study" and path is not None and not path.plan_confirmed:
                if not confirm:
                    raise ValueError("plan_confirmation_required")
                path.plan_confirmed = True
                path.status = "active"
                path.revision += 1
                path.updated_at = _now()
            if mode == "study" and (path is None or not path.plan_confirmed):
                raise ValueError("plan_not_confirmed")
            binding.mode = mode
            binding.revision += 1
            binding.updated_at = _now()
            result = {"status": "mode_set", "mode": mode, "path_id": binding.active_path_id}
            self._save_command(session, scope, command_id, "set_mode", result)
            return result

    def record_explained(
        self,
        scope: LearningScope,
        objective_id: str,
        *,
        summary: str,
        command_id: str,
    ) -> dict[str, Any]:
        replayed = self._replay(scope, command_id)
        if replayed is not None:
            return replayed
        with session_scope(immediate=True) as session:
            replay = self._command(session, scope, command_id)
            if replay is not None:
                return replay
            binding = self._ensure_binding(session, scope)
            path = self._binding_path(session, scope, binding, for_update=True)
            if path is None:
                raise ValueError("path_not_found")
            objective = self._objective(session, path.path_id, objective_id)
            progress = self._progress(session, path.path_id, objective_id, create=True)
            progress.explained = True
            progress.explanation_summary = str(summary or "")[:4000]
            progress.explained_at = _now()
            progress.updated_at = _now()
            if not path.current_objective_id:
                path.current_objective_id = objective_id
                path.current_module_id = objective.module_id
            path.revision += 1
            path.updated_at = _now()
            result = {
                "status": "explained",
                "path_id": path.path_id,
                "path_revision": path.revision,
                "current": self._objective_payload(
                    objective, progress, session, path
                ),
                "mastery": False,
            }
            self._save_command(session, scope, command_id, "record_explained", result)
            return result

    def mark_understood(
        self,
        scope: LearningScope,
        *,
        command_id: str,
        base_revision: int | None = None,
    ) -> dict[str, Any]:
        replayed = self._replay(scope, command_id)
        if replayed is not None:
            return replayed
        with session_scope(immediate=True) as session:
            replay = self._command(session, scope, command_id)
            if replay is not None:
                return replay
            binding = self._ensure_binding(session, scope)
            path = self._binding_path(session, scope, binding, for_update=True)
            if path is None:
                raise ValueError("path_not_found")
            if base_revision is not None and path.revision != int(base_revision):
                raise ValueError("path_conflict")
            if not path.current_objective_id:
                result = {
                    "status": "teaching_complete",
                    "path_id": path.path_id,
                    "path_revision": path.revision,
                    "current": None,
                    "teaching_complete": True,
                    "mastery": False,
                }
                self._save_command(session, scope, command_id, "mark_understood", result)
                return result
            objective = self._objective(
                session, path.path_id, path.current_objective_id
            )
            if not self._objective_sources_valid(objective):
                raise ValueError("source_unavailable")
            progress = self._progress(
                session, path.path_id, objective.objective_id, create=True
            )
            if progress.understood:
                result = {
                    "status": "already_understood",
                    "path_id": path.path_id,
                    "path_revision": path.revision,
                    "current": self._objective_payload(
                        objective, progress, session, path
                    ),
                    "teaching_complete": False,
                    "mastery": False,
                }
                self._save_command(session, scope, command_id, "mark_understood", result)
                return result
            if path.kind == "textbook_navigation":
                progress.understood = True
                progress.understood_at = _now()
                progress.updated_at = _now()
                path.revision += 1
                path.updated_at = _now()
                result = {
                    "status": "understood",
                    "path_id": path.path_id,
                    "path_revision": path.revision,
                    "current": self._objective_payload(
                        objective, progress, session, path
                    ),
                    "requires_navigation": True,
                    "teaching_complete": False,
                    "mastery": False,
                }
                self._save_command(session, scope, command_id, "mark_understood", result)
                return result
            order = self._ordered_objectives(session, path.path_id)
            index = next(
                (i for i, row in enumerate(order) if row.objective_id == objective.objective_id),
                -1,
            )
            nxt = order[index + 1] if index >= 0 and index + 1 < len(order) else None
            if nxt is not None and not self._objective_sources_valid(nxt):
                raise ValueError("source_unavailable")
            progress.understood = True
            progress.understood_at = _now()
            progress.updated_at = _now()
            previous = self._objective_payload(objective, progress, session, path)
            if nxt is None:
                path.current_objective_id = ""
                path.current_module_id = ""
                path.teaching_complete = True
            else:
                path.current_objective_id = nxt.objective_id
                path.current_module_id = nxt.module_id
                path.teaching_complete = False
            path.revision += 1
            path.updated_at = _now()
            current_progress = None
            if nxt is not None:
                current_progress = self._progress(
                    session, path.path_id, nxt.objective_id, create=False
                )
            result = {
                "status": "advanced",
                "path_id": path.path_id,
                "path_revision": path.revision,
                "previous": previous,
                "current": (
                    self._objective_payload(nxt, current_progress, session, path)
                    if nxt is not None
                    else None
                ),
                "teaching_complete": nxt is None,
                "mastery": False,
            }
            self._save_command(session, scope, command_id, "mark_understood", result)
            return result

    def switch_path(
        self, scope: LearningScope, path_id: str, *, command_id: str
    ) -> dict[str, Any]:
        replayed = self._replay(scope, command_id)
        if replayed is not None:
            return replayed
        with session_scope(immediate=True) as session:
            replay = self._command(session, scope, command_id)
            if replay is not None:
                return replay
            path = self._owned_path(session, scope, path_id, for_update=True)
            binding = self._ensure_binding(session, scope)
            binding.active_path_id = path.path_id
            binding.mode = "study" if path.plan_confirmed else "outline"
            binding.revision += 1
            binding.updated_at = _now()
            result = {
                "status": "switched",
                "path_id": path.path_id,
                "mode": binding.mode,
                "path_revision": path.revision,
            }
            self._save_command(session, scope, command_id, "switch_path", result)
            return result

    def leave_path(self, scope: LearningScope, *, command_id: str) -> dict[str, Any]:
        replayed = self._replay(scope, command_id)
        if replayed is not None:
            return replayed
        with session_scope(immediate=True) as session:
            replay = self._command(session, scope, command_id)
            if replay is not None:
                return replay
            binding = self._ensure_binding(session, scope)
            binding.active_path_id = ""
            binding.mode = "outline"
            binding.revision += 1
            binding.updated_at = _now()
            result = {"status": "left"}
            self._save_command(session, scope, command_id, "leave_path", result)
            return result

    def revise_objective(
        self,
        scope: LearningScope,
        path_id: str,
        objective_id: str,
        name: str,
        *,
        base_revision: int,
        command_id: str,
    ) -> dict[str, Any]:
        replayed = self._replay(scope, command_id)
        if replayed is not None:
            return replayed
        with session_scope(immediate=True) as session:
            replay = self._command(session, scope, command_id)
            if replay is not None:
                return replay
            path = self._owned_path(session, scope, path_id, for_update=True)
            if path.revision != int(base_revision):
                raise ValueError("path_conflict")
            binding = self._ensure_binding(session, scope)
            if path.plan_confirmed and binding.mode != "outline":
                raise ValueError("mode_not_allowed")
            objective = self._objective(session, path.path_id, objective_id)
            progress = self._progress(session, path.path_id, objective_id, create=False)
            if progress is not None and (progress.explained or progress.understood):
                raise ValueError("objective_protected")
            cleaned = str(name or "").strip()
            if not cleaned:
                raise ValueError("objective_name_required")
            objective.name = cleaned
            path.revision += 1
            path.updated_at = _now()
            result = {
                "status": "revised",
                "path_id": path.path_id,
                "objective_id": objective_id,
                "path_revision": path.revision,
                "name": cleaned,
            }
            self._save_command(session, scope, command_id, "revise_objective", result)
            return result

    # -- reads --------------------------------------------------------
    def status(self, scope: LearningScope) -> dict[str, Any]:
        with session_scope() as session:
            binding = session.get(Q5BindingRow, (scope.student_id, scope.session_id))
            if binding is None or not binding.active_path_id:
                return _no_path()
            path = session.get(Q5PathRow, binding.active_path_id)
            if path is None or path.student_id != scope.student_id:
                return _no_path()
            modules, objectives, progress = self._path_payload(session, path)
            current = next(
                (row for row in objectives if row["objective_id"] == path.current_objective_id),
                None,
            )
            if current is not None and not self._objective_sources_valid_by_refs(
                current.get("source_refs") or []
            ):
                return {
                    "status": "source_unavailable",
                    "path_id": path.path_id,
                    "path_revision": path.revision,
                    "current": current,
                    "next": None,
                    "modules": modules,
                    "mode": binding.mode,
                    "teaching_complete": False,
                    "path_complete": False,
                    "reason": "当前目标的来源版本已失效",
                }
            current_index = next(
                (
                    index
                    for index, row in enumerate(objectives)
                    if row["objective_id"] == path.current_objective_id
                ),
                -1,
            )
            next_row = (
                objectives[current_index + 1]
                if current_index >= 0 and current_index + 1 < len(objectives)
                else None
            )
            return {
                "status": path.status,
                "path_id": path.path_id,
                "path": {
                    "path_id": path.path_id,
                    "name": path.name,
                    "goal": path.goal,
                    "kind": path.kind,
                    "status": path.status,
                    "revision": path.revision,
                    "plan_confirmed": path.plan_confirmed,
                },
                "path_revision": path.revision,
                "plan_confirmed": path.plan_confirmed,
                "mode": binding.mode,
                "current": current,
                "next": next_row,
                "modules": modules,
                "teaching_complete": bool(path.teaching_complete or current is None),
                "path_complete": False,
            }

    def list_paths(self, scope: LearningScope) -> list[dict[str, Any]]:
        with session_scope() as session:
            rows = session.scalars(
                select(Q5PathRow)
                .where(Q5PathRow.student_id == scope.student_id)
                .order_by(Q5PathRow.updated_at.desc())
            ).all()
            out = []
            for path in rows:
                modules, objectives, _progress = self._path_payload(session, path)
                current = next(
                    (
                        row
                        for row in objectives
                        if row["objective_id"] == path.current_objective_id
                    ),
                    None,
                )
                out.append(
                    {
                        "path_id": path.path_id,
                        "name": path.name,
                        "goal": path.goal,
                        "kind": path.kind,
                        "status": path.status,
                        "revision": path.revision,
                        "plan_confirmed": path.plan_confirmed,
                        "current": current,
                        "modules": len(modules),
                        "objectives": len(objectives),
                        "understood": sum(1 for row in objectives if row["understood"]),
                    }
                )
            return out

    def current_target(self, scope: LearningScope):
        status = self.status(scope)
        current = status.get("current")
        if not current:
            return None
        from agents.q3_navigation import LearningTarget

        first = (current.get("source_refs") or [{}])[0]
        target_id = (
            str(first.get("unit_id") or current["objective_id"])
            if status.get("path", {}).get("kind") == "textbook_navigation"
            else str(current["objective_id"])
        )
        return LearningTarget(
            target_id=target_id,
            name=str(current["name"]),
            chapter_id=first.get("chapter_id"),
            section_id=first.get("section_id"),
            source_scope={
                "path_id": status["path_id"],
                "objective_id": current["objective_id"],
                "source_refs": current.get("source_refs") or [],
            },
            reason="Q5 当前教学位置",
            version=str(first.get("version") or ""),
        )

    def tool_state(self, scope: LearningScope) -> dict[str, Any]:
        status = self.status(scope)
        current = status.get("current") or {}
        return {
            "q5_path_id": status.get("path_id") or "",
            "q5_objective_id": current.get("objective_id") or "",
            "q5_mode": status.get("mode") or "outline",
            "q5_path_revision": status.get("path_revision") or 0,
        }

    # -- internals ----------------------------------------------------
    def _persist_draft(
        self,
        scope: LearningScope,
        draft: PlanDraft,
        command_id: str,
        *,
        command_type: str,
    ) -> dict[str, Any]:
        self._validate_draft(draft)
        path_id = uuid4().hex
        objective_rows: list[Q5ObjectiveRow] = []
        module_rows: list[Q5ModuleRow] = []
        for module_index, (module_name, module_objective, objectives) in enumerate(
            draft.modules
        ):
            module_id = uuid4().hex
            module_rows.append(
                Q5ModuleRow(
                    module_id=module_id,
                    path_id=path_id,
                    position=module_index,
                    name=module_name,
                    objective=module_objective,
                )
            )
            for objective_index, item in enumerate(objectives):
                objective_rows.append(
                    Q5ObjectiveRow(
                        objective_id=uuid4().hex,
                        path_id=path_id,
                        module_id=module_id,
                        position=objective_index,
                        name=item.name,
                        knowledge_type=item.knowledge_type,
                        prerequisite_ids=list(item.prerequisite_ids),
                        source_refs=list(item.source_refs),
                        required_visual_tasks=list(item.required_visual_tasks),
                    )
                )
        first = objective_rows[0] if objective_rows else None
        with session_scope(immediate=True) as session:
            replay = self._command(session, scope, command_id)
            if replay is not None:
                return replay
            path = Q5PathRow(
                path_id=path_id,
                student_id=scope.student_id,
                course_id=scope.course_id,
                kind="mastery_goal",
                name=draft.name or draft.goal[:200],
                goal=draft.goal,
                status="draft",
                revision=1,
                plan_confirmed=False,
                teaching_complete=False,
                source_scope=dict(draft.source_scope),
                current_objective_id=first.objective_id if first else "",
                current_module_id=first.module_id if first else "",
            )
            session.add(path)
            session.flush()
            session.add_all(module_rows)
            session.flush()
            session.add_all(objective_rows)
            session.flush()
            for objective in objective_rows:
                session.add(
                    Q5ProgressRow(path_id=path_id, objective_id=objective.objective_id)
                )
            binding = self._ensure_binding(session, scope)
            binding.active_path_id = path_id
            binding.mode = "outline"
            binding.revision += 1
            binding.updated_at = _now()
            result = {
                "status": "draft",
                "path_id": path_id,
                "path_revision": 1,
                "plan_confirmed": False,
                "mode": "outline",
                "modules": len(module_rows),
                "objectives": len(objective_rows),
            }
            self._save_command(session, scope, command_id, command_type, result)
            return result

    def _validate_draft(self, draft: PlanDraft) -> None:
        if not isinstance(draft, PlanDraft) or not str(draft.goal or "").strip():
            raise ValueError("plan_goal_required")
        if not draft.modules:
            raise ValueError("plan_modules_required")
        seen: set[str] = set()
        for module_name, module_objective, objectives in draft.modules:
            if not str(module_name or "").strip():
                raise ValueError("module_name_required")
            if not str(module_objective or "").strip():
                raise ValueError("module_objective_required")
            if not objectives:
                raise ValueError("module_objectives_required")
            for item in objectives:
                if not isinstance(item, ObjectiveDraft) or not item.name.strip():
                    raise ValueError("objective_name_required")
                if item.knowledge_type not in KNOWLEDGE_TYPES:
                    raise ValueError("objective_type_invalid")
                if not item.source_refs:
                    raise ValueError("objective_source_required")
                if not all(
                    isinstance(ref, dict) and self._source_validator(ref)
                    for ref in item.source_refs
                ):
                    raise ValueError("objective_source_unavailable")
                key = item.name.strip().casefold()
                if key in seen:
                    raise ValueError("objective_duplicate")
                seen.add(key)

    def _replay(self, scope: LearningScope, command_id: str) -> dict[str, Any] | None:
        with session_scope() as session:
            return self._command(session, scope, command_id)

    def _command(
        self, session, scope: LearningScope, command_id: str
    ) -> dict[str, Any] | None:
        row = session.scalar(
            select(Q5CommandRow).where(
                Q5CommandRow.student_id == scope.student_id,
                Q5CommandRow.command_id == command_id,
            )
        )
        if row is None:
            return None
        result = dict(row.result or {})
        result["replayed"] = True
        return result

    def _save_command(
        self,
        session,
        scope: LearningScope,
        command_id: str,
        command_type: str,
        result: dict[str, Any],
    ) -> None:
        session.add(
            Q5CommandRow(
                student_id=scope.student_id,
                command_id=command_id,
                command_type=command_type,
                result=dict(result),
            )
        )

    def _ensure_binding(self, session, scope: LearningScope) -> Q5BindingRow:
        binding = session.get(Q5BindingRow, (scope.student_id, scope.session_id))
        if binding is None:
            binding = Q5BindingRow(
                student_id=scope.student_id,
                session_id=scope.session_id,
                active_path_id="",
                mode="outline",
            )
            session.add(binding)
            session.flush()
        return binding

    def _binding_path(
        self,
        session,
        scope: LearningScope,
        binding: Q5BindingRow,
        *,
        for_update: bool = False,
    ):
        if not binding.active_path_id:
            return None
        path = session.scalar(
            select(Q5PathRow)
            .where(Q5PathRow.path_id == binding.active_path_id)
            .with_for_update()
            if for_update
            else select(Q5PathRow).where(Q5PathRow.path_id == binding.active_path_id)
        )
        if path is None or path.student_id != scope.student_id:
            return None
        return path

    def _owned_path(
        self,
        session,
        scope: LearningScope,
        path_id: str,
        *,
        for_update: bool = False,
    ) -> Q5PathRow:
        path = session.scalar(
            select(Q5PathRow)
            .where(Q5PathRow.path_id == path_id)
            .with_for_update()
            if for_update
            else select(Q5PathRow).where(Q5PathRow.path_id == path_id)
        )
        if path is None:
            raise ValueError("path_not_found")
        if path.student_id != scope.student_id:
            raise PermissionError("path_forbidden")
        return path

    def _objective(self, session, path_id: str, objective_id: str) -> Q5ObjectiveRow:
        objective = session.get(Q5ObjectiveRow, objective_id)
        if objective is None or objective.path_id != path_id:
            raise ValueError("objective_not_found")
        return objective

    def _progress(
        self, session, path_id: str, objective_id: str, *, create: bool
    ) -> Q5ProgressRow | None:
        row = session.scalar(
            select(Q5ProgressRow).where(
                Q5ProgressRow.path_id == path_id,
                Q5ProgressRow.objective_id == objective_id,
            )
        )
        if row is None and create:
            row = Q5ProgressRow(path_id=path_id, objective_id=objective_id)
            session.add(row)
            session.flush()
        return row

    def _ordered_objectives(self, session, path_id: str) -> list[Q5ObjectiveRow]:
        modules = session.scalars(
            select(Q5ModuleRow)
            .where(Q5ModuleRow.path_id == path_id)
            .order_by(Q5ModuleRow.position)
        ).all()
        rows: list[Q5ObjectiveRow] = []
        for module in modules:
            rows.extend(
                session.scalars(
                    select(Q5ObjectiveRow)
                    .where(Q5ObjectiveRow.module_id == module.module_id)
                    .order_by(Q5ObjectiveRow.position)
                ).all()
            )
        return rows

    def _path_payload(self, session, path: Q5PathRow):
        modules = session.scalars(
            select(Q5ModuleRow)
            .where(Q5ModuleRow.path_id == path.path_id)
            .order_by(Q5ModuleRow.position)
        ).all()
        objectives = self._ordered_objectives(session, path.path_id)
        progress_rows = session.scalars(
            select(Q5ProgressRow).where(Q5ProgressRow.path_id == path.path_id)
        ).all()
        progress = {row.objective_id: row for row in progress_rows}
        module_by_id = {row.module_id: row for row in modules}
        objective_payloads = [
            self._objective_payload(row, progress.get(row.objective_id), session, path)
            for row in objectives
        ]
        by_module: dict[str, list[dict[str, Any]]] = {}
        for row in objective_payloads:
            by_module.setdefault(row["module_id"], []).append(row)
        module_payloads = [
            {
                "module_id": module.module_id,
                "name": module.name,
                "objective": module.objective,
                "position": module.position,
                "objectives": by_module.get(module.module_id, []),
            }
            for module in modules
        ]
        return module_payloads, objective_payloads, progress

    def _objective_payload(
        self,
        objective: Q5ObjectiveRow,
        progress: Q5ProgressRow | None,
        session,
        path: Q5PathRow,
    ) -> dict[str, Any]:
        module = session.get(Q5ModuleRow, objective.module_id)
        return {
            "objective_id": objective.objective_id,
            "name": objective.name,
            "knowledge_type": objective.knowledge_type,
            "module_id": objective.module_id,
            "module_name": module.name if module is not None else "",
            "position": objective.position,
            "source_refs": list(objective.source_refs or []),
            "required_visual_tasks": list(objective.required_visual_tasks or []),
            "explained": bool(progress and progress.explained),
            "understood": bool(progress and progress.understood),
            "explanation_summary": progress.explanation_summary if progress else "",
            "mastered": False,
            "current": objective.objective_id == path.current_objective_id,
        }

    def _objective_sources_valid(self, objective: Q5ObjectiveRow) -> bool:
        return self._objective_sources_valid_by_refs(objective.source_refs or [])

    def _objective_sources_valid_by_refs(self, refs: list[dict[str, Any]]) -> bool:
        return bool(refs) and all(
            isinstance(ref, dict) and self._source_validator(ref) for ref in refs
        )


def selection_source_ref(selection: dict[str, Any]) -> dict[str, Any]:
    """Turn a server-resolved Q2 selection into a durable source reference."""
    if not isinstance(selection, dict):
        raise ValueError("selection_required")
    document_id = str(
        selection.get("document_id")
        or selection.get("document")
        or selection.get("source")
        or ""
    ).strip()
    version = str(selection.get("version") or selection.get("document_version") or "").strip()
    if not document_id or not version:
        raise ValueError("selection_source_unavailable")
    chapter_id = selection.get("chapter_id")
    section_id = selection.get("section_id")
    page = selection.get("page")
    unit_id = str(selection.get("unit_id") or selection.get("id") or "").strip()
    if not unit_id:
        unit_id = "selection:%s:%s:%s:%s:%s" % (
            document_id, version, chapter_id, section_id, page
        )
    text = str(selection.get("text") or selection.get("quote") or "")[:2000]
    return {
        "document_id": document_id,
        "version": version,
        "unit_id": unit_id,
        "chapter_id": chapter_id,
        "section_id": section_id,
        "page": page,
        "title": str(selection.get("title") or selection.get("section_title") or "")[:200],
        "text": text,
        "quote": str(selection.get("quote") or text)[:500],
        "release_id": str(selection.get("release_id") or ""),
        "source_version": str(selection.get("source_version") or ""),
    }


def _selection_matches_refs(
    refs: list[dict[str, Any]], selection: dict[str, Any]
) -> bool:
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        if str(ref.get("document_id") or "") != selection["document_id"]:
            continue
        if str(ref.get("version") or "") != selection["version"]:
            continue
        if ref.get("unit_id") and selection.get("unit_id"):
            if str(ref["unit_id"]) == str(selection["unit_id"]):
                return True
            continue
        if ref.get("page") is not None and selection.get("page") is not None:
            if ref.get("page") == selection.get("page"):
                return True
        if ref.get("section_id") is not None and selection.get("section_id") is not None:
            if ref.get("section_id") == selection.get("section_id"):
                return True
    return False


class Q5Navigator:
    """Q3 navigator adapter: Q5 supplies the current target; Q2 supplies search."""

    def __init__(self, service: Q5LearningService, scope: LearningScope, *, search_fn=None):
        self.service = service
        self.scope = scope
        self._search_fn = search_fn

    def resolve(self, *, message, student_id, session_id, current_target, context):
        from agents.q3_navigation import NavigationDecision

        target = self.service.current_target(self.scope)
        if target is None:
            return NavigationDecision(
                "clarify", None, missing=("target",),
                reason="Q5 没有当前教学位置，请先确认学习计划",
            )
        return NavigationDecision("teach", target, reason="Q5 当前教学位置")

    def search(self, *, target, query, limit, preferred_types=()):
        if self._search_fn is None:
            return []
        return self._search_fn(
            target=target, query=query, limit=limit,
            preferred_types=preferred_types,
        )


def _default_source_valid(ref: dict[str, Any]) -> bool:
    if not isinstance(ref, dict):
        return False
    version = str(ref.get("version") or "").strip()
    if ref.get("source_kind") == "q2_navigation":
        return bool(str(ref.get("unit_id") or "").strip() and version)
    return bool(str(ref.get("document_id") or "").strip() and version)


def _no_path() -> dict[str, Any]:
    return {
        "status": "no_path",
        "path_id": None,
        "path_revision": 0,
        "current": None,
        "next": None,
        "modules": [],
        "mode": "outline",
        "teaching_complete": False,
        "path_complete": False,
    }


def _now():
    import datetime as dt

    return dt.datetime.utcnow()


__all__ = [
    "KNOWLEDGE_TYPES",
    "LearningScope",
    "ObjectiveDraft",
    "PlanDraft",
    "Q5LearningService",
    "Q5Navigator",
    "intake_gaps",
    "selection_source_ref",
]
