"""Q5 first-batch runtime wiring around Q2 navigation and Q3 tools.

The Q5 branch deliberately kept its domain service independent.  This module is
the integration boundary: it turns the authoritative Q2 outline into a valid
plan draft, exposes the current Q5 target to the Q3 loop, and renders a small
plan/status projection for the existing clarification card.
"""
from __future__ import annotations

import os
import re
from typing import Any

from agents.q5_learning import LearningScope, ObjectiveDraft, PlanDraft, Q5LearningService
from agents.q5_tools import q5_tool_instances
from agents.q5_turn_adapter import Q5TurnAdapter


def q5_enabled() -> bool:
    return os.getenv("Q5_LEARNING_ENABLED", "0").strip() == "1"


def _course_id() -> str:
    return os.getenv("TUTOR_COURSE", "").strip()


def _scope(student_id: str, session_id: str) -> LearningScope:
    return LearningScope(student_id=student_id, session_id=session_id,
                        course_id=_course_id())


class Q5Runtime:
    def __init__(self, student_id: str, session_id: str) -> None:
        self.scope = _scope(student_id, session_id)
        self.service = Q5LearningService()
        self.adapter = Q5TurnAdapter(self.service, self.scope)
        from agents.session_study_service import SessionStudyService
        self.sessions = SessionStudyService(self.scope)
        self.session_snapshot = None
        self.session_execution = None

    # -- plan lifecycle -------------------------------------------------
    def status(self) -> dict[str, Any]:
        return dict(self.service.status(self.scope), session_plan=self.sessions.current())

    def has_path(self) -> bool:
        return bool(self.status().get("path_id"))

    def is_plan_request(self, message: str) -> bool:
        text = "".join(str(message or "").split())
        return bool(re.search(r"(?:制定|生成|做一份|设计|规划|安排).{0,8}(?:学习|复习)?计划|"
                              r"(?:今天|这次|本次).{0,12}(?:怎么安排|先学什么)|"
                              r"(?:帮我|请|给我)?安排.{0,16}(?:分钟|小时|学习|复习)|"
                              r"(?:今天|这次|本次).{0,20}(?:分钟|小时).{0,20}(?:想学|学习|复习)", text))

    def propose_session(self, message, llm, memory, *, previous=None, guard=lambda: None):
        from agents.session_study_planner import extract_request, collect_materials, generate_session
        from models.interaction_preferences import style_instructions
        profile_values = memory.get_profile(self.scope.student_id).preferences
        profile = {'teaching_preference': style_instructions(profile_values)} if profile_values else {}
        status = self.service.status(self.scope)
        guard()
        request = extract_request(llm, message, profile=profile, path=status.get('path',{}),
                                  previous=(previous or {}).get('request'))
        guard()
        if not request.scope and not status.get('path_id'):
            if previous and previous.get('intake_asked'):
                raise ValueError('仍缺少学习主题，请明确主题后重新安排；不会反复补问')
            return {'intake_asked':True, 'request':request.model_dump()}
        if any(re.search(r'全书|整本|全部章节|全教材',topic) for topic in request.scope):
            from knowledge.course import chapter_summary
            return {'intake_asked':True,'request':request.model_dump(),
                'coverage':{'status':'outline_only','chapters':[{'id':chapter['id'],'title':chapter['title']} for chapter in chapter_summary()]}}
        materials, calls = collect_materials(request, llm=llm, status=status, guard=guard)
        if not materials:
            raise ValueError('本次范围没有可核验教材资料，请明确教材主题或章节')
        value = generate_session(llm, request, scope=self.scope, status=status,
            current=self.sessions.current(), previous=previous, materials=materials, profile=profile,
            validator=self.sessions.validate, guard=guard)
        value['source_binding']['retrieval_calls'] = calls
        if re.search(r'(?:以后|今后|每次|长期).{0,10}先讲(?:解)?.{0,4}(?:后|再)练',message):
            from database.database import session_scope
            with session_scope(immediate=True):
                guard()
                memory.set_preferences(self.scope.student_id,{'teaching_sequence':1.0})
            value['source_binding']['long_preferences_updated']=['teaching_sequence']
        return value

    def session_result(self, proposal, task, *, adjust_prompt=False):
        if proposal.get('intake_asked'):
            from agents.ask_user_contract import build_ask_user_payload
            payload, error = build_ask_user_payload(questions=[{'id':'scope','prompt':'这次想学习哪个教材主题或章节？'}])
            if error:raise ValueError(error)
            inventory=proposal.get('coverage',{}).get('chapters',[])
            intro=('教材共'+str(len(inventory))+'章：'+'、'.join(str(c['id'])+' '+c['title'] for c in inventory)+
                '。这只是目录覆盖，尚未完成全书原文规划。请指定本次优先主题或章节，不会默认缩为第一章。') if inventory else '这次想学习哪个教材主题或章节？已提供的时长和偏好会保留。'
            return {'reply':intro,
                'answer_status':'awaiting_clarification','loop_paused':True,
                'q5_session_plan':proposal,'ask_user':payload.to_dict(),
                'clarification':{'mode':'q5_session_intake','ask_user':payload.to_dict(),'options':[]},
                'result_type':'session_plan','step_advanced':False}
        lines=['### 本次学习安排', '目标：'+proposal['request']['goal'],
            '预计总用时：'+str(sum(item['estimated_minutes'] for item in proposal['items']))+' 分钟（估算）']
        for text in proposal['request'].get('assumptions',[]): lines.append('假设：'+text)
        for text in proposal.get('omitted',[]): lines.append('未纳入：'+text)
        if proposal.get('source_binding',{}).get('long_preferences_updated'):
            lines.append('已按你的明确要求长期保存“先讲后练”；可在风格设置调整或学习记忆管理中撤销。')
        lines.append('教材资料为有界选取，本安排不代表整章或全书覆盖；完成活动不等于掌握。')
        lines.append('请说明要调整的范围、时间或教法。' if adjust_prompt else '确认后按本次安排开始，不改变长期路径。')
        return {'reply':'\n'.join(lines),'answer_status':'awaiting_clarification','loop_paused':True,
            'q5_session_plan':proposal,'result_type':'session_plan','step_advanced':False,
            'clarification':{'mode':'q5_session_adjust' if adjust_prompt else 'q5_session_plan',
                'options':[{'id':'q5sp:confirm','label':'确认本次安排并开始'}, {'id':'q5sp:adjust','label':'调整本次安排'}]}}

    def prepare_session(self, message, preferences=None):
        """活动推进只在本轮内预演，成功发布后再提交，不提前移动数据库位置。"""
        import copy
        current = self.sessions.current()
        if not current or current['status'] not in ('active','paused'):
            return None
        self.sessions.guard(current)
        self.session_snapshot = current
        self.session_execution = copy.deepcopy(current)
        if current['request'].get('value_sources',{}).get('teaching_preference')=='confirmed_profile' and preferences is not None:
            from models.interaction_preferences import style_instructions
            self.session_execution['request']['teaching_preference']=style_instructions(preferences) if preferences else ''
        if current['status'] == 'paused':
            return current
        if re.fullmatch(r'(?:我懂了[，,]?|明白了[，,]?|请)?(?:继续|下一部分|下一步|接下来|继续下一部分)[。！!？?\s]*', message.strip()):
            self.session_execution = self.sessions.transition(self.session_execution)
        return self.session_execution

    def session_guard(self):
        if self.session_snapshot:
            self.sessions.guard(self.session_snapshot)

    @staticmethod
    def is_confirm(message: str) -> bool:
        text = "".join(str(message or "").split())
        return bool(re.search(r"(?:确认|同意|认可|开始).{0,6}(?:计划|学习|安排)|确认开始", text)
                    or re.fullmatch(r'(?:确认|同意|就这样|开始吧)[。！!]*',text))

    @staticmethod
    def is_adjust(message: str) -> bool:
        return bool(re.search(r"调整|修改|改成|改为|改名|换个目标", str(message or "")))

    @staticmethod
    def is_understood(message: str) -> bool:
        text = "".join(str(message or "").split())
        if re.search(r"没听懂|不明白|不懂|换.*说法", text):
            return False
        return bool(re.search(r"(?:我懂了|明白了|懂了|学会了|清楚了|可以继续|继续下一部分)", text))

    def propose_chapter_plan(self, message: str, command_id: str,
                             chapter_id: int = 1) -> dict[str, Any]:
        from knowledge.course_navigation import outline
        from knowledge.course_release import binding as release_binding
        from knowledge.pdf_reader import document_for_chapter

        units = [unit for unit in outline()
                 if int(unit.get("chapter_id") or 0) == int(chapter_id)]
        if not units:
            raise ValueError("q5_source_unavailable")
        record = document_for_chapter(chapter_id) or {}
        release = release_binding()
        grouped: dict[int, list[dict[str, Any]]] = {}
        for unit in units:
            grouped.setdefault(int(unit.get("section_id") or 0), []).append(unit)
        modules = []
        for section_id in sorted(grouped):
            section_units = grouped[section_id]
            first = section_units[0]
            source_ref = {
                "source_kind": "q2_navigation",
                "unit_id": str(first["id"]),
                "version": str(first["version"]),
                "document_id": str(record.get("document_id") or ""),
                "chapter_id": first.get("chapter_id"),
                "section_id": first.get("section_id"),
                "page": first.get("page"),
                "title": str(first.get("title") or ""),
                "release_id": str(release.get("release_id") or ""),
                "source_version": str(first.get("source_version") or ""),
                "source_title": str(first.get("source_title") or ""),
                "target_schema": "q2.teaching_targets.v1",
                "source_block_ids": [str(first["id"])],
                "source_valid": bool(first.get("source_valid", True)),
            }
            objective = ObjectiveDraft(
                name=str(first.get("title") or first["id"]),
                knowledge_type="concept",
                source_refs=[source_ref],
            )
            modules.append((
                str(first.get("section_title") or f"第{chapter_id}章"),
                f"理解并能解释：{first.get('title') or first['id']}",
                [objective],
            ))
        draft = PlanDraft(
            goal=f"掌握实验心理学第{chapter_id}章",
            name=f"实验心理学第{chapter_id}章学习计划",
            modules=modules,
        )
        proposal = self.service.create_plan(self.scope, draft,
                                            command_id=f"{command_id}:plan")
        proposal.update(self.status())
        return proposal

    def plan_result(self, proposal: dict[str, Any], task: dict[str, Any],
                    *, adjust_prompt: bool = False) -> dict[str, Any]:
        text = self.format_plan(proposal)
        if adjust_prompt:
            text = "请说明要调整的内容（例如：把第一个目标改名为……）。\n\n" + text
        result = {
            "reply": text,
            "answer_status": "awaiting_clarification",
            "loop_paused": True,
            "clarification": {
                "mode": "q5_plan_adjust" if adjust_prompt else "q5_plan",
                "q5_plan": proposal,
                "options": [
                    {"id": "q5:confirm", "label": "确认计划并开始"},
                    {"id": "q5:adjust", "label": "调整计划"},
                ],
            },
            "q5_plan": proposal,
            "q5_status": proposal,
            "step_advanced": False,
            "task_id": task.get("id"),
            "task_revision": task.get("revision"),
        }
        return result

    def format_plan(self, proposal: dict[str, Any]) -> str:
        lines = ["### 学习计划草稿", f"目标：{proposal.get('path', {}).get('goal') or proposal.get('goal') or ''}"]
        modules = proposal.get("modules") or []
        for index, module in enumerate(modules, 1):
            lines.append(f"{index}. **{module.get('name') or '模块'}**")
            for objective in module.get("objectives") or []:
                refs = objective.get("source_refs") or [{}]
                source = refs[0].get("title") or refs[0].get("unit_id") or "教材"
                marker = " ← 当前" if objective.get("current") else ""
                lines.append(f"   - {objective.get('name')}{marker}（来源：{source}）")
        lines.append("\n确认后进入学习；也可以先调整。")
        return "\n".join(lines)

    def confirm(self, proposal: dict[str, Any], command_id: str) -> dict[str, Any]:
        path_id = str(proposal.get("path_id") or proposal.get("path", {}).get("path_id") or "")
        revision = int(proposal.get("path_revision") or proposal.get("path", {}).get("revision") or 1)
        self.adapter.confirm_and_start(path_id, revision, command_id)
        return self.status()

    def adjust_first(self, proposal: dict[str, Any], message: str,
                     command_id: str) -> dict[str, Any]:
        path_id = str(proposal.get("path_id") or proposal.get("path", {}).get("path_id") or "")
        current = proposal.get("current") or {}
        objective_id = str(current.get("objective_id") or "")
        match = re.search(r"(?:改成|改为|改名(?:为|成)?|调整成|调整为)[：: ]*[“\"]([^”\"]+)[”\"]|(?:改成|改为|改名(?:为|成)?|调整成|调整为)[：: ]*(.+)$", message)
        new_name = ""
        if match:
            new_name = (match.group(1) or match.group(2) or "").strip()
        if not path_id or not objective_id or not new_name:
            raise ValueError("q5_adjustment_unavailable")
        revision = int(proposal.get("path_revision") or proposal.get("path", {}).get("revision") or 1)
        self.service.revise_objective(
            self.scope, path_id, objective_id, new_name,
            base_revision=revision, command_id=f"{command_id}:revise",
        )
        updated = self.status()
        updated.update(self.status())
        return updated

    def advance_understood(self, command_id: str) -> dict[str, Any]:
        status = self.status()
        if status.get("path", {}).get("kind") == "textbook_navigation":
            return status
        if not status.get("current"):
            return status
        try:
            self.service.mark_understood(
                self.scope, command_id=f"{command_id}:understood",
                base_revision=int(status.get("path_revision") or 0) or None,
            )
        except ValueError as exc:
            if str(exc) != "source_unavailable":
                raise
        return self.status()

    def record_explained(self, summary: str, command_id: str, guard=lambda: None) -> None:
        if self.session_execution:
            self.sessions.guard(self.session_snapshot)
            updated = self.sessions.explained(self.session_execution, command_id=command_id+':session-explained',guard=guard)
            self.session_snapshot = updated
            self.session_execution = updated
            return
        status = self.status()
        current = status.get("current") or {}
        if not current.get("objective_id"):
            return
        try:
            self.service.record_explained(
                self.scope, str(current["objective_id"]), summary=summary[:500],
                command_id=f"{command_id}:explained",
            )
        except (ValueError, RuntimeError):
            return

    def status_line(self) -> str:
        if self.session_execution:
            plan = self.session_execution
            item = next((i for i in plan['items'] if i['item_id']==plan['current_item_id']),None)
            return '本次安排：'+plan['request']['goal']+' · 当前活动：'+(item['title'] if item else '已结束')
        status = self.status()
        if not status.get("path_id"):
            return ""
        current = status.get("current") or {}
        if not current:
            return f"学习路径：{status.get('path', {}).get('name', '')}（已完成）"
        return (f"学习路径：{status.get('path', {}).get('name', '')} · "
                f"当前目标：{current.get('name', '')}")

    def loop_binding(self) -> dict[str, Any]:
        if self.session_execution:
            return {'target':self.sessions.target(self.session_execution),'session_study':True,
                    'session_plan':self.session_execution,
                    'tool_instances':tuple(t for t in q5_tool_instances(self.service,self.scope)
                        if t.definition.name in ('mastery_status','mastery_paths')),
                    'tool_state':{'session_study_plan':self.session_execution},'scopes':('learning:read',)}
        binding = self.adapter.loop_binding()
        binding["tool_instances"] = q5_tool_instances(self.service, self.scope)
        binding["scopes"] = (
            "learning:read", "learning:plan:write", "learning:explain:write",
            "learning:position:write", "learning:mode:write", "learning:path:write",
        )
        return binding

    def search(self, *, target: Any, query: str, limit: int,
               preferred_types: tuple[str, ...] = ()) -> list[Any]:
        from agents.q3_navigation import source_from_chunk

        # A mastery goal's target_id is the Q5 objective id, not a Q2 unit id.
        # Only a textbook-navigation path may read a Q2 target directly.
        if (self.status().get("path", {}).get("kind") == "textbook_navigation"):
            from knowledge.course_navigation import read_target
            exact = read_target({"id": target.target_id, "version": target.version})
            if exact:
                return [source_from_chunk(chunk, index)
                        for index, chunk in enumerate(exact[:limit])]
        from knowledge.local_rag.course_retrieval import retrieve
        candidates = retrieve(f"{target.name} {query}".strip(),
                              limit=max(12, limit * 3),
                              preferred_types=preferred_types)
        scoped = [chunk for chunk in candidates
                  if target.chapter_id is not None
                  and getattr(chunk, "chapter_id", None) == target.chapter_id]
        return [source_from_chunk(chunk, index)
                for index, chunk in enumerate((scoped or candidates)[:limit])]


__all__ = ["Q5Runtime", "q5_enabled"]
