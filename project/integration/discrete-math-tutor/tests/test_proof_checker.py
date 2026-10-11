import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from agents.proof_checker import ProofChecker, CHECKS, needs_proof_audit
from agents.quality_checker import QualityChecker
from agents.teaching_planner import TeachingPlan
from models.student_state import StudentState
from llm.client import LLMError

class ProofCheckerTests(unittest.TestCase):
    def data(self):
        return {'checks':[{'name':name,'status':'verified','quote':'','reason':'核对通过'} for name in CHECKS]}
    def check(self,data,response='设e={u,v}。删去e后若仍连通，则有不经过e的u到v通路，与e构成回路。'):
        llm=SimpleNamespace(mock=False,chat_json=Mock(return_value=data))
        return ProofChecker(llm).check(response,'补充这个证明','已知T无回路')
    def test_complete_audit_passes(self):
        self.assertTrue(self.check(self.data()).passed)
    def test_missing_check_does_not_pass(self):
        data=self.data();data['checks'].pop()
        self.assertFalse(self.check(data).passed)
    def test_duplicate_check_does_not_pass(self):
        data=self.data();data['checks'][-1]=data['checks'][0]
        self.assertFalse(self.check(data).passed)
    def test_rejection_requires_quote_from_actual_reply(self):
        data=self.data();data['checks'][0].update(status='rejected',quote='回答里没有这句话',reason='虚构问题')
        self.assertEqual(self.check(data).status,'unavailable')
    def test_undefined_endpoints_are_rejected(self):
        response='取不同分支的vi、vj。再设e为任一边，T中有不含e的vi到vj通路。'
        data=self.data();data['checks'][0].update(status='rejected',quote='再设e为任一边，T中有不含e的vi到vj通路',reason='没有将vi、vj重新定义为e的两端点，上一分支定义不能沿用')
        audit=self.check(data,response)
        self.assertFalse(audit.passed);self.assertEqual(audit.status,'rejected')
        self.assertIn('两端点',audit.issues[0])
    def test_uncertain_inference_does_not_pass(self):
        data=self.data();data['checks'][2].update(status='uncertain',quote='与e构成回路',reason='不能核验所需前提')
        self.assertFalse(self.check(data).passed)
    def test_failed_check_without_quote_is_unavailable(self):
        data=self.data();data['checks'][0].update(status='rejected',reason='变量不清楚')
        self.assertEqual(self.check(data).status,'unavailable')
    def test_model_cannot_forge_global_pass_or_mode(self):
        for extra in ({'passed':True},{'mode':'mock'}):
            self.assertEqual(self.check(self.data()|extra).status,'unavailable')
    def test_timeout_is_not_a_mathematical_rejection(self):
        llm=SimpleNamespace(mock=False,chat_json=Mock(side_effect=LLMError('timeout')))
        audit=ProofChecker(llm).check('回答','证明','正文')
        self.assertEqual(audit.status,'unavailable');self.assertFalse(audit.passed)
    def test_mock_mode_is_marked(self):
        audit=ProofChecker(SimpleNamespace(mock=True)).check('回答','证明','正文')
        self.assertEqual(audit.mode,'mock')
    def test_only_explanatory_proofs_require_audit(self):
        self.assertTrue(needs_proof_audit('解释定理的证明','解释','explain'))
        self.assertTrue(needs_proof_audit('为什么成立','反证假设不成立','explain'))
        self.assertFalse(needs_proof_audit('请出证明题','证明题','ask_question'))
        self.assertFalse(needs_proof_audit('解释图的顶点','顶点含义','explain'))
    def test_quality_must_not_override_failed_proof_audit(self):
        data=self.data();data['checks'][0].update(status='rejected',quote='任意边e',reason='未定义边的端点')
        llm=SimpleNamespace(mock=False,chat_json=Mock(side_effect=lambda messages,**kwargs:data if 'AGENT:proof_checker' in messages[0]['content'] else {'passed':True,'issues':[],'suggestions':'良好'}))
        quality=QualityChecker(llm).check('任意边e，有u到v的通路',StudentState(),TeachingPlan(goal='证明',strategy='worked_example',action='explain',difficulty='medium'),'补充证明',textbook_excerpts='已知图无回路')
        self.assertFalse(quality.passed);self.assertEqual(quality.proof_audit.status,'rejected')
    def test_ordinary_explanation_does_not_add_model_call(self):
        llm=SimpleNamespace(mock=False,chat_json=Mock(return_value={'passed':True,'issues':[],'suggestions':''}))
        QualityChecker(llm).check('顶点是图中的对象',StudentState(),TeachingPlan(goal='图',strategy='worked_example',action='explain',difficulty='easy'),'解释顶点',textbook_excerpts='顶点定义')
        self.assertEqual(llm.chat_json.call_count,1)

if __name__=='__main__':unittest.main()
