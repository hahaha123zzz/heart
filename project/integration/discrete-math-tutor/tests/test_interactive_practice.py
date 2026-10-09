"""逐题练习的导入、账户隔离、幂等提交与草稿恢复验证。"""
import json,os,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import patch
_TMP=tempfile.TemporaryDirectory()
os.environ['DATABASE_URL']='sqlite:///'+str(Path(_TMP.name)/'practice.db')
os.environ['LLM_MOCK']='1'
from fastapi.testclient import TestClient
import main,practice_api as p
from sqlalchemy import select
from database.database import session_scope
from database.models import ExerciseSubmissionRow,ExerciseDraftRow
C=TestClient(main.app)
class PracticeTest(unittest.TestCase):
 def setUp(self):self.sid='practice-test-'+uuid.uuid4().hex[:12];self.version=p.catalog()['version'];self.q='ex-01-01-001'
 def body(self,answers):return {'student_id':self.sid,'version':self.version,'answers':answers}
 def test_coverage_and_numbering(self):
  audit=json.loads((p.ROOT/'knowledge/exercises/import_audit.json').read_text(encoding='utf8'))
  self.assertEqual(len(audit),31);self.assertTrue(all(a['match'] for a in audit));self.assertEqual(len(p.catalog()['questions']),341)
  self.assertEqual(sum(len(q['parts']) for q in p.catalog()['questions']),788)
  for q in p.catalog()['questions']:
   self.assertEqual(len({part['id'] for part in q['parts']}),len(q['parts']));self.assertTrue(q['source']['end_page']>=q['source']['page'])
 def test_draft_restore_and_isolation(self):
  a={'p1':['A']};self.assertEqual(C.put(f'/api/practice/questions/{self.q}/draft',json=self.body(a)).status_code,200)
  self.assertEqual(C.get(f'/api/practice/questions/{self.q}',params={'student_id':self.sid}).json()['answers'],a)
  other=C.get(f'/api/practice/questions/{self.q}',params={'student_id':'different-student'}).json();self.assertEqual(other['answers'],{});self.assertEqual(other['history'],[])
  self.assertNotIn('expected',json.dumps(other['question']))
 def test_rules_idempotency_and_history(self):
  body=self.body({'p1':['A'],'p2':['A']})|{'request_id':'request-12345'}
  r=C.post(f'/api/practice/questions/{self.q}/submit',json=body);self.assertEqual(r.status_code,200,r.text)
  r=C.get('/api/practice/submissions/'+r.json()['id'],params={'student_id':self.sid});data=r.json();self.assertEqual(data['status'],'completed',data);self.assertEqual(data['result']['confirmed_score'],50)
  results=data['result']['parts'];self.assertEqual([v['verdict'] for v in results],['correct','incorrect']);self.assertFalse(data['result']['needs_review'])
  second=C.post(f'/api/practice/questions/{self.q}/submit',json=body);self.assertEqual(second.json()['id'],data['id'])
  self.assertEqual(C.get('/api/practice/submissions/'+data['id'],params={'student_id':'someone-else'}).status_code,404)
  body['answers']={'p1':['B']};self.assertEqual(C.post(f'/api/practice/questions/{self.q}/submit',json=body).status_code,409)
 def test_invalid_answers_versions_and_graph(self):
  for a in ({'unknown':[]},{'p1':['Z']},{'p1':['A','B']},{'p1':'A'}):self.assertEqual(C.put(f'/api/practice/questions/{self.q}/draft',json=self.body(a)).status_code,422)
  body=self.body({'p1':['A']});body['version']='0'*64;self.assertEqual(C.put(f'/api/practice/questions/{self.q}/draft',json=body).status_code,409)
  q=next(q for q in p.catalog()['questions'] if any(x['type']=='graph' for x in q['parts']));part=next(x for x in q['parts'] if x['type']=='graph');a={'nodes':[{'id':'n1','x':.5,'y':.5,'label':'v1'}],'edges':[],'directed':False,'note':''}
  self.assertTrue(p.filled(a));p.validate_answers(q,{part['id']:a});a['edges']=[['n1','n999']]
  with self.assertRaises(Exception):p.validate_answers(q,{part['id']:a})
 def test_ai_failure_recovery(self):
  q='ex-01-01-003';body=self.body({'p1':{'text':'因为 A={{b}}，所以 b 属于 A','latex':''}})|{'request_id':'fail-123456'}
  with patch.object(p,'ai_parts',side_effect=RuntimeError('simulated outage')):r=C.post(f'/api/practice/questions/{q}/submit',json=body)
  data=C.get('/api/practice/submissions/'+r.json()['id'],params={'student_id':self.sid}).json();self.assertEqual(data['status'],'failed');self.assertEqual(data['answers'],body['answers'])
  self.assertEqual(C.get(f'/api/practice/questions/{q}',params={'student_id':self.sid}).json()['answers'],body['answers'])
 def test_ai_result_never_confirmed(self):
  q=p.question('ex-01-01-003');part=q['parts'][0]
  with patch.object(p,'exercise_context',return_value={'context':'context','images':[]}),patch.object(p,'memory_for',return_value={'summary':'暂无相关记录'}),patch.object(main.orchestrator.llm,'chat_json',return_value={'parts':[{'part_id':part['id'],'verdict':'uncertain','score':100,'feedback':'题目推理不成立','reference_answer':'A={b}','steps':[]}]}):
   r=p.ai_parts(q,[part],{part['id']:{'text':'test','latex':''}},self.sid)
  self.assertFalse(r[0]['confirmed']);self.assertIsNone(r[0]['score'])
 def test_hint_receives_grading_spec(self):
  q=p.question('ex-01-01-003');part=q['parts'][0]
  with patch.object(p,'exercise_context',return_value={'context':'context','images':[],'reference':{'image_refs':[]}}),patch.object(p,'memory_for',return_value={'summary':'暂无相关记录'}),patch.object(main.orchestrator.llm,'chat_json',return_value={'reply':'先使用单元素集合的定义'}) as model:
   result=p.ai_parts(q,[part],{},self.sid,'hint',1)
  self.assertIn('单元素集合',result['reply']);self.assertIn('rubric',model.call_args.args[0][-1]['content'])
 def test_set_equivalence_and_safe_parser(self):
  from knowledge.exercise_graders import finite_set,rational,evaluate_rule
  self.assertEqual(finite_set(r'\left\{7,1,3,5\right\}'),finite_set('{1,3,5,7}'))
  self.assertEqual(finite_set(r'{4,\frac{3}{2},\frac{2}{3},\frac{1}{4}}'),finite_set('{1/4,2/3,3/2,4}'))
  self.assertEqual(rational('0.25'),rational('1/4'))
  with self.assertRaises(ValueError):rational('1e100000000')
  with self.assertRaises(ValueError):rational('__import__("os").system("echo test")')
  part=p.question('ex-01-01-002')['parts'][0];key=p.keys()['ex-01-01-002']['p1']
  self.assertEqual(evaluate_rule(part,['{7,5,3,1}','{4,3/2,2/3,1/4}'],key)['score'],100)
  self.assertEqual(evaluate_rule(part,['{1,3,5}','{4,3/2,2/3,1/4}'],key)['score'],50)
 def test_truth_table_permutations_and_counterexample(self):
  from knowledge.exercise_graders import evaluate_rule,logic_tree,logic_value
  key=p.keys()['ex-04-01-004']['p3'];part=p.question('ex-04-01-004')['parts'][2]
  rows=[['1','1','1'],['0','1','0'],['1','0','1'],['0','0','1']]
  self.assertEqual(evaluate_rule(part,{'cells':rows,'note':''},key)['score'],100)
  rows[1][2]='1';self.assertEqual(evaluate_rule(part,{'cells':rows,'note':''},key)['score'],75)
  with self.assertRaises(ValueError):logic_tree('(p∨qr)→s')
  self.assertFalse(logic_value(logic_tree('p→q'),{'p':True,'q':False}))
 def test_delete_student_cascades(self):
  C.put(f'/api/practice/questions/{self.q}/draft',json=self.body({'p1':['A']}));C.post(f'/api/practice/questions/{self.q}/submit',json=self.body({'p1':['A']})|{'request_id':'cascade-1234'})
  C.delete('/api/accounts/test/'+self.sid)
  with session_scope() as db:
   self.assertIsNone(db.scalar(select(ExerciseDraftRow).where(ExerciseDraftRow.student_id==self.sid)));self.assertIsNone(db.scalar(select(ExerciseSubmissionRow).where(ExerciseSubmissionRow.student_id==self.sid)))
def tearDownModule():
 from database.database import engine
 engine.dispose();_TMP.cleanup()
if __name__=='__main__':unittest.main()
