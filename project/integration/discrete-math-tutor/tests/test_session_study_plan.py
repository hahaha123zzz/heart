"""本次安排：输入边界、旧库增量迁移和独立路径身份。"""
import unittest
from copy import deepcopy
from unittest.mock import Mock
from sqlalchemy import text, inspect
from database.session_plan_migration import has_session_plan, migrate_session_plan
from models.session_study_plan import StudyRequest, StudyItem, SessionStudyPlan
from tests.test_q5_learning import Q5TestBase


def plan_payload(scope, budget=20):
    return dict(plan_id='session-plan', revision=1, student_id=scope.student_id,
        session_id=scope.session_id, course_id=scope.course_id,
        request=StudyRequest(goal='自变量', scope=['自变量'], time_budget_minutes=budget),
        items=[StudyItem(item_id='i1', kind='explain', title='自变量',
            source_refs=[{'document_id':'doc-1','version':'v1','unit_id':'u1'}],
            estimated_minutes=10, order_reason='先明确变量含义', completion_criterion='能说明研究者操纵什么')])


class ContractTests(unittest.TestCase):
    def test_budget_and_no_exam_are_enforced(self):
        from agents.q5_learning import LearningScope
        payload=plan_payload(LearningScope('s','tab'))
        self.assertEqual(SessionStudyPlan(**payload).revision,1)
        with self.assertRaises(ValueError):
            SessionStudyPlan(**dict(payload,request=StudyRequest(goal='自变量',time_budget_minutes=5)))
        with self.assertRaises(ValueError):
            StudyRequest(goal='自变量',time_budget_minutes=True)
        with self.assertRaises(ValueError):
            SessionStudyPlan(**dict(payload,request=StudyRequest(goal='自变量',practice_preference='none'),
                items=[payload['items'][0].model_copy(update={'kind':'optional_check'})]))


class MigrationTests(Q5TestBase):
    def test_old_binding_reads_and_migration_is_repeatable(self):
        from database import database as db
        with self.engine.begin() as connection:
            connection.execute(text('ALTER TABLE q5_learning_bindings DROP COLUMN session_plan'))
        self.assertFalse(has_session_plan(self.engine))
        self.assertEqual(self.service.status(self.scope)['status'],'no_path')
        self.service.set_mode(self.scope,'outline',command_id='legacy-mode')
        self.assertTrue(migrate_session_plan(self.engine))
        self.assertTrue(migrate_session_plan(self.engine))
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(text('SELECT COUNT(*) FROM q5_learning_bindings')).scalar(),1)
        self.assertEqual(sum(c['name']=='session_plan' for c in inspect(self.engine).get_columns('q5_learning_bindings')),1)


class SessionServiceTests(Q5TestBase):
    def setUp(self):
        super().setUp()
        from agents.session_study_service import SessionStudyService
        self.sessions=SessionStudyService(self.scope,source_validator=lambda ref:ref.get('version')=='v1')
        self.value=SessionStudyPlan(**plan_payload(self.scope)).model_dump()

    def test_confirm_is_idempotent_and_bound_to_session(self):
        first=self.sessions.confirm(self.value,command_id='confirm')
        self.assertEqual(first,self.sessions.confirm(self.value,command_id='confirm'))
        self.assertEqual(self.sessions.current()['status'],'active')
        self.assertIsNone(self.service.status(self.scope)['path_id'])
        other=deepcopy(self.value);other['session_id']='other'
        with self.assertRaisesRegex(ValueError,'owner'):
            self.sessions.confirm(other,command_id='cross-owner')

    def test_stale_confirm_source_and_cancellation_do_not_write(self):
        bad=deepcopy(self.value);bad['items'][0]['source_refs'][0]['version']='v2'
        with self.assertRaisesRegex(ValueError,'source'):
            self.sessions.confirm(bad,command_id='bad')
        self.assertIsNone(self.sessions.current())
        with self.assertRaisesRegex(RuntimeError,'cancelled'):
            self.sessions.confirm(self.value,command_id='cancel',guard=Mock(side_effect=RuntimeError('cancelled')))
        self.assertIsNone(self.sessions.current())
        self.sessions.confirm(self.value,command_id='ok')
        with self.assertRaisesRegex(ValueError,'revision'):
            self.sessions.confirm(self.value,command_id='old-card')

    def test_prepared_next_is_not_saved_before_publication(self):
        first=self.sessions.confirm(self.value,command_id='confirm')
        with self.assertRaisesRegex(ValueError,'explanation_required'):
            self.sessions.transition(first)
        explained=self.sessions.explained(first,command_id='explain')
        prepared=self.sessions.transition(explained)
        self.assertEqual(prepared['status'],'done')
        self.assertEqual(self.sessions.current(),explained)
        with self.assertRaisesRegex(RuntimeError,'cancelled'):
            self.sessions.finish(prepared,command_id='late',guard=Mock(side_effect=RuntimeError('cancelled')))
        self.assertEqual(self.sessions.current(),explained)
        finished=self.sessions.finish(prepared,command_id='finish')
        self.assertEqual(finished['status'],'done')
        self.assertIsNone(self.service.status(self.scope)['path_id'])

    def test_two_old_revision_updates_cannot_both_commit(self):
        value=self.sessions.confirm(self.value,command_id='confirm')
        self.sessions.explained(value,command_id='first')
        with self.assertRaisesRegex(ValueError,'revision'):
            self.sessions.explained(value,command_id='second')

    def test_two_concurrent_continues_commit_at_most_once(self):
        import threading
        value=self.sessions.confirm(self.value,command_id='confirm')
        value=self.sessions.explained(value,command_id='explain')
        prepared=self.sessions.transition(value);barrier=threading.Barrier(2);results=[]
        def finish(command):
            barrier.wait()
            try:self.sessions.finish(prepared,command_id=command);results.append('ok')
            except ValueError:results.append('conflict')
        threads=[threading.Thread(target=finish,args=(str(i),)) for i in range(2)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(timeout=15);self.assertFalse(thread.is_alive())
        self.assertEqual(sorted(results),['conflict','ok'])

    def test_pause_resume_and_new_service_restore_same_activity(self):
        from agents.session_study_service import SessionStudyService
        value=self.sessions.confirm(self.value,command_id='confirm')
        paused=self.sessions.set_mode(value,'paused',command_id='pause')
        restored=SessionStudyService(self.scope,source_validator=lambda ref:True).current()
        self.assertEqual(restored,paused)
        active=self.sessions.set_mode(paused,'active',command_id='resume')
        self.assertEqual(active['current_item_id'],value['current_item_id'])


class PlannerTests(unittest.TestCase):
    def setUp(self):
        from agents.q5_learning import LearningScope
        self.scope=LearningScope('s','sess','course')
        self.material={'unit_id':'u1','title':'自变量','objective_id':None,'text':'研究者操纵的变量',
            'source_ref':{'unit_id':'u1','document_id':'doc','version':'v1'}}
        self.raw={'items':[{'unit_id':'u1','kind':'explain','title':'解释自变量',
            'estimated_minutes':10,'order_reason':'先认识变量','completion_criterion':'能说明操纵的条件'}],'omitted':['本次不涉及因变量']}

    def test_actual_generator_receives_budget_scope_and_confirmed_profile(self):
        from agents.session_study_planner import generate_session
        import json
        llm=Mock();llm.chat_json.return_value=self.raw
        request=StudyRequest(goal='自变量',scope=['自变量'],time_budget_minutes=20,prior_knowledge='基础弱',practice_preference='none')
        plan=generate_session(llm,request,scope=self.scope,status={},current=None,previous=None,
            materials=[self.material],profile={'teaching_preference':'先讲后练'},validator=lambda p:None,guard=lambda:None)
        sent=json.loads(llm.chat_json.call_args.args[0][-1]['content'])
        self.assertEqual(sent['study_request']['time_budget_minutes'],20)
        self.assertEqual(sent['study_request']['practice_preference'],'none')
        self.assertEqual(sent['confirmed_profile']['teaching_preference'],'先讲后练')
        self.assertEqual(plan['items'][0]['source_refs'][0]['version'],'v1')

    def test_unknown_target_and_overbudget_repair_are_bounded(self):
        from agents.session_study_planner import generate_session
        llm=Mock();bad=deepcopy(self.raw);bad['items'][0]['unit_id']='fabricated'
        llm.chat_json.return_value=bad
        with self.assertRaisesRegex(ValueError,'validation_failed'):
            generate_session(llm,StudyRequest(goal='自变量',time_budget_minutes=20),scope=self.scope,status={},
                current=None,previous=None,materials=[self.material],profile={},validator=lambda p:None,guard=lambda:None)
        self.assertEqual(llm.chat_json.call_count,2)

    def test_model_cannot_mark_unexplained_activity_done(self):
        from agents.session_study_planner import generate_session
        llm=Mock();bad=deepcopy(self.raw);bad['items'][0]['status']='done'
        llm.chat_json.return_value=bad
        with self.assertRaisesRegex(ValueError,'cannot_set_identity_or_status'):
            generate_session(llm,StudyRequest(goal='自变量'),scope=self.scope,status={},current=None,previous=None,
                materials=[self.material],profile={},validator=lambda p:None,guard=lambda:None)

    def test_empty_annotation_is_discarded_but_identity_is_not(self):
        from agents.session_study_planner import generate_session
        llm=Mock();raw=deepcopy(self.raw);raw['items'][0]['order_reason_note']=''
        llm.chat_json.return_value=raw
        plan=generate_session(llm,StudyRequest(goal='自变量'),scope=self.scope,status={},current=None,previous=None,
            materials=[self.material],profile={},validator=lambda p:None,guard=lambda:None)
        self.assertNotIn('order_reason_note',plan['items'][0])
        self.assertEqual(llm.chat_json.call_count,1)

    def test_malformed_json_has_one_bounded_repair(self):
        from agents.session_study_planner import generate_session
        from llm.client import LLMJSONError
        llm=Mock();llm.chat_json.side_effect=[LLMJSONError('invalid json'),self.raw]
        value=generate_session(llm,StudyRequest(goal='自变量'),scope=self.scope,status={},current=None,previous=None,
            materials=[self.material],profile={},validator=lambda p:None,guard=lambda:None)
        self.assertTrue(value['items']);self.assertEqual(llm.chat_json.call_count,2)

    def test_revision_preserves_explained_identity_and_facts(self):
        from agents.session_study_planner import generate_session
        previous=SessionStudyPlan(**plan_payload(self.scope)).model_dump()
        previous['items'][0]['status']='explained'
        llm=Mock();llm.chat_json.return_value={'items':[],'omitted':['保留已讲活动，不增加新内容']}
        plan=generate_session(llm,StudyRequest(goal='自变量',time_budget_minutes=20),scope=self.scope,
            status={},current=previous,previous=previous,materials=[self.material],profile={},validator=lambda p:None,guard=lambda:None)
        self.assertEqual(plan['items'],previous['items'])
        self.assertEqual(plan['plan_id'],previous['plan_id'])
        self.assertGreater(plan['revision'],previous['revision'])

    def test_arrangement_trigger_does_not_capture_plain_concept_question(self):
        from agents.q5_runtime import Q5Runtime
        runtime=Q5Runtime.__new__(Q5Runtime)
        for message in ['今天有一小时，想学自变量和因变量，基础弱，先讲不要考试','今天怎么安排','帮我安排一小时']:
            self.assertTrue(runtime.is_plan_request(message),message)
        self.assertFalse(runtime.is_plan_request('什么是自变量'))
