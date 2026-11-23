"""原生宿主接线：真实任务数据库，替身只在 worker HTTP 边界。"""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.test_q5_learning import Q5TestBase
from memory.memory_manager import MemoryManager
from models.chat_request import ChatRequest
from knowledge.request_resources import ResourceSnapshot
from knowledge.course_config import DEFAULT_GOAL
from integrations.deeptutor.native_executor import NativeTurnExecutor
from integrations.deeptutor.client import BackendUnavailable
from database.learning_tasks import LearningTaskRepository


class Backend:
    def __init__(self):
        self.starts=[]; self.commands=[]; self.offline=False; self.paused=False
    def native_start(self, payload):
        self.starts.append(deepcopy(payload))
        if self.offline: raise BackendUnavailable('offline')
        return {'turn_id':'native-turn'}
    def native_events(self, key, after_seq=0):
        if self.paused:
            yield {'seq':1,'type':'wait_for_input','metadata':{'questions':[{
                'id':'goal','question':'选择学习目标','options':[{'label':'基础'},{'label':'进阶'}]}]}}
        else:
            yield {'seq':after_seq+1,'type':'done','metadata':{}}
    def native_status(self, key):
        return {'status':'completed','reply':'这是经过原生运行时生成的回答。','result':{}}
    def native_command(self,key,**kwargs):
        self.commands.append((deepcopy(key),kwargs));self.paused=False
        return {'accepted':True}


class NativeExecutorTests(Q5TestBase):
    def setUp(self):
        super().setUp()
        self.memory=MemoryManager();self.backend=Backend()
        self.executor=NativeTurnExecutor(SimpleNamespace(memory=self.memory), backend=self.backend)
        self.guard=patch('knowledge.request_resources.resolve_resources', return_value=ResourceSnapshot([]))
        self.guard.start()
        self.documents=patch('knowledge.pdf_reader.documents',return_value=[]);self.documents.start()
    def tearDown(self):
        self.documents.stop();self.guard.stop();super().tearDown()
    def request(self, **kwargs):
        return ChatRequest(**({'student_id':'s','session_id':'sess','request_id':'r-native','message':'解释变量'}|kwargs))
    def test_options_reach_native_and_saved_request_does_not_execute_twice(self):
        req=self.request(capability='deep_research',tools=['web_search'],config={'topic':'变量'},skills=['my-skill'])
        result=self.executor.run(req)
        self.assertEqual(result['answer_status'],'answered')
        self.assertEqual(self.backend.starts[0]['capability'],'deep_research')
        self.assertEqual(self.backend.starts[0]['tools'],['web_search'])
        self.assertEqual(self.backend.starts[0]['skills'],['my-skill'])
        self.assertEqual(self.executor.run(req),result)
        self.assertEqual(len(self.backend.starts),1)
    def test_native_input_contract_reaches_worker_without_old_context(self):
        req=self.request(mastery_answer={'question_id':'q1','text':'A'},
            question_notebook_references=[7], parent_message_id=11,
            followup_question_context={'question_id':'q1'}, auto_route=True)
        with patch('agents.task_context_builder.TaskContextBuilder.build', side_effect=AssertionError('旧上下文被调用')):
            self.assertEqual(self.executor.run(req)['answer_status'],'answered')
        payload=self.backend.starts[0]
        for name in ('mastery_answer','question_notebook_references','parent_message_id',
                     'followup_question_context','auto_route'):
            self.assertEqual(payload[name],getattr(req,name))

    def test_preupgrade_receipt_replays_with_new_fields_at_defaults(self):
        import hashlib, json
        from database.database import session_scope
        from database.models import TaskRequestRow
        from sqlalchemy import select
        req=self.request()
        result=self.executor.run(req)
        original=req.model_dump(mode='json')
        from integrations.deeptutor.native_contract import ADDITIONAL_TURN_FIELDS
        for name in ADDITIONAL_TURN_FIELDS:
            original.pop(name)
        with session_scope() as db:
            row=db.scalar(select(TaskRequestRow).where(TaskRequestRow.request_id==req.request_id))
            row.payload_hash=hashlib.sha256(json.dumps(original,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(self.executor.run(req),result)
        self.assertEqual(len(self.backend.starts),1)
        changed=req.model_copy(update={'auto_route':True})
        self.assertEqual(self.executor.run(changed)['answer_status'],'request_conflict')

    def test_failed_admission_retries_same_native_identity(self):
        self.backend.offline=True;req=self.request()
        failed=self.executor.run(req)
        self.assertEqual(failed['answer_status'],'native_unavailable')
        self.backend.offline=False
        self.assertEqual(self.executor.run(req)['answer_status'],'answered')
        self.assertEqual(self.backend.starts[0],self.backend.starts[1])
    def test_pause_resume_keeps_native_identity_and_rejects_invalid_option_without_mutation(self):
        self.backend.paused=True
        pending=self.executor.run(self.request())
        self.assertEqual(pending['answer_status'],'awaiting_clarification')
        invalid=self.request(request_id='reply-invalid',task_id=pending['task_id'],task_revision=pending['task_revision'],selected_option='forged')
        self.assertEqual(self.executor.run(invalid)['answer_status'],'invalid_option')
        row=LearningTaskRepository().get('s','sess',pending['task_id'])
        self.assertEqual(row['revision'],pending['task_revision'])
        valid=invalid.model_copy(update={'request_id':'reply-valid','selected_option':pending['clarification']['options'][0]['id']})
        self.assertEqual(self.executor.run(valid)['answer_status'],'answered')
        self.assertEqual(self.backend.commands[0][0]['task_revision'],self.backend.starts[0]['task_revision'])
        self.assertEqual(len(self.backend.starts),1)
    def test_reading_capability_uses_current_host_reader_chapter(self):
        req=self.request(capability='immersive_reading',reader_location={'chapter_id':2,'section_id':1})
        self.assertEqual(self.executor.run(req)['answer_status'],'answered')
        self.assertEqual(self.backend.starts[0]['reading_viewport'],{'chapter_id':2})

    def test_deleted_epoch_prevents_stream_publication(self):
        from database.database import session_scope
        from database.models import MemoryControlRow
        def revoked(key,after_seq=0):
            with session_scope() as db:db.add(MemoryControlRow(student_id='s',knowledge_point=DEFAULT_GOAL,epoch=1))
            yield {'seq':1,'type':'done'}
        self.backend.native_events=revoked
        self.assertEqual(self.executor.run(self.request())['answer_status'],'memory_deleted')

if __name__ == '__main__':unittest.main()


class NativeCatalogTests(unittest.IsolatedAsyncioTestCase):
    from tests.test_deeptutor_native_runtime import NativeRuntimeTests as _fixtures
    asyncSetUp=_fixtures.asyncSetUp
    asyncTearDown=_fixtures.asyncTearDown
    async def test_catalog_uses_real_scoped_registries(self):
        from integrations.deeptutor.native_contract import NativeScopeRequest
        result=await self.bridge.catalog(NativeScopeRequest(student_id='s',course_id='course',course_title='课程',session_id='sess'))
        self.assertEqual(len(result['tools']),69)
        self.assertEqual(result['hidden_tool_count'],31)
        self.assertNotIn('obsidian_read', {tool['name'] for tool in result['tools']})
        self.assertNotIn('cron', {tool['name'] for tool in result['tools']})
        self.assertEqual(len(result['extensions']),8)
        self.assertEqual({c['name'] for c in result['capabilities']},{'chat','ask_questions'})


class ArtifactAuthenticationTests(unittest.TestCase):
    def test_signature_binds_each_identity_field_and_requires_server_secret(self):
        import os
        from integrations.deeptutor.artifact_auth import signature,verify
        with patch.dict(os.environ,DEEPTUTOR_BRIDGE_TOKEN='t'*32):
            args=['student','session','task','file'];token=signature(*args)
            self.assertTrue(verify(*args,token))
            for i in range(4):
                changed=list(args);changed[i]='other'
                self.assertFalse(verify(*changed,token))
            self.assertFalse(verify(*args,'0'*64))
        with patch.dict(os.environ,DEEPTUTOR_BRIDGE_TOKEN=''):
            with self.assertRaises(ValueError):signature(*args)

    def test_artifact_route_rejects_bad_signature_before_reading_any_task(self):
        import os
        from fastapi import HTTPException
        from integrations.deeptutor import router
        calls=[]
        with patch.dict(os.environ,DEEPTUTOR_BRIDGE_TOKEN='t'*32), \
             patch('database.learning_tasks.LearningTaskRepository.get',
                   side_effect=lambda *args:calls.append(args)):
            with self.assertRaises(HTTPException) as raised:
                router.native_artifact('task','file','student','session','0'*64)
        self.assertEqual(raised.exception.status_code,403)
        self.assertEqual(calls,[])
