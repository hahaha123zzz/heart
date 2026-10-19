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
import os
from uuid import uuid4
from memory.evidence_policy import assess_attempt, project_state
from typing import Any, Dict, Optional

from agents.task_execution import build_execution
from agents.conversation_context import build_history
from agents.followup_context import SIMPLIFY_PATTERN, followup_directive
from agents.context_sufficiency import ContextSufficiency
from agents.conversation_router import ConversationRouter
from agents.evidence_extractor import AnalysisResult, EvidenceExtractor
from agents.lesson_planner import LessonPlanner
from agents.learning_feedback import adapt_answer_feedback, consecutive_stuck, is_self_report_understood, is_stuck
from agents.misconception_resolver import MisconceptionResolver
from agents.quality_checker import QualityChecker,QualityResult
from agents.question_designer import QuestionDesigner
from agents.response_generator import ResponseGenerator
from agents.state_analyzer import StateAnalyzer
from agents.state_updater import StateUpdater, UpdateResult
from agents.strategy_router import InstructionalMove, StrategyRouter
from agents.teaching_planner import TeachingPlan, TeachingPlanner
from agents.tutor_error_detector import TutorErrorDetector
from database.database import init_db
from llm.client import LLMClient,LLMError
from knowledge.figures import FIGURE_NUMBER, format_figure_context, retrieve_figures
from knowledge.textbook import format_excerpts, load_textbook, retrieve
from knowledge.hybrid_retrieval import retrieve_hybrid
from knowledge.pdf_evidence import enrich_sources
from knowledge.proof_units import expand_proof_sources
from memory.memory_manager import MemoryManager
from knowledge.course_config import DEFAULT_GOAL,PSYCHOLOGY
from agents.course_prompts import GATE

MAX_REGEN = 1

def retrieve_course(query,chunks,**kwargs):
    if PSYCHOLOGY:
        from knowledge.psychology_retrieval import retrieve as retrieve_psychology
        result = retrieve_psychology(query,chunks,**kwargs)
        if os.getenv("DEEPTUTOR_KNOWLEDGE_ENABLED", "0") == "1":
            from integrations.deeptutor.knowledge_client import supplement
            result = supplement(query, result, limit=kwargs.get("limit", 6))
        return result
    return retrieve_hybrid(query,chunks,**kwargs)


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
        self.context_sufficiency = ContextSufficiency(self.llm,system=GATE) if PSYCHOLOGY else ContextSufficiency(self.llm)
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
        task_context=None,
        precomputed_routing=None,
        routing_interceptor=None,
        task_guard=None,
        visualization_jobs=None,
    ) -> Dict[str, Any]:
        def report(stage, label, detail=""):
            if progress is not None:
                progress(stage, label, detail)

        report("routing", "理解问题", "识别本轮问题与学习目标")
        if task_guard is not None:
            task_guard()
        elif account_type == "test":
            self.memory.accounts.create_test_account(student_id, ttl_hours=24)
        elif account_type == "production":
            self.memory.ensure_student(student_id, account_type="production")
        else:
            raise ValueError("account_type 只能是 test 或 production")

        # 0) Conversation Router：判断学生这一轮在做什么 / 在聊什么
        metadata = getattr(task_context, "history_summary", "") if task_context is not None else ""
        raw_history = task_context.history if task_context is not None else self.memory.get_history(student_id)
        if task_context is not None:
            history = raw_history
            history_summary = metadata
        else:
            # 非任务入口也使用同一预算策略；摘要只作背景，不替代当前教材证据。
            model = getattr(getattr(self, "llm", None), "model", "")
            packed = build_history(raw_history, model=model if isinstance(model, str) else "")
            history, history_summary = packed.history, packed.summary
        active_point = (
            self.memory.get_active_goal(student_id) or learning_goal or DEFAULT_GOAL
        )
        if precomputed_routing is not None:
            routing = precomputed_routing
        elif task_context is not None:
            if task_context.student_id != student_id or task_context.message != message:
                raise ValueError("任务上下文不属于当前请求")
            routing = self.conversation_router.route(message, task_context.knowledge_point,
                task_context.history, task_context.known_points, context=task_context)
        else:
            routing = self.conversation_router.route(
                message, active_point, raw_history, self.memory.list_knowledge_points(student_id),
                history_summary=history_summary)

        if routing_interceptor is not None:
            intercepted = routing_interceptor(routing, task_context)
            if intercepted is not None: return intercepted

        def save_exchange(reply):
            from database.database import session_scope
            with session_scope(immediate=True):
                if task_guard is not None: task_guard()
                self.memory.append(student_id, "user", message)
                self.memory.append(student_id, "assistant", reply)

        # 识别失败不进入检索/教学，不把用户问题写成能力观测。
        if routing.status != "ok":
            report("routing-stopped", "需要补充问题" if routing.status == "unknown" else "问题识别未完成",
                   "本轮未推进学习进度")
            reply = (
                "你想切换到哪个知识点？请说出具体目标。" if routing.status == "unknown"
                else "暂时无法可靠识别这次问题，请重试或补充具体教材对象。本次没有推进学习进度。"
            )
            return {
                "reply": reply,
                "answer_status": "routing_unavailable" if routing.status == "unavailable" else
                                 ("awaiting_clarification" if routing.status == "unknown" else "routing_failed"),
                "routing": routing.model_dump(), "knowledge_point": active_point,
                "student_state": self.memory.get_state(student_id, active_point).model_dump(),
                "step_advanced": False, "step_reason": "问题识别未完成",
                "textbook_sources": [], "image_refs": [], "pdf_image_refs": [], "pdf_references": [],
            }

        # 0.1) 非学习消息：不进教学流程（简短共情 + 轻推回学习，不强行拉回）
        if routing.intent == "off_task":
            report("generating", "生成回答", "准备回复")
            reply = self.response_generator.social_reply(message, active_point, history)
            save_exchange(reply)
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
                missing = getattr(routing, "missing_slots", [])
                if "target" in missing:
                    reply = "你指的是哪段文字、哪个图或哪条公式？可以选中教材内容后再问。"
                elif "task" in missing:
                    reply = "你想继续哪个任务？可以告诉我章节、题目或接下来想学的内容。"
                elif "answer_format" in missing:
                    reply = "你希望我解释含义、给出提示，还是展开证明？"
                else:
                    reply = "你想换到哪个知识点？请直接说具体目标。"
                save_exchange(reply)
                return {
                    "reply": reply,
                    "routing": routing.model_dump(),
                    "knowledge_point": active_point,
                    "student_state": self.memory.get_state(
                        student_id, active_point
                    ).model_dump(),
                }
            point = topic
        if task_context is not None and routing.intent == "continue":
            point = task_context.knowledge_point or point
        if task_context is not None and (task_context.graph_snapshot or task_context.truth_table_snapshot or task_context.relation_snapshot):
            point = task_context.knowledge_point
        goal = point
        execution = build_execution(message, routing, task_context)
        stuck_count = consecutive_stuck(history, message)
        query = execution.retrieval_query if execution.target_refs else self._retrieval_query(message, point, routing, history)
        citation_path=None
        if PSYCHOLOGY:
            from knowledge.grounded_citations import settings as citation_settings,choose_evidence
            citation_path=citation_settings()
        if citation_path and history and (routing.needs_context or is_self_report_understood(message)):
            # 历史只补检索指代，最终证据仍须来自当前版本教材；章节名不能代替刚才的具体对象。
            query+='\n最近对话所指内容（仅作检索线索）：'+re.sub(r'\[\d+\]','', '\n'.join(row['content'] for row in history[-4:]))[-1800:]
        resource_query = bool(re.search(r"(?:图|表)\s*\d+\s*[.．]\s*\d+|表格|真值表|函数表|公式|表达式|配图|插图|图片", message))
        report("retrieving", "检索教材", "查找相关正文、公式、表格和插图")
        sources = retrieve_course(message if resource_query and not execution.target_refs else query, self.textbook_chunks,
                                  limit=6 if PSYCHOLOGY else 2, preferred_types=execution.retrieval_types())
        if is_stuck(message) and sources:
            chapter = sources[0].source
            basics = [
                chunk for chunk in self.textbook_chunks
                if chunk.source == chapter and "基本概念" in chunk.section
            ]
            if basics:
                sources = basics[:2]
        # 当前辅助图有自己的权威边集；无显式教材图号时，不附另一张教材图冒充该实例。
        figures = ([] if task_context is not None and (task_context.graph_snapshot or task_context.truth_table_snapshot or task_context.relation_snapshot) and not FIGURE_NUMBER.search(message)
                   else retrieve_figures(message, sources))
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
        if sources and not direct_figure_question and not PSYCHOLOGY:
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
            save_exchange(reply)
            return {
                "reply": reply,
                "answer_status": "evidence_rejected", "step_advanced": False,
                "routing": routing.model_dump(),
                "knowledge_point": active_point,
                "student_state": self.memory.get_state(student_id, active_point).model_dump(),
                "textbook_sources": [],
                "image_refs": [],
            }
        expected_token, expected_epoch = self.memory.read_version(student_id, point)
        report("memory", "检索相关学习记忆", "从完整历史筛选相关记录、来源与当前偏好")
        memory_title = sources[0].section if sources and not routing.needs_context and not execution.target_refs else point
        memory_context = self.memory.retrieve_context(student_id, title=memory_title, question=message)
        memory_context["preferences"] = {**memory_context.get("preferences", {}), **execution.preferences}
        report("evidence", "核验教材依据", "检查教材内容能否支持完整问题")
        evidence = [{"id": str(i), "source": item.source, "section": item.section, "text": item.text}
                    for i, item in enumerate(sources, 1)]
        if figures:
            evidence.append({"id": "images", "text": format_figure_context(figures)})
        evidence_question = execution.retrieval_query if execution.target_refs else message
        if is_self_report_understood(message) and not execution.no_questions:
            evidence_question = f"围绕{point}及最近教材讲解设计一个简短理解检查，核验检查所需定义和条件是否有教材依据。学生本轮只是确认理解，不是新的事实问题。"
        evidence_check = self.context_sufficiency.check(
            evidence_question, evidence, topic=point, history=history,
            image_paths=model_images or None,
            hint_only=execution.hint_only,
            memory_context=memory_context,
        )
        recovered = recover_evidence(evidence_question, sources, self.textbook_chunks, evidence_check, retrieve_course,
                                     max_sources=9 if PSYCHOLOGY else 6)
        if len(recovered) > len(sources):
            report("evidence", "补充核验依据", "补检索缺失的定义与条件，再核验完整问题")
            original_count = len(sources)
            sources = recovered
            # 补召回也须读取原页；否则新召回的公式仍是缺符号的旧文本。
            for index in range(original_count, len(sources)):
                anchor = re.match(r'(定义|定理|例)\s*\d+\s*[.．]\s*\d+', sources[index].text.lstrip())
                query_for_source = '解释' + anchor.group() if anchor else message
                updated, supplement = enrich_sources([sources[index]], query_for_source)
                sources[index] = updated[0]
                if supplement:
                    supplement.source_index = index
                    if pdf_supplement is None: pdf_supplement = supplement
                    model_images = list(dict.fromkeys([*model_images, *supplement.images]))[:2]
            evidence = [{"id": str(i), "source": item.source, "section": item.section, "text": item.text}
                        for i, item in enumerate(sources, 1)]
            if figures:
                evidence.append({"id": "images", "text": format_figure_context(figures)})
            evidence_check = self.context_sufficiency.check(
                evidence_question, evidence, topic=point, history=history, image_paths=model_images or None,
                hint_only=execution.hint_only,
                memory_context=memory_context,
            )
        if self.memory.repo.memory_epoch(student_id, point) != expected_epoch:
            return {"reply": "这个知识点的学习记忆已被删除，本次回答未保存，请重新提问。",
                    "answer_status": "memory_deleted", "memory_commit": {"status": "forgotten"},
                    "knowledge_point": point, "step_advanced": False,
                    "textbook_sources": [], "image_refs": [], "pdf_references": [], "pdf_image_refs": [],
                    "selection_ref": None}
        if not evidence_check.allowed:
            reply = evidence_check.reply()
            save_exchange(reply)
            return {
                "reply": reply, "answer_status": "evidence_rejected", "step_advanced": False, "routing": routing.model_dump(),
                "knowledge_point": active_point,
                "student_state": self.memory.get_state(student_id, active_point).model_dump(),
                "textbook_sources": [], "image_refs": [],
                "evidence_check": evidence_check.model_dump(),
            }
        grounded_bundle = None
        grounded_references = None
        if PSYCHOLOGY:
            if citation_path:
                report('citation-selection','选择支持原文','从检索上下文中选择可逐项核验的细粒度证据')
                try:
                    grounded_bundle=choose_evidence(self.llm,message,sources,citation_path,history=history)
                    sources=grounded_bundle.sources
                    evidence=[{'id':str(i),'source':s.source,'section':s.section,'text':s.text} for i,s in enumerate(sources,1)]
                    pdf_supplement=None
                except (ValueError,LLMError,OSError):
                    reply='本次未能确认可靠的教材引用证据，请缩小问题范围或选中教材原文后重试。'
                    save_exchange(reply)
                    return {'reply':reply,'answer_status':'quality_rejected','step_advanced':False,
                        'quality':{'passed':False,'issues':['引用证据选择未完成'],'suggestions':''},
                        'textbook_sources':[],'pdf_references':[],'image_refs':[]}
        excerpts = format_excerpts(sources)
        figure_context = format_figure_context(figures)
        if pdf_supplement:
            figure_context = f"随附原 PDF 裁图对应教材引用[{pdf_supplement.source_index + 1}]，页码为{pdf_supplement.pages}；以原图核对公式。"

        report("resources", "读取教材资源", f"已检索 {len(sources)} 个片段，关联 {len(model_images)} 张图像")

        event_id = str(uuid4())
        previous_event = self.memory.get_previous_event(student_id, point)

        state = self.memory.get_state(student_id, point)
        profile = self.memory.get_profile(student_id, point=point)
        saved_state = state.model_copy(deep=True)

        report("planning", "组织讲解", "结合教材与学习记录确定讲解方式")

        # 明确的内容提问只消费已有画像；学生作答和主动学习仍进入教学评估。
        direct_answer = execution.can_answer_directly(routing, message)
        prior_feedback = (previous_event or {}).get("payload", {}).get("teaching_context", {}).get("feedback_mode")
        assisted_retry = routing.student_move == "statement" and prior_feedback in (
            "targeted_hint", "hint_only", "worked_example", "supportive_hint")
        diagnose_answer = PSYCHOLOGY and (routing.student_move == "attempt" or "check_answer" in execution.learning_intents or assisted_retry)
        lesson_plan = self.memory.get_lesson_plan(student_id, point)
        saved_lesson_plan = lesson_plan.model_copy(deep=True) if lesson_plan else None
        if direct_answer:
            current_step = None
            analysis = AnalysisResult()
            plan = TeachingPlan(goal="回答本轮问题：" + point, strategy="worked_example",
                                action="explain", difficulty="medium", rationale="先完成用户明确的内容请求")
            move = InstructionalMove(instructional_move="direct_explanation", action="explain")
        else:
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
            if PSYCHOLOGY:
                report("diagnosing", "核对本轮理解", "依据本轮教材核对学生原话与疑点")
                analysis = self.evidence_extractor.analyze(message, state, history,
                    textbook_evidence=evidence, assess_answer=diagnose_answer)
            else:
                analysis = self.evidence_extractor.analyze(message, state, history)
        answer_diagnosis = analysis.answer_diagnosis if PSYCHOLOGY else None
        uncertain_answer = answer_diagnosis is not None and answer_diagnosis.verdict == "unclear"
        decision = assess_attempt(routing, message, analysis.evidence, previous_event,
                                  has_history=bool(history), blocked=bool(direct_answer or stuck_count or direct_resource_question or uncertain_answer))
        if not direct_answer:
            state = self.state_analyzer.build(state, analysis)
        if PSYCHOLOGY and (diagnose_answer or stuck_count):
            state.interaction_preference = saved_state.interaction_preference
        # 分析用于选择教学动作，仍不能提前落库或改变掌握投影。
        if not decision.eligible:
            state.mastery = saved_state.mastery
            state.steps_mastery = dict(saved_state.steps_mastery)
        state.current_concept = point

        # 2) 教学计划（State + Profile + Plan 三方决策）
        curriculum_done = bool(lesson_plan and lesson_plan.status == "completed")
        if not direct_answer:
            plan = self.teaching_planner.plan(
                state, goal, current_step, curriculum_done, profile
            )

        # 2.2) Strategy Router：按学生 move + 状态 + 画像选本轮教学动作
        profile = self.memory.get_profile(student_id, point=point, difficulty=plan.difficulty, hint_level=plan.hint_level)
        recent_moves = self.memory.get_recent_moves(student_id)
        if not direct_answer:
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

        explicit_answer = execution.align(plan, move)
        direct_content_question = explicit_answer if execution.explicit else direct_content_question

        # 2.5) 诊断性问题设计
        question_spec = None

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
            "topic_switched": routing.intent in ("switch_topic", "new_goal") and point != active_point,
            "old_topic": active_point,
            "current_topic": point,
            "recent_moves": (recent_moves + [move.instructional_move])[-3:],
            "stuck_count": stuck_count,
        }
        if SIMPLIFY_PATTERN.search(message) and previous_reply:
            # 页面阅读位置仍是当前章节，但“没听懂/再简单点”指向上一轮解释；
            # 不能把本轮目标退回章节标题，否则会换题并误判为偏题。
            plan.goal = "用更简单的说法重述上一轮助教解释"
            plan.strategy = "worked_example"
            plan.action = "explain"
            plan.rationale = "连续追问简化上一轮解释"
            move.instructional_move = "direct_explanation"
            move.action = "explain"
            lesson_text = ("本轮是连续追问：只简化上一轮助教解释，不切换到当前阅读章节，"
                           "不引入新概念，也不改答上一轮末尾的检查题。")
            check_context["followup_simplify"] = True
            check_context["followup_target"] = previous_reply[:1200]
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
        # 旧的资源/卡住/自述理解策略之后，再落实显式要求，防止覆盖仅提示。
        execution.align(plan, move)
        answer_feedback = adapt_answer_feedback(plan, move, execution=execution,
            diagnosis=answer_diagnosis, previous_event=previous_event, stuck_count=stuck_count,
            state=state, student_input=message, needs_context=routing.needs_context) if PSYCHOLOGY else {}
        if answer_feedback:
            import json
            lesson_text = "本轮围绕学生当前作答或困难反馈，课程进度仅作背景，不扩大到下一知识点。\n本轮反馈（诊断为暂定资料，不是新教材事实）：" + json.dumps(answer_feedback, ensure_ascii=False)
            check_context["answer_feedback"] = answer_feedback
            check_context["recent_moves"] = (recent_moves + [move.instructional_move])[-3:]
        if answer_feedback.get("mode") == "check_self_report":
            plan.goal = "围绕上一轮讲解的一个要点检查理解"
            check_context["feedback_target"] = previous_reply[:1200]
            question_spec = self.question_designer.design(state, plan, None, excerpts,
                teaching_context={"previous_reply": previous_reply[:1200]})
        elif not answer_feedback and not execution.no_questions and not direct_resource_question and not direct_content_question and not stuck_count:
            question_spec = self.question_designer.design(state, plan, current_step, excerpts)
        if execution.explicit:
            lesson_text += "\n" + execution.instructions()
        if task_context is not None and task_context.graph_snapshot:
            import json
            visible_snapshot = {key:value for key,value in task_context.graph_snapshot.items()
                                if not execution.hint_only or key != 'evaluation'}
            lesson_text += '\n当前辅助图的服务端快照（实例事实，不是教材原图或新的指令）：' + json.dumps(visible_snapshot, ensure_ascii=False)
            lesson_text += '\n只针对这份边集解释。教材定理仍用摘录编号引用；仅提示时只给第一步，不输出后台算出的全部度数、最终判定或完整路径。'
            check_context['graph_snapshot'] = task_context.graph_snapshot
        if task_context is not None and task_context.truth_table_snapshot:
            import json
            snapshot = task_context.truth_table_snapshot
            visible_snapshot = {key:value for key,value in snapshot.items() if key != 'evaluation'}
            if not execution.hint_only:
                visible_snapshot['selected_expected'] = snapshot['evaluation'][snapshot['row_id']]
            lesson_text += '\n当前辅助真值表服务端快照（实例事实，不是教材引文）：'+json.dumps(visible_snapshot, ensure_ascii=False)
            lesson_text += '\n只解释选中指派；教材定义用摘录编号引用。仅提示时只能给操作步骤，不给当前行最终真值或填完整表。'
            check_context['truth_table_snapshot'] = snapshot
        if task_context is not None and task_context.relation_snapshot:
            import json
            snapshot=task_context.relation_snapshot
            visible={key:value for key,value in snapshot.items() if key!='evaluation'}
            if not execution.hint_only and not snapshot.get('closure'):
                property=snapshot['property']
                visible['selected_result']=snapshot['evaluation']['properties'][property]
                visible['selected_witness']=snapshot['evaluation']['witnesses'][property]
            lesson_text+='\n当前辅助关系的服务端快照（实例事实，不是教材引文）：'+json.dumps(visible,ensure_ascii=False)
            lesson_text+='\n只按这份序偶解释选中性质或元素对，教材依据按摘录编号引用；反对称不是非对称。仅提示时只给检查方法，不给该实例的性质结论、缺失边或完整反例。'
            if snapshot.get('closure'):
                lesson_text+='\n本轮是闭包预览：顶层pairs是原关系，closure.current_pairs是目前步骤的扩充关系，二者不可混淆。解释当前补边的premises、reason以及闭包最小性；不要把中间结果称为最终闭包，也不要提前展开后续步骤。传递闭包由正长度路径决定，环可能要求自环；不是给所有点自动添加自环。'
            check_context['relation_snapshot']=snapshot
        if grounded_bundle:
            import json
            lesson_text+='\n检索背景（只用于理解问题，不是可直接引用的证据；引用只准使用本轮摘录编号）：'+json.dumps(
                [{'source':s.source,'section':s.section,'text':s.text} for s in grounded_bundle.backgrounds],ensure_ascii=False)
            check_context['grounded_evidence']=[{k:e[k] for k in ('evidence_id','quote','document_id','document_version','source_block_id')}
                                                for e in grounded_bundle.evidence]
        feedback: Optional[str] = None
        check_context["learner_preferences"] = {**profile.preferences, **execution.preferences}
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
                learner_preferences={**profile.preferences, **execution.preferences},
                memory_context=memory_context,
                task_execution=execution,
                answer_feedback=answer_feedback,
                revision_draft=response if feedback else None,
                history_summary=history_summary,
                followup_context=followup_directive(message, history),
            )
            report(f"checking-{attempts}", "核对回答与引用", "检查回答是否与教材证据一致")
            quality = self.quality_checker.check(
                response, state, plan, message, question_spec, check_context,
                excerpts + ("\n" + figure_context if figure_context else ""),
                figure_images=model_images,
                task_execution=execution,
            )
            if self._quality_accepted(quality):
                if grounded_bundle:
                    report('citation-grounding','核验引用与展示范围','按同一证据记录核对引句、版本、高亮和裁图')
                    try:grounded_references=grounded_bundle.references(response,allow_uncited_question=plan.action=='ask_question')
                    except (ValueError,OSError):
                        quality=QualityResult(passed=False,issues=['本轮引用编号或原文位置核验失败，请只引用提供的证据并保留必要条件'])
                if self._quality_accepted(quality):break
            feedback = "；".join(quality.issues) or quality.suggestions
            if grounded_bundle and attempts <= MAX_REGEN:
                report('citation-reselection','重新选择支持原文','依据质检缺项重新选择；新草稿必须重新核验')
                try:
                    grounded_bundle=choose_evidence(self.llm,message,grounded_bundle.backgrounds,citation_path,feedback=feedback,history=history)
                    sources=grounded_bundle.sources
                    excerpts=format_excerpts(sources)
                    check_context['grounded_evidence']=grounded_bundle.evidence
                except (ValueError,LLMError,OSError):
                    break

        if not self._quality_accepted(quality):
            report("quality-rejected", "本次讲解未通过核对", "停止发布草稿，不推进课程步骤")
            reply = "本次讲解未通过教材核对，暂时不能可靠给出解释。你可以选中具体教材步骤再问。本次没有推进学习进度。"
            save_exchange(reply)
            return {
                "reply": reply, "answer_status": "quality_rejected",
                "quality": quality.model_dump() if quality else None,
                "evidence_check": evidence_check.model_dump(),
                "regenerated": attempts - 1, "routing": routing.model_dump(),
                "task_execution": execution.public(),
                "knowledge_point": active_point, "student_state": saved_state.model_dump(),
                "lesson_progress": saved_lesson_plan.progress() if saved_lesson_plan else None,
                "step_advanced": False, "step_reason": "回答未通过质检，不推进学习步骤",
                "textbook_sources": [], "image_refs": [], "pdf_image_refs": [], "pdf_references": [],
                "selection_ref": None, "pdf_evidence": None, "proof_evidence": None,
            }


        report("saving", "更新学习记录", "整理本轮反馈并保存回答和图片引用")

        # 5) 状态更新 + 新证据 + 教学错误自检
        update = UpdateResult(state=saved_state.model_copy(deep=True)) if direct_answer else self.state_updater.update(
            state, message, response, current_step,
            quality.issues if quality else None, excerpts,
        )
        all_evidence = analysis.evidence + update.new_evidence
        decision = assess_attempt(routing, message, all_evidence, previous_event,
            has_history=bool(history), blocked=bool(direct_answer or stuck_count or direct_resource_question or uncertain_answer))
        state = project_state(saved_state, update.state, update.raw, decision)
        if answer_feedback:
            state.interaction_preference = saved_state.interaction_preference
        hypotheses = self._prepare_hypotheses(student_id, point,
            analysis.hypotheses + update.new_hypotheses) if decision.eligible else []
        error = self.tutor_error_detector.detect(update.raw)
        rolled_back = bool(error.detected and error.rollback)
        if rolled_back:
            state = saved_state.model_copy(deep=True)
            if saved_lesson_plan is not None:
                lesson_plan = saved_lesson_plan.model_copy(deep=True)
        step_advanced = False
        current = lesson_plan.current() if lesson_plan else None
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
        if figures and not grounded_bundle and not any(figure.label in response for figure in figures):
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
        pdf_references = grounded_references if grounded_bundle else complete_pdf_references(sources, response, pdf_references, figures=figures, include_primary=True)
        if grounded_bundle and not pdf_references and plan.action=='ask_question':
            # 已核验的检查题没有教材结论引文时，不强加编号，也不自动展开可能泄露答案的定义。
            textbook_sources=[]
        base_reference = pdf_supplement.reference if pdf_supplement else (pdf_references[0]["selection_ref"] if pdf_references else None)
        stored_reference = (base_reference | {"pdf_references": pdf_references,
            "textbook_sources": textbook_sources}) if base_reference else None
        if grounded_bundle and stored_reference:
            stored_reference['grounding_schema']='citation-grounding-v1'
        if task_context and task_context.relation_snapshot:
            snapshot = task_context.relation_snapshot
            relation_location = {name:snapshot.get(name) for name in
                ('artifact_id','revision','epoch','property','selected_pair','answer_scope')}
            if snapshot.get('closure'):
                relation_location['closure']={key:snapshot['closure'][key] for key in ('kind','step','epoch')}
            stored_reference = (stored_reference or {'pdf_references':pdf_references,
                'textbook_sources':textbook_sources}) | {'relation_context':relation_location}
        guided_visualization = None
        from visualization.service import rollout_settings,VisualizationService
        if (PSYCHOLOGY and os.getenv('VISUALIZATION_ON_DEMAND','0')=='1') or (not PSYCHOLOGY and rollout_settings()[0]!='off' and VisualizationService().enabled(student_id)):
            try:
                from visualization.on_demand import build_guide
                guided_visualization=build_guide(self.llm,message,response,sources,execution,
                    student_id=student_id,turn_id=event_id,references=pdf_references,progress=progress,
                    deferred=visualization_jobs)
            except (ValueError,OSError,KeyError,RuntimeError):
                # 教材映射失效时保留已核对的文字，不凭空绘制图。
                guided_visualization=None
        if guided_visualization:
            stored_reference=(stored_reference or {'pdf_references':pdf_references,
                'textbook_sources':textbook_sources}) | {'guided_visualization':guided_visualization}
        memory_commit = self.memory.commit_learning_turn(
            student_id=student_id, point=point, event_id=event_id, expected_token=expected_token, expected_epoch=expected_epoch,
            message=message, reply=response, state=state, lesson_plan=None if direct_answer else lesson_plan, decision=decision,
            evidence=all_evidence, hypotheses=hypotheses, strategy=plan.strategy, success=success,
            teaching_context={"strategy": plan.strategy, "difficulty": move.difficulty, "hint_level": move.hint_level,
                "feedback_mode": answer_feedback.get("mode"),
                "answer_diagnosis": answer_diagnosis.model_dump() if answer_diagnosis else None,
                "support_diagnosis": answer_feedback.get("support_diagnosis")},
            instructional_move=move.instructional_move, figure_ids=[figure.id for figure in figures],
            selection_ref=stored_reference, task_guard=task_guard, misconception_updates=getattr(update, "misconception_updates", []), tutor_error=(error.reason or "检测到教学错误") if rolled_back else None,
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
            "response_path": "direct_answer" if direct_answer else "tutoring",
            "memory_commit": memory_commit,
            "conversation_id": memory_commit.get("conversation_id"),
            "memory_summary": memory_context.get("summary", ""),
            "memory_retrieval": memory_context.get("retrieval", {}),
            "student_state": state.model_dump(),
            "teaching_plan": plan.model_dump(),
            "task_execution": execution.public(),
            "answer_diagnosis": answer_diagnosis.model_dump() if answer_diagnosis and not execution.hint_only else None,
            "teaching_feedback": {key: answer_feedback[key] for key in ("mode", "hint_level", "verification") if key in answer_feedback},
            "question_spec": question_spec.model_dump() if question_spec else None,
            "quality": quality.model_dump() if quality else None,
            "evidence_check": evidence_check.model_dump(),
            "proof_evidence": proof_evidence.public() if proof_evidence else None,
            "pdf_evidence": pdf_supplement.public() if pdf_supplement else None,
            "pdf_references": pdf_references,
            "guided_visualization": guided_visualization,
            "pdf_image_refs": pdf_supplement.reference["image_refs"] if pdf_supplement else [],
            "selection_ref": base_reference,
            "regenerated": attempts - 1,
            "lesson_progress": lesson_plan.progress() if lesson_plan else None,
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
    def _retrieval_query(message, point, routing, history=None):
        if getattr(routing, 'needs_context', False) and history:
            context='\n'.join(str(item.get('content',''))[:400] for item in history[-4:])
            return point+' '+message+'\n最近对话（仅用于检索定位，不作为教材证据）：\n'+context
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
