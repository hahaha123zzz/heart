"""可视化技能的显式触发、证据发布及交互数据边界。"""
import copy
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from visualization.learning_visuals import requested_skill, enabled_for, render
from visualization.on_demand import build_guide, CACHE


GRAPH = {'nodes': [{'id': 'a', 'label': '自变量'}, {'id': 'b', 'label': '因变量'}],
         'edges': [{'source': 'a', 'target': 'b', 'label': '拟检验的影响'}],
         'steps': [{'node': 'a', 'text': '改变实验条件'}, {'node': 'b', 'text': '观察测量指标'}]}


def interactive():
    choice = {'prompt': '比较两种情境', 'options': [
        {'label': '改变条件', 'node': 'a', 'feedback': '关注操纵的自变量'},
        {'label': '测量结果', 'node': 'b', 'feedback': '关注测量的因变量'}]}
    return {'nodes': GRAPH['nodes'], 'edges': GRAPH['edges'], 'puzzle': copy.deepcopy(choice),
            'explore': copy.deepcopy(choice), 'concept': {'title': '变量的角色', 'text': '操纵与测量承担不同角色'},
            'challenge': copy.deepcopy(choice)}


class LearningVisualSkillsTests(unittest.TestCase):
    def setUp(self):
        CACHE.clear()
        self.env = patch.dict(os.environ, {'VISUALIZATION_ON_DEMAND': '0'})
        self.env.start(); self.addCleanup(self.env.stop)

    def test_triggers_and_opt_out(self):
        for message, name in [('画章节关系图', 'drawio_relation'), ('用drawio画一个图', 'drawio_relation'),
                              ('给我分步图文讲解', 'visual_explainer'), ('/aha 自变量', 'interactive_educator'),
                              ('交互式讲解变量', 'interactive_educator')]:
            self.assertEqual(requested_skill(message), name)
            self.assertTrue(enabled_for(message))
        for message in ['解释自变量', '解释图1-4', '不要画关系图，解释自变量', '只要文字，用图解解释', '继续下一部分']:
            self.assertIsNone(requested_skill(message), message)
            self.assertFalse(enabled_for(message), message)
        with patch.dict(os.environ, {'VISUALIZATION_ON_DEMAND': '1'}):
            self.assertFalse(enabled_for('不用画图，解释自变量'))

    def test_four_stages_and_unknown_nodes(self):
        frames = render('interactive_educator', interactive())
        self.assertEqual(len(frames), 4)
        self.assertNotIn('interaction', frames[2])
        self.assertEqual(frames[1]['interaction']['options'][1]['node'], 'b')
        changed = interactive()
        changed['challenge']['graph'] = {'nodes': [{'id': 'a', 'label': '光照条件'}, {'id': 'b', 'label': '生长高度'}], 'edges': []}
        frames = render('interactive_educator', changed)
        self.assertEqual(frames[-1]['graph']['nodes'][0]['label'], '光照条件')
        self.assertEqual(frames[0]['graph']['nodes'][0]['label'], '自变量')
        invalid = interactive();invalid['challenge']['options'][0]['node'] = 'unknown'
        with self.assertRaises(ValueError): render('interactive_educator', invalid)
        invalid = interactive();invalid['explore']['options'][0]['script'] = 'evil()'
        with self.assertRaises(ValueError): render('interactive_educator', invalid)

    def run_guide(self, name, *, bad_quote=False, reject=False, hint=False):
        source = SimpleNamespace(chunk_id='block-a', source='教材', chapter_id=2, section_id=2,
                                 section='变量', text='自变量是实验者操纵的条件，因变量是测量的反应。')
        ref = {'document_id': 'chapter-02', 'version': 'v1', 'rects': [{'page': 3}]}
        references = [{'evidence': {'retrieval_source_id': 'block-a', 'document_id': 'chapter-02',
                                    'document_version': 'v1', 'chapter_id': 2, 'section_id': 2}, 'selection_ref': ref}]
        raw = {'template': name, 'title': '变量联系', 'source_index': 0,
               'evidence_quote': '伪造证据不在教材里' if bad_quote else source.text,
               'origin': 'teaching_example', 'payload': interactive() if name == 'interactive_educator' else GRAPH}
        llm = Mock()
        llm.chat_json.side_effect = ([{'plans': [raw]}] * 2 if bad_quote else
            [{'plans': [raw]}, {'passed': not reject, 'issues': ['不符'] if reject else []}] * 2)
        message = {'drawio_relation': '画变量关系图', 'visual_explainer': '分步图文讲解变量',
                   'interactive_educator': '/aha 变量'}[name]
        jobs = []
        self.assertIsNone(build_guide(llm, message, '操纵条件，测量结果。', [source],
            SimpleNamespace(hint_only=hint, learning_intents=['explain']), deferred=jobs,
            student_id='synthetic', turn_id='turn-' + name, references=references))
        self.assertFalse(llm.chat_json.called)
        return jobs[0](), llm

    def test_three_skills_publish_after_answer_with_bound_sources(self):
        for name in ['drawio_relation', 'visual_explainer', 'interactive_educator']:
            guide, llm = self.run_guide(name)
            self.assertIsNotNone(guide)
            self.assertEqual(guide['frames'][0]['selection_ref']['version'], 'v1')
            self.assertIn('skills', guide['generation'])
            self.assertEqual(llm.chat_json.call_count, 2)  # 明确请求省去模板选择调用。

    def test_bad_evidence_audit_and_hint_never_publish(self):
        self.assertIsNone(self.run_guide('drawio_relation', bad_quote=True)[0])
        self.assertIsNone(self.run_guide('drawio_relation', reject=True)[0])
        guide, llm = self.run_guide('drawio_relation', hint=True)
        self.assertIsNone(guide); self.assertFalse(llm.chat_json.called)

    def test_skills_are_mounted_and_documented(self):
        from agents.teaching_skills import allowed_skills, SKILLS_ROOT
        for name in ['drawio', 'visual-explainer', 'interactive-educator']:
            self.assertIn(name, allowed_skills(SKILLS_ROOT, 'experimental-psychology-3'))
            self.assertIn('调用条件', (SKILLS_ROOT / name / 'SKILL.md').read_text(encoding='utf-8'))
            self.assertTrue((SKILLS_ROOT / name / 'LICENSE').is_file())


if __name__ == '__main__': unittest.main()
