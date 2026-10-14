"""图提问使用实际服务端快照；测试不调用模型或学生数据库。"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pydantic import ValidationError
from models.chat_request import ChatRequest
from models.visualization import CreateVisualization, GraphOperation, VisualizationTarget
from agents.task_context_builder import TaskContextBuilder
from agents.task_execution import build_execution
from agents.task_service import TaskService
from models.task_understanding import TaskUnderstanding
from models.task_context import TaskContext, TaskObject
from tests.test_visualization import VisualizationTests
from tests.test_quality_guard import QualityGuardTests
from agents.quality_checker import QualityResult
from knowledge.textbook import TextbookChunk
from knowledge.figures import retrieve_figures


class GraphChatTests(unittest.TestCase):
    def setUp(self):
        VisualizationTests.setUp(self)
        self.artifact = self.service.create(CreateVisualization(student_id='s',session_id='tab',request_id='graph',expected_epoch=0))

    def tearDown(self):
        VisualizationTests.tearDown(self)

    def target(self, **updates):
        return VisualizationTarget(artifact_id=self.artifact['artifact_id'],expected_revision=1,**updates)

    def request(self, target=None, session='tab'):
        return ChatRequest(student_id='s',session_id=session,request_id='question',account_type='test',message='解释当前图',visualization_target=target or self.target())

    def test_authoritative_context_and_exact_edge_set(self):
        context=TaskContextBuilder().build(student_id='s',session_id='tab',message='解释当前图',visualization_target=self.target())
        self.assertEqual(context.graph_snapshot['evaluation']['degrees'],dict.fromkeys(['v1','v2','v3','v4'],2))
        execution=build_execution('解释当前图',TaskUnderstanding(learning_intents=['explain']),context)
        self.assertIn('v1-v4',execution.retrieval_query)
        self.assertEqual(execution.targets[0]['kind'],'visualization')

    def test_other_session_stale_revision_and_forged_conclusions_rejected(self):
        for request in (self.request(session='another'),self.request(self.target().model_copy(update={'expected_revision':9}))):
            result=TaskService(SimpleNamespace(memory=self.memory)).run(request,lambda *args:self.fail('不应调用执行器'))
            self.assertIn(result['answer_status'],('visualization_changed','visualization_unavailable'))
        with self.assertRaises(ValidationError):
            VisualizationTarget.model_validate({**self.target().model_dump(),'has_euler_circuit':True})

    def test_graph_change_during_answer_refuses_write_and_releases_task(self):
        tasks=TaskService(SimpleNamespace(memory=self.memory))
        def executor(request,context,resolved,intercept,guard,progress):
            intercept(TaskUnderstanding(learning_intents=['explain']))
            self.service.operate(self.artifact['artifact_id'],GraphOperation(student_id='s',session_id='tab',request_id='add',expected_revision=1,operation='add_edge',source='v1',target='v3'))
            with self.memory.repo.unit_of_work():
                guard()
                self.fail('旧快照不应进入写入')
        result=tasks.run(self.request(),executor)
        self.assertEqual(result['answer_status'],'visualization_changed')
        self.assertIsNone(tasks.repo.pending('s','tab'))
        self.assertFalse(result['step_advanced'])

    def test_layout_change_does_not_invalidate_snapshot(self):
        snapshot=self.service.snapshot(self.target(),'s','tab')
        self.service.operate(self.artifact['artifact_id'],GraphOperation(student_id='s',session_id='tab',request_id='drag',expected_revision=1,operation='layout',positions=self.artifact['layout'],expected_layout_revision=1))
        self.service.guard_snapshot(snapshot,'s','tab')

    def test_hint_button_keeps_hint_constraints(self):
        context=TaskContextBuilder().build(student_id='s',session_id='tab',message='第一步提示',visualization_target=self.target())
        route=TaskContextBuilder.button_task(context,'hint')
        execution=build_execution('第一步提示',route,context)
        self.assertTrue(execution.hint_only)
        self.assertIn('不提供完整解答',execution.instructions())

    def test_graph_candidates_clarification_resume_and_stale_target(self):
        tasks=TaskService(SimpleNamespace(memory=self.memory))
        def execute(route):
            def executor(request,context,resolved,intercept,guard,progress):
                halted=intercept(route)
                if halted is not None:return halted
                guard()
                return {'reply':'完成解释','answer_status':'answered','step_advanced':False}
            return executor
        tasks.run(self.request(),execute(TaskUnderstanding(learning_intents=['explain'])))
        second=self.service.create(CreateVisualization(student_id='s',session_id='tab',request_id='another',expected_epoch=0))
        request=self.request().model_copy(update={'request_id':'second','visualization_target':VisualizationTarget(artifact_id=second['artifact_id'],expected_revision=1)})
        tasks.run(request,execute(TaskUnderstanding(learning_intents=['explain'])))
        ambiguous=ChatRequest(student_id='s',session_id='tab',account_type='test',request_id='ambiguous',message='这个图呢')
        context,_,_=tasks._context(ambiguous)
        self.assertEqual(len([obj for obj in context.objects if obj.kind=='visualization']),2)
        first=tasks.run(ambiguous,execute(TaskUnderstanding(status='unknown',intent='clarify_task',missing_slots=['target'])))
        self.assertEqual(len(first['clarification']['options']),2)
        # 补充请求使用原图版本；用户改图后拒绝恢复，不会悄悄换图。
        self.service.operate(second['artifact_id'],GraphOperation(student_id='s',session_id='tab',request_id='change',expected_revision=1,operation='add_edge',source='v1',target='v3'))
        resume=ambiguous.model_copy(update={'request_id':'resume','message':'第一个','task_id':first['task_id'],'task_revision':first['task_revision']})
        result=tasks.run(resume,lambda *args:self.fail('旧图版本不能恢复执行'))
        self.assertEqual(result['answer_status'],'visualization_changed')

    def test_explicit_graph_button_ignores_other_graph_candidates(self):
        context=TaskContextBuilder().build(student_id='s',session_id='tab',message='提示',visualization_target=self.target())
        other=context.objects[0].model_copy(update={'id':'visualization:other'})
        context.objects.append(other)
        self.assertEqual(TaskContextBuilder.button_task(context,'hint').target_refs,['visualization:'+self.artifact['artifact_id']])
        execution=build_execution('解释当前图',TaskUnderstanding(learning_intents=['explain']),context)
        self.assertEqual(execution.target_refs,['visualization:'+self.artifact['artifact_id']])
        self.assertNotIn('visualization:other',str(execution.targets))

    def test_clarification_selection_recovers_live_graph_snapshot(self):
        tasks=TaskService(SimpleNamespace(memory=self.memory))
        def clarify(request,context,resolved,intercept,guard,progress):
            return intercept(TaskUnderstanding(status='unknown',intent='clarify_task',missing_slots=['target']))
        first=tasks.run(self.request(),clarify)
        request=ChatRequest(student_id='s',session_id='tab',account_type='test',request_id='resume-live',message='第一个',
            task_id=first['task_id'],task_revision=first['task_revision'])
        def resume(request,context,resolved,intercept,guard,progress):
            self.assertEqual(context.graph_snapshot['artifact_id'],self.artifact['artifact_id'])
            self.assertIsNone(request.visualization_target.action)
            intercept(TaskUnderstanding(learning_intents=['explain'],target_refs=[context.objects[0].id]));guard()
            return {'reply':'完成解释','answer_status':'answered'}
        self.assertEqual(tasks.run(request,resume)['answer_status'],'answered')

    def test_seeded_graph_saved_and_recomputed(self):
        graph=self.artifact['graph']
        graph={'nodes':graph['nodes'],'edges':graph['edges']+[{'source':'v1','target':'v3'}]}
        artifact=self.service.create(CreateVisualization(student_id='s',session_id='tab',request_id='diagonal',expected_epoch=0,graph=graph))
        self.assertEqual(artifact['evaluation']['degrees'],{'v1':3,'v2':2,'v3':3,'v4':2})
        self.assertFalse(artifact['evaluation']['has_euler_circuit'])

    def test_hint_artifact_api_masks_answers_including_after_operation(self):
        artifact=self.service.create(CreateVisualization(student_id='s',session_id='tab',request_id='hint',expected_epoch=0,mode='hint'))
        self.assertEqual(artifact['evaluation']['degrees'],{})
        self.assertNotIn('has_euler_circuit',artifact['evaluation'])
        after=self.service.operate(artifact['artifact_id'],GraphOperation(student_id='s',session_id='tab',request_id='add-hint',expected_revision=1,operation='add_edge',source='v1',target='v3'))
        self.assertEqual(after['mode'],'hint')
        self.assertEqual(after['evaluation']['odd_vertices'],[])
        self.assertNotIn('has_open_euler_path',after['evaluation'])


class ConversationRegressionTests(unittest.TestCase):
    def test_selected_graph_does_not_append_implicit_textbook_figure(self):
        tutor=QualityGuardTests().tutor([QualityResult(passed=True)])
        tutor.conversation_router.route.return_value=TaskUnderstanding(intent='continue',learning_intents=['explain'])
        tutor.response_generator.generate.side_effect=['当前图为教材定义中的单孤立点特例。']
        context=TaskContext(student_id='guard-test',message='我选第一张，请解释',knowledge_point='欧拉图',
            objects=[TaskObject(id='visualization:test',kind='visualization',title='欧拉辅助图',text='顶点 v1，边为空',chapter_id=7,section_id=7)],
            graph_snapshot={'artifact_id':'test','graph':{'nodes':[{'id':'v1','label':'v1'}],'edges':[]},'evaluation':{},'answer_scope':'full'})
        tutor.memory.get_lesson_plan.return_value.goal=context.knowledge_point
        source=TextbookChunk('教材','欧拉图','已知定理',frozenset())
        with patch('orchestrator.retrieve_hybrid',return_value=[source]),patch('orchestrator.retrieve_figures') as figures,patch('orchestrator.expand_proof_sources',return_value=([source],None)),patch('orchestrator.enrich_sources',return_value=([source],None)):
            result=tutor.handle_turn('guard-test',context.message,task_context=context)
        figures.assert_not_called()
        self.assertEqual(result['answer_status'],'answered');self.assertEqual(result['image_refs'],[])

    def test_continue_with_section_title_is_not_topic_switch(self):
        tutor=QualityGuardTests().tutor([QualityResult(passed=True)])
        tutor.memory.get_active_goal.return_value='欧拉回路'
        tutor.conversation_router.route.return_value=TaskUnderstanding(intent='continue',learning_intents=['explain'])
        tutor.response_generator.generate.side_effect=['这个图没有欧拉回路。']
        context=TaskContext(student_id='guard-test',message='增加对角边后如何判定',knowledge_point='7.3.1欧拉图及欧拉路径')
        tutor.memory.get_lesson_plan.return_value.goal = context.knowledge_point
        source=TextbookChunk('教材','欧拉图','已知定理',frozenset())
        with patch('orchestrator.retrieve_hybrid',return_value=[source]),patch('orchestrator.retrieve_figures',return_value=[]),patch('orchestrator.expand_proof_sources',return_value=([source],None)),patch('orchestrator.enrich_sources',return_value=([source],None)):
            result=tutor.handle_turn('guard-test',context.message,task_context=context)
        self.assertEqual(result['answer_status'],'answered')
        self.assertFalse(tutor.quality_checker.check.call_args.args[5]['topic_switched'])

    def test_custom_instance_does_not_pull_unrelated_textbook_graph(self):
        with patch('knowledge.figures.load_figures') as load:
            self.assertEqual(retrieve_figures('四节点环增加 v1-v3',[]),[])
            load.assert_not_called()


if __name__=='__main__':unittest.main()
