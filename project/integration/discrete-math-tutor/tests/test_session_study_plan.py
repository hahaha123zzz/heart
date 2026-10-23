"""本次安排：输入边界、旧库增量迁移和独立路径身份。"""
import unittest
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
