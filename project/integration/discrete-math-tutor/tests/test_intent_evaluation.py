"""评测必须把失败与澄清分开，并阻止跨集合泄漏。"""
import json
import tempfile
import unittest
from pathlib import Path
from scripts.eval_intent import score, load_cases, task_context, limit_model_calls


class IntentEvaluationTests(unittest.TestCase):
    def test_macro_f1_uses_missed_class_and_not_only_accuracy(self):
        cases = [{"id": "a", "expected": {"intent": "continue"}},
                 {"id": "b", "expected": {"intent": "off_task"}}]
        predictions = {i: {"prediction": {"intent": "continue", "status": "ok"}} for i in ("a", "b")}
        report = score(cases, predictions)
        self.assertEqual(report["field_scores"]["intent"]["accuracy"], .5)
        self.assertAlmostEqual(report["flow_macro_f1_supported_classes"], 1 / 3)

    def test_failure_is_not_successful_clarification(self):
        report = score([{"id": "a", "expected": {"intent": "clarify_task"}}],
                       {"a": {"prediction": {"intent": "clarify_task", "status": "parse_error"}}})
        self.assertEqual(report["necessary_clarification_recall"]["value"], 0)
        self.assertIsNone(report["unnecessary_clarification_rate"]["value"])

    def test_prediction_ids_cannot_silently_mismatch(self):
        with self.assertRaises(ValueError):
            score([{"id": "a", "expected": {"intent": "continue"}}], {})

    def test_template_leakage_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "cases.jsonl"
            rows = [{"id": i, "conversation_id": i, "template_family": "same-template",
                     "split": split, "expected": {"intent": "continue"}} for i, split in
                    (("a", "optimization"), ("b", "holdout"))]
            path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "泄漏"):
                load_cases(path)

    def task_case(self, **desired):
        return {'id':'task','input':{'message':'比较A和B','knowledge_point':'图','history':[],'known_points':[],
            'context':{'objects':[{'id':key,'kind':'pdf_selection','title':key,'chapter_id':7,'section_id':1} for key in ('a','b')]}},
            'expected':{'intent':'continue'},'desired_task':desired}

    def prediction(self, case, **overrides):
        from models.task_understanding import TaskUnderstanding
        return {'task':{'prediction':TaskUnderstanding(rewritten_query=case['input']['message'],**overrides).model_dump()}}

    def test_task_order_is_scored_and_target_order_is_not(self):
        case=self.task_case(learning_intents=['compare','example'],target_refs=['a','b'])
        report=score([case],self.prediction(case,learning_intents=['example','compare'],target_refs=['b','a']),router_mode='task')
        self.assertEqual(report['field_scores']['learning_intents']['correct'],0)
        self.assertEqual(report['multi_intent_order'],{'correct':0,'total':1,'accuracy':0})
        self.assertEqual(report['field_scores']['target_refs']['correct'],1)

    def test_unprovided_target_invalidates_even_other_matching_task_fields(self):
        case=self.task_case(learning_intents=['hint'],target_refs=['a'])
        report=score([case],self.prediction(case,learning_intents=['hint'],target_refs=['invented']),router_mode='task')
        self.assertEqual(report['status_counts'],{'parse_error':1})
        self.assertEqual(report['field_scores']['learning_intents']['correct'],0)

    def test_unresolved_gold_is_not_counted_as_target_failure(self):
        case=self.task_case(target_refs=['unresolved'])
        report=score([case],self.prediction(case),router_mode='task')
        self.assertNotIn('target_refs',report['field_scores'])
        self.assertEqual(report['unsupported_task_fields']['target_refs:unresolved_fixture'],1)

    def test_missing_task_output_cannot_get_empty_constraint_credit(self):
        case=self.task_case(answer_constraints=[])
        report=score([case],{'task':{'prediction':{'status':'ok','intent':'continue'}}},router_mode='task')
        self.assertEqual(report['field_scores']['answer_constraints']['correct'],0)

    def test_context_does_not_import_gold_targets(self):
        case=self.task_case(target_refs=['gold-secret'])
        context=task_context(case)
        self.assertEqual([obj.id for obj in context.objects],['a','b'])
        case['input']['context']['student_id']='other'
        with self.assertRaises(ValueError):task_context(case)

    def test_modified_formula_is_not_a_valid_task_prediction(self):
        case=self.task_case(learning_intents=['explain'])
        predictions=self.prediction(case,learning_intents=['explain'])
        predictions['task']['prediction']['rewritten_query']='另一个问题'
        report=score([case],predictions,router_mode='task')
        self.assertEqual(report['status_counts'],{'parse_error':1})

    def test_network_budget_includes_failed_calls_and_disables_sdk_retries(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from llm.client import LLMError
        sdk=Mock()
        gateway=Mock(side_effect=RuntimeError('模拟连接失败'))
        client=SimpleNamespace(_one_call=gateway,_client_lazy=lambda:sdk)
        budget=limit_model_calls(client,1)
        client._client_lazy();sdk.with_options.assert_called_once_with(max_retries=0)
        with self.assertRaises(RuntimeError):client._one_call([])
        with self.assertRaises(LLMError):client._one_call([])
        self.assertEqual(gateway.call_count,1)
        self.assertEqual(budget,{'attempts':1,'limit':1})


if __name__ == "__main__":
    unittest.main()
