"""灰度与回滚：临时数据库、模型替身，不发送外部请求。"""
import unittest
from unittest.mock import Mock
from agents.intent_policy import IntentPolicy
from agents.conversation_router import ConversationRouter, TASK_PROMPT
from agents.task_service import TaskService
from models.task_context import TaskContext
from models.task_understanding import TaskUnderstanding
from database.models import LearningTaskRow, TaskRequestRow, ConversationRow
from database.learning_tasks import TaskConflict
from tests import test_clarification_tasks as fixtures


class IntentPolicyTests(unittest.TestCase):
    def test_scope_and_dependencies(self):
        self.assertTrue(IntentPolicy.from_env({}).enabled('s', 'production'))
        policy = IntentPolicy.from_env({'INTENT_ROLLOUT':'test'})
        self.assertTrue(policy.enabled('s','test'))
        self.assertFalse(policy.enabled('s','production'))
        policy = IntentPolicy.from_env({'INTENT_ROLLOUT':'allowlist','INTENT_STUDENT_ALLOWLIST':' a, b '})
        self.assertTrue(policy.enabled('b','production'))
        self.assertFalse(policy.enabled('c','test'))
        for values in ({'INTENT_ROLLOUT':'off'}, {'INTENT_CONTEXT_ENABLED':'0'}, {'INTENT_TASK_ENABLED':'0'}):
            self.assertFalse(IntentPolicy.from_env(values).can_clarify('s','test'))
        policy=IntentPolicy.from_env({'INTENT_CLARIFICATION_ENABLED':'0'})
        self.assertTrue(policy.enabled('s','test'))
        self.assertFalse(policy.can_clarify('s','test'))

    def test_invalid_config_is_not_silently_enabled(self):
        for values in ({'INTENT_ROLLOUT':'typo'}, {'INTENT_ROLLOUT':'allowlist'},
                       {'INTENT_TASK_ENABLED':'yes'}, {'INTENT_REWRITE_ENABLED':'1'}):
            with self.subTest(values=values), self.assertRaises(ValueError): IntentPolicy.from_env(values)

    def test_legacy_route_uses_strict_validation_without_task_prompt(self):
        llm=Mock()
        llm.chat_json.return_value={'student_move':'question','intent':'continue','confidence':.9,'needs_context':False}
        context=TaskContext(student_id='s',message='解释交集',knowledge_point='集合',task_understanding_enabled=False)
        router=ConversationRouter(llm)
        result=router.route(context.message,context.knowledge_point,[],[],context=context)
        self.assertEqual(result.status,'ok')
        self.assertNotIn(TASK_PROMPT,llm.chat_json.call_args.args[0][0]['content'])
        self.assertNotIn('task_understanding_enabled',context.prompt_payload())
        llm.chat_json.return_value['confidence']=float('nan')
        self.assertEqual(router.route(context.message,'集合',[],[],context=context).status,'parse_error')


class IntentRollbackTests(unittest.TestCase):
    setUp=fixtures.ClarificationTests.setUp
    tearDown=fixtures.ClarificationTests.tearDown
    request=fixtures.ClarificationTests.request
    execute=fixtures.ClarificationTests.execute
    clarify=fixtures.ClarificationTests.clarify
    count=fixtures.ClarificationTests.count

    def disable(self, **changes):
        self.service.policy=IntentPolicy(**changes)

    def test_rollback_rejects_pending_reply_and_keeps_receipts(self):
        first=self.clarify(request_id='r1')
        self.disable(scope='off')
        result=self.service.run(self.request(message='第一个',request_id='r2',task_id=first['task_id'],
            task_revision=first['task_revision']),self.execute(TaskUnderstanding()))
        self.assertEqual(result['answer_status'],'task_disabled')
        self.assertEqual(len(self.calls),1)
        self.assertIsNone(self.repo.pending('s','tab-a'))
        self.assertEqual(self.count(LearningTaskRow),1)
        self.assertEqual(self.count(TaskRequestRow),1)
        self.assertEqual(self.count(ConversationRow),0)
        self.disable()  # 重新开启不能复活已经撤销的任务。
        again=self.service.run(self.request(message='第一个',request_id='r2',task_id=first['task_id'],
            task_revision=first['task_revision']),self.execute(TaskUnderstanding()))
        self.assertEqual(again['answer_status'],'task_conflict')

    def test_rollback_blocks_implicit_resume_then_allows_complete_new_question(self):
        self.clarify(request_id='r1')
        self.disable(scope='off')
        result=self.service.run(self.request(message='第一个',request_id='r2'),self.execute(TaskUnderstanding()))
        self.assertEqual(result['answer_status'],'task_disabled')
        result=self.service.run(self.request(message='解释交集的定义',request_id='r3'),self.execute(TaskUnderstanding()))
        self.assertEqual(result['answer_status'],'answered')
        effective,context=self.calls[-1]
        self.assertEqual(effective.message,'解释交集的定义')
        self.assertFalse(context.task_understanding_enabled)
        self.assertEqual(context.objects,[])

    def test_clarification_off_returns_no_pending_and_does_not_execute(self):
        self.disable(clarification=False)
        result=self.clarify(request_id='r1')
        self.assertEqual(result['answer_status'],'clarification_required')
        self.assertIsNone(self.repo.pending('s','tab-a'))
        self.assertEqual(self.count(ConversationRow),0)
        self.assertTrue(self.calls[-1][1].task_understanding_enabled)

    def test_gray_account_type_comes_from_database(self):
        self.disable(scope='test')
        with self.assertRaisesRegex(ValueError,'正式账户'):
            self.service.run(self.request(message='解释交集',account_type='test'),self.execute(TaskUnderstanding()))
        self.assertEqual(self.calls,[])
        result=self.service.run(self.request(message='解释交集'),self.execute(TaskUnderstanding()))
        self.assertEqual(result['answer_status'],'answered')
        self.assertEqual(self.repo.account_type('s'),'production')
        self.assertFalse(self.calls[-1][1].task_understanding_enabled)

    def test_recovery_or_retry_cannot_forward_old_number_reply(self):
        self.clarify(request_id='r1')
        self.repo.invalidate_pending('s','tab-a')
        self.disable(scope='off')
        for message in ('第一个','2个'):
            result=self.service.run(self.request(message=message,request_id='r2'),self.execute(TaskUnderstanding()))
            self.assertEqual(result['answer_status'],'task_disabled')
        self.assertEqual(len(self.calls),1)

    def test_scope_does_not_cancel_other_session(self):
        self.clarify(request_id='r1')
        self.clarify(request_id='other1',session_id='tab-b')
        self.repo.invalidate_pending('s','tab-a')
        self.assertIsNotNone(self.repo.pending('s','tab-b'))

    def test_rollback_revision_rejects_late_write(self):
        first=self.clarify(request_id='r1')
        stale=self.repo.get('s','tab-a',first['task_id'])
        self.repo.invalidate_pending('s','tab-a')
        with self.assertRaises(TaskConflict):
            self.repo.save(task=stale,receipt_id='unused',memory_repo=self.memory.repo,status='completed',result={'reply':'迟到结果'})

