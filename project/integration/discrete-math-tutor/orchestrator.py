"""Orchestrator —— 系统的"胶水层"（本项目最核心的自主实现）。

V0.2 数据流（全部经 MemoryManager 落 MySQL）：
    load(三类记忆) -> Lesson Planner -> Evidence Extractor -> State Analyzer
    -> Teaching Policy(State+Profile+Plan) -> Teaching Planner -> Question Designer
    -> Response Generator -> Quality Checker -> State Updater
    -> 误解读写/教学错误回滚/步骤推进/教学效果更新 -> save(MySQL)

【自主衔接】本文件不实现 AI 能力，只负责连接与闭环控制。
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from agents.conversation_router import ConversationRouter
from agents.evidence_extractor import EvidenceExtractor
from agents.lesson_planner import LessonPlanner
from agents.learning_feedback import consecutive_stuck, is_self_report_understood, is_stuck
from agents.misconception_resolver import MisconceptionResolver
from agents.quality_checker import QualityChecker
from agents.question_designer import QuestionDesigner
from agents.response_generator import ResponseGenerator
from agents.state_analyzer import StateAnalyzer
from agents.state_updater import StateUpdater
from agents.strategy_router import StrategyRouter
from agents.teaching_planner import TeachingPlanner
from agents.tutor_error_detector import TutorErrorDetector
from database.database import init_db
from llm.client import LLMClient
from knowledge.figures import FIGURE_NUMBER, format_figure_context, retrieve_figures
from knowledge.textbook import format_excerpts, load_textbook, retrieve
from memory.memory_manager import MemoryManager

MAX_REGEN = 1
DEFAULT_GOAL = "图的基本概念"


class TutorOrchestrator:
    def __init__(
        self,
        llm: Optional[LLMClient] = None,
        memory: Optional[MemoryManager] = None,
    ) -> None:
        self.llm = llm or LLMClient()
        self.memory = memory or MemoryManager()
        init_db()  # 幂等建表，保证任何入口都能直接用
        self.cleared_test_accounts = self.memory.accounts.cleanup_after_code_update()
        self.conversation_router = ConversationRouter(self.llm)
        self.lesson_planner = LessonPlanner(self.llm)
        self.evidence_extractor = EvidenceExtractor(self.llm)
        self.misconception_resolver = MisconceptionResolver(self.llm)
        self.state_analyzer = StateAnalyzer()
        self.teaching_planner = TeachingPlanner(self.llm)
        self.strategy_router = StrategyRouter(self.llm)
        self.question_designer = QuestionDesigner(self.llm)
        self.response_generator = ResponseGenerator(self.llm)
        self.quality_checker = QualityChecker(self.llm)
        self.state_updater = StateUpdater(self.llm)
        self.tutor_error_detector = TutorErrorDetector()
        self.textbook_chunks = load_textbook()

    def handle_turn(
        self,
        student_id: str,
        message: str,
        learning_goal: Optional[str] = None,
        account_type: str = "production",
        progress=None,
    ) -> Dict[str, Any]:
        def report(stage, label, detail=""):
            if progress is not None:
                progress(stage, label, detail)

        report("routing", "理解问题", "识别本轮问题与学习目标")
        if account_type == "test":
            self.memory.accounts.create_test_account(student_id, ttl_hours=24)
        elif account_type == "production":
            self.memory.ensure_student(student_id, account_type="production")
        else:
            raise ValueError("account_type 只能是 test 或 production")

        # 0) Conversation Router：判断学生这一轮在做什么 / 在聊什么
        history = self.memory.get_history(student_id)
        active_point = (
            self.memory.get_active_goal(student_id) or learning_goal or DEFAULT_GOAL
        )
        routing = self.conversation_router.route(
            message, active_point, history, self.memory.list_knowledge_points(student_id)
        )

        # 0.1) 非学习消息：不进教学流程（简短共情 + 轻推回学习，不强行拉回）
        if routing.intent == "off_task":
            report("generating", "生成回答", "准备回复")
            reply = self.response_generator.social_reply(message, active_point, history)
            self.memory.append(student_id, "user", message)
            self.memory.append(student_id, "assistant", reply)
            return {
                "reply": reply,
                "routing": routing.model_dump(),
                "knowledge_point": active_point,
                "student_state": self.memory.get_state(student_id, active_point).model_dump(),
            }

        # 0.2) 换话题 / 新目标：切换知识点（旧计划保留在库中，可恢复）；信息不足则先澄清
        point = active_point
        if routing.intent in ("switch_topic", "new_goal", "clarify_task"):
            topic = (routing.topic or "").strip()
            if (
                routing.intent == "clarify_task"
                or not topic
                or routing.confidence < 0.5
            ):
                reply = (
                    "你是想换一个新的话题，还是先继续当前的知识点？"
                    "想换的话，直接说你想学什么就行。"
                )
                self.memory.append(student_id, "user", message)
                self.memory.append(student_id, "assistant", reply)
                return {
                    "reply": reply,
                    "routing": routing.model_dump(),
                    "knowledge_point": active_point,
                    "student_state": self.memory.get_state(
                        student_id, active_point
                    ).model_dump(),
                }
            point = topic
        self.memory.set_active_goal(student_id, point)
        goal = point
        stuck_count = consecutive_stuck(history, message)
        query = point if is_stuck(message) or is_self_report_understood(message) else point + " " + message
        resource_query = bool(re.search(r"图\s*\d+\s*[.．]\s*\d+|表格|真值表|函数表|公式|表达式|配图|插图|图片", message))
        report("retrieving", "检索教材", "查找相关正文、公式、表格和插图")
        sources = retrieve(message if resource_query else query, self.textbook_chunks, limit=2)
        if is_stuck(message) and sources:
            chapter = sources[0].source
            basics = [
                chunk for chunk in self.textbook_chunks
                if chunk.source == chapter and "基本概念" in chunk.section
            ]
            if basics:
                sources = basics[:2]
        figures = retrieve_figures(message, sources)
        direct_figure_question = bool(figures and FIGURE_NUMBER.search(message))
        direct_resource_question = direct_figure_question or (resource_query and any(item.kind != "text" for item in sources))
        if direct_figure_question:
            matching = [
                chunk for chunk in self.textbook_chunks
                if any(
                    chunk.source.removesuffix(".txt") == figure.source.removesuffix(".doc")
                    and figure.label in chunk.text
                    for figure in figures
                )
            ]
            if matching:
                sources = matching[:2]
        excerpts = format_excerpts(sources)
        figure_context = format_figure_context(figures)

        report("resources", "读取教材资源", f"已检索 {len(sources)} 个片段，关联 {len(figures)} 张图像")

        # 快照：用于 Tutor Error 回滚
        self.memory.snapshot(student_id, point)

        state = self.memory.get_state(student_id, point)
        profile = self.memory.get_profile(student_id)
        start_mastery = state.mastery

        report("planning", "组织讲解", "结合教材与学习记录确定讲解方式")

        # 0) 知识点课程计划（先有目标和计划，再开始对话）
        lesson_plan = self.memory.get_lesson_plan(student_id, point)
        if lesson_plan is None or lesson_plan.goal != point:
            lesson_plan = self.lesson_planner.create(point, state, excerpts)
            state.steps_mastery = {}
        if lesson_plan.status == "in_progress":
            weak = lesson_plan.first_unmastered(state.steps_mastery)
            if weak is None:
                lesson_plan.status = "completed"
            else:
                lesson_plan.current_step = weak.step_id
        current_step = lesson_plan.current()

        # 1) 证据提取 + 状态整合（合并为一次 LLM 调用）
        analysis = self.evidence_extractor.analyze(message, state, history)
        for item in analysis.evidence:
            self.memory.add_evidence(
                student_id, point, item.evidence_type, item.content, item.confidence
            )
        self._store_hypotheses(student_id, point, analysis.hypotheses)
        state = self.state_analyzer.build(state, analysis)
        # 刷新误解列表：让 Strategy Router 能看到本轮刚发现的误解
        state.misconceptions = self.memory.get_misconceptions(student_id, point)

        # 2) 教学计划（State + Profile + Plan 三方决策）
        curriculum_done = lesson_plan.status == "completed"
        plan = self.teaching_planner.plan(
            state, goal, current_step, curriculum_done, profile
        )

        # 2.2) Strategy Router：按学生 move + 状态 + 画像选本轮教学动作
        recent_moves = self.memory.get_recent_moves(student_id)
        move = self.strategy_router.select(
            routing.student_move,
            routing.move_status,
            state,
            current_step,
            profile,
            recent_moves,
            message,
        )

        # 2.5) 诊断性问题设计
        question_spec = None if direct_resource_question else self.question_designer.design(
            state, plan, current_step, excerpts
        )

        lesson_text = self._lesson_text(lesson_plan, current_step, curriculum_done)
        if direct_resource_question:
            labels = "、".join(figure.label for figure in figures)
            labels = labels or "表格"
            lesson_text = f"本轮直接回答学生对教材{labels}的具体问题，不推进原课程步骤，不出诊断题。"
            plan.goal = f"准确解释教材{labels}及其图中标记"
            plan.strategy = "worked_example"
            plan.action = "explain"
            plan.rationale = "学生明确询问教材图片，先解答该图"

        # 3) 生成 + 4) 质检（失败带 feedback 重新生成）
        previous_reply = next(
            (
                m.get("content", "")
                for m in reversed(history)
                if m.get("role") == "assistant"
            ),
            "",
        )
        check_context = {
            "previous_reply": previous_reply,
            "topic_switched": point != active_point,
            "old_topic": active_point,
            "current_topic": point,
            "recent_moves": (recent_moves + [move.instructional_move])[-3:],
            "stuck_count": stuck_count,
        }
        if stuck_count:
            question_spec = None
            move.instructional_move = "worked_example" if stuck_count == 1 else "direct_explanation"
            move.action = "give_example" if stuck_count == 1 else "explain"
            move.difficulty = "easy"
            move.hint_level = min(3, stuck_count)
            move.rationale = "学生卡住，先示范或退回前置概念"
        elif is_self_report_understood(message):
            move.instructional_move = "retrieval_practice"
            move.action = "ask_question"
            move.difficulty = "easy"
            move.rationale = "自述理解不等于掌握，先做小检查"
        if direct_resource_question:
            move.instructional_move = "direct_explanation"
            move.action = "explain"
            move.rationale = "优先回答学生明确指定的教材图片"
        self.memory.push_recent_move(student_id, move.instructional_move)
        feedback: Optional[str] = None
        response = ""
        quality = None
        attempts = 0
        for _ in range(MAX_REGEN + 1):
            attempts += 1
            report(f"generating-{attempts}", "生成回答" if attempts == 1 else "修订回答", "根据教材资源组织回答")
            response = self.response_generator.generate(
                state,
                plan,
                message,
                history,
                question_spec,
                lesson_text,
                feedback,
                instructional_move=move.instructional_move,
                textbook_excerpts=excerpts,
                figure_context=figure_context,
                figure_images=[figure.path for figure in figures],
                stuck_count=stuck_count,
                learner_preferences=profile.preferences,
            )
            report(f"checking-{attempts}", "核对回答与引用", "检查回答是否与教材证据一致")
            quality = self.quality_checker.check(
                response, state, plan, message, question_spec, check_context,
                excerpts + ("\n" + figure_context if figure_context else ""),
                figure_images=[figure.path for figure in figures],
            )
            if quality.passed:
                break
            feedback = "；".join(quality.issues) or quality.suggestions

        report("saving", "更新学习记录", "整理本轮反馈并保存回答和图片引用")

        # 5) 状态更新 + 新证据 + 教学错误自检
        update = self.state_updater.update(
            state, message, response, current_step,
            quality.issues if quality else None, excerpts,
        )
        state = update.state
        if direct_resource_question:
            state.mastery = start_mastery
            update.step_completed = False
        if stuck_count:
            state.mastery = start_mastery
            update.step_completed = False
        for item in update.new_evidence:
            self.memory.add_evidence(
                student_id, point, item.evidence_type, item.content, item.confidence
            )
        self._store_hypotheses(student_id, point, update.new_hypotheses)
        if update.resolve_misconceptions:
            self.memory.resolve_misconceptions(student_id, point)

        # 5.5) Tutor Error 检测与回滚
        error = self.tutor_error_detector.detect(update.raw)
        rolled_back = False
        if error.detected and error.rollback:
            rolled_back = self.memory.rollback(student_id, point)
            self.memory.add_evidence(
                student_id, point, "tutor_error",
                error.reason or error.error_type or "检测到教学错误", 0.6,
            )

        # 6) 步骤推进（仅在本轮未被回滚时）
        step_advanced = False
        if update.step_completed and lesson_plan.status == "in_progress" and not rolled_back:
            step_id = lesson_plan.current_step
            step = lesson_plan.get_step(step_id)
            if step_id and step is not None:
                state.steps_mastery[step_id] = max(
                    state.steps_mastery.get(step_id, 0.0), step.target_mastery
                )
            lesson_plan.advance(state.steps_mastery)
            step_advanced = True

        # 7) 教学有效性（策略 -> 效果）更新
        success = step_advanced or (state.mastery - start_mastery) >= 0.08
        if rolled_back:
            success = False
        self.memory.update_effectiveness(student_id, plan.strategy, success)

        # 8) 写回记忆
        if figures and not any(figure.label in response for figure in figures):
            response = response.rstrip() + "\n教材图像：" + "、".join(
                figure.label for figure in figures
            ) + "。"
        self.memory.append(student_id, "user", message)
        self.memory.append(student_id, "assistant", response, [figure.id for figure in figures])
        self.memory.save_state(student_id, point, state)
        self.memory.save_lesson_plan(
            student_id, point, lesson_plan, state.steps_mastery
        )

        return {
            "reply": response,
            "student_state": state.model_dump(),
            "teaching_plan": plan.model_dump(),
            "question_spec": question_spec.model_dump() if question_spec else None,
            "quality": quality.model_dump() if quality else None,
            "regenerated": attempts - 1,
            "lesson_progress": lesson_plan.progress(),
            "step_advanced": step_advanced,
            "step_reason": update.step_reason,
            "misconceptions": [
                m.model_dump()
                for m in self.memory.get_misconceptions(student_id, point)
            ],
            "tutor_error": error.model_dump(),
            "knowledge_point": point,
            "routing": routing.model_dump(),
            "instructional_move": move.model_dump(),
            "textbook_sources": [f"{item.source}／{item.section}" for item in sources],
            "image_refs": [figure.public() for figure in figures],
        }

    def _store_hypotheses(self, student_id: str, point: str, hypotheses) -> None:
        """把本轮新误解假设去重后写入（规范化匹配 + LLM 语义合并）。"""
        if not hypotheses:
            return
        existing = self.memory.get_misconceptions(student_id, point)
        for hypo in hypotheses:
            merge_id = self.misconception_resolver.resolve(hypo, existing)
            saved = self.memory.add_hypothesis(
                student_id,
                point,
                hypo.type,
                hypo.description,
                hypo.confidence,
                merge_into_id=merge_id,
            )
            existing = [m for m in existing if m.id != saved.id] + [saved]

    @staticmethod
    def _lesson_text(lesson_plan, current_step, curriculum_done: bool) -> str:
        if curriculum_done:
            return "课程已全部完成，本轮做总结与迁移应用"
        if current_step is not None:
            progress = lesson_plan.progress()
            return "第 {}/{} 步（目标：{}）".format(
                progress["current_step_index"],
                progress["total_steps"],
                current_step.objective,
            )
        return ""
