import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from agents.psychology_qa import explain

SOURCE={'text':'被试间设计中，不同的实验处理使用不同的被试。','section':'第一节 被试间设计概述',
        'reference':{'rects':[{'page':1}],'section_id':1}}
GATE={'status':'sufficient','source_ids':['1'],'missing':[],'reason':'定义充分'}

class PsychologyQATests(unittest.TestCase):
    def model(self, *results):
        return SimpleNamespace(mock=False,chat_json=Mock(side_effect=results))

    def test_supported_answer_has_only_used_clickable_sources(self):
        llm=self.model(GATE,{'answer':'**被试间设计**使用不同被试接受不同处理。[1]'},
                       {'supported':True,'reason':'定义与引用一致'})
        result=explain(llm,'什么是被试间设计？',[SOURCE])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['citations'][0]['reference'],SOURCE['reference'])
        self.assertIn('实验心理学',llm.chat_json.call_args_list[0].args[0][0]['content'])

    def test_unknown_citation_never_published(self):
        llm=self.model(GATE,{'answer':'错误引用[99]'})
        result=explain(llm,'概念',[SOURCE])
        self.assertEqual(result['status'],'unavailable')
        self.assertEqual(result['citations'],[])
        self.assertNotIn('错误引用',result['answer'])

    def test_rejected_draft_never_published(self):
        llm=self.model(GATE,{'answer':'草稿把相关说成因果。[1]'},
                       {'supported':False,'reason':'因果结论不受证据支持'})
        result=explain(llm,'解释',[SOURCE])
        self.assertEqual(result['status'],'rejected')
        self.assertNotIn('草稿',result['answer'])

    def test_partial_evidence_stops_generation(self):
        llm=self.model({'status':'partial','source_ids':['1'],'missing':['统计结果'],'reason':'未提供结果'})
        result=explain(llm,'计算显著性',[SOURCE])
        self.assertEqual(result['status'],'partial')
        self.assertEqual(llm.chat_json.call_count,1)

    def test_mock_is_not_real_validation(self):
        self.assertEqual(explain(SimpleNamespace(mock=True),'解释',[SOURCE])['status'],'unavailable')

if __name__=='__main__':unittest.main()
