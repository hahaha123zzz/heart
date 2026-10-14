import unittest
from types import SimpleNamespace
from unittest.mock import patch
from knowledge.proof_units import units_for
from knowledge.textbook import TextbookChunk
from visualization.textbook_guides import build_textbook_guide


class TextbookGuideTests(unittest.TestCase):
    def source(self,chapter,label):
        u=units_for(chapter)[label]
        return TextbookChunk(u.record['source'],u.section['title'],u.text,frozenset(),chapter_id=chapter,section_id=u.section['id'])
    def guide(self,question,chapter=9,label='例9.8',**options):
        execution=SimpleNamespace(hint_only=options.get('hint',False),learning_intents=options.get('intents',['explain']))
        return build_textbook_guide(question,options.get('response',''),[self.source(chapter,label)],execution,turn_id='turn')
    def test_original_example_r2_keeps_numeric_labels_and_cycle_loops(self):
        g=self.guide('请讲解例9.8中R₂的传递闭包')
        self.assertEqual(g['origin'],'textbook_example');self.assertIn('R2',g['title'])
        self.assertEqual([n['label'] for n in g['frames'][0]['graph']['nodes']],['1','2','3'])
        self.assertEqual({e['id'] for e in g['frames'][0]['graph']['edges']},{'ab','ba'})
        self.assertEqual({e['id'] for e in g['frames'][-1]['graph']['edges']},{'ab','ba','aa','bb'})
        self.assertEqual(g['selection_ref']['rects'][0]['page'],11)
        self.assertIn('(1,1)',g['frames'][1]['text'])
    def test_no_guides_for_hint_practice_unrelated_or_other_example(self):
        for q,options in [('只给提示，不要答案',{}),('讲解例9.8',{'hint':True}),('讲解例9.8',{'intents':['practice']}),('讲解例9.7',{}),('讲解例9.8 R4的传递闭包',{}),('你好',{}),('我想休息一下',{})]:
            self.assertIsNone(self.guide(q,**options))
    def test_retrieval_and_version_required(self):
        execution=SimpleNamespace(hint_only=False,learning_intents=['explain'])
        self.assertIsNone(build_textbook_guide('解释例9.8','',[],execution))
        with patch.dict('visualization.textbook_guides.VERSIONS',{9:'0'*64}):self.assertIsNone(self.guide('解释例9.8'))
    def test_implication_uses_actual_textbook_example(self):
        g=self.guide('解释例4.6为什么没车也算真',4,'例4.6')
        self.assertEqual(g['origin'],'textbook_example');self.assertEqual(len(g['frames']),9)
        self.assertIn('我有车',g['frames'][0]['text'])
        self.assertEqual(g['frames'][3]['table']['rows'][1],['真','假','待检查'])
        self.assertEqual(g['frames'][4]['table']['rows'][1],['真','假','假'])
        self.assertEqual(g['frames'][4]['table']['warning_row'],1)
        self.assertEqual(g['frames'][3]['table']['focus_columns'],[0,1])
        self.assertEqual(g['frames'][4]['table']['focus_columns'],[2])
    def test_closure_separates_missing_preview_and_actual_addition(self):
        g=self.guide('讲解例9.8 R2的传递闭包')
        before,after=g['frames'][1:3]
        self.assertEqual(before['graph']['missing_edges'][0]['source'],'a')
        self.assertNotIn('aa',{e['id'] for e in before['graph']['edges']})
        self.assertIn('aa',after['graph']['added'])
        self.assertEqual(after['graph']['missing_edges'],[])
        self.assertEqual(set(before['graph']['focus']),{'ab','ba'})
    def test_relation_counterexample_preserves_original_and_marks_missing(self):
        g=self.guide('请解释关系传递性',9,'定义9.5')
        frame=g['frames'][1]
        self.assertEqual({e['id'] for e in frame['graph']['edges']},{'ab','bc'})
        self.assertEqual(frame['graph']['missing_edges'],[{'source':'a','target':'c','id':'missing-ac'}])
        self.assertEqual(set(frame['graph']['focus']),{'ab','bc'})
        self.assertEqual(frame['badges'][0]['tone'],'warning')
    def test_custom_euler_edges_are_not_replaced_with_cycle_template(self):
        g=self.guide('无向图的顶点为v1、v2、v3、v4，边为v1-v2、v2-v3、v3-v4、v4-v1、v1-v3。解释为什么没有欧拉回路',7,'定理7.11')
        self.assertEqual(g['origin'],'user_example');self.assertEqual(len(g['frames'][0]['graph']['edges']),5)
        self.assertIn('没有欧拉回路',g['frames'][-1]['text'])
        self.assertIsNone(self.guide('解释有向图的欧拉回路',7,'定理7.11'))
    def test_euler_steps_highlight_degrees_and_cover_actual_circuit(self):
        from visualization.euler_guide import euler_frames
        from models.visualization import GraphSpec
        graph=GraphSpec(nodes=[{'id':n,'label':n} for n in ['v1','v2','v3','v4']],edges=[{'source':a,'target':b} for a,b in [('v1','v2'),('v2','v3'),('v3','v4'),('v4','v1')]])
        frames=euler_frames(graph)
        degrees=[f for f in frames if f['title'].startswith('检查 v')]
        self.assertEqual(len(degrees),4)
        for frame in degrees:
            self.assertEqual(len(frame['graph']['focus']),2)
            self.assertEqual(len(frame['graph']['focus_nodes']),1)
        route=[f for f in frames if f['title'].startswith('沿回路')]
        self.assertEqual([len(f['graph']['traversed']) for f in route],[1,2,3,4])
        self.assertEqual(set(route[-1]['graph']['traversed']),{e['source']+'-'+e['target'] for e in graph.model_dump()['edges']})
        self.assertIn('回到起点',route[-1]['text'])
    def test_disconnected_graph_shows_components_without_fake_circuit(self):
        from visualization.euler_guide import euler_frames
        from models.visualization import GraphSpec
        graph=GraphSpec(nodes=[{'id':n,'label':n} for n in ['v1','v2','v3']],edges=[{'source':'v1','target':'v2'}])
        frames=euler_frames(graph)
        self.assertEqual([f['graph']['focus_nodes'] for f in frames if f['title']=='检查连通性'],[['v1','v2'],['v3']])
        self.assertFalse(any(f['title'].startswith('沿回路') for f in frames))
    def test_auto_deck_saved_only_after_answer_quality_passes(self):
        import tests.test_quality_guard as fixtures
        from agents.quality_checker import QualityResult
        from models.task_understanding import TaskUnderstanding
        source=self.source(9,'例9.8')
        tutor=fixtures.QualityGuardTests().tutor([QualityResult(passed=True)])
        tutor.llm=None  # 此测试只检查已审核场景，按需模型测试另行隔离。
        tutor.response_generator.generate.side_effect=['例9.8中R2的传递闭包还需加入两个自环[1]。']
        with patch('orchestrator.retrieve_hybrid',return_value=[source]),patch('orchestrator.retrieve_figures',return_value=[]),patch('orchestrator.expand_proof_sources',return_value=([source],None)),patch('orchestrator.enrich_sources',return_value=([source],None)),patch('visualization.service.rollout_settings',return_value=('test',set())),patch('visualization.service.VisualizationService.enabled',return_value=True):
            result=tutor.handle_turn('guard-test','请讲解例9.8 R2的传递闭包')
        self.assertEqual(result['answer_status'],'answered');self.assertIsNotNone(result['guided_visualization'])
        self.assertEqual(tutor.memory.commit_learning_turn.call_args.kwargs['selection_ref']['guided_visualization'],result['guided_visualization'])
