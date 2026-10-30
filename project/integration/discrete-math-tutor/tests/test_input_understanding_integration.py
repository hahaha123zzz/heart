"""真实宿主循环消费统一理解，替身模型只提供受控正文。"""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from agents.adaptive_tutoring import TeachingTurn, snapshot_from_recent
from agents.agent_loop_service import run_agent_loop_turn, _target_from_context
from agents.input_understanding.adapters import preserve_activity, preference_proposal,legacy_routing,resume_understanding
from agents.input_understanding.service import understand
from agents.q3_navigation import LearningTarget, StubLearningNavigator, SourceRef
from models.chat_request import ChatRequest
from models.task_context import TaskContext, TaskObject
from tests.test_adaptive_tutoring import prior
from tests.test_q3_q4_integration import ScriptedLLM, FakeMemory
from llm.client import ChatToolResult


def bound(message, old=None):
    request=ChatRequest(student_id='s',session_id='x',request_id='r',message=message)
    context=TaskContext(student_id='s',session_id='x',message=message,knowledge_point='自变量',
                        tutoring=deepcopy(old or prior(pending=True)),input_mode='active')
    context.input_understanding=understand(context,request)
    return context,request


class InputIntegrationTests(unittest.TestCase):
    def test_reading_chapter_does_not_erase_pending_and_target(self):
        old=prior(pending=True)|{'chapter_id':2,'topic':'自变量','target_id':'kp:自变量'}
        context=TaskContext(student_id='s',session_id='x',message='回到原题',knowledge_point='第一章',
            input_mode='active',objects=[TaskObject(id='section:1:1',kind='section',title='第一章',chapter_id=1,section_id=1)])
        recent=[dict(student_id='s',session_id='x',epoch=0,knowledge_point='自变量',
            context={'tutoring':old},result={'answer_status':'answered','memory_commit':{'status':'committed'}})]
        memory=Mock();memory.memory_epoch.return_value=0
        with patch.dict('os.environ',{'INPUT_UNDERSTANDING_MODE':'active'}):
            context.tutoring=snapshot_from_recent(recent,context,memory,'s')
        request=ChatRequest(student_id='s',session_id='x',message=context.message)
        preserve_activity(context,request)
        self.assertEqual(context.knowledge_point,'自变量')
        self.assertEqual(_target_from_context(context).chapter_id,2)
        self.assertIsNotNone(context.tutoring['progress']['pending_question'])

    def test_compound_explanation_runs_loop_then_appends_same_question(self):
        context,request=bound('先解释“操作性定义”这个词，再回到原来的题，不要替我作答。')
        model=ScriptedLLM([ChatToolResult(text='操作性定义规定具体如何操纵或测量。',finish_reason='stop')])
        original=context.tutoring['progress']['pending_question']
        navigator=StubLearningNavigator(target=LearningTarget('kp:自变量','自变量'),sources=[
            SourceRef('e','d','操作性定义规定具体操作。',version='v')])
        with patch.dict('os.environ',{'ADAPTIVE_TUTORING_ENABLED':'1'}), \
             patch('agents.tools.first_wave_runtime.bind_resources',return_value=(None,())), \
             patch('agents.adaptive_tutoring.verified_sources',side_effect=lambda rows:rows):
            result=run_agent_loop_turn(orchestrator=SimpleNamespace(llm=model,memory=FakeMemory(),quality_checker=None),
                request=request,context=context,navigator=navigator,publish_gate=lambda *_:(True,''))
        self.assertEqual(result['answer_status'],'answered')
        self.assertIn('操作性定义',result['reply'])
        self.assertTrue(result['reply'].endswith(original['prompt']))
        self.assertEqual(result['input_resume_question_id'],original['question_id'])
        self.assertEqual(context.tutoring['progress']['pending_question']['question_id'],original['question_id'])
        self.assertTrue(model.calls)
        self.assertIn('先完成首项解释',model.calls[0]['messages'][0]['content'])

    def test_negation_and_option_question_do_not_call_assessment_model(self):
        for message in ('我不选 B','为什么 B 不对？'):
            context,request=bound(message);model=Mock()
            turn=TeachingTurn(context,request,model,validate_sources=lambda rows:rows)
            self.assertIsNotNone(turn.progress.pending_question)
            model.chat_json.assert_not_called()
            self.assertIsNone(turn.state['assessment'])

    def test_do_not_return_cannot_trigger_restore(self):
        context,request=bound('不要回到原题，先解释操作性定义。')
        turn=TeachingTurn(context,request,Mock(),validate_sources=lambda rows:rows)
        self.assertIsNone(turn.restore_reply())

    def test_turn_only_no_questions_does_not_disable_future_checks(self):
        context,request=bound('先解释操作性定义，不要出题。')
        turn=TeachingTurn(context,request,Mock(),validate_sources=lambda rows:rows)
        self.assertFalse(turn.state['allow_check'])
        self.assertTrue(turn.state['requested_allow_check'])
        self.assertIsNotNone(turn.progress.pending_question)

    def test_invalid_source_cannot_silently_restore_a_question(self):
        context,request=bound('回到原题')
        model=Mock()
        with patch.dict('os.environ',{'ADAPTIVE_TUTORING_ENABLED':'1'}), \
             patch('agents.tools.first_wave_runtime.bind_resources',return_value=(None,())), \
             patch('agents.adaptive_tutoring.verified_sources',return_value=[]):
            result=run_agent_loop_turn(orchestrator=SimpleNamespace(llm=model,memory=FakeMemory(),quality_checker=None),
                request=request,context=context,
                navigator=StubLearningNavigator(target=LearningTarget('kp:自变量','自变量')))
        self.assertEqual(result['answer_status'],'reference_stale')
        self.assertFalse(result['step_advanced'])
        model.chat_with_tools.assert_not_called()

    def test_preference_proposal_does_not_write_and_shadow_is_inert(self):
        context,request=bound('以后详细一点，但这一题直接给答案。')
        proposal=preference_proposal(context)
        self.assertEqual(proposal['values'],{'answer_length':1.})
        self.assertEqual(proposal['default_scope'],'long')
        context.input_mode='shadow'
        self.assertIsNone(preference_proposal(context))

    def test_legacy_route_consumes_clear_single_task_without_reclassifying(self):
        context,request=bound('什么是自变量？',old={})
        result=legacy_routing(context)
        self.assertEqual(result.learning_intents,['explain'])
        self.assertEqual(result.rewritten_query,request.message)
        context.input_mode='shadow'
        self.assertIsNone(legacy_routing(context))

    def test_ask_user_resume_preserves_actual_reply_and_original_task(self):
        context,request=bound('先解释自变量，不要出题。')
        previous={'context':{'input_understanding':context.input_understanding.model_dump(),
                             'loop_state':{'pending_tool_call_id':'call1'}}}
        reply=request.model_copy(update={'message':'第二个','request_id':'reply'})
        restored=resume_understanding(previous,reply,'reply')
        self.assertEqual(restored.envelope.raw_text,request.message)
        self.assertEqual(restored.reply_envelope.raw_text,'第二个')
        self.assertEqual(restored.tasks,context.input_understanding.tasks)


if __name__=='__main__':unittest.main()
