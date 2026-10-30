"""实际FastAPI/TaskService/SQLite；受控回答验证接线、收据与影子模式。"""
import os
import unittest
from uuid import uuid4
from unittest.mock import patch
from tests import test_task_api as fixtures
from models.task_understanding import TaskUnderstanding
from database.learning_tasks import LearningTaskRepository


class InputTaskAPITests(unittest.TestCase):
    setUpClass = classmethod(fixtures.TaskAPITests.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.TaskAPITests.tearDownClass.__func__)
    setUp = fixtures.TaskAPITests.setUp

    def answer(self,*args,**kwargs):
        halted=kwargs['routing_interceptor'](TaskUnderstanding(),kwargs['task_context'])
        if halted is not None:return halted
        cid=self.tutor.memory.append_exchange(args[0],args[1],'解释已完成',task_guard=kwargs['task_guard'])
        return {'answer_status':'answered','reply':'解释已完成','conversation_id':cid,'step_advanced':False}

    def post(self,text='解释自变量',mode='active',side_effect=None):
        self.tutor.handle_turn.side_effect=side_effect or self.answer
        payload={'student_id':'input-'+uuid4().hex,'session_id':'tab','request_id':'request','message':text}
        with patch.dict(os.environ,INPUT_UNDERSTANDING_MODE=mode,LOCAL_AGENT_LOOP_ENABLED='0',
                        Q5_LEARNING_ENABLED='0',ADAPTIVE_TUTORING_ENABLED='0',DEEPTUTOR_SESSION_SYNC='0',DEEPTUTOR_TURN_SYNC='0'):
            result=self.client.post('/api/chat',json=payload).json()
        return payload,result

    def test_active_snapshot_is_persisted_and_replayed_without_reparse(self):
        payload,result=self.post()
        self.assertEqual(result['answer_status'],'answered')
        row=LearningTaskRepository().get(payload['student_id'],'tab',result['task_id'])
        understood=row['context']['input_understanding']
        self.assertEqual(understood['context']['task_id'],result['task_id'])
        self.assertEqual(understood['envelope']['raw_text'],payload['message'])
        with patch.dict(os.environ,INPUT_UNDERSTANDING_MODE='active'), \
             patch('agents.input_understanding.service.understand',side_effect=AssertionError('must replay')):
            replay=self.client.post('/api/chat',json=payload).json()
        self.assertEqual(replay['reply'],result['reply'])
        self.assertEqual(replay['task_revision'],result['task_revision'])
        self.assertEqual(self.tutor.handle_turn.call_count,1)

    def test_shadow_snapshot_never_changes_response_or_preferences(self):
        payload,result=self.post('以后详细一点，但这题直接给答案。',mode='shadow')
        self.assertNotIn('input_understanding',result)
        self.assertNotIn('style_suggestion',result)
        self.assertNotIn('answer_length',self.tutor.memory.get_profile(payload['student_id']).preferences)

    def test_active_preference_requires_explicit_confirmation(self):
        payload,result=self.post('以后详细一点，但这题直接给答案。')
        self.assertEqual(result['style_suggestion']['origin'],'explicit_request')
        self.assertEqual(result['style_suggestion']['values'],{'answer_length':1.})
        self.assertNotIn('answer_length',self.tutor.memory.get_profile(payload['student_id']).preferences)

    def test_cancel_during_understanding_cannot_execute_or_publish(self):
        from sqlalchemy import select
        from database.database import session_scope
        from database.models import LearningTaskRow
        from agents.input_understanding.service import understand
        def cancel(context,request,**kwargs):
            with session_scope() as db:
                row=db.scalar(select(LearningTaskRow).where(LearningTaskRow.student_id==request.student_id))
                self.assertIsNotNone(row, '理解模型调用前必须已经认领任务')
                task_id,revision=row.id,row.revision
            LearningTaskRepository().cancel(request.student_id,request.session_id,task_id,revision)
            return understand(context,request,**kwargs)
        with patch('agents.input_understanding.service.understand',side_effect=cancel):
            payload,result=self.post()
        self.assertEqual(result['answer_status'],'task_cancelled')
        self.tutor.handle_turn.assert_not_called()
        self.assertFalse(self.tutor.memory.get_history(payload['student_id']))


    def test_cancel_during_generation_cannot_publish_or_save(self):
        from sqlalchemy import select
        from database.database import session_scope
        from database.models import LearningTaskRow
        from database.learning_tasks import TaskConflict
        def cancelled(*args,**kwargs):
            with session_scope() as db:
                row=db.scalar(select(LearningTaskRow).where(LearningTaskRow.student_id==args[0]))
                task_id,revision=row.id,row.revision
            LearningTaskRepository().cancel(args[0],'tab',task_id,revision)
            # 真实执行器通过同一 guard 抛出取消/版本冲突，旧正文与收据不得落库。
            raise TaskConflict('task_cancelled','任务已取消，旧结果不会保存')
        with patch.object(self.tutor,'handle_turn',side_effect=cancelled):
            payload,result=self.post(side_effect=cancelled)
        self.assertEqual(result['answer_status'],'task_cancelled')
        self.assertFalse(self.tutor.memory.get_history(payload['student_id']))
        from sqlalchemy import select
        from database.database import session_scope
        from database.models import LearningTaskRow
        with session_scope() as db:
            row=db.scalar(select(LearningTaskRow).where(LearningTaskRow.student_id==payload['student_id']))
            self.assertEqual(row.status,'cancelled')
            self.assertIsNone(row.scope_key)


if __name__=='__main__':unittest.main()
