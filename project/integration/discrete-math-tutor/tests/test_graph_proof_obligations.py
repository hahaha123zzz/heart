import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from agents.proof_checker import ProofChecker, CHECKS

class GraphProofObligationTests(unittest.TestCase):
    def audit(self,response):
        llm=SimpleNamespace(mock=False,chat_json=Mock(return_value={'checks':[{'name':n,'status':'verified','quote':'','reason':'通过'} for n in CHECKS]}))
        return ProofChecker(llm).check(response,'补充证明','每条边为割边'),llm
    def test_local_pair_cannot_certify_global_connectivity(self):
        audit,llm=self.audit('若u、v有两条通路则存在回路。取回路上一条边e，删去e后u、v仍相连，T仍连通。')
        self.assertFalse(audit.passed);self.assertEqual(audit.mode,'rules');llm.chat_json.assert_not_called()
    def test_endpoints_alone_need_arbitrary_path_replacement(self):
        audit,_=self.audit('取回路中的边e={a,b}。回路其余部分连接e的两端点，故T-e仍连通。')
        self.assertFalse(audit.passed)
    def test_explicit_path_replacement_can_proceed_to_model(self):
        audit,llm=self.audit('取回路边e={a,b}，回路剩余部分连接e的两端点。任意两点原来的通路不经过e则保留，经过e时用该绕行通路替换e，得到游走并可化为通路，故T-e仍连通。')
        self.assertTrue(audit.passed);llm.chat_json.assert_called_once()
    def test_conditional_connectedness_is_not_a_claim(self):
        audit,_=self.audit('设e={u,v}。删去e后若仍连通，则有不经过e的u到v通路，与e构成回路。')
        self.assertTrue(audit.passed)
    def test_assumption_with_graph_name_is_not_a_claim(self):
        audit,_=self.audit('反设T-e仍连通，则e两端存在另一条通路。')
        self.assertTrue(audit.passed)
    def test_criticism_is_not_a_claim(self):
        audit,_=self.audit('删去e后u、v相连不能推出T仍连通，需要检查任意顶点。')
        self.assertTrue(audit.passed)
    def test_real_rephrasing_cannot_bypass_guard(self):
        audit,_=self.audit('若x,y间有两条不同通路，则它们可拼出一条回路，回路上每条边删去后其余顶点仍连通，与每条边为割边矛盾。')
        self.assertFalse(audit.passed)
    def test_equivalent_arbitrary_path_wording_is_accepted(self):
        audit,_=self.audit('取回路边e，其两端点在回路剩余部分仍相连。任取两点的原通路，经过e时改走这条绕行通路，不经过则保留，故T-e仍连通。')
        self.assertTrue(audit.passed)
