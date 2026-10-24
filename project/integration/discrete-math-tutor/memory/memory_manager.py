"""MemoryManager —— 唯一记忆入口（Conversation / Learning / Profile 三类记忆）。

【参考实现】LearningMAP 的 student_memory（retrieve / ingest / notes 的职责划分）。
【自主衔接】Agents 只调用本类，永远不碰 database/；
本类统一负责：三类记忆读写、误解状态机触发、快照/回滚、测试账户生命周期。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import hashlib
from memory.evidence_policy import source_quote

from database.account_manager import AccountManager
from database.repository import Repository
from models.learner_profile import LearnerProfile
from models.lesson_plan import LessonPlan
from models.misconception import Misconception, normalize_type
from models.student_state import StudentState

MAX_HISTORY = 20  # 控制 prompt 长度


class MemoryManager:
    def __init__(self, repository: Optional[Repository] = None) -> None:
        self.repo = repository or Repository()
        self.accounts = AccountManager(self.repo)
        self._snapshots: Dict[Tuple[str, str], StudentState] = {}
        self._recent_moves: Dict[str, List[str]] = {}

    # ---- 最近教学动作（从已提交事件恢复；旧缓存写接口保留兼容）------
    def get_recent_moves(self, student_id: str) -> List[str]:
        return self.repo.recent_teaching_moves(student_id)

    def push_recent_move(self, student_id: str, move: str) -> None:
        moves = self._recent_moves.setdefault(student_id, [])
        moves.append(move)
        if len(moves) > 5:
            del moves[:-5]

    # ---- 学生生命周期 ----------------------------------------------
    def ensure_student(self, student_id: str, account_type: str = "production") -> None:
        self.repo.ensure_student(student_id, account_type=account_type)

    def reset(self, student_id: str) -> bool:
        deleted = self.repo.delete_student(student_id)
        if deleted:
            self._recent_moves.pop(student_id, None)
            for key in list(self._snapshots):
                if key[0] == student_id:
                    self._snapshots.pop(key, None)
        return deleted

    def cleanup_expired(self) -> int:
        return self.accounts.cleanup_expired()

    def get_active_goal(self, student_id: str) -> Optional[str]:
        """当前活跃知识点：优先取 active_state，其次取最近一次教学计划。"""
        return self.repo.get_active_knowledge_point(
            student_id
        ) or self.repo.get_latest_knowledge_point(student_id)

    def set_active_goal(self, student_id: str, knowledge_point: str) -> None:
        self.repo.set_active_knowledge_point(student_id, knowledge_point)

    def list_knowledge_points(self, student_id: str) -> List[str]:
        return self.repo.list_knowledge_points(student_id)

    def list_learning_points(self, student_id: str) -> List[str]:
        return self.repo.list_learning_points(student_id)

    # ---- Conversation 记忆 -----------------------------------------
    def get_history(self, student_id: str, limit: int = MAX_HISTORY, *, session_id: str | None = None) -> List[Dict[str, str]]:
        return self.repo.get_conversation(student_id, limit, session_id=session_id)

    def append(
        self, student_id: str, role: str, content: str,
        figure_ids: list[str] | None = None,
        selection_ref: dict | None = None,
        session_id: str | None = None,
    ) -> int:
        with self.repo.unit_of_work():
            conversation_id = self.repo.append_conversation(student_id, role, content, figure_ids, selection_ref, session_id)
            if role == "user":
                self.repo.record_event(student_id, f"conversation:{conversation_id}",
                    (selection_ref or {}).get("section_title") or self.get_active_goal(student_id) or "",
                    "pdf_selection" if selection_ref else "interaction",
                    {"conversation_id": conversation_id, "content": content, "selection_ref": selection_ref})
            return conversation_id

    def append_exchange(self, student_id, message, reply, selection_ref=None, *, expected_epoch=None, expected_point=None, task_guard=None, session_id=None):
        """圈选等不更新状态的问答，也将两条对话和行为事件一起提交。"""
        with self.repo.unit_of_work():
            if task_guard is not None: task_guard()
            point = expected_point or (selection_ref or {}).get("section_title") or self.get_active_goal(student_id) or ""
            if expected_epoch is not None and self.repo.memory_epoch(student_id, point) != expected_epoch:
                return False
            self.append(student_id, "user", message, selection_ref=selection_ref, session_id=session_id)
            return self.append(student_id, "assistant", reply, selection_ref=selection_ref, session_id=session_id)

    # ---- Learning 记忆 ---------------------------------------------
    def get_state(self, student_id: str, knowledge_point: str) -> StudentState:
        state = self.repo.get_knowledge_state(student_id, knowledge_point)
        state.misconceptions = self.repo.list_misconceptions(student_id, knowledge_point)
        state.skill_states = self.repo.skill_summary(student_id, knowledge_point, limit=3)
        return state

    def save_state(
        self, student_id: str, knowledge_point: str, state: StudentState
    ) -> None:
        self.repo.save_knowledge_state(student_id, knowledge_point, state)

    def get_misconceptions(
        self, student_id: str, knowledge_point: str
    ) -> List[Misconception]:
        return self.repo.list_misconceptions(student_id, knowledge_point)

    def find_misconception(
        self, student_id: str, knowledge_point: str, mtype: str
    ) -> Optional[Misconception]:
        """按规范化 type 查找已有误解。"""
        target = normalize_type(mtype)
        if not target:
            return None
        for item in self.repo.list_misconceptions(student_id, knowledge_point):
            if normalize_type(item.type) == target:
                return item
        return None

    def add_hypothesis(
        self,
        student_id: str,
        knowledge_point: str,
        mtype: str,
        description: str,
        confidence: float,
        merge_into_id: Optional[int] = None,
    ) -> Misconception:
        """写入一条误解证据：优先并入指定/同名的已有误解，否则新建（去重）。"""
        target: Optional[Misconception] = None
        if merge_into_id is not None:
            target = next(
                (
                    m
                    for m in self.repo.list_misconceptions(student_id, knowledge_point)
                    if m.id == merge_into_id
                ),
                None,
            )
        if target is None:
            target = self.find_misconception(student_id, knowledge_point, mtype)
        if target is None:
            target = Misconception(
                knowledge_point=knowledge_point,
                type=mtype or "",
                description=description or "",
            )
            target.add_supporting_evidence(confidence)
        else:
            if description and not target.description:
                target.description = description
            target.add_supporting_evidence(confidence)
        saved = self.repo.save_misconception(student_id, target)
        self.repo.add_evidence(
            student_id,
            knowledge_point,
            "misconception",
            description,
            confidence,
            saved.id,
        )
        return saved

    def add_evidence(
        self,
        student_id: str,
        knowledge_point: str,
        evidence_type: str,
        content: str,
        confidence: float,
        misconception_type: Optional[str] = None,
        misconception_description: Optional[str] = None,
    ) -> Optional[Misconception]:
        """写入一条证据。若带误解信息，则走 add_hypothesis（含去重）。"""
        if misconception_type or misconception_description:
            return self.add_hypothesis(
                student_id,
                knowledge_point,
                misconception_type or "",
                misconception_description or "",
                confidence,
            )
        self.repo.add_evidence(
            student_id, knowledge_point, evidence_type, content, confidence, None
        )
        return None

    def resolve_misconceptions(
        self, student_id: str, knowledge_point: str, mtype: Optional[str] = None
    ) -> int:
        return self.repo.set_misconception_status(
            student_id, knowledge_point, "resolved", mtype
        )

    def list_evidence(self, student_id: str, knowledge_point: Optional[str] = None) -> List[Dict]:
        return self.repo.list_evidence(student_id, knowledge_point)

    def get_lesson_plan(
        self, student_id: str, knowledge_point: str
    ) -> Optional[LessonPlan]:
        return self.repo.get_lesson_plan(student_id, knowledge_point)

    def save_lesson_plan(
        self,
        student_id: str,
        knowledge_point: str,
        plan: LessonPlan,
        steps_mastery: Optional[Dict[str, float]] = None,
    ) -> None:
        self.repo.save_lesson_plan(student_id, knowledge_point, plan, steps_mastery or {})

    # ---- Profile 记忆 ----------------------------------------------
    def strategy_summary(self, student_id, point):
        from memory.strategy_reflection import summarize
        return summarize(self.repo.strategy_observations(student_id, point))

    def get_profile(self, student_id: str, *, point=None, difficulty="medium", hint_level=1) -> LearnerProfile:
        profile=self.repo.get_profile(student_id)
        if point is not None:
            # 只供规划使用，不覆盖持久画像；旧无来源 EMA 不继续作为决策权重。
            profile=profile.model_copy(deep=True)
            profile.teaching_effectiveness={item["instructional_move"]:item["weight"]
                for item in self.strategy_summary(student_id,point)
                if item["weight"] is not None and item["difficulty"]==difficulty and item["hint_level"]==hint_level}
        return profile

    def save_profile(self, profile: LearnerProfile) -> None:
        self.repo.save_profile(profile)

    def update_effectiveness(
        self, student_id: str, strategy: str, success: bool
    ) -> None:
        profile = self.repo.get_profile(student_id)
        profile.update_effectiveness(strategy, success)
        self.repo.save_profile(profile)

    # ---- 快照 / 回滚（Tutor Error 用）------------------------------
    def snapshot(self, student_id: str, knowledge_point: str) -> None:
        self._snapshots[(student_id, knowledge_point)] = self.get_state(
            student_id, knowledge_point
        ).model_copy(deep=True)

    def rollback(self, student_id: str, knowledge_point: str) -> bool:
        snap = self._snapshots.get((student_id, knowledge_point))
        if snap is None:
            return False
        self.save_state(student_id, knowledge_point, snap)
        return True

    def retrieve_context(self, student_id, *, title="", text="", question="",
                         selection_ref=None, question_id=None, version=None, budget=6000):
        from memory.retrieval import MemoryRetriever
        return MemoryRetriever(self).retrieve(student_id, title=title, text=text, question=question,
            selection_ref=selection_ref, question_id=question_id, version=version, budget=budget)

    def skill_summary(self, student_id, point):
        return self.repo.skill_summary(student_id,point)

    def memory_overview(self, student_id, point=None):
        return self.repo.memory_overview(student_id, point)

    def set_preferences(self, student_id, values):
        return self.repo.set_explicit_preferences(student_id, values)

    def forget_preference(self, student_id, key):
        return self.repo.forget_preference(student_id, key)

    def dispute_misconception(self, student_id, item_id, note):
        return self.repo.dispute_misconception(student_id, item_id, note)

    def forget_point(self, student_id, point):
        result=self.repo.forget_learning_point(student_id, point)
        self._snapshots.pop((student_id,point),None)
        self._recent_moves.pop(student_id,None)
        return result

    def read_version(self, student_id, point):
        with self.repo.unit_of_work():
            return self.get_version(student_id,point), self.repo.memory_epoch(student_id,point)

    def get_version(self, student_id: str, knowledge_point: str) -> str:
        return self.repo.memory_token(student_id, knowledge_point)

    def get_previous_event(self, student_id: str, knowledge_point: str):
        return self.repo.latest_learning_event(student_id, knowledge_point)

    def commit_learning_turn(self, *, student_id, point, event_id, expected_token,
                             message, reply, state, lesson_plan, decision, evidence, hypotheses,
                             strategy, success, instructional_move, figure_ids=None, selection_ref=None,
                             tutor_error=None, misconception_updates=None, teaching_context=None, expected_epoch=0, task_guard=None,
                             session_id=None):
        """借鉴 episode 来源链和版本化记忆；LLM 工作在此事务之前完成。"""
        with self.repo.unit_of_work():
            if task_guard is not None: task_guard()
            key = "turn:" + event_id
            old = self.repo.get_event(student_id, key)
            if old:
                return {"status": "duplicate", "event_id": old["id"]}
            if self.repo.memory_epoch(student_id, point) != expected_epoch:
                return {"status": "forgotten", "event_id": event_id}
            previous = self.repo.latest_learning_event(student_id, point)
            before = self.repo.memory_snapshot(student_id, point)
            conflict = self.repo.memory_token(student_id, point) != expected_token
            status = "conflict" if conflict else "rolled_back" if tutor_error else "committed"
            event = self.repo.record_event(student_id, key, point, "chat_turn",
                {"content": message, "independent": decision.independent, "eligible": decision.eligible,
                 "verification": decision.verification, "reason": decision.reason,
                 "instructional_move": instructional_move, "selection_ref": selection_ref,
                 "tutor_error": tutor_error, "teaching_context": teaching_context or {}}, status, event_id)
            user_id = self.repo.append_conversation(student_id, "user", message, session_id=session_id)
            assistant_id = self.repo.append_conversation(student_id, "assistant", reply, figure_ids, selection_ref, session_id)
            # 事件直接包含持久化的对话 ID，作为原始材料入口。
            self.repo.link_event_conversations(event["id"], [user_id, assistant_id])
            if conflict or tutor_error:
                if tutor_error:
                    self.repo.add_event_evidence(event_id, point, "tutor_error", str(tutor_error), .6,
                        "tutor_error", verification="ai_provisional", source_quote=message)
                return {"status": status, "event_id": event_id, "conversation_id": assistant_id}
            seen = set()
            for item in evidence:
                quote = source_quote(item, message)
                observation = item.evidence_type + ":" + hashlib.sha256((quote or item.content).encode()).hexdigest()
                if observation in seen:
                    continue
                seen.add(observation)
                self.repo.add_event_evidence(event_id, point, item.evidence_type, item.content, item.confidence,
                    observation, independent=decision.independent and bool(quote), source_quote=quote)
            from memory.misconception_lifecycle import apply_updates
            assessments=apply_updates(self,student_id,point,event_id,message,decision,hypotheses,misconception_updates or [])
            self.repo.set_event_assessments(student_id,event_id,assessments)
            state.misconceptions = self.get_misconceptions(student_id, point)
            active=[m for m in state.misconceptions if m.status in ("hypothesis","supported","confirmed")]
            state.misconception="；".join(m.description for m in active[:3]) or None
            self.repo.save_knowledge_state(student_id, point, state)
            if lesson_plan is not None:
                self.repo.save_lesson_plan(student_id, point, lesson_plan, state.steps_mastery)
            self.repo.set_active_knowledge_point(student_id, point)
            self.repo.record_strategy_observation(student_id, point, event_id, previous, decision,
                before["knowledge_states"][0]["mastery"] if before["knowledge_states"] else .5, state.mastery)
            after = self.repo.memory_snapshot(student_id, point)
            self.repo.add_revision(student_id, event_id, point, before, after)
            job_id = self.repo.enqueue_memory_job(student_id, event_id)
            return {"status": status, "event_id": event_id, "conversation_id": assistant_id, "misconception_updates": assessments, "memory_job_id": job_id}

    def record_graph_submission(self, student_id, point, attempt_id, payload, *, expected_epoch):
        """图提交复用学习事件/证据；不据单题自动更新掌握度或课程进度。"""
        import json
        from memory.evidence_policy import assess_graph_attempt
        with self.repo.unit_of_work():
            if self.repo.memory_epoch(student_id, point) != expected_epoch:
                raise ValueError('知识点记忆已变化')
            source_key = 'graph-submission:' + attempt_id
            old = self.repo.get_event(student_id, source_key)
            if old:
                return old['id']
            decision = assess_graph_attempt(payload['assisted'])
            event = self.repo.record_event(student_id, source_key, point, 'graph_submission', payload)
            for field, correct in payload['checks'].items():
                quote = json.dumps(payload['answers'][field], ensure_ascii=False)
                self.repo.add_event_evidence(event['id'], point,
                    'conceptual_understanding' if correct else 'misconception',
                    json.dumps({'field': field, 'correct': correct, 'student_answer': payload['answers'][field],
                                'expected': payload['expected'][field], 'graph': payload['graph'],
                                'scope': '四顶点无向简单图的结构化判定，不验证自由解释'}, ensure_ascii=False),
                    .9, 'graph:' + field, verification=decision.verification,
                    independent=decision.independent, source_quote=quote)
            self.repo.sync_memory_index(student_id)
            return event['id']

    def record_truth_table_submission(self, student_id, point, attempt_id, payload, *, expected_epoch):
        """只记录已核验各行真值，不据单题更新掌握度。"""
        import json
        from memory.evidence_policy import assess_graph_attempt
        with self.repo.unit_of_work():
            if self.repo.memory_epoch(student_id, point) != expected_epoch:
                raise ValueError('知识点记忆已变化')
            key = 'truth-table-submission:' + attempt_id
            old = self.repo.get_event(student_id, key)
            if old:
                return old['id']
            decision = assess_graph_attempt(payload['assisted'])
            event = self.repo.record_event(student_id, key, point, 'truth_table_submission', payload)
            for row_id, correct in payload['checks'].items():
                answer = payload['answers']['values'][row_id]
                self.repo.add_event_evidence(event['id'], point,
                    'conceptual_understanding' if correct else 'misconception',
                    json.dumps({'formula': payload['formula'], 'row_id': row_id,
                        'student_answer': answer, 'expected': payload['expected'][row_id], 'correct': correct,
                        'scope': '双变量公式单行真值，不验证文字解释或推断整体掌握'}, ensure_ascii=False),
                    .9, 'truth-table:'+row_id, verification=decision.verification,
                    independent=decision.independent, source_quote=json.dumps(answer))
            self.repo.sync_memory_index(student_id)
            return event['id']

    def record_relation_submission(self, student_id, point, attempt_id, payload, *, expected_epoch):
        """只记录固定论域上的结构化性质判断，不验证自由解释。"""
        import json
        from memory.evidence_policy import assess_graph_attempt
        with self.repo.unit_of_work():
            if self.repo.memory_epoch(student_id,point)!=expected_epoch:raise ValueError('知识点记忆已变化')
            key='relation-submission:'+attempt_id
            old=self.repo.get_event(student_id,key)
            if old:return old['id']
            decision=assess_graph_attempt(payload['assisted'])
            event=self.repo.record_event(student_id,key,point,'relation_submission',payload)
            for property,correct in payload['checks'].items():
                answer=payload['answers']['values'][property]
                self.repo.add_event_evidence(event['id'],point,'conceptual_understanding' if correct else 'misconception',
                    json.dumps({'property':property,'student_answer':answer,'expected':payload['expected'][property],
                        'spec':payload['spec'],'correct':correct,'scope':'三元素非空论域关系的单项性质，不验证文字解释'},ensure_ascii=False),
                    .9,'relation:'+property,verification=decision.verification,independent=decision.independent,source_quote=json.dumps(answer))
            self.repo.sync_memory_index(student_id)
            return event['id']

    def record_exercise_submission(self, student_id, point, submission_id, question_id, version, answers, output, assisted, *, expected_epoch=None):
        """由批改完成事务调用，复用外层事务，事件以提交 ID 幂等。"""
        import json
        with self.repo.unit_of_work():
            if self.repo.memory_source_excluded(student_id, "exercise", submission_id):
                return
            if expected_epoch is not None and self.repo.memory_epoch(student_id, point) != expected_epoch:
                self.repo.exclude_exercise_memory(student_id, point, submission_id)
                return
            key = "submission:" + submission_id
            if self.repo.get_event(student_id, key):
                return
            event = self.repo.record_event(student_id, key, point, "exercise_submission",
                {"submission_id": submission_id, "question_id": question_id, "version": version,
                 "answers": answers, "feedback": output, "assisted": assisted})
            for part in output.get("parts", []):
                pid = part["part_id"]
                verification = "rule_verified" if part.get("confirmed") is True and part.get("method") == "rule" else "ai_provisional"
                self.repo.add_event_evidence(event["id"], point, "exercise_submission",
                    json.dumps({"part": part, "answer": answers.get(pid)}, ensure_ascii=False),
                    .9 if verification == "rule_verified" else .45, "part:" + pid,
                    verification=verification, independent=not assisted,
                    source_quote=json.dumps(answers.get(pid), ensure_ascii=False))

            self.repo.record_exercise_skills(student_id,point,event["id"],question_id,version,answers,output,assisted)
