"""Orchestrator —— 系统的"胶水层"（本项目最核心的自主实现）。

V0.2 数据流（全部经 MemoryManager 落 MySQL）：
    load(三类记忆) -> Lesson Planner -> Evidence Extractor -> State Analyzer
    -> Teaching Policy(State+Profile+Plan) -> Teaching Planner -> Question Designer
    -> Response Generator -> Quality Checker -> State Updater
    -> 误解读写/教学错误回滚/步骤推进/教学效果更新 -> save(MySQL)

【自主衔接】本文件不实现 AI 能力，只负责连接与闭环控制。
"""

from __future__ import annotations
from knowledge.evidence_recovery import recover_evidence
from knowledge.citation_locations import complete_pdf_references

import re
from uuid import uuid4
from memory.evidence_policy import assess_attempt, project_state
from typing import Any, Dict, Optional

from agents.context_sufficiency import ContextSufficiency
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
from knowledge.hybrid_retrieval import retrieve_hybrid
from knowledge.pdf_evidence import enrich_sources
from knowledge.proof_units import expand_proof_sources
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
        self.context_sufficiency = ContextSufficiency(self.llm)
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
        goal = point
        stuck_count = consecutive_stuck(history, message)
        query = self._retrieval_query(message, point, routing)
        resource_query = bool(re.search(r"(?:图|表)\s*\d+\s*[.．]\s*\d+|表格|真值表|函数表|公式|表达式|配图|插图|图片", message))
        report("retrieving", "检索教材", "查找相关正文、公式、表格和插图")
        sources = retrieve_hybrid(message if resource_query else query, self.textbook_chunks, limit=2)
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
                    chunk.source.removesuffix(".txt").removesuffix(".doc") == figure.source.removesuffix(".txt").removesuffix(".doc")
                    and figure.label in chunk.text
                    for figure in figures
                )
            ]
            if matching:
                sources = matching[:2]
        pdf_supplement = None
        proof_evidence = None
        if sources and not direct_figure_question:
            report("proof-context", "关联证明与前置知识", "核对完整证明边界和显式引用")
            sources, proof_evidence = expand_proof_sources(sources, query)
            if proof_evidence:
                pdf_supplement = proof_evidence.supplement
        if sources and not direct_figure_question and not proof_evidence:
            report("pdf-evidence", "核对教材原页", "按正文锚点补充缺失公式与相邻上下文")
            sources, pdf_supplement = enrich_sources(sources, message)
        if pdf_supplement:
            # 原页包含完整公式和相邻说明，避免两张零散公式图占满视觉输入。
            figures = []
        model_images = pdf_supplement.images if pdf_supplement else [figure.path for figure in figures[:2]]
        if not sources and not figures:
            reply = "目前没有检索到与这个问题直接相关的教材依据。你可以选中教材里的相关内容再问，或告诉我具体章节。"
            self.memory.append(student_id, "user", message)
            self.memory.append(student_id, "assistant", reply)
            return {
                "reply": reply,
                "routing": routing.model_dump(),
                "knowledge_point": active_point,
                "student_state": self.memory.get_state(student_id, active_point).model_dump(),
                "textbook_sources": [],
                "image_refs": [],
            }
        report("evidence", "核验教材依据", "检查教材内容能否支持完整问题")
        evidence = [{"id": str(i), "source": item.source, "section": item.section, "text": item.text}
                    for i, item in enumerate(sources, 1)]
        if figures:
            evidence.append({"id": "images", "text": format_figure_context(figures)})
        evidence_check = self.context_sufficiency.check(
            message, evidence, topic=point, history=history,
            image_paths=model_images or None,
        )
        recovered = recover_evidence(message, sources, self.textbook_chunks, evidence_check, retrieve_hybrid)
        if len(recovered) > len(sources):
            report("evidence", "补充核验依据", "补检索缺失的定义与条件，再核验完整问题")
            sources = recovered
            evidence = [{"id": str(i), "source": item.source, "section": item.section, "text": item.text}
                        for i, item in enumerate(sources, 1)]
            if figures:
                evidence.append({"id": "images", "text": format_figure_context(figures)})
            evidence_check = self.context_sufficiency.check(
                message, evidence, topic=point, history=history, image_paths=model_images or None,
            )
        if not evidence_check.allowed:
            reply = evidence_check.reply()
            self.memory.append(student_id, "user", message)
            self.memory.append(student_id, "assistant", reply)
            return {
                "reply": reply, "routing": routing.model_dump(),
                "knowledge_point": active_point,
                "student_state": self.memory.get_state(student_id, active_point).model_dump(),
                "textbook_sources": [], "image_refs": [],
                "evidence_check": evidence_check.model_dump(),
            }
        excerpts = format_excerpts(sources)
        figure_context = format_figure_context(figures)
        if pdf_supplement:
            figure_context = f"随附原 PDF 裁图对应教材引用[{pdf_supplement.source_index + 1}]，页码为{pdf_supplement.pages}；以原图核对公式。"

        report("resources", "读取教材资源", f"已检索 {len(sources)} 个片段，关联 {len(model_images)} 张图像")

        report("memory", "检索相关学习记忆", "从完整历史筛选相关记录、来源与当前偏好")
        memory_context = self.memory.retrieve_context(student_id, title=point, question=message)

        # 记录读版本；模型调用期间不持有数据库写事务。
        event_id = str(uuid4())
        expected_token, expected_epoch = self.memory.read_version(student_id, point)
        previous_event = self.memory.get_previous_event(student_id, point)

        state = self.memory.get_state(student_id, point)
        profile = self.memory.get_profile(student_id, point=point)
        saved_state = state.model_copy(deep=True)

        report("planning", "组织讲解", "结合教材与学习记录确定讲解方式")

        # 0) 知识点课程计划（先有目标和计划，再开始对话）
        lesson_plan = self.memory.get_lesson_plan(student_id, point)
        saved_lesson_plan = lesson_plan.model_copy(deep=True) if lesson_plan else None
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
        decision = assess_attempt(routing, message, analysis.evidence, previous_event,
                                  has_history=bool(history), blocked=bool(stuck_count or direct_resource_question))
        state = self.state_analyzer.build(state, analysis)
        # 分析用于选择教学动作，仍不能提前落库或改变掌握投影。
        if not decision.eligible:
            state.mastery = saved_state.mastery
            state.steps_mastery = dict(saved_state.steps_mastery)
        state.current_concept = point

        # 2) 教学计划（State + Profile + Plan 三方决策）
        curriculum_done = lesson_plan.status == "completed"
        plan = self.teaching_planner.plan(
            state, goal, current_step, curriculum_done, profile
        )

        # 2.2) Strategy Router：按学生 move + 状态 + 画像选本轮教学动作
        profile = self.memory.get_profile(student_id, point=point, difficulty=plan.difficulty, hint_level=plan.hint_level)
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

        direct_content_question = self._align_explanation(
            plan, move, routing.student_move,
            explanation_requested=bool(re.search(r"解释|说明|为什么|为何|讲解|怎样理解|是什么意思|证明|推导", message)),
        )

        # 2.5) 诊断性问题设计
        question_spec = None if (direct_resource_question or direct_content_question) else self.question_designer.design(
            state, plan, current_step, excerpts
        )

        lesson_text = self._lesson_text(lesson_plan, current_step, curriculum_done)
        if direct_content_question:
            lesson_text = "本轮先回答学生明确的教材问题，不出诊断题，不将助教的讲解视为学生已经掌握。"
        if direct_resource_question:
            labels = "、".join(figure.label for figure in figures)
            labels = labels or ("原 PDF 图文" if pdf_supplement else "表格")
            lesson_text = f"本轮直接回答学生对教材{labels}的具体问题，不推进原课程步骤，不出诊断题。"
            plan.goal = f"准确解释教材{labels}及其图中标记"
            plan.strategy = "worked_example"
            plan.action = "explain"
            plan.rationale = "学生明确询问教材图片，先解答该图"

        if proof_evidence:
            plan.goal = f"解释{proof_evidence.unit.label}的证明及学生指定步骤"
            lesson_text += "\n本轮证明资料包含完整编号单元及显式引用。先回答指定步骤；完整证明请求先概述路线，再解释一小步，明确还未展开哪些部分。教材留给读者的步骤须称为补充推导。显式引用只证明原文引用过该编号，不保证引用正确；不得把未核实的编号关系当作数学前提。"

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
                figure_images=model_images,
                stuck_count=stuck_count,
                learner_preferences=profile.preferences,
                memory_context=memory_context,
            )
            report(f"checking-{attempts}", "核对回答与引用", "检查回答是否与教材证据一致")
            quality = self.quality_checker.check(
                response, state, plan, message, question_spec, check_context,
                excerpts + ("\n" + figure_context if figure_context else ""),
                figure_images=model_images,
            )
            if self._quality_accepted(quality):
                break
            feedback = "；".join(quality.issues) or quality.suggestions

        if not self._quality_accepted(quality):
            report("quality-rejected", "本次讲解未通过核对", "停止发布草稿，不推进课程步骤")
            reply = "本次讲解未通过教材核对，暂时不能可靠给出解释。你可以选中具体教材步骤再问。本次没有推进学习进度。"
            self.memory.append(student_id, "user", message)
            self.memory.append(student_id, "assistant", reply)
            return {
                "reply": reply, "answer_status": "quality_rejected",
                "quality": quality.model_dump() if quality else None,
                "evidence_check": evidence_check.model_dump(),
                "regenerated": attempts - 1, "routing": routing.model_dump(),
                "knowledge_point": active_point, "student_state": saved_state.model_dump(),
                "lesson_progress": saved_lesson_plan.progress() if saved_lesson_plan else None,
                "step_advanced": False, "step_reason": "回答未通过质检，不推进学习步骤",
                "textbook_sources": [], "image_refs": [], "pdf_image_refs": [], "pdf_references": [],
                "selection_ref": None, "pdf_evidence": None, "proof_evidence": None,
            }


        report("saving", "更新学习记录", "整理本轮反馈并保存回答和图片引用")

        # 5) 状态更新 + 新证据 + 教学错误自检
        update = self.state_updater.update(
            state, message, response, current_step,
            quality.issues if quality else None, excerpts,
        )
        all_evidence = analysis.evidence + update.new_evidence
        decision = assess_attempt(routing, message, all_evidence, previous_event,
            has_history=bool(history), blocked=bool(stuck_count or direct_resource_question or direct_content_question))
        state = project_state(saved_state, update.state, update.raw, decision)
        hypotheses = self._prepare_hypotheses(student_id, point,
            analysis.hypotheses + update.new_hypotheses) if decision.eligible else []
        error = self.tutor_error_detector.detect(update.raw)
        rolled_back = bool(error.detected and error.rollback)
        if rolled_back:
            state = saved_state.model_copy(deep=True)
            if saved_lesson_plan is not None:
                lesson_plan = saved_lesson_plan.model_copy(deep=True)
        step_advanced = False
        current = lesson_plan.current()
        if (decision.eligible and not rolled_back and update.step_completed
                and lesson_plan.status == "in_progress" and current is not None
                and state.steps_mastery.get(current.step_id, 0) >= current.target_mastery):
            lesson_plan.advance(state.steps_mastery)
            step_advanced = True
        if not decision.eligible or rolled_back:
            update.step_reason = "本轮未形成独立有效测量，保持原学习进度"
        # 策略效果由提交事务关联上一轮教学；不评价尚未发生的本轮动作。
        success = None

        # 8) 写回记忆
        if figures and not any(figure.label in response for figure in figures):
            response = response.rstrip() + "\n教材图像：" + "、".join(
                figure.label for figure in figures
            ) + "。"
        textbook_sources = [
            f"{item.source}／{item.section}" + (f"（PDF第{item.page}页起）" if item.page else "")
            for item in sources
        ]
        pdf_references = proof_evidence.public_references(sources) if proof_evidence else (
            [{"source_index": pdf_supplement.source_index, "selection_ref": pdf_supplement.reference}]
            if pdf_supplement else []
        )
        pdf_references = complete_pdf_references(sources, response, pdf_references, figures=figures)
        base_reference = pdf_supplement.reference if pdf_supplement else (pdf_references[0]["selection_ref"] if pdf_references else None)
        stored_reference = (base_reference | {"pdf_references": pdf_references,
            "textbook_sources": textbook_sources}) if base_reference else None
        memory_commit = self.memory.commit_learning_turn(
            student_id=student_id, point=point, event_id=event_id, expected_token=expected_token, expected_epoch=expected_epoch,
            message=message, reply=response, state=state, lesson_plan=lesson_plan, decision=decision,
            evidence=all_evidence, hypotheses=hypotheses, strategy=plan.strategy, success=success,
            teaching_context={"strategy": plan.strategy, "difficulty": move.difficulty, "hint_level": move.hint_level},
            instructional_move=move.instructional_move, figure_ids=[figure.id for figure in figures],
            selection_ref=stored_reference, misconception_updates=getattr(update, "misconception_updates", []), tutor_error=(error.reason or "检测到教学错误") if rolled_back else None,
        )
        if memory_commit["status"] == "forgotten":
            return {"reply":"这个知识点的学习记忆已被删除，本次回答未保存，请重新提问。",
                "answer_status":"memory_deleted","memory_commit":memory_commit,
                "student_state":self.memory.get_state(student_id,point).model_dump(),
                "knowledge_point":point,"step_advanced":False,"textbook_sources":[],"image_refs":[],
                "pdf_references":[],"pdf_image_refs":[],"selection_ref":None}
        if memory_commit["status"] == "conflict":
            state = self.memory.get_state(student_id, point)
            lesson_plan = self.memory.get_lesson_plan(student_id, point) or lesson_plan
            step_advanced = False
            update.step_reason = "并发学习记录已更新，本轮回答已保存，未覆盖新状态"
        elif memory_commit["status"] == "committed":
            self.memory.push_recent_move(student_id, move.instructional_move)

        return {
            "reply": response,
            "answer_status": "answered",
            "memory_commit": memory_commit,
            "memory_summary": memory_context.get("summary", ""),
            "memory_retrieval": memory_context.get("retrieval", {}),
            "student_state": state.model_dump(),
            "teaching_plan": plan.model_dump(),
            "question_spec": question_spec.model_dump() if question_spec else None,
            "quality": quality.model_dump() if quality else None,
            "evidence_check": evidence_check.model_dump(),
            "proof_evidence": proof_evidence.public() if proof_evidence else None,
            "pdf_evidence": pdf_supplement.public() if pdf_supplement else None,
            "pdf_references": pdf_references,
            "pdf_image_refs": pdf_supplement.reference["image_refs"] if pdf_supplement else [],
            "selection_ref": base_reference,
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
            "textbook_sources": textbook_sources,
            "image_refs": [figure.public() for figure in figures],
        }

    @staticmethod
    def _quality_accepted(quality):
        return quality is not None and quality.passed is True and not quality.issues

    @staticmethod
    def _retrieval_query(message, point, routing):
        if is_stuck(message) or is_self_report_understood(message):
            return point
        if routing.intent in ("switch_topic", "new_goal"):
            return message
        if getattr(routing, "student_move", "") == "question" and not getattr(routing, "needs_context", False):
            return message
        return point + " " + message

    @staticmethod
    def _align_explanation(plan, move, student_move, *, explanation_requested=False):
        """直接解释时统一生成和质检的计划，避免把正常讲解判为泄露。"""
        direct = student_move == "question" and (move.action == "explain" or explanation_requested)
        if direct:
            if move.action != "explain":
                move.action = "explain"
                move.instructional_move = "direct_explanation"
            plan.strategy = "worked_example"
            plan.action = "explain"
            plan.rationale = "先解答学生明确提出的教材问题"
        return direct

    def _prepare_hypotheses(self, student_id, point, hypotheses):
        """只准备合并目标；所有模型工作必须在写事务之前完成。"""
        existing = self.memory.get_misconceptions(student_id, point)
        return [(hypo, self.misconception_resolver.resolve(hypo, existing)) for hypo in hypotheses]

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
