import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from agents.quality_checker import QualityChecker
from agents.proof_checker import CHECKS
from agents.teaching_planner import TeachingPlan
from models.student_state import StudentState
from llm.client import LLMError

class ParallelQualityTests(unittest.TestCase):
    def audit(self):
        return {'checks':[{'name':n,'status':'verified','quote':'','reason':'通过'} for n in CHECKS]}
    def check(self,callback):
        llm=SimpleNamespace(mock=False,chat_json=Mock(side_effect=callback))
        return QualityChecker(llm).check('设e={u,v}，删边后通路与e成环，矛盾。',StudentState(),TeachingPlan(goal='证明',strategy='worked_example',action='explain',difficulty='medium'),'补充证明',textbook_excerpts='无回路')
    def test_independent_checks_overlap_and_both_finish_before_acceptance(self):
        barrier=threading.Barrier(2);finished=[]
        def call(messages,**kwargs):
            proof='AGENT:proof_checker' in messages[0]['content']
            barrier.wait(timeout=1)
            finished.append('proof' if proof else 'teaching')
            return self.audit() if proof else {'passed':True,'issues':[],'suggestions':''}
        result=self.check(call)
        self.assertTrue(result.passed)
        self.assertEqual(set(finished),{'proof','teaching'})
        self.assertEqual(result.timings['mode'],'parallel')
    def test_teaching_failure_cannot_be_overridden_by_passed_proof(self):
        def call(messages,**kwargs):
            return self.audit() if 'AGENT:proof_checker' in messages[0]['content'] else {'passed':False,'issues':['没有回应请求'],'suggestions':''}
        result=self.check(call);self.assertFalse(result.passed);self.assertTrue(result.proof_audit.passed)
    def test_teaching_exception_blocks_publication(self):
        def call(messages,**kwargs):
            if 'AGENT:proof_checker' in messages[0]['content']:return self.audit()
            raise LLMError('provider error')
        result=self.check(call);self.assertFalse(result.passed)
        self.assertIn('未完成',result.issues[0])
    def test_proof_exception_blocks_publication(self):
        def call(messages,**kwargs):
            if 'AGENT:proof_checker' in messages[0]['content']:raise LLMError('timeout')
            return {'passed':True,'issues':[],'suggestions':''}
        result=self.check(call);self.assertFalse(result.passed);self.assertEqual(result.proof_audit.status,'unavailable')

if __name__=='__main__':unittest.main()
