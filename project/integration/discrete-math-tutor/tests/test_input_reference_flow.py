"""真实 HTTP/SQLite 对象引用与恢复；模型正文受控，不冒充真实模型验收。"""
import os
import unittest
from unittest.mock import patch
from uuid import uuid4
from tests import test_task_api as fixtures
from models.task_understanding import TaskUnderstanding
from database.learning_tasks import LearningTaskRepository


class ReferenceFlowTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.TaskAPITests.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.TaskAPITests.tearDownClass.__func__)

    def setUp(self):
        fixtures.TaskAPITests.setUp(self)
        self.student = 'reference-' + uuid4().hex
        self.reply = '例子一：研究者安排光照强弱。\n\n例子二：研究者安排睡眠时长。'
        self.contexts = []
        def answer(*args, **kwargs):
            context = kwargs['task_context']; self.contexts.append(context)
            halted = kwargs['routing_interceptor'](TaskUnderstanding(),context)
            if halted is not None:return halted
            cid = self.tutor.memory.append_exchange(args[0],args[1],self.reply,task_guard=kwargs['task_guard'])
            return dict(answer_status='answered', reply=self.reply, conversation_id=cid, step_advanced=False)
        self.tutor.handle_turn.side_effect = answer

    def post(self, text, previous=None, selected=None, session='tab', mode='active', request_id=None):
        payload=dict(student_id=self.student, session_id=session, request_id=request_id or uuid4().hex,
                     message=text, account_type='test')
        if previous:payload.update(task_id=previous['task_id'],task_revision=previous['task_revision'])
        if selected:payload['selected_option']=selected
        with patch.dict(os.environ,INPUT_UNDERSTANDING_MODE=mode,INPUT_UNDERSTANDING_SEMANTIC_ENABLED='0',
                        Q5_LEARNING_ENABLED='0',LOCAL_AGENT_LOOP_ENABLED='0',ADAPTIVE_TUTORING_ENABLED='0',
                        DEEPTUTOR_SESSION_SYNC='0',DEEPTUTOR_TURN_SYNC='0'):
            return self.client.post('/api/chat',json=payload).json()

    def test_ambiguous_example_text_choice_restores_original_request(self):
        self.post('请给两个例子')
        paused=self.post('刚才那个例子，请再解释一下')
        self.assertEqual(paused['answer_status'],'awaiting_clarification')
        self.assertEqual(len(paused['clarification']['options']),2)
        self.assertEqual(len(self.contexts),1)
        self.reply='只解释睡眠时长这个例子。'
        done=self.post('第二个',paused)
        self.assertEqual(done['answer_status'],'answered')
        self.assertEqual(done['task_id'],paused['task_id'])
        turn=self.contexts[-1].input_understanding
        self.assertEqual(turn.envelope.raw_text,'刚才那个例子，请再解释一下')
        self.assertEqual(turn.reply_envelope.raw_text,'第二个')
        selected=next(r for r in turn.references if r.ref_id=='mention')
        self.assertIn('睡眠时长',selected.quote)
        self.assertEqual(selected.status,'resolved')

    def test_click_and_replay_do_not_repeat_execution(self):
        self.post('请给两个例子')
        paused=self.post('刚才那个例子，请解释')
        option=paused['clarification']['options'][0]['id']
        request_id=uuid4().hex
        first=self.post('选择第一个',paused,option,request_id=request_id)
        replay=self.post('选择第一个',paused,option,request_id=request_id)
        self.assertEqual(first['task_revision'],replay['task_revision'])
        self.assertEqual(len(self.contexts),2)

    def test_click_label_is_not_added_to_the_retrieval_question(self):
        self.post('请给两个例子')
        paused=self.post('刚才那个例子，请解释')
        selected=paused['clarification']['options'][1]
        result=self.post(selected['label'],paused,selected['id'])
        self.assertEqual(result['answer_status'],'answered')
        context=self.contexts[-1]
        self.assertNotIn(selected['label'],context.message)
        self.assertEqual(context.input_understanding.reply_envelope.raw_text,selected['label'])
        self.assertIn('睡眠时长',context.input_understanding.references[-1].quote)

    def test_other_session_cannot_guess_example_or_pick_foreign_id(self):
        self.post('请给两个例子')
        paused=self.post('刚才那个例子，请解释',session='another-tab')
        self.assertEqual(paused['clarification']['options'],[])
        invalid=self.post('选择',paused,'foreign',session='another-tab')
        self.assertNotEqual(invalid['answer_status'],'answered')

    def test_disabled_mode_keeps_new_pending_for_explicit_recovery(self):
        self.post('请给两个例子')
        paused=self.post('刚才那个例子，请解释')
        disabled=self.post('第二个',paused,mode='off')
        self.assertEqual(disabled['answer_status'],'input_mode_disabled')
        self.assertEqual(LearningTaskRepository().get(self.student,'tab',paused['task_id'])['status'],'awaiting_clarification')
        self.assertEqual(self.post('第二个',paused)['answer_status'],'answered')

    def test_missing_reference_uses_details_as_query_without_fabricating_id(self):
        paused=self.post('刚才那个例子，请解释')
        self.reply='就你补充的光照情境解释。'
        result=self.post('我指的是研究者调节灯光亮度的例子',paused)
        self.assertEqual(result['answer_status'],'answered')
        turn=self.contexts[-1].input_understanding
        self.assertIsNone(turn.tasks[0].target_ref)
        self.assertIn('调节灯光',turn.tasks[0].query)

    def test_expired_source_is_not_rebound_to_a_similar_new_object(self):
        import datetime as dt
        from database.database import session_scope
        from database.models import LearningTaskRow
        from database.learning_tasks import now
        seed=self.post('请给两个例子')
        paused=self.post('刚才那个例子，请解释')
        with session_scope() as db:
            db.get(LearningTaskRow,seed['task_id']).expires_at=now()-dt.timedelta(seconds=1)
        result=self.post('第二个',paused)
        self.assertEqual(result['answer_status'],'reference_stale')
        self.assertEqual(len(self.contexts),1)

    def test_source_removed_during_generation_cannot_publish_a_late_answer(self):
        import datetime as dt
        from database.database import session_scope
        from database.models import LearningTaskRow
        from database.learning_tasks import now
        seed=self.post('请给两个例子')
        paused=self.post('刚才那个例子，请解释')
        original=self.tutor.handle_turn.side_effect
        def generating(*args,**kwargs):
            with session_scope() as db:
                db.get(LearningTaskRow,seed['task_id']).expires_at=now()-dt.timedelta(seconds=1)
            return original(*args,**kwargs)
        self.tutor.handle_turn.side_effect=generating
        result=self.post('第二个',paused)
        self.assertEqual(result['answer_status'],'reference_stale')


if __name__=='__main__':unittest.main()
