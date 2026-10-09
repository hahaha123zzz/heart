"""MemoryManager —— 唯一记忆入口（Conversation / Learning / Profile 三类记忆）。

【参考实现】LearningMAP 的 student_memory（retrieve / ingest / notes 的职责划分）。
【自主衔接】Agents 只调用本类，永远不碰 database/；
本类统一负责：三类记忆读写、误解状态机触发、快照/回滚、测试账户生命周期。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

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

    # ---- 最近教学动作（防重复推进，进程内记忆）----------------------
    def get_recent_moves(self, student_id: str) -> List[str]:
        return list(self._recent_moves.get(student_id, []))

    def push_recent_move(self, student_id: str, move: str) -> None:
        moves = self._recent_moves.setdefault(student_id, [])
        moves.append(move)
        if len(moves) > 5:
            del moves[:-5]

    # ---- 学生生命周期 ----------------------------------------------
    def ensure_student(self, student_id: str, account_type: str = "production") -> None:
        self.repo.ensure_student(student_id, account_type=account_type)

    def reset(self, student_id: str) -> bool:
        return self.repo.delete_student(student_id)

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
    def get_history(self, student_id: str, limit: int = MAX_HISTORY) -> List[Dict[str, str]]:
        return self.repo.get_conversation(student_id, limit)

    def append(
        self, student_id: str, role: str, content: str,
        figure_ids: list[str] | None = None,
        selection_ref: dict | None = None,
    ) -> None:
        self.repo.append_conversation(student_id, role, content, figure_ids, selection_ref)

    # ---- Learning 记忆 ---------------------------------------------
    def get_state(self, student_id: str, knowledge_point: str) -> StudentState:
        state = self.repo.get_knowledge_state(student_id, knowledge_point)
        state.misconceptions = self.repo.list_misconceptions(student_id, knowledge_point)
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
    def get_profile(self, student_id: str) -> LearnerProfile:
        return self.repo.get_profile(student_id)

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
        )

    def rollback(self, student_id: str, knowledge_point: str) -> bool:
        snap = self._snapshots.get((student_id, knowledge_point))
        if snap is None:
            return False
        self.save_state(student_id, knowledge_point, snap)
        return True
