"""辅助证据只记录真实发布帮助，不产生正式掌握结论。"""
from copy import deepcopy
import json
import unittest
from unittest.mock import Mock

from tests.test_adaptive_tutoring import SOURCE, assessment, prior, record, turn


class FormativeEvidenceTests(unittest.TestCase):
    def help(self, old, message='只给提示', request_id='hint-1'):
        t = turn(message, old)
        t.request.request_id = request_id
        return t

    def test_published_hints_follow_original_question_and_are_idempotent(self):
        old = prior(pending=True)
        t = self.help(old)
        self.assertNotIn('host_formative_assistance', t.progress.pending_question.visual_context)
        t.commit_sources([SOURCE], '先找出研究者主动改变的条件。')
        t.commit_sources([SOURCE], '重复投递的发布回执。')
        help_state = t.progress.pending_question.visual_context['host_formative_assistance']
        self.assertEqual(help_state['hints_used'], 1)
        self.assertEqual(len(help_state['events']), 1)
        second = self.help(t.state, '第2级提示', 'hint-2')
        second.commit_sources([SOURCE], '比较不同背景音乐条件。')
        self.assertEqual(second.progress.pending_question.question_id, old['progress']['pending_question']['question_id'])
        self.assertEqual(second.progress.pending_question.visual_context['host_formative_assistance']['hints_used'], 2)
        self.assertFalse(second.progress.learning_evidence)

    def test_failed_or_unpublished_help_does_not_mutate_saved_question(self):
        old = prior(pending=True)
        before = deepcopy(old)
        t = self.help(old)
        t.commit_sources([SOURCE], '')
        self.assertNotIn('host_formative_assistance', t.progress.pending_question.visual_context)
        self.assertEqual(old, before)

    def test_no_help_is_zero_hints_and_remains_formative(self):
        model = Mock()
        model.chat_json.return_value = assessment()
        t = turn('背景音乐', prior(pending=True), model)
        event = t.progress.learning_evidence[0]
        self.assertEqual(event.hints_used, 0)
        self.assertFalse(event.visual_context['independent'])
        self.assertEqual(event.visual_context['verification'], 'ai_provisional')
        self.assertFalse(t.progress.quiz_attempts[0].independent)
        self.assertFalse(t.state['formal_mastery'])

    def test_explanations_and_hints_are_distinct_and_link_to_student_and_sources(self):
        explained = self.help(prior(pending=True), '直接解释这个例子', 'explain-1')
        explained.commit_sources([SOURCE], '这里研究者操纵背景音乐。')
        hinted = self.help(explained.state)
        hinted.commit_sources([SOURCE], '先看研究者操纵了什么。')
        model = Mock()
        model.chat_json.return_value = assessment()
        graded = turn('背景音乐', hinted.state, model)
        event = graded.progress.learning_evidence[0]
        self.assertEqual(event.hints_used, 1)
        self.assertEqual(event.visual_context['assistance']['explanations_used'], 1)
        self.assertEqual(event.visual_context['student_quote'], '背景音乐')
        self.assertEqual(event.visual_context['source_refs'][0]['version'], SOURCE['version'])
        self.assertEqual(event.visual_context['source_refs'][0]['evidence'], SOURCE['location']['evidence'])
        self.assertIsNone(event.confidence)
        self.assertNotIn('PRIVATE-', json.dumps(graded.public(), ensure_ascii=False))

    def test_side_question_and_restored_prompt_are_not_hints(self):
        for message in ('先插问一下，什么是控制变量', '回到刚才的题', '我懂了'):
            with self.subTest(message=message):
                t = self.help(prior(pending=True), message)
                t.commit_sources([SOURCE], '回应插问或恢复原题。')
                self.assertNotIn('host_formative_assistance', t.progress.pending_question.visual_context)

    def test_private_help_context_does_not_leak_answer_key(self):
        t = self.help(prior(pending=True))
        t.commit_sources([SOURCE], '先分析条件。')
        public = json.dumps([t.public(), t.instructions(), t.context.prompt_payload()], ensure_ascii=False)
        self.assertNotIn('PRIVATE-', public)
        self.assertNotIn('host_formative_assistance', public)

    def test_recorded_method_wins_over_suggested_hint_strategy(self):
        t = self.help(prior(pending=True), '带我思考')
        self.assertEqual(t.strategy, 'hint')
        t.strategy = 'hint'
        self.assertTrue(record(t, strategy='worked_example').success)
        t.commit_sources([SOURCE], '教学示例：改变音乐，观察阅读时间。')
        help_state = t.progress.pending_question.visual_context['host_formative_assistance']
        self.assertEqual(help_state['hints_used'], 0)
        self.assertEqual(help_state['examples_used'], 1)
        self.assertEqual(help_state['events'][0]['strategy'], 'worked_example')

    def test_help_does_not_cross_target_or_invalid_source(self):
        t = self.help(prior(pending=True))
        t.commit_sources([SOURCE], '先分析条件。')
        changed = turn('换个知识点，什么是信度', t.state)
        self.assertIsNone(changed.progress.pending_question)
        invalid = turn('再给一个提示', t.state, validate_sources=lambda _: [])
        self.assertIsNone(invalid.progress.pending_question)
        self.assertFalse(invalid.progress.learning_evidence)

    def test_multisentence_question_is_accepted_only_as_complete_reply_suffix(self):
        t = turn('考考我')
        question = '研究者改变音乐音量。测量阅读得分。自变量是什么？因变量是什么？说明依据。'
        self.assertTrue(record(t, check_prompt=question, check_focus='变量定位').success)
        self.assertTrue(t.gate('先看操纵和测量的区别。[1]\n现在换你来判断：' + question)[0])
        self.assertFalse(t.gate(question + '\n答案是音乐音量和阅读得分。')[0])
        self.assertFalse(t.gate('研究者改变室温。测量阅读得分。自变量是什么？因变量是什么？说明依据。')[0])


if __name__ == '__main__':
    unittest.main()
