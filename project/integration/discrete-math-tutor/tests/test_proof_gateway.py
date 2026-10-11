import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from llm.client import LLMClient
from agents.response_generator import ResponseGenerator
from agents.quality_checker import QualityChecker
from agents.teaching_planner import TeachingPlan
from models.student_state import StudentState

class ProofGatewayTests(unittest.TestCase):
    def client(self):
        client=LLMClient(api_key='unit-test-placeholder',base_url='https://api.deepseek.com',mock=False)
        create=Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"checks":[]}',reasoning_content='PRIVATE-REASONING'),finish_reason='stop')]))
        client._client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        return client,create
    def test_proof_mode_enables_reasoning_without_returning_private_reasoning(self):
        client,create=self.client()
        result=client.chat_json([{'role':'user','content':'核验'}],reasoning_effort='low',retries=0)
        self.assertEqual(result,{'checks':[]})
        self.assertEqual(create.call_args.kwargs['extra_body']['thinking']['type'],'enabled')
        self.assertEqual(create.call_args.kwargs['reasoning_effort'],'low')
        self.assertNotIn('PRIVATE-REASONING',str(result))
    def test_default_calls_still_disable_reasoning(self):
        client,create=self.client();client.chat([{'role':'user','content':'定义'}])
        self.assertEqual(create.call_args.kwargs['extra_body']['thinking']['type'],'disabled')
        self.assertNotIn('reasoning_effort',create.call_args.kwargs)
    def test_feedback_is_pending_data_not_system_authority(self):
        llm=SimpleNamespace(chat=Mock(return_value='解释'))
        plan=TeachingPlan(goal='证明',strategy='worked_example',action='explain',difficulty='medium')
        bad='添加边后端点仍无通路'
        ResponseGenerator(llm).generate(StudentState(),plan,'补充证明',[],feedback=bad,textbook_excerpts='原文')
        messages=llm.chat.call_args.args[0]
        self.assertNotIn(bad,messages[0]['content'])
        self.assertIn(bad,messages[-1]['content'])
        self.assertIn('待核实',messages[-1]['content'])
    def test_string_false_cannot_pass_quality_gate(self):
        llm=SimpleNamespace(mock=False,chat_json=Mock(return_value={'passed':'false','issues':[],'suggestions':''}))
        result=QualityChecker(llm).check('解释',StudentState(),TeachingPlan(goal='图',strategy='worked_example',action='explain',difficulty='easy'),'顶点含义')
        self.assertFalse(result.passed)
    def test_wrong_issue_shape_cannot_pass_quality_gate(self):
        llm=SimpleNamespace(mock=False,chat_json=Mock(return_value={'passed':True,'issues':'','suggestions':''}))
        result=QualityChecker(llm).check('解释',StudentState(),TeachingPlan(goal='图',strategy='worked_example',action='explain',difficulty='easy'),'顶点含义')
        self.assertFalse(result.passed)

    def test_proof_is_not_silently_cut_before_critical_conclusion(self):
        answer='证明。'+('说明。'*130)+'关键结论由这两个分情况推出。'
        llm=SimpleNamespace(chat=Mock(return_value=answer))
        plan=TeachingPlan(goal='证明',strategy='worked_example',action='explain',difficulty='medium')
        result=ResponseGenerator(llm).generate(StudentState(),plan,'补充这个证明',[])
        self.assertEqual(result,answer)
        self.assertTrue(QualityChecker._rule_check(result,plan,{'supplementary_proof':True}))

    def test_parallel_calls_share_one_lazy_client(self):
        import time,threading
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch
        client=LLMClient(api_key='unit-test-placeholder',mock=False)
        calls=[];barrier=threading.Barrier(2);shared=object()
        def construct(**kwargs):
            calls.append(1);time.sleep(.02);return shared
        def load():
            barrier.wait(timeout=1);return client._client_lazy()
        with patch('openai.OpenAI',side_effect=construct):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda _:load(),range(2)))
        self.assertEqual(len(calls),1)
        self.assertTrue(all(r is shared for r in results))

    def test_supplementary_proof_overrides_default_one_step_instruction(self):
        llm=SimpleNamespace(chat=Mock(return_value='补充推导'))
        plan=TeachingPlan(goal='证明',strategy='worked_example',action='explain',difficulty='medium')
        ResponseGenerator(llm).generate(StudentState(),plan,'请补充这个证明',[])
        prompt=llm.chat.call_args.args[0][0]['content']
        self.assertIn('在本轮完成该方向的全部必要推理',prompt)
        self.assertIn('不能把删边后任意路径的替换',prompt)

if __name__=='__main__':unittest.main()
