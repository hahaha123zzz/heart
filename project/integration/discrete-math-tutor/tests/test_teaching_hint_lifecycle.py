"""三级提示与完整解释沿原题保存，不产生独立掌握证据。"""
from copy import deepcopy
import json
import unittest
from unittest.mock import Mock

from tests.test_adaptive_tutoring import SOURCE, assessment, prior, record, turn


class TeachingHintLifecycleTests(unittest.TestCase):
    def publish(self, old, message='再给一个提示', *, key='help', strategy=None):
        model = Mock()
        current = turn(message, old, model)
        current.request.request_id = key
        if strategy:
            self.assertTrue(record(current, strategy=strategy).success)
        current.commit_sources([SOURCE], '已发布的帮助内容。')
        model.chat_json.assert_not_called()
        return current

    def test_progresses_to_three_and_never_automatically_reveals_answer(self):
        old = prior(pending=True)
        question = old['progress']['pending_question']['question_id']
        for index, level in enumerate((1, 2, 3, 3)):
            current = self.publish(old, key='hint-' + str(index))
            self.assertEqual(current.public()['hint_level'], level)
            self.assertEqual(current.public()['assistance']['max_hint_level'], level)
            self.assertFalse(current.public()['assistance']['full_explanation_seen'])
            self.assertEqual(current.progress.pending_question.question_id, question)
            self.assertIn('本轮提示级别：第' + str(level) + '级', current.instructions())
            old = deepcopy(current.state)
        events = current.progress.pending_question.visual_context['host_formative_assistance']['events']
        self.assertEqual([event['hint_level'] for event in events], [1, 2, 3, 3])

    def test_explicit_level_and_repeat_publication_are_bounded(self):
        third = self.publish(prior(pending=True), '第三级提示', key='third')
        self.assertEqual(third.public()['hint_level'], 3)
        third.commit_sources([SOURCE], '同一任务重复发布。')
        self.assertEqual(third.public()['assistance']['hints_used'], 1)
        first = self.publish(third.state, '第1级提示', key='first')
        self.assertEqual(first.public()['hint_level'], 1)
        self.assertEqual(first.public()['assistance']['max_hint_level'], 3)

    def test_unpublished_help_does_not_advance_or_mark_full_explanation(self):
        old = prior(pending=True)
        requested = turn('第三级提示', old)
        self.assertEqual(requested.public()['hint_level'], 3)
        self.assertEqual(requested.public()['assistance']['max_hint_level'], 0)
        following = self.publish(requested.state)
        self.assertEqual(following.public()['hint_level'], 1)
        full = turn('查看完整解释', following.state)
        self.assertFalse(full.public()['assistance']['full_explanation_seen'])

    def test_actual_example_is_not_recorded_as_a_delivered_hint(self):
        current = self.publish(prior(pending=True), '带我思考', strategy='worked_example')
        self.assertEqual(current.public()['assistance']['examples_used'], 1)
        self.assertEqual(current.public()['assistance']['hints_used'], 0)
        self.assertEqual(current.public()['assistance']['max_hint_level'], 0)

    def test_full_explanation_preserves_question_and_marks_only_published_help(self):
        hinted = self.publish(prior(pending=True), '第2级提示')
        question = hinted.progress.pending_question.question_id
        full = self.publish(hinted.state, '查看完整解释', key='full')
        self.assertEqual(full.progress.pending_question.question_id, question)
        self.assertTrue(full.public()['assistance']['full_explanation_seen'])
        self.assertEqual(full.public()['assistance']['max_hint_level'], 2)
        self.assertEqual(full.public()['assistance']['explanations_used'], 1)
        restored = turn('回到刚才的题', full.state)
        self.assertIn(full.progress.pending_question.prompt, restored.restore_reply())
        self.assertTrue(restored.public()['assistance']['full_explanation_seen'])
        model = Mock(); model.chat_json.return_value = assessment()
        graded = turn('背景音乐', full.state, model)
        evidence = graded.progress.learning_evidence[-1]
        self.assertTrue(evidence.visual_context['assistance']['full_explanation_seen'])
        self.assertFalse(evidence.visual_context['independent'])
        self.assertFalse(graded.public()['formal_mastery'])

    def test_legacy_help_context_gets_safe_defaults(self):
        old = prior(pending=True)
        old['progress']['pending_question']['visual_context']['host_formative_assistance'] = {
            'hints_used': 1, 'examples_used': 0, 'explanations_used': 0, 'events': []}
        current = self.publish(old)
        self.assertEqual(current.public()['assistance']['hints_used'], 2)
        self.assertEqual(current.public()['assistance']['max_hint_level'], 1)

    def test_help_metadata_never_exposes_private_key_or_crosses_target(self):
        current = self.publish(prior(pending=True), '第2级提示')
        restored = turn('只给提示', json.loads(json.dumps(current.state)))
        self.assertEqual(restored.public()['assistance']['max_hint_level'], 2)
        self.assertNotIn('PRIVATE-', json.dumps([restored.public(), restored.instructions()], ensure_ascii=False))
        changed = turn('换个知识点，什么是信度', current.state)
        self.assertIsNone(changed.public()['assistance'])
        invalid = turn('再给一个提示', current.state, validate_sources=lambda _: [])
        self.assertIsNone(invalid.public()['assistance'])

    def test_negated_full_answer_request_stays_hint_only(self):
        current = self.publish(prior(pending=True), '不要直接告诉我答案，只给提示')
        self.assertFalse(current.public()['assistance']['full_explanation_seen'])
        self.assertEqual(current.public()['hint_level'], 1)

    def test_progress_card_only_exposes_published_help_summary(self):
        from agents.learning_cards import build_learning_cards
        third = self.publish(prior(pending=True), '第3级提示')
        full = self.publish(third.state, '查看完整解释', key='full')
        card = build_learning_cards(full, [SOURCE], '已经发布的解释。[1]')[-1]
        self.assertEqual(card['assistance']['max_hint_level'], 3)
        self.assertTrue(card['assistance']['full_explanation_seen'])
        self.assertNotIn('events', card['assistance'])
        self.assertNotIn('PRIVATE-', json.dumps(card, ensure_ascii=False))


if __name__ == '__main__':
    unittest.main()
