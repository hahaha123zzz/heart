"""关系性质、矩阵一致性、测评事务与 AI 快照验证。"""
import itertools
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pydantic import ValidationError
from sqlalchemy import select
from database.database import session_scope
from database.models import RelationRow, RelationOperationRow, LearningEventRow, EventEvidenceRow
from models.relation import CreateRelation, RelationAnswers, RelationOperation, RelationTarget, RelationSpec
from visualization.relation import RelationService, POINT, target_key
from visualization.relation_validator import evaluate_relation, matrix, template_spec, PROPERTIES
from visualization.service import VisualizationError
from tests import test_visualization as fixtures


class RelationMathTests(unittest.TestCase):
    def test_empty_identity_and_full_relation(self):
        empty=evaluate_relation(template_spec('r1'))['properties']
        self.assertEqual(empty,dict(reflexive=False,irreflexive=True,symmetric=True,antisymmetric=True,transitive=True))
        identity=evaluate_relation(template_spec('r2'))['properties']
        self.assertEqual(identity,dict(reflexive=True,irreflexive=False,symmetric=True,antisymmetric=True,transitive=True))
        full=RelationSpec(pairs=[{'source':a,'target':b} for a in 'abc' for b in 'abc'])
        self.assertEqual(evaluate_relation(full)['properties'],dict(reflexive=True,irreflexive=False,symmetric=True,antisymmetric=False,transitive=True))

    def test_transitivity_witness_includes_self_loops(self):
        chain=evaluate_relation(template_spec('r3'))
        self.assertEqual(chain['witnesses']['transitive']['missing'],[['a','c']])
        self.assertTrue(evaluate_relation(template_spec('r4'))['properties']['transitive'])
        reverse=evaluate_relation(template_spec('r5'))
        self.assertTrue(reverse['properties']['symmetric']);self.assertFalse(reverse['properties']['antisymmetric'])
        self.assertEqual(reverse['witnesses']['transitive']['missing'],[['a','a']])

    def test_all_512_relations_against_boolean_matrix_definitions(self):
        pairs=list(itertools.product('abc',repeat=2))
        for mask in range(512):
            selected={pair for i,pair in enumerate(pairs) if mask & (1<<i)}
            spec=RelationSpec(pairs=[{'source':a,'target':b} for a,b in sorted(selected)])
            cells=matrix(spec)
            expected={'reflexive':all(cells[i][i] for i in range(3)),
                'irreflexive':all(not cells[i][i] for i in range(3)),
                'symmetric':all(cells[i][j]==cells[j][i] for i in range(3) for j in range(3)),
                'antisymmetric':all(not (cells[i][j] and cells[j][i]) for i in range(3) for j in range(3) if i!=j),
                'transitive':all(not (cells[i][j] and cells[j][k]) or cells[i][k] for i in range(3) for j in range(3) for k in range(3))}
            actual=evaluate_relation(spec)
            self.assertEqual(actual['properties'],expected)
            for witness in actual['witnesses'].values():
                if witness:
                    self.assertTrue(all(tuple(pair) in selected for pair in witness['present']))
                    self.assertTrue(all(tuple(pair) not in selected for pair in witness['missing']))

    def test_direction_loops_and_strict_spec(self):
        spec=RelationSpec(pairs=[{'source':'a','target':'a'},{'source':'b','target':'a'}])
        self.assertEqual(matrix(spec),[[1,0,0],[1,0,0],[0,0,0]])
        for pairs in ([{'source':'x','target':'a'}],[{'source':'a','target':'b'}]*2):
            with self.assertRaises(ValidationError):RelationSpec(pairs=pairs)


class RelationTests(unittest.TestCase):
    def setUp(self):
        fixtures.VisualizationTests.setUp(self)
        self.relations=RelationService()
        self.artifact=self.relations.create(CreateRelation(student_id='s',session_id='tab',request_id='relation',expected_epoch=0))
        self.identifier=self.artifact['artifact_id']

    def tearDown(self):fixtures.VisualizationTests.tearDown(self)

    def answer(self,**updates):
        values=evaluate_relation(RelationSpec(pairs=self.artifact['pairs']))['properties']
        return RelationAnswers(**dict(dict(student_id='s',session_id='tab',request_id='answer',expected_revision=1,values=values,explanation='检查全部序偶。'),**updates))

    def operation(self,**updates):
        return RelationOperation(**dict(dict(student_id='s',session_id='tab',request_id='operation',expected_revision=1,
            operation='set_pair',pair={'source':'a','target':'c'},present=True),**updates))

    def target(self,**updates):
        return RelationTarget(**dict(dict(artifact_id=self.identifier,expected_revision=1,property='transitive',pair={'source':'a','target':'c'},action='explain'),**updates))

    def assessment(self):
        with patch('visualization.relation.secrets.choice',return_value='r3'):
            self.artifact=self.relations.create(CreateRelation(student_id='s',session_id='tab',request_id='assessment',expected_epoch=0,mode='assessment'))
        self.identifier=self.artifact['artifact_id']

    def test_graph_matrix_operation_and_idempotency(self):
        updated=self.relations.operate(self.identifier,self.operation())
        self.assertEqual(updated['matrix'][0][2],1)
        self.assertTrue(updated['evaluation']['properties']['transitive'])
        self.assertEqual(updated['revision'],2)
        self.assertEqual(self.relations.operate(self.identifier,self.operation()),updated)
        with self.assertRaises(VisualizationError):self.relations.operate(self.identifier,self.operation(request_id='stale'))

    def test_layout_does_not_invalidate_ai_snapshot(self):
        snapshot=self.relations.snapshot(self.target(),'s','tab')
        request=RelationOperation(student_id='s',session_id='tab',request_id='layout',expected_revision=1,
            operation='layout',positions=self.artifact['layout'],expected_layout_revision=1)
        updated=self.relations.operate(self.identifier,request)
        self.assertEqual(updated['revision'],1);self.assertEqual(updated['layout_revision'],2)
        self.relations.guard_snapshot(snapshot,'s','tab')

    def test_draft_cas_and_memory_receipt(self):
        self.assessment()
        self.assertIsNone(self.artifact['evaluation']);self.assertIsNone(self.artifact['feedback'])
        saved=self.relations.save_draft(self.identifier,self.answer())
        self.assertEqual(saved['revision'],2)
        self.assertEqual(self.relations.save_draft(self.identifier,self.answer()),saved)
        result=self.relations.submit(self.identifier,self.answer(request_id='submit',expected_revision=2))
        self.assertTrue(result['correct']);self.assertTrue(result['independent'])
        self.assertFalse(result['mastery_updated']);self.assertFalse(result['explanation_verified'])
        self.assertEqual(self.relations.submit(self.identifier,self.answer(request_id='submit',expected_revision=2)),result)
        with session_scope() as session:
            evidence=session.scalars(select(EventEvidenceRow).where(EventEvidenceRow.event_id==result['event_id'])).all()
            self.assertEqual(len(evidence),5);self.assertTrue(all(item.independent for item in evidence))

    def test_correction_preserves_spec_and_first_result(self):
        self.assessment()
        first=self.relations.submit(self.identifier,self.answer(values=dict.fromkeys(PROPERTIES,True)))
        corrected=self.relations.create(CreateRelation(student_id='s',session_id='tab',request_id='correction',expected_epoch=0,mode='assessment',correction_of=self.identifier))
        self.assertEqual(corrected['pairs'],self.artifact['pairs']);self.assertEqual(corrected['draft'],first['answers'])
        result=self.relations.submit(corrected['artifact_id'],self.answer(request_id='corrected'))
        self.assertTrue(result['correct']);self.assertFalse(result['independent'])
        self.assertEqual(self.relations.get(self.identifier,'s','tab')['feedback'],first)

    def test_assessment_fixed_pairs_strict_types_and_incomplete(self):
        self.assessment()
        with self.assertRaises(VisualizationError):self.relations.operate(self.identifier,self.operation())
        with self.assertRaises(VisualizationError):self.relations.submit(self.identifier,self.answer(values=dict.fromkeys(PROPERTIES)))
        with self.assertRaises(ValidationError):self.answer(values=dict.fromkeys(PROPERTIES,1))
        with self.assertRaises(ValidationError):RelationTarget(**dict(self.target().model_dump(),property='execute'))
        with self.assertRaises(ValidationError):self.operation(present=1)

    def test_scope_forget_and_delayed_write(self):
        self.assessment();self.relations.submit(self.identifier,self.answer())
        for student,tab in [('s','other'),('other','tab')]:
            with self.assertRaises(VisualizationError):self.relations.get(self.identifier,student,tab)
        self.memory.repo.forget_learning_point('s',POINT)
        with session_scope() as session:
            self.assertIsNone(session.get(RelationRow,self.identifier))
            self.assertEqual(len(session.scalars(select(LearningEventRow).where(LearningEventRow.event_type=='relation_submission')).all()),0)
        with self.assertRaises(VisualizationError):self.relations.submit(self.identifier,self.answer())

    def test_memory_failure_rolls_back_submission(self):
        self.assessment()
        with patch.object(self.relations.repo,'add_event_evidence',side_effect=RuntimeError('模拟失败')):
            with self.assertRaises(RuntimeError):self.relations.submit(self.identifier,self.answer())
        self.assertIsNone(self.relations.get(self.identifier,'s','tab')['feedback'])

    def test_ai_snapshot_selected_pair_hint_scope_and_leak_check(self):
        from agents.task_context_builder import TaskContextBuilder
        from agents.task_execution import build_execution
        from agents.quality_checker import QualityChecker
        from agents.teaching_planner import TeachingPlan
        self.assessment()
        context=TaskContextBuilder().build(student_id='s',session_id='tab',message='解释所选性质',knowledge_point=POINT,relation_target=self.target())
        self.assertEqual(context.relation_snapshot['selected_pair'],{'source':'a','target':'c'})
        self.assertNotIn('evaluation',context.prompt_payload()['relation_snapshot'])
        execution=build_execution(context.message,TaskContextBuilder.button_task(context,'explain'),context)
        self.assertTrue(execution.hint_only);self.assertEqual(execution.target_refs,[target_key(context.relation_snapshot)])
        plan=TeachingPlan(goal=POINT,strategy='progressive_hinting',action='give_hint',difficulty='easy')
        for text in ('当前关系不满足传递性。','所以应补上 (a,c)。'):
            self.assertTrue(QualityChecker._rule_check(text,plan,{'relation_snapshot':context.relation_snapshot}))
        self.assertFalse(QualityChecker._rule_check('先检查是否存在相连的两条有向边。',plan,{'relation_snapshot':context.relation_snapshot}))
        self.assertFalse(self.relations.submit(self.identifier,self.answer())['independent'])

    def test_change_during_ai_and_rollout(self):
        from agents.task_service import TaskService
        from models.chat_request import ChatRequest
        import os
        request=ChatRequest(student_id='s',session_id='tab',request_id='ask',message='解释当前关系',relation_target=self.target())
        def execute(request,context,resolved,intercept,guard,progress):
            self.assertEqual(context.knowledge_point,POINT)
            self.relations.operate(self.identifier,self.operation())
            guard();self.fail('不能保存过期回答')
        result=TaskService(SimpleNamespace(memory=self.memory)).run(request,execute)
        self.assertEqual(result['answer_status'],'visualization_changed')
        with patch.dict(os.environ,{'VISUALIZATION_ROLLOUT':'off'}):
            self.assertTrue(self.relations.get(self.identifier,'s','tab')['readonly'])
            with self.assertRaises(VisualizationError):self.relations.save_draft(self.identifier,self.answer(expected_revision=2))


if __name__=='__main__':unittest.main()
