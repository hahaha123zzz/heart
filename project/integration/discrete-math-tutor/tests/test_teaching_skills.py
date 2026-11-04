"""教学技能读取协议的离线回归；本轮按用户要求未执行。"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agents.teaching_skills import prepare_teaching_skills, current_teaching_skills
from agents.tool_protocol import ToolContext


class TeachingSkillsTests(unittest.TestCase):
    def test_guide_precedes_selected_skill_and_context_is_authoritative(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, body in [('teaching-skills', '每轮先读指南。'), ('teach-concept', '先解释理由。')]:
                (root / name).mkdir()
                (root / name / 'SKILL.md').write_text(body, encoding='utf-8')
            calls = []
            def chat(messages, tools, **kwargs):
                calls.append((messages, tools, kwargs))
                name = ['teaching-skills', 'teach-concept', None][len(calls) - 1]
                tool_calls = [] if name is None else [SimpleNamespace(
                    id='skill-' + str(len(calls)), name='read_skill',
                    arguments={'name': name}, extra_content=None)]
                return SimpleNamespace(tool_calls=tool_calls, text='SKILLS_READY' if name is None else '',
                                       finish_reason='stop' if name is None else 'tool_calls')
            context = ToolContext(student_id='s', session_id='session', state={
                'skills_root': str(root), 'allowed_skills': ('teaching-skills', 'teach-concept')})
            token = current_teaching_skills.set('')
            try:
                policy, receipts = prepare_teaching_skills(SimpleNamespace(chat_with_tools=chat),
                    [{'role': 'user', 'content': '解释这个概念'}], context=context)
                self.assertEqual(calls[0][1][0]['function']['parameters']['properties']['name']['enum'],
                                 ['teaching-skills'])
                self.assertEqual([row['skill'] for row in receipts], ['teaching-skills', 'teach-concept'])
                self.assertIn('先解释理由。', policy)
                self.assertIn('优先于旧教学策略', policy)
                self.assertEqual(current_teaching_skills.get(), policy)
                self.assertEqual(len(calls), 3)
            finally:
                current_teaching_skills.reset(token)

    def test_skill_teaching_overrides_old_action_but_keeps_bound_hint_scope(self):
        from agents.quality_checker import QualityChecker
        plan = SimpleNamespace(action='give_hint')
        response = '答案是研究者操纵的变量。'
        self.assertTrue(QualityChecker._rule_check(response, plan))
        self.assertEqual(QualityChecker._rule_check(response, plan, {'teaching_skills': True}), [])
        scoped = {'teaching_skills': True, 'truth_table_snapshot': {
            'answer_scope': 'hint', 'formula': 'p∧q'}}
        self.assertTrue(QualityChecker._rule_check('当前行的结果是1', plan, scoped))
