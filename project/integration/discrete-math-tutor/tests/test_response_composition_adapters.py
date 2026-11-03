"""第二批：投影已确认任务、真实入口和保存边界，不让组合层重出题或评分。"""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from agents.response_composition import ResponseComposer, plan_response
from agents.response_composition_adapters import response_plan, published_snapshot, snapshot_kind
from agents.task_execution import TaskExecution
from agents.teaching_planner import TeachingPlan
from models.input_understanding import GroundedTurn
from models.evidence_execution import EvidencePackage
from models.learning_response import GeneratedBlock, PublishedBlock
from models.task_context import TaskContext
from models.chat_request import ChatRequest
from agents.agent_loop_service import run_agent_loop_turn
from agents.q3_navigation import LearningTarget, StubLearningNavigator
from llm.client import ChatToolResult
from tests.test_evidence_execution import package_data
from tests.test_adaptive_tutoring import prior
from tests.test_learning_cards import STEPS
from tests.test_q3_q4_integration import ScriptedLLM, FakeMemory, tool_round
from tests import test_clarification_tasks as database_fixtures
from tests import test_task_resource_execution as resource_fixtures


def context(tasks, **kwargs):
    text = '比较两个变量，然后解释原因'
    turn = GroundedTurn.model_validate(dict(envelope=dict(request_id='r',raw_text=text,
        normalized_text=text,source_positions=list(range(len(text)))),
        context=dict(student_id='s',session_id='x',course_id='book'), tasks=tasks, **kwargs))
    return TaskContext(student_id='s',session_id='x',message=text,knowledge_point='变量',
        input_mode='active',input_understanding=turn)


class CompositionAdapterTests(unittest.TestCase):
    def test_original_teaching_strategy_survives_legacy_alias(self):
        for original, legacy, expected in (
            ('summary', 'explain', 'recap'),
            ('counterexample', 'worked_example', 'counterexample'),
        ):
            with self.subTest(strategy=original):
                teaching = SimpleNamespace(plan=SimpleNamespace(primary_strategy=original),
                                           strategy=legacy, limit_disclosure=False)
                plan = response_plan('test-target', teaching=teaching)
                self.assertEqual(plan.blocks[0].semantic_type, expected)

    def test_transfer_comparison_and_scaffolding_keep_distinct_plans(self):
        for strategy, expected in (
            ('transfer', ['explanation', 'worked_example']),
            ('conceptual_comparison', ['direct_answer', 'comparison']),
            ('scaffolding', ['explanation', 'procedure']),
        ):
            with self.subTest(strategy=strategy):
                teaching = SimpleNamespace(plan=SimpleNamespace(primary_strategy=strategy),
                                           strategy='explain', limit_disclosure=False)
                plan = response_plan('test-target', teaching=teaching)
                self.assertEqual([block.semantic_type for block in plan.blocks], expected)

    def test_composer_explains_purpose_of_different_blocks(self):
        prompt = ResponseComposer(plan_response(target_id='t', strategy='counterexample')).instructions()
        self.assertIn('counterexample说明违反的条件', prompt)
        self.assertIn('不必机械套用固定结构', prompt)

    def test_active_transfer_frame_retains_task_identity_and_hint_limit(self):
        ctx = context([dict(task_frame_id='t1', action='explain_content')])
        teaching = SimpleNamespace(plan=SimpleNamespace(primary_strategy='transfer'),
                                   strategy='transfer', limit_disclosure=False)
        plan = response_plan('t', context=ctx, teaching=teaching)
        self.assertEqual([b.semantic_type for b in plan.blocks], ['explanation', 'worked_example'])
        self.assertTrue(all(b.task_frame_ids == ['t1'] for b in plan.blocks))
        ctx.input_understanding.tasks[0].constraints = ['no_full_answer']
        self.assertEqual([b.semantic_type for b in response_plan('t', context=ctx, teaching=teaching).blocks], ['hint'])

    def test_active_task_order_dependencies_and_strategy_do_not_reclassify_input(self):
        ctx = context([dict(task_frame_id='t1',action='compare_content'),
            dict(task_frame_id='t2',action='explain_content',depends_on=['t1'])])
        plan = response_plan('target',context=ctx,teaching=SimpleNamespace(strategy='explain',limit_disclosure=False))
        self.assertEqual([b.semantic_type for b in plan.blocks],['comparison','explanation'])
        self.assertEqual(plan.blocks[1].depends_on,['b1'])
        self.assertEqual(plan.blocks[1].task_frame_ids,['t2'])
        ctx.input_mode='shadow'
        self.assertEqual(len(response_plan('target',context=ctx).blocks),1)

    def test_disclosure_limit_dominates_comparison_and_persistent_proposal_is_not_active(self):
        ctx = context([dict(task_frame_id='t1',action='compare_content',constraints=['no_full_answer'])])
        self.assertEqual([b.semantic_type for b in response_plan('target',context=ctx).blocks],['hint'])
        ctx.input_understanding.tasks[0].constraints=[]
        from models.input_understanding import ScopedDirective
        ctx.input_understanding.directives=[ScopedDirective(scope='persistent',key='hint_only',value=True,
            quote='以后只提示',requires_confirmation=True)]
        self.assertEqual(response_plan('target',context=ctx).blocks[0].semantic_type,'comparison')
        self.assertEqual(response_plan('target',context=ctx,
            teaching=SimpleNamespace(strategy='hint',limit_disclosure=False)).blocks[0].semantic_type,'hint')

    def test_legacy_teaching_plan_and_execution_use_same_compiler(self):
        plan = TeachingPlan(goal='解释变量',strategy='conceptual_comparison',action='explain',difficulty='easy')
        self.assertEqual(response_plan('t',teaching_plan=plan).blocks[-1].semantic_type,'comparison')
        plan.action='give_hint'
        self.assertEqual(response_plan('t',teaching_plan=plan).blocks[0].semantic_type,'hint')
        self.assertEqual(snapshot_kind(teaching_plan=plan),'hint')
        self.assertEqual(response_plan('t',execution=TaskExecution(learning_intents=['summary'])).blocks[0].semantic_type,'recap')
        ctx=context([dict(task_frame_id='t1',action='explain_content')])
        prerequisite=response_plan('t',context=ctx,teaching=SimpleNamespace(strategy='prerequisite',limit_disclosure=False))
        self.assertEqual([b.semantic_type for b in prerequisite.blocks],['definition','explanation'])
        self.assertEqual(prerequisite.blocks[1].task_frame_ids,['t1'])

    def test_complete_evidence_requires_exact_task_context_and_source_bytes(self):
        package = EvidencePackage(**package_data())
        with self.assertRaisesRegex(ValueError,'context_mismatch'):
            ResponseComposer(plan_response(target_id='t'),evidence_package=package,
                expected_context=package.request.context.model_copy(update={'session_id':'other'}))
        composer = ResponseComposer(plan_response(target_id='t'),evidence_package=package,
            expected_context=package.request.context)
        raw = json.dumps({'blocks':[{'block_id':'b1','claims':[dict(text='测试原文',source_ids=['source'],provenance='quotation')]}]})
        sources = [s.to_dict() for s in package.sources]
        self.assertIn('测试原文',composer.accept(raw,sources))
        forged=deepcopy(sources);forged[0]['image_refs']=[{'model_saw_pixels':True}]
        with self.assertRaisesRegex(ValueError,'source_mismatch'):
            composer.instructions(forged)
        sources[0]['text']='替换后的原文'
        with self.assertRaisesRegex(ValueError,'source_mismatch'):
            composer.accept(raw,sources)
        data=package_data();data['status']='partial'
        data['coverage'][0]={'requirement_id':'iv','status':'missing','reason':'缺失'}
        with self.assertRaisesRegex(ValueError,'evidence_incomplete'):
            ResponseComposer(plan_response(target_id='t'),evidence_package=EvidencePackage(**data),
                expected_context=package.request.context)

    @patch.dict('os.environ',{'RESPONSE_COMPOSITION_ENABLED':'1'})
    def test_snapshot_is_same_body_no_generated_claim_or_private_question_key(self):
        reply='先看操纵条件[1]。\n\n谁是自变量？'
        snapshot=published_snapshot(reply=reply,response_id='r',target_id='t',semantic_type='check_question',authority_ref='q1')
        self.assertEqual(snapshot['reply'],reply)
        self.assertEqual(snapshot['blocks'][0]['rendered_text'],reply)
        self.assertEqual(snapshot['blocks'][0]['claims'],[])
        self.assertEqual(snapshot['blocks'][0]['authority_ref'],'q1')
        self.assertEqual(snapshot['blocks'][0]['content_origin'],'host_snapshot')
        spaced=published_snapshot(reply='  保留原有空白\n',response_id='space',target_id='t')
        self.assertEqual(spaced['reply'],'  保留原有空白\n')
        self.assertEqual(spaced['blocks'][0]['rendered_text'],spaced['reply'])
        with self.assertRaises(ValidationError):
            GeneratedBlock(block_id='b1',claims=[],content_origin='host_snapshot',authority_ref='q1')
        with self.assertRaises(ValidationError):
            PublishedBlock(block_id='b1',semantic_type='feedback',rendered_text='错误',content_origin='host_snapshot')
        with patch.dict('os.environ',{'RESPONSE_COMPOSITION_ENABLED':'0'}):
            self.assertIsNone(published_snapshot(reply=reply,response_id='r',target_id='t'))


@patch.dict('os.environ',{'RESPONSE_COMPOSITION_ENABLED':'1','ADAPTIVE_TUTORING_ENABLED':'1','Q5_LEARNING_ENABLED':'0'})
class CompositionHostTests(unittest.TestCase):
    def run_turn(self, message, model, old=None):
        memory=FakeMemory()
        ctx=TaskContext(student_id='s',session_id='x',message=message,knowledge_point='自变量',tutoring=deepcopy(old or {}))
        req=ChatRequest(student_id='s',session_id='x',request_id='c2',message=message)
        with patch('agents.tools.first_wave_runtime.bind_resources',return_value=(None,())), \
             patch('agents.adaptive_tutoring.verified_sources',side_effect=lambda rows:deepcopy(rows)):
            result=run_agent_loop_turn(orchestrator=SimpleNamespace(llm=model,memory=memory,quality_checker=None),
                request=req,context=ctx,navigator=StubLearningNavigator(target=LearningTarget('target','自变量')),
                publish_gate=lambda *_:(True,''))
        return result,memory,ctx

    def test_step_card_reuses_tool_result_one_model_call_and_same_saved_body(self):
        model=ScriptedLLM([tool_round('teaching_step',dict(strategy='explain',summary='先操纵再测量',
            card_kind='step_reveal',explanation_steps=STEPS))])
        result,memory,_=self.run_turn('直接解释变量，并分步展开',model)
        self.assertEqual(result['answer_status'],'answered')
        self.assertEqual(len(model.calls),1)
        self.assertEqual(result['learning_response']['reply'],result['reply'])
        self.assertEqual(result['learning_response']['blocks'][0]['semantic_type'],'procedure')
        self.assertEqual(memory.calls[0]['kwargs']['selection_ref']['learning_response'],result['learning_response'])
        self.assertEqual(result['learning_cards'][0]['kind'],'step_reveal')

    def test_pending_question_replays_without_model_or_rewriting_private_key(self):
        model=ScriptedLLM([])
        result,memory,ctx=self.run_turn('回到刚才的题',model,prior(pending=True))
        self.assertEqual(result['answer_status'],'answered')
        self.assertEqual(model.calls,[])
        snapshot=result['learning_response']
        self.assertEqual(snapshot['blocks'][0]['semantic_type'],'check_question')
        self.assertEqual(snapshot['blocks'][0]['authority_ref'],ctx.tutoring['progress']['pending_question']['question_id'])
        self.assertNotIn('PRIVATE-',json.dumps(snapshot))
        self.assertEqual(snapshot,memory.calls[0]['kwargs']['selection_ref']['learning_response'])

    def test_failed_final_gate_does_not_publish_or_save_snapshot(self):
        model=ScriptedLLM([tool_round('teaching_step',dict(strategy='explain',summary='总结',
            card_kind='step_reveal',explanation_steps=STEPS))])
        with patch('agents.agent_loop_service._publish_gate',return_value=lambda *_:(False,'拒绝')):
            # 用原服务验证失败；不构造已经通过核验的快照。
            memory=FakeMemory();req=ChatRequest(student_id='s',session_id='x',request_id='fail-c2',message='分步展开')
            with patch('agents.tools.first_wave_runtime.bind_resources',return_value=(None,())):
                result=run_agent_loop_turn(orchestrator=SimpleNamespace(llm=model,memory=memory,quality_checker=None),
                    request=req,context=TaskContext(student_id='s',session_id='x',message=req.message),
                    navigator=StubLearningNavigator(target=LearningTarget('t','变量')))
        self.assertNotEqual(result['answer_status'],'answered')
        self.assertNotIn('learning_response',result)
        self.assertEqual(memory.calls,[])


@patch.dict('os.environ',{'RESPONSE_COMPOSITION_ENABLED':'1','VISUALIZATION_ON_DEMAND':'0'})
class CompositionResourceTests(unittest.TestCase):
    setUp=database_fixtures.ClarificationTests.setUp
    tearDown=database_fixtures.ClarificationTests.tearDown
    pdf_tutor=resource_fixtures.TaskResourceExecutionTests.pdf_tutor
    pdf_run=resource_fixtures.TaskResourceExecutionTests.pdf_run

    def test_legacy_pdf_hint_keeps_crops_body_and_saved_composition(self):
        from agents.quality_checker import QualityResult
        tutor,ctx,resolved,selection=self.pdf_tutor(QualityResult(passed=True))
        ctx.request_id='legacy-selection-c2'
        with patch('knowledge.grounded_citations.settings',return_value=None):
            result=self.pdf_run(tutor,ctx,resolved,selection)
        self.assertEqual(result['learning_response']['blocks'][0]['semantic_type'],'hint')
        self.assertEqual(result['learning_response']['reply'],result['reply'])
        self.assertEqual(tutor.llm.chat.call_count,1)
        from database.models import PDFCitationRow
        with self.factory() as session:
            saved=session.get(PDFCitationRow,result['conversation_id'])
            self.assertEqual(saved.reference['learning_response'],result['learning_response'])

    def test_chat_exercise_fixture_persists_same_help_without_grading_and_wrong_session(self):
        import practice_api as practice
        from agents.exercise_task_tutor import explain_exercise
        from models.task_context import ExerciseTarget,TaskObject
        version='a'*64
        question={'id':'fixture-q','knowledge_point':'变量','parts':[{'id':'p1','label':'第一问'}]}
        target=f'exercise:fixture-q:p1:{version}'
        req=ChatRequest(student_id='s',session_id='exercise-tab',request_id='fixture-help',message='只给提示',
            exercise_target=ExerciseTarget(question_id='fixture-q',part_id='p1',version=version),exercise_help='hint')
        ctx=TaskContext(student_id='s',session_id=req.session_id,message=req.message,knowledge_point='变量',
            objects=[TaskObject(id=target,kind='exercise_part',title='第一问',chapter_id=2,section_id=1)])
        tutor=SimpleNamespace(memory=self.memory)
        with patch.object(practice,'catalog',return_value={'version':version,'by_id':{'fixture-q':question}}), \
             patch.object(practice,'ai_parts',return_value={'reply':'先找研究者操纵的条件。'}) as generate:
            result=explain_exercise(tutor,req,ctx,lambda *_:None,lambda:None)
        self.assertEqual(generate.call_count,1)
        self.assertEqual(result['learning_response']['blocks'][0]['semantic_type'],'hint')
        from sqlalchemy import select
        from database.models import ConversationRow,PDFCitationRow
        with self.factory() as session:
            conversation=session.scalar(select(ConversationRow).where(ConversationRow.role=='assistant'))
            self.assertEqual(conversation.session_id,'exercise-tab')
            saved=session.get(PDFCitationRow,conversation.id)
            self.assertEqual(saved.reference['learning_response'],result['learning_response'])
        self.assertEqual(self.memory.get_history('s',session_id='another-tab'),[])
        from database.models import ExerciseHelpRow,ExerciseSubmissionRow
        self.assertEqual(database_fixtures.ClarificationTests.count(self,ExerciseHelpRow),1)
        self.assertEqual(database_fixtures.ClarificationTests.count(self,ExerciseSubmissionRow),0)

    def test_practice_help_button_saves_same_snapshot_without_new_model(self):
        import sys
        import practice_api as practice
        from models.task_context import TaskObject
        version='a'*64
        q={'id':'fixture-q','knowledge_point':'变量','group_id':'fixture','number':1,
           'parts':[{'id':'p1','label':'第一问','type':'text'}]}
        ctx=TaskContext(student_id='s',message='只给这个小题的提示',knowledge_point='变量',
            objects=[TaskObject(id=f'exercise:fixture-q:p1:{version}',kind='exercise_part',
                title='第一问',chapter_id=2,section_id=1)])
        with patch.dict(sys.modules,{'main':SimpleNamespace(orchestrator=SimpleNamespace(memory=self.memory))}), \
             patch.object(practice,'student',return_value='s'), patch.object(practice,'check_version'), \
             patch.object(practice,'question',return_value=q), \
             patch('agents.task_context_builder.TaskContextBuilder.build',return_value=ctx), \
             patch.object(practice,'ai_parts',return_value={'reply':'先找操纵条件。'}) as generate:
            result=practice.help_question('fixture-q',practice.HelpRequest(student_id='s',version=version,part_id='p1',action='hint'))
        self.assertEqual(generate.call_count,1)
        from sqlalchemy import select
        from database.models import ExerciseHelpRow,PDFCitationRow,ConversationRow
        with self.factory() as session:
            help_row=session.scalar(select(ExerciseHelpRow))
            self.assertEqual(help_row.response['learning_response'],result['learning_response'])
            cid=session.scalar(select(ConversationRow.id).where(ConversationRow.role=='assistant'))
            self.assertEqual(session.get(PDFCitationRow,cid).reference['learning_response'],result['learning_response'])


class CompositionLegacyTests(unittest.TestCase):
    @patch.dict('os.environ',{'RESPONSE_COMPOSITION_ENABLED':'1'})
    def test_legacy_orchestrator_keeps_original_generation_and_commit(self):
        from tests.test_task_execution import TaskExecutionTests
        from models.task_understanding import TaskUnderstanding
        tutor,result,_=TaskExecutionTests().run_task(TaskUnderstanding(student_move='question',
            learning_intents=['hint','proof'],answer_constraints=['hint_only']))
        self.assertEqual(result['learning_response']['reply'],result['reply'])
        self.assertEqual(result['learning_response']['blocks'][0]['semantic_type'],'hint')
        self.assertEqual(tutor.response_generator.generate.call_count,1)
        self.assertEqual(tutor.memory.commit_learning_turn.call_args.kwargs['selection_ref']['learning_response'],
                         result['learning_response'])
