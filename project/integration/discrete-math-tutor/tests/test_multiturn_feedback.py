"""教材诊断、最终反馈策略及能力投影边界；不调用外部模型。"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from agents.evidence_extractor import EvidenceExtractor, AnswerDiagnosis, AnalysisResult
from agents.learning_feedback import adapt_answer_feedback, is_stuck, is_self_report_understood, HINT_FEEDBACK_RULES
from agents.strategy_router import InstructionalMove
from agents.teaching_planner import TeachingPlan
from agents.task_execution import TaskExecution
from models.task_understanding import TaskUnderstanding
from models.student_state import StudentState
from models.evidence import Evidence
from tests import test_answer_flow as fixtures


class DiagnosisTests(unittest.TestCase):
    def check(self, diagnosis, assess=True):
        llm=SimpleNamespace(chat_json=Mock(return_value={"answer_diagnosis":diagnosis}))
        result=EvidenceExtractor(llm).analyze("我判断每人接受所有水平",StudentState(),[],
            textbook_evidence=[{"id":"1","text":"被试间设计中每名被试只接受一种处理水平"}],assess_answer=assess)
        llm.chat_json.assert_called_once()
        return result

    def test_diagnosis_requires_current_quote_and_actual_textbook_ids(self):
        valid={"verdict":"incorrect","error_type":"concept_confusion","source_quote":"每人接受所有水平","source_ids":["1"],"reason":"混淆了两种设计"}
        self.assertEqual(self.check(valid).answer_diagnosis.verdict,"incorrect")
        for bad in [dict(valid,source_quote="上一轮的原话"),dict(valid,source_ids=["9"]),dict(valid,source_ids=[]),
                    dict(valid,verdict="correct"),dict(valid,error_type="none"),dict(valid,extra="越界字段")]:
            with self.subTest(bad=bad):self.assertEqual(self.check(bad).answer_diagnosis.verdict,"unclear")
        self.assertIsNone(self.check(valid,assess=False).answer_diagnosis)

    def test_understood_signal_requires_a_standalone_student_report(self):
        for text in ["我明白了。", "懂了，谢谢", "我已经理解了"]:
            self.assertTrue(is_self_report_understood(text),text)
        for text in ["如果被试理解了实验目的，为什么产生要求特征？", "我明白了，先不做题，请解释原因", "被试明白了实验目的"]:
            self.assertFalse(is_self_report_understood(text),text)

    def test_missing_diagnosis_never_becomes_correct(self):
        self.assertEqual(self.check({}).answer_diagnosis.verdict,"unclear")

    def test_experiment_description_is_not_self_reported_confusion(self):
        for text in ["被试不知道分组", "我认为被试不知道接受什么处理", "研究者不会干预被试"]:
            self.assertFalse(is_stuck(text),text)
        for text in ["不知道", "我不知道怎么分组", "我还是看不懂", "还是不会", "完全没思路"]:
            self.assertTrue(is_stuck(text),text)


class FeedbackPolicyTests(unittest.TestCase):
    def adapt(self, verdict="incorrect", intents=None, previous=None, stuck=0, emotion="neutral", message="我判断每人都接受所有水平"):
        diagnosis=AnswerDiagnosis(verdict=verdict,error_type="none" if verdict=="correct" else "concept_confusion",source_quote="每人",source_ids=["1"],reason="核对定义") if verdict else None
        plan=TeachingPlan(goal="实验设计",strategy="worked_example",action="explain",difficulty="hard")
        move=InstructionalMove()
        result=adapt_answer_feedback(plan,move,execution=TaskExecution(learning_intents=intents or ["check_answer"]),
            diagnosis=diagnosis,previous_event=previous,
            stuck_count=stuck,state=StudentState(emotion=emotion),student_input=message)
        return plan,move,result

    def prior(self,level=1):
        return {"payload":{"instructional_move":"guided_revision","teaching_context":{"feedback_mode":"targeted_hint","hint_level":level,
            "answer_diagnosis":{"verdict":"incorrect","error_type":"concept_confusion"}}}}

    def test_wrong_attempt_then_repeated_error_changes_support(self):
        plan,move,context=self.adapt();self.assertEqual((plan.action,move.hint_level,context["mode"]),("give_hint",1,"targeted_hint"))
        plan,move,context=self.adapt(previous=self.prior());self.assertEqual((plan.action,move.hint_level,context["mode"]),("give_example",2,"worked_example"))

    def test_only_hint_escalates_without_switching_to_complete_answer(self):
        plan,move,context=self.adapt(intents=["hint"],previous=self.prior(2),stuck=3)
        self.assertEqual((plan.action,plan.hint_level,move.action),("give_hint",3,"give_hint"))
        self.assertIn("不自动转完整讲解",context["instructions"])

    def test_support_target_survives_hint_turn_without_new_diagnosis(self):
        prior=self.prior()
        plan,move,feedback=self.adapt(verdict=None,intents=["hint"],previous=prior,stuck=1)
        self.assertEqual(feedback["support_diagnosis"],prior["payload"]["teaching_context"]["answer_diagnosis"])
        next_event={"payload":{"teaching_context":{"feedback_mode":"hint_only","hint_level":2,"support_diagnosis":feedback["support_diagnosis"]}}}
        self.assertEqual(self.adapt(verdict=None,intents=["hint"],previous=next_event,stuck=2)[0].hint_level,3)
        # 同知识点中一个自足的新提示问题不继承旧任务的提示级别。
        self.assertEqual(self.adapt(verdict=None,intents=["hint"],previous=next_event,stuck=0)[0].hint_level,1)

    def test_explicit_explanation_wins_over_stuck(self):
        plan,move,context=self.adapt(verdict=None,intents=["explain"],stuck=3,message="我还是不懂，请完整解释")
        self.assertEqual((plan.action,context["mode"]),("explain","explain_feedback"))

    def test_unclear_correct_and_self_report_have_distinct_followups(self):
        self.assertEqual(self.adapt(verdict="unclear",message="请完整解释")[2]["mode"],"clarify_attempt")
        self.assertEqual(self.adapt(verdict="correct")[2]["mode"],"confirm_and_reflect")
        self.assertEqual(self.adapt(verdict=None,message="我明白了")[2]["mode"],"check_self_report")

    def test_frustration_lowers_current_challenge(self):
        plan,move,context=self.adapt(emotion="frustrated")
        self.assertEqual((plan.difficulty,move.difficulty,context["mode"]),("easy","easy","supportive_hint"))


class FeedbackIntegrationTests(unittest.TestCase):
    def run_attempt(self,verdict="incorrect",previous=None,intents=None, inferred_preference=None,move="attempt"):
        fixture=fixtures.AnswerFlowTests();tutor=fixture.tutor(intents or ["check_answer"])
        message="我判断每名被试接受所有处理水平"
        tutor.conversation_router.route.return_value=TaskUnderstanding(student_move=move,confidence=.98,learning_intents=intents or ["check_answer"])
        tutor.memory.get_previous_event.return_value=previous
        if inferred_preference:
            tutor.state_analyzer.build.return_value.interaction_preference=inferred_preference
            tutor.state_updater.update.return_value.state=tutor.memory.get_state.return_value.model_copy(update={"interaction_preference":inferred_preference})
        tutor.evidence_extractor.analyze.return_value=AnalysisResult(
            evidence=[Evidence(evidence_type="misconception",content=message,source_quote=message,confidence=.9)],
            answer_diagnosis=AnswerDiagnosis(verdict=verdict,error_type="concept_confusion",source_quote=message,source_ids=["1"]))
        result=fixture.run_turn(tutor,message)
        return tutor,result

    def test_explicit_explanation_after_understanding_never_creates_a_quiz(self):
        f=fixtures.AnswerFlowTests();tutor=f.tutor(["explain"])
        result=f.run_turn(tutor,"我明白了双盲定义，先不做题，请解释实验者偏差。")
        self.assertEqual(result["teaching_plan"]["action"],"explain")
        tutor.question_designer.design.assert_not_called()

    def test_short_confirmation_checks_a_grounded_teaching_task(self):
        f=fixtures.AnswerFlowTests();tutor=f.tutor(["explain"])
        tutor.conversation_router.route.return_value=TaskUnderstanding(student_move="acknowledgement",learning_intents=[],confidence=.98)
        f.run_turn(tutor,"我明白了。")
        self.assertIn("设计一个简短理解检查",tutor.context_sufficiency.check.call_args.args[0])
        self.assertEqual(tutor.question_designer.design.call_count,1)
        self.assertIsNone(tutor.question_designer.design.call_args.args[2])
        self.assertIn("previous_reply",tutor.question_designer.design.call_args.kwargs["teaching_context"])

    def test_verdict_only_does_not_turn_into_hint_or_question(self):
        from agents.task_execution import build_execution
        routing=TaskUnderstanding(student_move="attempt",confidence=.98,learning_intents=["check_answer"],answer_constraints=["no_full_answer"])
        execution=build_execution("只判断我这句话对不对，不要再问我理由：双盲要求两方不知处理。",routing)
        guessed=build_execution("只让被试不知道处理，就可以称为双盲。请看看我的判断。",routing.model_copy(update={"answer_constraints":["verdict_only"]}))
        self.assertFalse(guessed.verdict_only)
        self.assertTrue(execution.verdict_only)
        self.assertFalse(execution.hint_only)
        plan=TeachingPlan(goal="双盲",strategy="worked_example",action="explain",difficulty="easy")
        feedback=adapt_answer_feedback(plan,InstructionalMove(),execution=execution,diagnosis=AnswerDiagnosis(verdict="correct",error_type="none"),previous_event=None,stuck_count=0,state=StudentState(),student_input="只判断对错")
        self.assertEqual(feedback["mode"],"verdict_only")
        self.assertEqual(plan.action,"explain")
        self.assertNotIn("本轮提示级别",feedback["instructions"])

    def test_no_questions_still_allows_complete_requested_feedback(self):
        plan=TeachingPlan(goal="双盲",strategy="worked_example",action="explain",difficulty="easy")
        execution=TaskExecution(learning_intents=["check_answer","explain"],answer_constraints=["no_questions"])
        feedback=adapt_answer_feedback(plan,InstructionalMove(),execution=execution,diagnosis=AnswerDiagnosis(verdict="incorrect",error_type="missing_condition"),previous_event=None,stuck_count=0,state=StudentState(),student_input="我的判断不够吗，请完整解释，不要出题")
        self.assertEqual(feedback["mode"],"explain_feedback")
        self.assertEqual(plan.action,"explain")
        self.assertIn("完整回应",feedback["instructions"])

    def test_worked_example_retry_invitation_is_not_silently_removed(self):
        from agents.response_generator import ResponseGenerator
        from agents.quality_checker import QualityChecker
        answer="辅助例子（非原书例题）。"+"比较两组条件。"*29+"请用一句话重述你原来的判断。"
        llm=SimpleNamespace(mock=True,chat=Mock(return_value=answer),chat_json=Mock(return_value={"passed":True,"issues":[]}))
        plan=TeachingPlan(goal="实验设计",strategy="worked_example",action="give_example",difficulty="easy")
        feedback={"mode":"worked_example"}
        result=ResponseGenerator(llm).generate(StudentState(),plan,"换种方法",[],answer_feedback=feedback)
        self.assertEqual(result,answer)
        self.assertTrue(QualityChecker(llm).check(result,StudentState(),plan,"换种方法",context={"answer_feedback":feedback}).passed)

    def test_one_feedback_contract_reaches_generator_checker_and_event(self):
        tutor,result=self.run_attempt()
        self.assertEqual(result["teaching_feedback"]["mode"],"targeted_hint")
        feedback=tutor.quality_checker.check.call_args.args[5]["answer_feedback"]
        self.assertEqual(feedback["mode"],"targeted_hint")
        self.assertIn("targeted_hint",tutor.response_generator.generate.call_args.args[5])
        context=tutor.memory.commit_learning_turn.call_args.kwargs["teaching_context"]
        self.assertEqual(context["feedback_mode"],"targeted_hint")
        self.assertEqual(context["answer_diagnosis"]["source_quote"],"我判断每名被试接受所有处理水平")
        self.assertTrue(tutor.memory.commit_learning_turn.call_args.kwargs["decision"].eligible)
        tutor.question_designer.design.assert_not_called()

    def test_assisted_statement_retry_is_rechecked_without_mastery_credit(self):
        tutor,result=self.run_attempt(previous=FeedbackPolicyTests().prior(),intents=["explain"],move="statement")
        self.assertTrue(tutor.evidence_extractor.analyze.call_args.kwargs["assess_answer"])
        self.assertEqual(result["teaching_feedback"]["mode"],"worked_example")
        self.assertFalse(tutor.memory.commit_learning_turn.call_args.kwargs["decision"].eligible)

    def test_unknown_and_assisted_retry_do_not_measure_mastery(self):
        for verdict,previous in [("unclear",None),("incorrect",FeedbackPolicyTests().prior()),
            ("correct", {"payload":{"instructional_move":"direct_correction", "teaching_context":{"feedback_mode":"explain_feedback"}}}),
            ("correct", {"payload":{"instructional_move":"self_explanation", "teaching_context":{"feedback_mode":"confirm_and_reflect"}}}),
            ("correct", {"payload":{"instructional_move":"direct_correction", "teaching_context":{"feedback_mode":"verdict_only"}}})]:
            with self.subTest(verdict=verdict):
                tutor,result=self.run_attempt(verdict,previous)
                self.assertFalse(tutor.memory.commit_learning_turn.call_args.kwargs["decision"].eligible)
                self.assertEqual(result["student_state"]["mastery"],.6)

    def test_quoted_student_error_is_not_an_asserted_textbook_fact(self):
        from agents.quality_checker import QualityChecker
        llm=SimpleNamespace(mock=True,chat_json=Mock(return_value={"passed":True,"issues":[],"suggestions":""}))
        checker=QualityChecker(llm)
        plan=TeachingPlan(goal="被试间设计",strategy="scaffolding",action="give_hint",difficulty="easy")
        quote='你的判断方向反了：你描述的是“每名被试接受所有水平”。请核对人数与水平的关系。[1]'
        excerpt='[1] 被试间设计每名被试只接受一种处理水平。'
        self.assertTrue(checker.check(quote,StudentState(),plan,'被试间设计',textbook_excerpts=excerpt).passed)
        self.assertFalse(checker.check('被试间设计每名被试接受所有处理水平。[1]',StudentState(),plan,'被试间设计',textbook_excerpts=excerpt).passed)
        quoted_question='你的判断不正确。请只核对原句里“每名被试都接受所有处理水平”这一处：这更像哪种设计？'
        self.assertTrue(checker.check(quoted_question,StudentState(),plan,'检查我的判断',textbook_excerpts=excerpt).passed)

    def test_inferred_state_does_not_replace_saved_style(self):
        tutor,result=self.run_attempt(inferred_preference="example_first")
        self.assertEqual(result["student_state"]["interaction_preference"],"step_by_step")
        self.assertEqual(tutor.teaching_planner.plan.call_args.args[0].interaction_preference,"step_by_step")

    def test_hint_contract_reaches_both_system_prompts(self):
        from agents.response_generator import ResponseGenerator
        from agents.quality_checker import QualityChecker
        llm=SimpleNamespace(mock=True,chat=Mock(return_value="请核对原句的对象。"),chat_json=Mock(return_value={"passed":True,"issues":[]}))
        plan=TeachingPlan(goal="实验设计",strategy="scaffolding",action="give_hint",difficulty="easy")
        ResponseGenerator(llm).generate(StudentState(),plan,"检查我的判断",[])
        self.assertIn("不得先完整引用正确的定义",llm.chat.call_args.args[0][0]["content"])
        QualityChecker(llm).check("请核对原句的对象。",StudentState(),plan,"检查我的判断",context={"answer_feedback":{"mode":"targeted_hint"}})
        self.assertIn("必须拒绝",llm.chat_json.call_args.args[0][0]["content"])

    def test_distress_and_self_report_tone_constraints_reach_models(self):
        from agents.response_generator import ResponseGenerator
        from agents.quality_checker import QualityChecker
        llm=SimpleNamespace(mock=True,chat=Mock(return_value="我们慢慢拆开看。"),chat_json=Mock(return_value={"passed":True,"issues":[]}))
        plan=TeachingPlan(goal="双盲",strategy="error_based_learning",action="explain",difficulty="easy")
        frustrated={"mode":"explain_feedback","support_required":True,"instructions":"先回应困难再解释"}
        ResponseGenerator(llm).generate(StudentState(),plan,"我很烦，请解释",[],answer_feedback=frustrated)
        self.assertIn("不要训斥、淡化情绪",llm.chat.call_args.args[0][0]["content"])
        checker=QualityChecker(llm)
        bad="先别急着说，‘明白了’不算掌握证据。"
        context={"answer_feedback":{"mode":"check_self_report"}}
        self.assertTrue(any("不训诫" in issue for issue in checker.check(bad,StudentState(),plan,"我明白了",context=context).issues))
        self.assertFalse(checker.check("这不能当作掌握证据，所以再练一个小检查。",StudentState(),plan,"我明白了",context=context).passed)
        self.assertEqual(checker.check("太好了，我们用一道小题确认一下。",StudentState(),plan,"我明白了",context=context).issues,[])

    def test_only_hint_hides_answer_diagnosis_from_response(self):
        tutor,result=self.run_attempt(intents=["hint","check_answer"])
        self.assertIsNone(result["answer_diagnosis"])
        self.assertEqual(result["instructional_move"]["action"],"give_hint")


if __name__=="__main__":unittest.main()
