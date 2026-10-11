"""符号规则的等价性、解析边界及实际 API/技能接线。"""
import json
import unittest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
import practice_api as practice
from knowledge.symbolic_answers import equivalent
from knowledge.exercise_graders import evaluate_rule
from tests import test_exercise_skills as fixtures

class SymbolicMathTests(unittest.TestCase):
    def setUp(self):
        self.exp=practice.keys()['ex-03-01-002']['p3']
        self.poly=practice.keys()['ex-07-01-002']['p2']

    def test_polynomial_equivalence_is_exact(self):
        for value in ['n-1','-1+n','(2*n-2)/2','n+0.5-1.5',r'\frac{2*n-2}{2}']:
            self.assertTrue(equivalent(value,'n-1',self.poly),value)
        self.assertTrue(equivalent('m+(-k)','m-k',self.poly))
        self.assertTrue(equivalent('(n+m)*(n-m)','n^2-m^2',self.poly))
        self.assertFalse(equivalent('n+1','n-1',self.poly))

    def test_simple_exponential_equivalence(self):
        for value in ['3^n','3**n','3^{n}','3^(n+1)/3','3*3^(n-1)',r'\frac{3^{n+1}}{3}','(3^n+3^n)/2']:
            self.assertTrue(equivalent(value,'3^n',self.exp),value)
        self.assertFalse(equivalent('3^n+1','3^n',self.exp))
        self.assertFalse(equivalent('3^(2*n)','3^n',self.exp))

    def test_finite_sample_agreement_does_not_imply_identity(self):
        # 此错误式在 n=0,1,2,3 时恰好与答案相等。
        self.assertFalse(equivalent('3^n+n*(n-1)*(n-2)*(n-3)','3^n',self.exp))

    def test_unsupported_operators_names_functions_and_domains_are_unknown(self):
        expressions=['__import__("os").system("echo unsafe")','n.__class__','[n]','n if n else 1',
            'sin(n)','N-1','n/(n+1)','n/n','n^-1','9^n','3^(n/2)','3^(n*n)','3^(n+m)','3^(-n)']
        for value in expressions:
            with self.assertRaises((ValueError,SyntaxError)):
                equivalent(value,'3^n',self.exp)

    def test_scale_limits_are_enforced(self):
        for value in ['n^13','3^(n+13)','1e101','9'*257,'+'.join(['n']*45),'(n+m+k)^12*(n+m+k)']:
            with self.assertRaises((ValueError,SyntaxError)):
                equivalent(value,'n',self.poly)

    def test_partial_feedback_and_unknown_are_not_confused(self):
        q=practice.question('ex-07-01-002');p=q['parts'][1]
        out=evaluate_rule(p,['n-1','m','n','m-1'],self.poly)
        self.assertEqual(out['score'],75);self.assertEqual(out['verdict'],'partial');self.assertTrue(out['confirmed'])
        unknown=evaluate_rule(p,['n-1','m-k','n/n','m-1'],self.poly)
        self.assertEqual(unknown['verdict'],'uncertain');self.assertFalse(unknown['confirmed']);self.assertIsNone(unknown['score'])

class SymbolicSkillAPITests(unittest.TestCase):
    setUp=fixtures.ExerciseSkillTests.setUp
    tearDown=fixtures.ExerciseSkillTests.tearDown

    def post(self,qid,answers):
        app=FastAPI();app.include_router(practice.router)
        main=SimpleNamespace(orchestrator=SimpleNamespace(memory=self.memory))
        with patch.dict('sys.modules',{'main':main}),patch.object(practice,'student',return_value='s'),patch.object(practice,'ai_parts',side_effect=AssertionError('符号规则不得调 AI')):
            with TestClient(app) as client:
                body={'student_id':'s','version':self.version,'request_id':uuid4().hex,'answers':answers}
                response=client.post('/api/practice/questions/'+qid+'/submit',json=body)
                self.assertEqual(response.status_code,200,response.text)
                return client.get('/api/practice/submissions/'+response.json()['id'],params={'student_id':'s'}).json()

    def test_room_assignment_equivalent_answer_reaches_skill_memory(self):
        qid='ex-03-01-002';row=self.post(qid,{'p3':[r'\frac{3^{n+1}}{3}']})
        self.assertEqual(row['status'],'completed');self.assertEqual(row['result']['confirmed_score'],100)
        point=practice.question(qid)['knowledge_point'];item=self.memory.skill_summary('s',point)[0]
        self.assertEqual(item['skill_id'],'count.room_assignment');self.assertAlmostEqual(item['mastery_estimate'],.7)
        self.assertEqual(self.memory.get_state('s',point).mastery,.5)

    def test_graph_deletion_exposes_four_blanks_and_accepts_four_answers(self):
        qid='ex-07-01-002';q=practice.public_question(practice.question(qid));p=q['parts'][1]
        self.assertEqual(p['blank_count'],4);self.assertEqual(p['grader'],'rule')
        self.assertNotIn('3^n',p['answer_format']['instruction'])
        self.assertNotIn('"expected"',json.dumps(q))
        with self.assertRaises(practice.HTTPException):
            practice.validate_answers(practice.question(qid),{'p2':['n-1']})
        row=self.post(qid,{'p2':['-1+n','m+(-k)','n','m-1']})
        self.assertEqual(row['result']['confirmed_score'],100)
        item=self.memory.skill_summary('s',practice.question(qid)['knowledge_point'])[0]
        self.assertEqual(item['skill_id'],'graph.deletion_counts');self.assertEqual(item['independent_items'],1)

    def test_partial_symbolic_result_has_scoped_skill_feedback(self):
        qid='ex-07-01-002';row=self.post(qid,{'p2':['n-1','m','n','m-1']})
        self.assertEqual(row['result']['confirmed_score'],75)
        point=practice.question(qid)['knowledge_point'];item=self.memory.skill_summary('s',point)[0]
        self.assertAlmostEqual(item['mastery_estimate'],.6);self.assertTrue(item['needs_review'])
        self.assertEqual(self.memory.get_misconceptions('s',point),[])

    def test_unparseable_answer_does_not_measure_skill(self):
        qid='ex-03-01-002';row=self.post(qid,{'p3':['3n']})
        self.assertEqual(row['status'],'completed');self.assertIsNone(row['result']['confirmed_score'])
        self.assertTrue(row['result']['needs_review'])
        self.assertEqual(self.memory.skill_summary('s',practice.question(qid)['knowledge_point']),[])

if __name__=='__main__':unittest.main()
