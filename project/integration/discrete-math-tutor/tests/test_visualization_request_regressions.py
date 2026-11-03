"""普通讲解请求和多模板输出的图解回归。"""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from knowledge.textbook import TextbookChunk
from visualization.on_demand import CACHE, generate_guide, permitted, source_reference
from llm.client import LLMClient, LLMError, LLMJSONError


class VisualizationRequestTests(unittest.TestCase):
    def setUp(self):
        CACHE.clear()
        self.execution = SimpleNamespace(hint_only=False, learning_intents=['explain'])

    def test_native_json_mode_is_opt_in_and_deepseek_only(self):
        client = LLMClient(mock=False)
        transport = Mock()
        transport.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"plans":[]}'), finish_reason='stop')], usage=None)
        with patch.object(client, '_client_lazy', return_value=transport), patch.dict('os.environ', {'DEEPTUTOR_LLM_ENABLED':'0'}):
            client.base_url = 'https://api.deepseek.com'
            client._one_call([{'role':'user','content':'JSON'}], .1, 100, json_mode=True)
            self.assertEqual(transport.chat.completions.create.call_args.kwargs['response_format'], {'type':'json_object'})
            client._one_call([{'role':'user','content':'JSON'}], .1, 100)
            self.assertNotIn('response_format', transport.chat.completions.create.call_args.kwargs)
            client.base_url = 'https://example.test'
            client._one_call([{'role':'user','content':'JSON'}], .1, 100, json_mode=True)
            self.assertNotIn('response_format', transport.chat.completions.create.call_args.kwargs)

    def test_negated_exercise_is_not_an_exercise_request(self):
        self.assertTrue(permitted('请解释自变量和因变量，只讲解不要出题。', self.execution))
        self.assertTrue(permitted('解释变量，无需出题。', self.execution))
        self.assertFalse(permitted('请解释变量，然后出一道题。', self.execution))
        self.assertFalse(permitted('不要出题，再出一道题。', self.execution))
        self.assertFalse(permitted('只给提示，不要出题。', self.execution))
        self.assertFalse(permitted('不要出题', SimpleNamespace(hint_only=True, learning_intents=['hint'])))

    @patch.dict('os.environ', {'VISUALIZATION_ON_DEMAND': '1', 'TUTOR_COURSE': 'experimental-psychology-3'})
    def test_excess_selected_templates_are_audited_after_retry(self):
        source = TextbookChunk('教材', '实验设计', '自变量由研究者操纵，因变量是测量结果。', frozenset(), chapter_id=2, section_id=2, chunk_id='source-1')
        payload = {'nodes': [{'id':'iv','label':'自变量'}, {'id':'dv','label':'因变量'}],
                   'edges': [{'source':'iv','target':'dv','label':'研究关系'}],
                   'steps': [{'node':'iv','text':'操纵条件'}, {'node':'dv','text':'测量反应'}]}
        plan = {'template':'variable_map','title':'变量关系','source_index':0,'evidence_index':0,
                'origin':'teaching_example','payload':payload}
        llm = Mock()
        extra = {'template':'experiment_flow'}
        llm.chat_json.side_effect = [
            {'templates':['variable_map','experiment_flow']}, {'plans':[plan, extra]},
            {'plans':[plan, extra]}, {'passed':True,'issues':[]},
        ]
        references = [self.reference('source-1', 0)]
        guide = generate_guide(llm, '解释变量关系', '自变量与因变量', [source], self.execution,
                               student_id='isolated', turn_id='partial', references=references)
        self.assertIsNotNone(guide)
        self.assertEqual(guide['generation']['templates'], ['variable_map'])
        self.assertEqual(len(guide['frames']), 2)
        self.assertEqual(llm.chat_json.call_count, 4)

    def test_preset_ignores_only_presentation_constraints(self):
        from visualization.psychology_presets import match_topic
        source = SimpleNamespace(chapter_id=2, section_id=2, source='chapter.txt')
        reply = '自变量是操纵的条件，因变量是测量的结果。'
        with patch('visualization.psychology_presets.document_for_chapter', return_value={'source':'chapter.txt'}):
            self.assertEqual(match_topic('请解释自变量和因变量，只讲解不要出题。', reply, [source], self.execution), 'variables')
            self.assertIsNone(match_topic('解释音乐实验中自变量和因变量，只讲解不要出题。', reply, [source], self.execution))

    @patch.dict('os.environ', {'VISUALIZATION_ON_DEMAND': '1'})
    def test_unknown_partial_template_is_rejected(self):
        source = TextbookChunk('教材', '实验设计', '自变量由研究者操纵。', frozenset(), chapter_id=2, section_id=2, chunk_id='source-1')
        llm = Mock()
        llm.chat_json.side_effect = [{'templates':['variable_map','experiment_flow']},
                                    {'plans':[{'template':'unknown'}]}, {'plans':[{'template':'unknown'}]}]
        self.assertIsNone(generate_guide(llm, '解释变量', '解释', [source], self.execution,
                                         student_id='isolated', turn_id='unknown'))
        self.assertEqual(llm.chat_json.call_count, 3)

    @patch.dict('os.environ', {'VISUALIZATION_ON_DEMAND': '1'})
    def test_invalid_json_retries_once_and_still_checks_evidence_and_content(self):
        source = TextbookChunk('教材', '实验设计', '自变量由研究者操纵。', frozenset(), chapter_id=2, section_id=2, chunk_id='source-1')
        payload = {'nodes':[{'id':'iv','label':'自变量'}], 'edges':[],
                   'steps':[{'node':'iv','text':'操纵条件'}]}
        plan = {'template':'variable_map','title':'变量','source_index':0,'evidence_index':0,
                'origin':'teaching_example','payload':payload}
        refs = [self.reference('source-1', 0)]
        llm = Mock()
        llm.chat_json.side_effect = [{'templates':['variable_map']}, LLMJSONError('invalid'),
                                     {'plans':[plan]}, {'passed':True,'issues':[]}]
        guide = generate_guide(llm, '解释变量', '讲解', [source], self.execution,
                               student_id='isolated', turn_id='json-retry', references=refs)
        self.assertIsNotNone(guide)
        self.assertEqual(llm.chat_json.call_count, 4)
        self.assertIn('无法解析', llm.chat_json.call_args_list[2].args[0][1]['content'])

        CACHE.clear()
        llm.chat_json.reset_mock()
        llm.chat_json.side_effect = [{'templates':['variable_map']}, LLMJSONError('invalid'),
                                     {'plans':[plan]}, {'passed':False,'issues':['不支持']}]
        self.assertIsNone(generate_guide(llm, '解释变量', '讲解', [source], self.execution,
                                         student_id='isolated', turn_id='json-audit', references=refs))

    @patch.dict('os.environ', {'VISUALIZATION_ON_DEMAND': '1'})
    def test_json_retry_bounded_and_other_model_error_not_retried(self):
        source = TextbookChunk('教材', '实验设计', '自变量由研究者操纵。', frozenset(), chapter_id=2, section_id=2, chunk_id='source-1')
        for error, expected in ((LLMJSONError('invalid'), 3), (LLMError('unavailable'), 2)):
            with self.subTest(error=type(error).__name__):
                llm = Mock()
                llm.chat_json.side_effect = [{'templates':['variable_map']}, error, error]
                self.assertIsNone(generate_guide(llm, '解释变量', '讲解', [source], self.execution,
                                                 student_id='isolated', turn_id=type(error).__name__))
                self.assertEqual(llm.chat_json.call_count, expected)

    @patch.dict('os.environ', {'VISUALIZATION_ON_DEMAND': '1'})
    def test_selector_json_retry_and_audit_json_failure_never_publish(self):
        source = TextbookChunk('教材', '实验设计', '自变量由研究者操纵。', frozenset(), chapter_id=2, section_id=2, chunk_id='source-1')
        plan = {'template':'variable_map','title':'变量','source_index':0,'evidence_index':0,
                'origin':'teaching_example','payload':{'nodes':[{'id':'iv','label':'自变量'}],
                'edges':[], 'steps':[{'node':'iv','text':'操纵条件'}]}}
        refs = [self.reference('source-1', 0)]
        llm = Mock()
        llm.chat_json.side_effect = [LLMJSONError('invalid'), {'templates':['variable_map']},
                                     {'plans':[plan]}, LLMJSONError('invalid'),
                                     {'plans':[plan]}, LLMJSONError('invalid')]
        self.assertIsNone(generate_guide(llm, '解释变量', '讲解', [source], self.execution,
                                         student_id='isolated', turn_id='audit-json', references=refs))
        self.assertEqual(llm.chat_json.call_count, 6)

    @staticmethod
    def reference(source_id, index):
        return {'source_index':index, 'evidence':{'retrieval_source_id':source_id,
                'document_id':'doc','document_version':'v1','chapter_id':2,'section_id':2},
                'selection_ref':{'document_id':'doc','version':'v1','rects':[{'page':1}]}}

    def test_reference_identity_not_published_index(self):
        source = TextbookChunk('教材', '实验设计', '正文', frozenset(), chapter_id=2, section_id=2, chunk_id='source-1')
        wrong = self.reference('source-2', 0)
        correct = self.reference('source-1', 1)
        self.assertEqual(source_reference(source, [wrong, correct]), correct['selection_ref'])
        correct['selection_ref']['version'] = 'other'
        self.assertIsNone(source_reference(source, [wrong, correct]))


if __name__ == '__main__':
    unittest.main()
