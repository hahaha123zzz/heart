"""测评提交闭环：隐藏答案、事务收据、辅助证据及删除保护。"""
import unittest
from unittest.mock import patch
from sqlalchemy import select
from database.database import session_scope
from database.models import GraphAttemptRow, LearningEventRow, EventEvidenceRow
from models.visualization import CreateVisualization, GraphSubmission, VisualizationTarget, GraphOperation
from visualization.assessment import submit
from visualization.graph_validator import evaluate_graph
from visualization.service import VisualizationError, POINT
from tests import test_visualization as fixtures


class GraphAssessmentTests(unittest.TestCase):
    def setUp(self):
        fixtures.VisualizationTests.setUp(self)
        self.artifact = self.service.create(CreateVisualization(student_id='s', session_id='tab',
            request_id='assessment', expected_epoch=0, mode='assessment'))
        self.identifier = self.artifact['artifact_id']

    def tearDown(self):
        fixtures.VisualizationTests.tearDown(self)

    def answer(self, **updates):
        from models.visualization import GraphSpec
        actual = evaluate_graph(GraphSpec.model_validate(self.artifact['graph']))
        values = dict(student_id='s', session_id='tab', request_id='submit', expected_revision=1,
            degrees=actual['degrees'], connected=actual['connected'],
            prediction='circuit' if actual['has_euler_circuit'] else 'open_path' if actual['has_open_euler_path'] else 'neither',
            explanation='先计算顶点度数，再检查连通性。')
        return GraphSubmission(**dict(values, **updates))

    def test_hidden_until_submit_and_rule_verified_memory(self):
        self.assertNotIn('has_euler_circuit', self.artifact['evaluation'])
        self.assertEqual(self.artifact['evaluation']['degrees'], {})
        self.assertIsNone(self.artifact['attempt']['feedback'])
        before = self.memory.repo.get_knowledge_state('s', POINT).model_dump()
        result = submit(self.service, self.identifier, self.answer())
        self.assertTrue(result['correct']); self.assertTrue(result['independent'])
        self.assertFalse(result['mastery_updated']); self.assertFalse(result['explanation_verified'])
        self.assertEqual(self.memory.repo.get_knowledge_state('s', POINT).model_dump(), before)
        public = self.service.get(self.identifier, 's', 'tab')
        self.assertTrue(public['attempt']['submitted'])
        self.assertIn('has_euler_circuit', public['evaluation'])
        with session_scope() as session:
            evidence = session.scalars(select(EventEvidenceRow).where(EventEvidenceRow.event_id == result['event_id'])).all()
            self.assertEqual(len(evidence), 3)
            self.assertTrue(all(item.independent and item.verification == 'rule_verified' for item in evidence))
        # 记忆检索索引中保留了本次证据，且没有单独的新记忆库。
        from database.models import MemoryDocumentRow
        with session_scope() as session:
            docs=session.scalars(select(MemoryDocumentRow).where(MemoryDocumentRow.student_id=='s', MemoryDocumentRow.knowledge_point==POINT)).all()
            self.assertGreaterEqual(len(docs), 3)

    def test_ai_request_marks_assisted_on_server(self):
        target=VisualizationTarget(artifact_id=self.identifier, expected_revision=1, action='explain')
        snapshot=self.service.snapshot(target, 's', 'tab')
        self.assertEqual(snapshot['answer_scope'],'hint')
        from agents.task_context_builder import TaskContextBuilder
        from agents.task_execution import build_execution
        context=TaskContextBuilder().build(student_id='s',session_id='tab',message='告诉我答案',visualization_target=target)
        self.assertTrue(build_execution('告诉我答案',TaskContextBuilder.button_task(context,'explain'),context).hint_only)
        from agents.quality_checker import QualityChecker
        from agents.teaching_planner import TeachingPlan
        plan=TeachingPlan(goal=POINT,strategy='progressive_hinting',action='give_hint',difficulty='easy')
        self.assertTrue(QualityChecker._rule_check('所以这张图有欧拉回路。',plan,{'graph_snapshot':snapshot}))
        self.assertFalse(QualityChecker._rule_check('第一步先数与各顶点相接的边。',plan,{'graph_snapshot':snapshot}))
        result=submit(self.service, self.identifier, self.answer())
        self.assertFalse(result['independent']); self.assertFalse(result['eligible'])
        with session_scope() as session:
            evidence=session.scalars(select(EventEvidenceRow).where(EventEvidenceRow.event_id==result['event_id'])).all()
            self.assertTrue(all(not item.independent for item in evidence))

    def test_idempotency_payload_conflict_and_concurrent_submit(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:submit(self.service,self.identifier,self.answer()), range(2)))
        self.assertEqual(results[0], results[1])
        with self.assertRaises(VisualizationError):
            submit(self.service,self.identifier,self.answer(request_id='different'))
        with self.assertRaises(VisualizationError):
            submit(self.service,self.identifier,self.answer(explanation='修改答案'))
        with session_scope() as session:
            events=session.scalars(select(LearningEventRow).where(LearningEventRow.event_type=='graph_submission')).all()
            self.assertEqual(len(events),1)

    def test_submission_and_memory_rollback_together(self):
        with patch.object(self.service.repo, 'add_event_evidence', side_effect=RuntimeError('模拟证据保存失败')):
            with self.assertRaises(RuntimeError):submit(self.service,self.identifier,self.answer())
        with session_scope() as session:
            self.assertIsNone(session.scalar(select(GraphAttemptRow)).submission)
            self.assertEqual(len(session.scalars(select(LearningEventRow).where(LearningEventRow.event_type=='graph_submission')).all()),0)
        self.assertTrue(submit(self.service,self.identifier,self.answer())['correct'])

    def test_forget_deletes_receipt_and_rejects_late_submission(self):
        submit(self.service,self.identifier,self.answer())
        self.memory.repo.forget_learning_point('s',POINT)
        with session_scope() as session:
            self.assertIsNone(session.scalar(select(GraphAttemptRow)))
            self.assertEqual(len(session.scalars(select(LearningEventRow).where(LearningEventRow.event_type=='graph_submission')).all()),0)
        with self.assertRaises(VisualizationError):submit(self.service,self.identifier,self.answer())

    def test_bad_scope_revision_input_and_fixed_edges(self):
        from pydantic import ValidationError
        for updates in ({'session_id':'other'}, {'student_id':'other'}, {'expected_revision':2}, {'degrees':{'v1':0}}):
            with self.subTest(updates=updates), self.assertRaises(VisualizationError):
                submit(self.service,self.identifier,self.answer(**updates))
        with self.assertRaises(ValidationError): self.answer().model_validate({**self.answer().model_dump(), 'assisted':False})
        with self.assertRaises(ValidationError): self.answer(degrees={'v1':True})
        with self.assertRaises(ValidationError):
            CreateVisualization(student_id='s',session_id='tab',request_id='known',expected_epoch=0,mode='assessment',graph=self.artifact['graph'])
        with self.assertRaises(VisualizationError):
            self.service.operate(self.identifier,GraphOperation(student_id='s',session_id='tab',request_id='edge',expected_revision=1,operation='add_edge',source='v1',target='v3'))
        moved=self.service.operate(self.identifier,GraphOperation(student_id='s',session_id='tab',request_id='layout',expected_revision=1,operation='layout',positions=self.artifact['layout'],expected_layout_revision=1))
        self.assertNotIn('has_euler_circuit',moved['evaluation'])

    def test_wrong_answer_is_observation_not_mastery(self):
        result=submit(self.service,self.identifier,self.answer(degrees=dict.fromkeys(['v1','v2','v3','v4'],0)))
        self.assertFalse(result['correct']); self.assertFalse(result['checks']['degrees'])
        self.assertTrue(result['independent']); self.assertFalse(result['mastery_updated'])

    def test_correction_preserves_original_and_records_assisted(self):
        original=submit(self.service,self.identifier,self.answer(connected=False))
        request=CreateVisualization(student_id='s',session_id='tab',request_id='correction',expected_epoch=0,
            mode='assessment',correction_of=self.identifier)
        correction=self.service.create(request)
        self.assertNotEqual(correction['artifact_id'],self.identifier)
        self.assertEqual(correction['graph'],self.artifact['graph'])
        self.assertEqual(correction['layout'],self.artifact['layout'])
        self.assertEqual(correction['attempt']['correction']['answers'],original['answers'])
        self.assertFalse(correction['attempt']['submitted'])
        self.assertNotIn('has_euler_circuit',correction['evaluation'])
        self.assertEqual(self.service.create(request),correction)
        result=submit(self.service,correction['artifact_id'],self.answer(request_id='corrected'))
        self.assertTrue(result['correct'])
        self.assertFalse(result['independent']); self.assertFalse(result['eligible'])
        self.assertEqual(self.service.get(self.identifier,'s','tab')['attempt']['feedback'],original)
        self.assertTrue(self.service.get(correction['artifact_id'],'s','tab')['attempt']['submitted'])

    def test_correction_rejects_unsubmitted_other_scope_and_forgotten(self):
        def request(**updates):
            return CreateVisualization(**dict(dict(student_id='s',session_id='tab',request_id='correction',
                expected_epoch=0,mode='assessment',correction_of=self.identifier),**updates))
        with self.assertRaises(VisualizationError): self.service.create(request())
        submit(self.service,self.identifier,self.answer())
        for scope in ({'session_id':'other'},{'student_id':'other'}):
            with self.subTest(scope=scope),self.assertRaises(VisualizationError):self.service.create(request(**scope))
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):request(mode='explore')
        self.memory.repo.forget_learning_point('s',POINT)
        with self.assertRaises(VisualizationError):self.service.create(request(expected_epoch=1))

    def test_disabled_rollout_keeps_history_readonly_and_rejects_submit(self):
        import os
        with patch.dict(os.environ,{'VISUALIZATION_ROLLOUT':'off'}):
            public=self.service.get(self.identifier,'s','tab')
            self.assertTrue(public['readonly'])
            self.assertNotIn('has_euler_circuit',public['evaluation'])
            with self.assertRaises(VisualizationError) as caught:submit(self.service,self.identifier,self.answer())
            self.assertEqual(caught.exception.status,403)
        self.assertFalse(self.service.get(self.identifier,'s','tab')['attempt']['submitted'])


if __name__=='__main__': unittest.main()
