"""C3：依赖前沿、发布顺序、失败恢复和引用冻结；不调用真实模型。"""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from agents.composition_execution import composition_io, execute_batches, freeze_publication, active_spent, resume_allowed
from agents.response_composition import ResponseComposer, plan_response
from agents.agent_loop import LoopResult
from agents.tool_protocol import Cancellation, CancelledError
from llm.answer_events import AnswerEvents,current_answer
from llm.client import LLMError
from models.learning_response import BlockSpec, ResponsePlan
from tests.test_q3_agent_loop import ScriptedLLM,final_round
from tests.test_response_composition import SOURCES,block,response
from tests import test_clarification_tasks as fixtures
from database.learning_tasks import TaskConflict


def references(sources):
    return [{'source_index':s['index']-1,'evidence':{'document_id':s['document_id'],
        'document_version':s['version'],'evidence_id':s['source_id']}} for s in sources]


def gate(text,result,complete):
    import re
    used={int(n) for n in re.findall(r'\[(\d+)\]',text)}
    rows=[s for s in result.sources if s['index'] in used]
    mapping={s['index']:i for i,s in enumerate(rows,1)}
    result._publication={'reply':re.sub(r'\[(\d+)\]',lambda m:f'[{mapping[int(m[1])]}]',text),
        'pdf_references':[{**r,'source_index':i} for i,r in enumerate(references(rows))]}
    return True,''


class CompositionExecutionTests(unittest.TestCase):
    def test_checkpoint_cannot_rebind_block_identity_or_skip_dependencies(self):
        from agents.composition_execution import restored_blocks
        plan=plan_response(target_id='t',strategy='contrast')
        for rows in ({'b2':block('b2')},{'b1':block('b2')},{'unknown':block('unknown')}):
            with self.assertRaises(ValueError):restored_blocks(plan,rows)
    def test_disabling_base_composition_also_disables_checkpoint_resume(self):
        from agents.composition_execution import enabled
        with patch.dict('os.environ',{'RESPONSE_BLOCK_STREAMING_ENABLED':'1','RESPONSE_COMPOSITION_ENABLED':'0'}):
            self.assertFalse(enabled())
    def test_unfinished_attempt_reserves_only_its_remaining_budget_and_cannot_reset_limit(self):
        with patch('agents.composition_execution.time',return_value=1000):
            state={'active_seconds':109,'active_limit_seconds':120,'in_flight':True,'updated_at':0,'calls':2}
            self.assertEqual(active_spent(state),120)
            self.assertFalse(resume_allowed(state))
            self.assertTrue(resume_allowed({**state,'final_result':{'conversation_id':1}}))
            state['active_seconds']=4
            self.assertEqual(active_spent(state),94)
            self.assertTrue(resume_allowed(state))

    def execute(self,rounds,*,saved=None,plan=None,cancellation=None,custom_gate=gate):
        model=ScriptedLLM(rounds);states=[];events=[]
        from agents.context_runtime.context import UnifiedContext
        request=SimpleNamespace(cancellation=cancellation,guard=None,temperature=.2,round_max_tokens=1200,
                                request_id='r',context=UnifiedContext(language="zh"))
        composer=ResponseComposer(plan or plan_response(target_id='t',strategy='contrast'))
        result=LoopResult(sources=deepcopy(SOURCES))
        for source,reference in zip(result.sources,references(result.sources)):
            source['location']['evidence']=reference['evidence']
        answer=AnswerEvents(lambda event,data:events.append((event,data,len(states))))
        answer.bind(lambda:{'task_id':'task','task_revision':2},lambda:None)
        token=current_answer.set(answer);io_token=composition_io.set({'save':lambda s:states.append(deepcopy(s)),'restored':saved})
        try:
            outcome=execute_batches(SimpleNamespace(llm=model),request,result,[],lambda *_:None,composer=composer,gate=custom_gate)
        finally:current_answer.reset(token);composition_io.reset(io_token)
        return outcome,model,states,events,composer

    def test_dependency_batches_persist_before_display_and_keep_global_citation_numbers(self):
        outcome,model,states,events,composer=self.execute([
            final_round(response(block('b1',text='先解释因变量',ids=['s2']))),
            final_round(response(block('b2',text='再比较自变量',ids=['s1'])))])
        self.assertTrue(outcome.completed);self.assertEqual(len(model.calls),2)
        first,second=[e for e in events if e[0]=='answer_blocks']
        self.assertEqual(first[1]['publication']['reply'],'先解释因变量[1]')
        self.assertEqual(second[1]['publication']['reply'],'先解释因变量[1]\n\n再比较自变量[2]')
        self.assertGreater(first[2],0)
        self.assertEqual(states[first[2]-1]['publication']['reply'],first[1]['publication']['reply'])
        self.assertEqual(list(states[-1]['accepted']),['b1','b2'])
        self.assertFalse(any(e[0]=='answer_delta' for e in events))
        self.assertIn('"b2"',model.calls[1]['messages'][-1]['content'])

    def test_failure_keeps_prefix_and_new_executor_generates_only_remaining_block(self):
        first,_,states,_,_=self.execute([final_round(response(block('b1'))),LLMError('受控断线')])
        self.assertFalse(first.completed)
        checkpoint=states[-1]
        self.assertEqual(list(checkpoint['accepted']),['b1'])
        resumed,model,_,events,_=self.execute([final_round(response(block('b2',text='只补第二块')))],saved=checkpoint)
        self.assertTrue(resumed.completed);self.assertEqual(len(model.calls),1)
        self.assertIn('只补第二块',events[0][1].get('publication',{}).get('reply','') if events[0][0]=='answer_blocks' else resumed.final_text)
        self.assertNotIn('"block_id": "b1", "claims": [{"text": "不含编号',model.calls[0]['messages'][-1]['content'])

    def test_independent_frontier_is_one_call_and_invalid_stage_never_replaces_published_prefix(self):
        plan=ResponsePlan(plan_id='p',target_id='t',strategy='direct',blocks=[
            BlockSpec(block_id='b1',semantic_type='definition'),BlockSpec(block_id='b2',semantic_type='comparison')])
        outcome,model,_,_,_=self.execute([final_round(response(block('b1'),block('b2')))],plan=plan)
        self.assertTrue(outcome.completed);self.assertEqual(len(model.calls),1)
        repaired,model,_,_,_=self.execute([final_round(response(block('b1'),block('b2',ids=['bad']))),
            final_round(response(block('b2')))],plan=plan)
        self.assertTrue(repaired.completed)
        self.assertIn('"pending": ["b2"]',model.calls[1]['messages'][-2]['content'])
        failed,_,states,events,_=self.execute([final_round(response(block('b1'))),
            final_round(response(block('b2',ids=['bad']))),final_round(response(block('b2',ids=['bad'])))])
        self.assertFalse(failed.completed)
        self.assertEqual(list(states[-1]['accepted']),['b1'])
        self.assertEqual(len([e for e in events if e[0]=='answer_blocks']),1)

    def test_cancellation_call_budget_and_source_change_cannot_resume(self):
        token=Cancellation();token.cancel()
        with self.assertRaises(CancelledError):self.execute([],cancellation=token)
        _,_,states,_,_=self.execute([final_round(response(block('b1'))),LLMError('断线')])
        saved=states[-1];saved['calls']=8
        result,model,_,_,_=self.execute([],saved=saved)
        self.assertFalse(result.completed);self.assertEqual(model.calls,[])
        saved['source_digest']='changed'
        with self.assertRaisesRegex(ValueError,'input_changed'):self.execute([],saved=saved)

    def test_fully_committed_checkpoint_finishes_without_regenerating(self):
        _,_,states,_,_=self.execute([final_round(response(block('b1'))),final_round(response(block('b2')))])
        outcome,model,_,_,_=self.execute([],saved=states[-1])
        self.assertTrue(outcome.completed);self.assertEqual(model.calls,[])

    def test_old_checkpoint_keeps_existing_duplicate_label_before_continuing(self):
        first=block('b1',text='教学示例（非原书例题）：一项模拟实验。',provenance='generated_example')
        _,_,states,_,_=self.execute([final_round(response(first)),LLMError('中断')])
        saved=states[-1]
        saved.pop('label_policy_version');saved.pop('legacy_label_blocks')
        saved['publication']['reply']=saved['publication']['reply'].replace('教学示例（非教材原例）：',
            '教学示例（非教材原例）：教学示例（非原书例题）：')
        resumed,model,_,events,_=self.execute([final_round(response(block('b2')))],saved=saved)
        self.assertTrue(resumed.completed);self.assertEqual(len(model.calls),1)
        self.assertTrue([e for e in events if e[0]=='answer_blocks'][-1][1]['publication']['reply'].startswith(saved['publication']['reply']))

    def test_frozen_prefix_cannot_be_rewritten_or_have_sources_removed(self):
        pub={'reply':'已发布[2]','pdf_references':references([SOURCES[0],SOURCES[1]])}
        first=freeze_publication(pub)
        with self.assertRaisesRegex(ValueError,'prefix_changed'):
            freeze_publication({**pub,'reply':'改写[2]'},first)
        with self.assertRaisesRegex(ValueError,'source_disappeared'):
            freeze_publication({'reply':'已发布[2]','pdf_references':references([SOURCES[1]])},first)


class CompositionCheckpointTests(unittest.TestCase):
    setUp=fixtures.ClarificationTests.setUp
    tearDown=fixtures.ClarificationTests.tearDown
    request=fixtures.ClarificationTests.request

    @patch.dict('os.environ',{'RESPONSE_BLOCK_STREAMING_ENABLED':'1','RESPONSE_COMPOSITION_ENABLED':'1','Q5_LEARNING_ENABLED':'0','INPUT_UNDERSTANDING_MODE':'off'})
    def test_task_service_failure_keeps_checkpoint_and_does_not_mark_it_completed(self):
        from models.task_context import TaskContext
        from agents.composition_execution import composition_io
        def executor(request,context,*args):
            composition_io.get()['save']({'schema':'response-checkpoint/v1','updated_at':0})
            return {'answer_status':'quality_rejected','reply':'未全部完成','step_advanced':False}
        req=self.request(request_id='partial-fail-c3',message='解释概念')
        ctx=TaskContext(student_id='s',session_id='tab-a',message=req.message)
        with patch.object(self.service,'_context',return_value=(ctx,None,{})), \
             patch('agents.composition_recovery.partial_result',return_value=None):
            result=self.service.run(req,executor)
        row=self.repo.get('s','tab-a',result['task_id'])
        self.assertEqual(row['status'],'failed')
        self.assertIn('composition_checkpoint',row['context'])

    def test_public_checkpoint_revalidates_owner_revision_and_every_source(self):
        from agents.composition_recovery import partial_result
        _,_,states,_,_=CompositionExecutionTests().execute([final_round(response(block('b1'))),LLMError('断线')])
        task,receipt=self.claimed()
        state={**states[-1],'payload':self.request(request_id='c3').model_dump(),'document_versions':{},'context':{}}
        self.repo.composition_checkpoint(task,state,self.memory.repo)
        row=self.repo.get('s','tab-a',task['id'])
        with patch('integrations.deeptutor.task_projection.source_pointers',return_value=[]) as check:
            published=partial_result(row)
            self.assertEqual(published['answer_status'],'partial_answer')
            self.assertEqual(len(check.call_args.args[1]['pdf_references']),2)
            wrong={**row,'session_id':'other'}
            with self.assertRaises(TaskConflict):partial_result(wrong)
        with patch('integrations.deeptutor.task_projection.source_pointers',side_effect=ValueError('教材已变更')):
            with self.assertRaises(ValueError):partial_result(row)
        changed=deepcopy(state)
        changed['sources'][0]['location']['evidence']['textbook_release']='old'
        from agents.composition_execution import source_digest
        changed['source_digest']=source_digest(changed['sources'])
        self.repo.composition_checkpoint(task,changed,self.memory.repo)
        with patch('integrations.deeptutor.task_projection.source_pointers',return_value=[]), \
             patch('knowledge.course_release.binding',return_value={'release_id':'new'}):
            with self.assertRaises(ValueError):partial_result(self.repo.get('s','tab-a',task['id']))
        self.repo.cancel('s','tab-a',task['id'],task['revision'])
        with self.assertRaises(TaskConflict):partial_result(row)

    def test_q3_ready_task_enters_execution_on_first_checkpoint_without_revision_change(self):
        payload=self.request(request_id='ready-c3').model_dump()
        task,_,_=self.repo.claim(student_id='s',session_id='tab-a',request_id='ready-c3',payload=payload,
            point='',epoch=0,memory_repo=self.memory.repo)
        self.repo.composition_checkpoint(task,{'updated_at':0},self.memory.repo)
        row=self.repo.get('s','tab-a',task['id'])
        self.assertEqual(row['status'],'executing');self.assertEqual(row['revision'],task['revision'])

    def claimed(self):
        payload=self.request(request_id='c3').model_dump()
        task,receipt,_=self.repo.claim(student_id='s',session_id='tab-a',request_id='c3',payload=payload,
            point='',epoch=0,memory_repo=self.memory.repo)
        task,_=self.repo.save(task=task,receipt_id=receipt,status='executing',result={},context={},memory_repo=self.memory.repo)
        return task,receipt

    def test_checkpoint_is_owned_atomic_and_new_revision_fences_old_worker(self):
        task,receipt=self.claimed()
        from time import time
        cp={'schema':'response-checkpoint/v1','updated_at':time()-121}
        self.repo.composition_checkpoint(task,cp,self.memory.repo)
        self.assertEqual(self.repo.get('s','tab-a',task['id'])['context']['composition_checkpoint'],cp)
        with self.assertRaises(TaskConflict):self.repo.get('s','another-tab',task['id'])
        with patch.object(self.memory.repo,'memory_epoch',return_value=1):
            with self.assertRaises(TaskConflict):self.repo.composition_checkpoint(task,cp,self.memory.repo)
            with self.assertRaises(TaskConflict):self.repo.prepare_composition_resume('s','tab-a',task['id'],task['revision'],self.memory.repo)
        prepared=self.repo.prepare_composition_resume('s','tab-a',task['id'],task['revision'],self.memory.repo)
        self.assertGreater(prepared['revision'],task['revision'])
        with self.assertRaises(TaskConflict):self.repo.composition_checkpoint(task,cp,self.memory.repo)
        with self.assertRaises(TaskConflict):self.repo.prepare_composition_resume('s','tab-a',task['id'],task['revision'],self.memory.repo)

    def test_live_worker_cancellation_and_failure_retention(self):
        from time import time
        task,receipt=self.claimed()
        cp={'updated_at':time()}
        self.repo.composition_checkpoint(task,cp,self.memory.repo)
        with self.assertRaisesRegex(TaskConflict,'仍在执行'):
            self.repo.prepare_composition_resume('s','tab-a',task['id'],task['revision'],self.memory.repo)
        failed,_=self.repo.save(task=task,receipt_id=receipt,status='failed',result={},context={},memory_repo=self.memory.repo)
        self.assertEqual(failed['context']['composition_checkpoint'],cp)
        self.repo.cancel('s','tab-a',failed['id'],failed['revision'])


@patch.dict('os.environ',{'RESPONSE_COMPOSITION_ENABLED':'1','RESPONSE_BLOCK_STREAMING_ENABLED':'1',
    'ADAPTIVE_TUTORING_ENABLED':'0','Q5_LEARNING_ENABLED':'0'})
@patch("agents.teaching_skills.enabled", new=lambda *_args: False)
class CompositionFinalizationTests(unittest.TestCase):
    setUp=fixtures.ClarificationTests.setUp
    tearDown=fixtures.ClarificationTests.tearDown
    request=fixtures.ClarificationTests.request
    claimed=CompositionCheckpointTests.claimed

    def run_final(self, fail_marker=False):
        from agents.agent_loop_service import run_agent_loop_turn
        from agents.q3_navigation import LearningTarget,StubLearningNavigator
        from models.chat_request import ChatRequest
        from models.task_context import TaskContext
        _,_,states,_,_=CompositionExecutionTests().execute([final_round(response(block('b1'))),final_round(response(block('b2')))])
        task,_=self.claimed()
        req=ChatRequest(student_id='s',session_id='tab-a',request_id='final-c3',message='解释概念')
        ctx=TaskContext(student_id='s',session_id='tab-a',message=req.message)
        state={**states[-1],'payload':req.model_dump(),'context':ctx.model_dump(),'document_versions':{}}
        self.repo.composition_checkpoint(task,state,self.memory.repo)
        runtime={'restored':state,'latest':state}
        def save(value):
            if fail_marker:raise TaskConflict('task_conflict','模拟最终标记失败')
            value={**value,'payload':req.model_dump(),'context':ctx.model_dump(),'document_versions':{}}
            self.repo.composition_checkpoint(task,value,self.memory.repo);runtime['latest']=value
        runtime['save']=save
        token=composition_io.set(runtime);model=ScriptedLLM([])
        try:
            with patch('agents.agent_loop_service._target_from_context',return_value=LearningTarget('t','变量')), \
                 patch('agents.tools.first_wave_runtime.bind_resources',return_value=(None,())):
                result=run_agent_loop_turn(orchestrator=SimpleNamespace(llm=model,memory=self.memory,quality_checker=None),
                    request=req,context=ctx,navigator=StubLearningNavigator(target=LearningTarget('t','变量')),
                    publish_gate=lambda text,outcome:gate(text,outcome,True))
        finally:composition_io.reset(token)
        return result,runtime,task,model

    def test_final_exchange_marker_replays_same_conversation_without_model_and_rejects_deleted_record(self):
        from agents.composition_recovery import checked_checkpoint
        from agents.agent_loop_service import run_agent_loop_turn
        from models.chat_request import ChatRequest
        from models.task_context import TaskContext
        from database.models import ConversationRow
        result,runtime,task,model=self.run_final()
        self.assertEqual(result['answer_status'],'answered')
        self.assertEqual(runtime['latest']['final_result']['conversation_id'],result['conversation_id'])
        self.assertEqual(model.calls,[])
        with patch('integrations.deeptutor.task_projection.source_pointers',return_value=[]):
            state,_=checked_checkpoint(self.repo.get('s','tab-a',task['id']))
            from agents.composition_recovery import partial_result
            pending=partial_result(self.repo.get('s','tab-a',task['id']))
            self.assertEqual(pending['conversation_id'],result['conversation_id'])
            self.assertEqual(pending['reply'],result['reply'])
        token=composition_io.set({'restored':state})
        never=ScriptedLLM([])
        try:
            replay=run_agent_loop_turn(orchestrator=SimpleNamespace(llm=never,memory=self.memory),
                request=ChatRequest(student_id='s',session_id='tab-a',request_id='replay-c3',message='解释概念'),
                context=TaskContext(student_id='s',session_id='tab-a',message='解释概念'))
        finally:composition_io.reset(token)
        self.assertEqual(replay['conversation_id'],result['conversation_id']);self.assertEqual(never.calls,[])
        self.assertEqual(fixtures.ClarificationTests.count(self,ConversationRow),2)
        with self.factory.begin() as session:session.delete(session.get(ConversationRow,result['conversation_id']))
        with patch('integrations.deeptutor.task_projection.source_pointers',return_value=[]):
            with self.assertRaises(ValueError):checked_checkpoint(self.repo.get('s','tab-a',task['id']))

    def test_marker_failure_rolls_back_conversation_instead_of_saving_twice_on_retry(self):
        from database.models import ConversationRow
        result,_,_,_=self.run_final(fail_marker=True)
        self.assertEqual(result['answer_status'],'loop_failed')
        self.assertEqual(fixtures.ClarificationTests.count(self,ConversationRow),0)
