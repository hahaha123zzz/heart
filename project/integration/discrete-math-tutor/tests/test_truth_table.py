"""真值表的数学、事务、选中行、提示及删除保护。"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import select
from pydantic import ValidationError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from database.database import session_scope
from database.models import TruthTableRow, LearningEventRow, EventEvidenceRow
from models.truth_table import CreateTruthTable, TableAnswers, TruthTableTarget
from visualization.truth_table import TruthTableService, results, POINT
from visualization.service import VisualizationError
from tests import test_visualization as fixtures


class TruthTableTests(unittest.TestCase):
    def setUp(self):
        fixtures.VisualizationTests.setUp(self)
        self.tables=TruthTableService()
        self.artifact=self.tables.create(CreateTruthTable(student_id='s',session_id='tab',request_id='table',expected_epoch=0))
        self.identifier=self.artifact['artifact_id']

    def tearDown(self):
        fixtures.VisualizationTests.tearDown(self)

    def answer(self, **updates):
        return TableAnswers(**dict(dict(student_id='s',session_id='tab',request_id='answer',expected_revision=1,
            values=results('implies'),explanation='前件真后件假是蕴含的反例。'),**updates))

    def target(self, **updates):
        return TruthTableTarget(**dict(dict(artifact_id=self.identifier,expected_revision=1,row_id='10',action='explain'),**updates))

    def test_all_templates_and_truth_assignments(self):
        self.assertEqual(list(results('implies').values()),[True,True,False,True])
        self.assertEqual(list(results('and').values()),[False,False,False,True])
        self.assertEqual(list(results('or').values()),[False,True,True,True])
        self.assertEqual(list(results('equivalent').values()),[True,False,False,True])
        self.assertEqual(results('not-or'),results('implies'))
        with self.assertRaises(ValidationError):CreateTruthTable(student_id='s',session_id='tab',request_id='bad',expected_epoch=0,template_id='code')
        with self.assertRaises(ValidationError):self.answer(values={'00':0,'01':True,'10':False,'11':True})

    def test_submit_hidden_answers_and_four_evidence_rows(self):
        self.assertIsNone(self.artifact['evaluation'])
        self.assertIsNone(self.artifact['feedback'])
        result=self.tables.submit(self.identifier,self.answer())
        self.assertTrue(result['correct']);self.assertTrue(result['independent'])
        self.assertFalse(result['mastery_updated']);self.assertFalse(result['explanation_verified'])
        self.assertEqual(self.tables.get(self.identifier,'s','tab')['revision'],2)
        with session_scope() as session:
            evidence=session.scalars(select(EventEvidenceRow).where(EventEvidenceRow.event_id==result['event_id'])).all()
            self.assertEqual(len(evidence),4)
            self.assertTrue(all(item.independent and item.verification=='rule_verified' for item in evidence))

    def test_draft_cas_idempotency_and_selected_row(self):
        request=self.answer(values={'00':None,'01':True,'10':None,'11':None})
        saved=self.tables.save_draft(self.identifier,request)
        self.assertEqual(saved['revision'],2)
        self.assertEqual(self.tables.save_draft(self.identifier,request),saved)
        with self.assertRaises(VisualizationError):self.tables.save_draft(self.identifier,self.answer(request_id='stale'))
        snapshot=self.tables.snapshot(self.target(expected_revision=2,row_id='01'),'s','tab')
        self.assertEqual(snapshot['assignment'],{'p':False,'q':True})
        self.assertEqual(snapshot['student_value'],True)

    def test_submission_idempotency_conflict_and_incomplete(self):
        with self.assertRaises(VisualizationError):self.tables.submit(self.identifier,self.answer(values={'00':None,'01':True,'10':False,'11':True}))
        result=self.tables.submit(self.identifier,self.answer())
        self.assertEqual(self.tables.submit(self.identifier,self.answer()),result)
        with self.assertRaises(VisualizationError):self.tables.submit(self.identifier,self.answer(request_id='another'))
        with session_scope() as session:
            self.assertEqual(len(session.scalars(select(LearningEventRow).where(LearningEventRow.event_type=='truth_table_submission')).all()),1)

    def test_correction_same_formula_original_unchanged_and_assisted(self):
        original=self.tables.submit(self.identifier,self.answer(values=dict.fromkeys(['00','01','10','11'],True)))
        self.assertFalse(original['correct'])
        request=CreateTruthTable(student_id='s',session_id='tab',request_id='correction',expected_epoch=0,
            template_id='and',correction_of=self.identifier)
        corrected=self.tables.create(request)
        self.assertEqual(corrected['template_id'],'implies')
        self.assertEqual(corrected['draft'],original['answers'])
        self.assertEqual(self.tables.create(request),corrected)
        result=self.tables.submit(corrected['artifact_id'],self.answer(request_id='corrected'))
        self.assertTrue(result['correct']);self.assertFalse(result['independent']);self.assertFalse(result['eligible'])
        self.assertEqual(self.tables.get(self.identifier,'s','tab')['feedback'],original)

    def test_transaction_rollback(self):
        with patch.object(self.tables.repo,'add_event_evidence',side_effect=RuntimeError('模拟失败')):
            with self.assertRaises(RuntimeError):self.tables.submit(self.identifier,self.answer())
        self.assertIsNone(self.tables.get(self.identifier,'s','tab')['feedback'])
        with session_scope() as session:
            self.assertEqual(len(session.scalars(select(LearningEventRow).where(LearningEventRow.event_type=='truth_table_submission')).all()),0)

    def test_scope_forget_and_stale_snapshot(self):
        for student,tab in [('other','tab'),('s','other')]:
            with self.assertRaises(VisualizationError):self.tables.get(self.identifier,student,tab)
        snapshot=self.tables.snapshot(self.target(),'s','tab')
        self.tables.save_draft(self.identifier,self.answer())
        with self.assertRaises(VisualizationError):self.tables.guard_snapshot(snapshot,'s','tab')
        self.memory.repo.forget_learning_point('s',POINT)
        with session_scope() as session:self.assertIsNone(session.get(TruthTableRow,self.identifier))
        with self.assertRaises(VisualizationError):self.tables.submit(self.identifier,self.answer())

    def test_ai_context_hint_and_current_row_quality(self):
        from agents.task_context_builder import TaskContextBuilder
        from agents.task_execution import build_execution
        from agents.quality_checker import QualityChecker
        from agents.teaching_planner import TeachingPlan
        context=TaskContextBuilder().build(student_id='s',session_id='tab',message='解释这一行',knowledge_point=POINT,truth_table_target=self.target())
        self.assertEqual(context.truth_table_snapshot['assignment'],{'p':True,'q':False})
        self.assertIsNone(context.graph_snapshot)
        execution=build_execution('解释这一行',TaskContextBuilder.button_task(context,'explain'),context)
        self.assertTrue(execution.hint_only)
        self.assertEqual(len(execution.targets),1)
        plan=TeachingPlan(goal=POINT,strategy='progressive_hinting',action='give_hint',difficulty='easy')
        self.assertTrue(QualityChecker._rule_check('所以这一行的公式结果为假。',plan,{'truth_table_snapshot':context.truth_table_snapshot}))
        self.assertFalse(QualityChecker._rule_check('第一步，先检查前件的真值。',plan,{'truth_table_snapshot':context.truth_table_snapshot}))
        self.assertFalse(QualityChecker._rule_check('现在对照这一行，p 和 q 是否同时为真？',plan,{'truth_table_snapshot':context.truth_table_snapshot}))
        self.assertFalse(QualityChecker._rule_check('第一步核对 p 的真值为真，q 的真值为假；暂不写公式结果。',plan,{'truth_table_snapshot':context.truth_table_snapshot}))
        self.assertTrue(QualityChecker._rule_check('因此 p→q 应为假。',plan,{'truth_table_snapshot':context.truth_table_snapshot}))
        self.assertFalse(self.tables.submit(self.identifier,self.answer())['independent'])

    def test_task_guard_rejects_changes_during_answer(self):
        from agents.task_service import TaskService
        from models.chat_request import ChatRequest
        request=ChatRequest(student_id='s',session_id='tab',request_id='ask',message='解释选中行',truth_table_target=self.target())
        def executor(request,context,resolved,intercept,guard,progress):
            self.assertEqual(context.knowledge_point,POINT)
            self.tables.save_draft(self.identifier,self.answer())
            guard()
            self.fail('版本变化必须拒绝')
        result=TaskService(SimpleNamespace(memory=self.memory)).run(request,executor)
        self.assertEqual(result['answer_status'],'visualization_changed')

    def test_real_api_routes_and_scope_validation(self):
        from truth_table_api import router
        app=FastAPI();app.include_router(router)
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/truth-tables',params={'student_id':'s','session_id':'tab'}).status_code,200)
            path='/api/truth-tables/'+self.identifier
            self.assertEqual(client.get(path,params={'student_id':'s','session_id':'other'}).status_code,404)
            self.assertEqual(client.post(path+'/submissions',json=self.answer().model_dump()).status_code,200)

    def test_clarification_keeps_exact_row_and_revalidates_revision(self):
        from agents.task_service import TaskService
        from models.chat_request import ChatRequest
        from models.task_understanding import TaskUnderstanding
        tasks=TaskService(SimpleNamespace(memory=self.memory))
        request=ChatRequest(student_id='s',session_id='tab',request_id='clarify',message='解释这一行',truth_table_target=self.target())
        def clarify(request,context,resolved,intercept,guard,progress):
            self.assertNotIn('evaluation',context.prompt_payload()['truth_table_snapshot'])
            return intercept(TaskUnderstanding(status='unknown',intent='clarify_task',missing_slots=['target']))
        first=tasks.run(request,clarify)
        resume=ChatRequest(student_id='s',session_id='tab',request_id='resume',message='第一个',task_id=first['task_id'],task_revision=first['task_revision'])
        def execute(request,context,resolved,intercept,guard,progress):
            self.assertEqual(context.truth_table_snapshot['row_id'],'10')
            self.assertEqual(context.knowledge_point,POINT)
            intercept(TaskUnderstanding(learning_intents=['hint'],target_refs=[context.objects[0].id]))
            return {'answer_status':'answered','reply':'先查看联结词。'}
        self.assertEqual(tasks.run(resume,execute)['answer_status'],'answered')

    def test_rollout_off_readonly_and_rejects_edits(self):
        import os
        with patch.dict(os.environ,{'VISUALIZATION_ROLLOUT':'off'}):
            self.assertTrue(self.tables.get(self.identifier,'s','tab')['readonly'])
            self.assertIsNone(self.tables.get(self.identifier,'s','tab')['evaluation'])
            with self.assertRaises(VisualizationError):self.tables.save_draft(self.identifier,self.answer())
            with self.assertRaises(VisualizationError):self.tables.submit(self.identifier,self.answer())


if __name__=='__main__':unittest.main()
