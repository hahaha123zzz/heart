"""教学技能读取协议与准备阶段切换的离线回归。"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agents.teaching_skills import prepare_teaching_skills, current_teaching_skills, current_skill_receipts, allowed_skills, SKILLS_ROOT
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
                self.assertEqual(list(current_skill_receipts.get()), receipts)
            finally:
                current_teaching_skills.reset(token)

    def test_teaching_tool_request_after_skill_reads_finishes_preparation_without_execution(self):
        from tests.test_q3_agent_loop import ScriptedLLM,tool_round
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ['teaching-skills','learn']:
                (root/name).mkdir();(root/name/'SKILL.md').write_text('仅供本地测试的教学指南。',encoding='utf-8')
            for next_tool in ['retrieve_course','ask_user','teaching_step','unknown_tool']:
                with self.subTest(tool=next_tool):
                    model=ScriptedLLM([
                        tool_round(('read_skill',{'name':'teaching-skills'})),
                        tool_round(('read_skill',{'name':'learn'})),
                        tool_round((next_tool,{'query':'selected passage'}))])
                    events=[]
                    context=ToolContext(student_id='s',session_id='x',state={
                        'skills_root':str(root),'allowed_skills':('teaching-skills','learn')},
                        emit=lambda kind,message,data:events.append((kind,message,data)))
                    policy,receipts=prepare_teaching_skills(model,[{'role':'user','content':'这个实验的目的是什么'}],context=context)
                    self.assertEqual([row['skill'] for row in receipts],['teaching-skills','learn'])
                    self.assertIn('本地测试的教学指南',policy)
                    self.assertEqual(len(model.calls),3)
                    self.assertTrue(all(message=='read_skill' for kind,message,_ in events if kind=='tool_call'))
                    self.assertTrue(any(data.get('deferred_tools')==[next_tool] for _,_,data in events))

    def test_other_tool_before_guide_is_still_rejected(self):
        from llm.client import LLMError
        from tests.test_q3_agent_loop import ScriptedLLM,tool_round
        model=ScriptedLLM([tool_round(('retrieve_course',{'query':'不能跳过指南'}))])
        with self.assertRaises(LLMError):
            prepare_teaching_skills(model,[{'role':'user','content':'解释选区'}])

    def test_skill_teaching_overrides_old_action_but_keeps_bound_hint_scope(self):
        from agents.quality_checker import QualityChecker
        plan = SimpleNamespace(action='give_hint')
        response = '答案是研究者操纵的变量。'
        self.assertTrue(QualityChecker._rule_check(response, plan))
        self.assertEqual(QualityChecker._rule_check(response, plan, {'teaching_skills': True}), [])
        scoped = {'teaching_skills': True, 'truth_table_snapshot': {
            'answer_scope': 'hint', 'formula': 'p∧q'}}
        self.assertTrue(QualityChecker._rule_check('当前行的结果是1', plan, scoped))

    def test_learning_primary_skills_are_available_to_course(self):
        names = set(allowed_skills(SKILLS_ROOT, 'experimental-psychology-3'))
        self.assertTrue({'learn', 'universal-diagnostic-tutor', 'learn-feynman',
                         'exam-review', 'confusion-tracker'} <= names)
