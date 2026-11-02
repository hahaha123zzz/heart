"""隔离评测允许观察模型改写，但不能修改原始规则结果。"""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from copy import deepcopy
import tempfile
import json

spec = importlib.util.spec_from_file_location('semantic_shadow',
    Path(__file__).resolve().parents[1] / 'scripts/check_semantic_shadow.py')
shadow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shadow)


class SemanticShadowTests(unittest.TestCase):
    def test_uncomparable_snapshot_never_reduces_effective_difference_rate(self):
        rows=[{'case_id':'a','parser':'rule','legacy_comparable':True,
               'legacy_differences':['intent'],'candidate_projection':{},'model_calls':0,
               'legacy_model_calls':0,'baseline_unchanged':True},
              {'case_id':'b','parser':'rule','legacy_comparable':False,
               'legacy_differences':[],'candidate_projection':None,'model_calls':0,
               'legacy_model_calls':0,'baseline_unchanged':True}]
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder)/'input.jsonl'; output=Path(folder)/'output.json'
            data.write_text('{"text":"a"}\n{"text":"b"}',encoding='utf-8')
            with patch('sys.argv',['check','--input',str(data),'--out',str(output),'--live','--legacy']), \
                 patch('llm.client.LLMClient'), patch.object(shadow,'compare_case',side_effect=rows):
                shadow.main()
            summary=json.loads(output.read_text(encoding='utf-8'))['summary']
        self.assertEqual(summary['difference_rate'],1.0)
        self.assertEqual(summary['unprojected'],1)
        self.assertIsNone(summary['effective_difference_rate'])
        self.assertFalse(summary['eligible_for_removal'])

    def test_interrupted_batch_keeps_completed_cases_without_claiming_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)/'input.jsonl'
            output = Path(folder)/'output.json'
            data.write_text('\n'.join(json.dumps({'text':text}) for text in ('a','b')),encoding='utf-8')
            with patch('sys.argv',['check','--input',str(data),'--out',str(output)]), \
                 patch.object(shadow,'compare_case',side_effect=[{'case_id':'done','parser':'rule'},ValueError('bad snapshot')]):
                with self.assertRaisesRegex(ValueError,'bad snapshot'):
                    shadow.main()
            saved = json.loads(output.read_text(encoding='utf-8'))
        self.assertFalse(saved['complete'])
        self.assertEqual(len(saved['cases']),1)
        self.assertFalse(saved['promoted'])

    def test_runtime_comparison_does_not_force_simple_input_into_model_parser(self):
        from models.task_understanding import TaskUnderstanding
        model = Mock()
        with patch('agents.conversation_router.ConversationRouter.route', return_value=TaskUnderstanding()):
            result = shadow.compare_case({'case_id':'simple','text':'解释自变量'},model,compare_legacy=True)
        self.assertEqual(result['model_calls'],0)
        self.assertEqual(result['candidate_mode'],'runtime_conditional')
        model.chat_json.assert_not_called()

    def test_snapshot_pending_and_preferences_are_not_mutated(self):
        from tests.test_adaptive_tutoring import prior
        sample = {'case_id':'snapshot','text':'只给提示，不要完整答案', 'context':{
            'student_id':'owner','session_id':'original','knowledge_point':'自变量',
            'tutoring':prior(pending=True), 'preferences':{'answer_length':1.0}}}
        original = deepcopy(sample)
        result = shadow.compare_case(sample)
        self.assertEqual(sample, original)
        self.assertTrue(result['context_unchanged'])
        self.assertTrue(result['baseline_unchanged'])

    def test_old_router_constraint_difference_is_visible(self):
        from models.task_understanding import TaskUnderstanding
        model = Mock()
        model.chat_json.return_value = {'tasks':[{'task_frame_id':'candidate',
            'action':'explain_content','query':'自变量'}]}
        with patch('agents.conversation_router.ConversationRouter.route', return_value=
                   TaskUnderstanding(student_move='question', learning_intents=['explain'])):
            result = shadow.compare_case({'case_id':'compare','text':'解释自变量，不要出题',
                                          'context':{'knowledge_point':'自变量'}},
                                         model, compare_legacy=True)
        self.assertTrue(result['legacy_comparable'])
        self.assertIn('answer_constraints',result['legacy_differences'])
        self.assertTrue(result['context_unchanged'])
        self.assertFalse(result['promoted'])

    def test_offline_never_calls_a_model(self):
        row = shadow.compare_case({'case_id':'a','text':'我分不清这两个概念'})
        self.assertEqual(row['model_calls'], 0)
        self.assertTrue(row['baseline_unchanged'])
        self.assertFalse(row['promoted'])

    def test_model_rewrite_is_only_reported(self):
        model = Mock()
        model.chat_json.return_value = {'tasks':[{'task_frame_id':'candidate',
            'action':'explain_content','query':'改写后的主题'}], 'labels':[
            {'dimension':'self_report','label':'confused','quote':'一团浆糊','source':'rule'}]}
        row = shadow.compare_case({'case_id':'b','text':'脑子里一团浆糊'}, model)
        self.assertTrue(row['baseline_unchanged'])
        self.assertTrue(row['task_changed'])
        self.assertFalse(row['promoted'])
        self.assertEqual(row['candidate_labels'][0]['label'], 'confused')
        self.assertEqual(row['candidate_labels'][0]['source'], 'model')
        self.assertEqual(model.chat_json.call_count, 1)
