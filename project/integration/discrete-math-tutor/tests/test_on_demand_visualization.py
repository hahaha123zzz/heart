import copy
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from visualization.on_demand import generate_guide, CACHE, read_skill
from visualization.templates import VisualPlan, render_plan
from tests import test_textbook_guides as textbook_fixtures
from knowledge.proof_units import units_for


def plan(name,payload):
    return VisualPlan(template=name,title='本题讲解',source_index=0,evidence_quote='教材定义',origin='user_example',payload=payload)


class TemplateTests(unittest.TestCase):
    def test_all_eight_templates(self):
        seeds={
            'euler':{'nodes':[{'id':'v1','label':'v1'},{'id':'v2','label':'v2'}],'edges':[{'source':'v1','target':'v2'}]},
            'relation':{'pairs':[{'source':'a','target':'b'},{'source':'b','target':'c'}],'kind':'transitive','mode':'closure'},
            'truth_table':{'operator':'implies','p_label':'有车','q_label':'接人'},
            'sets':{'universe':['1','2','3'],'a':['1','2'],'b':['2','3'],'operation':'intersection'},
            'mapping':{'domain':['a','b'],'codomain':['1','2'],'pairs':[['a','1'],['b','1']]},
            'tree':{'nodes':[{'id':'n1','label':'分类','parent':None},{'id':'n2','label':'情况一','parent':'n1'}],'steps':[{'node':'n1','text':'先分类'},{'node':'n2','text':'查看一类'}]},
            'formula':{'steps':[{'before':'a+b','after':'b+a','rule':'加法交换律'}]},
            'flow':{'nodes':[{'id':'n1','label':'前提'},{'id':'n2','label':'结论'}],'edges':[{'source':'n1','target':'n2','label':'依据规则'}],'steps':[{'node':'n1','text':'检查前提'},{'node':'n2','text':'得到结论'}]},
        }
        self.assertIn('没有欧拉回路',render_plan(plan('euler',seeds['euler']))[-1]['text'])
        self.assertEqual(render_plan(plan('sets',seeds['sets']))[-1]['sets']['selected'],['2'])
        self.assertIn('不是单射',render_plan(plan('mapping',seeds['mapping']))[-1]['text'])
        self.assertIn('不是满射',render_plan(plan('mapping',seeds['mapping']))[-1]['text'])
        for name,seed in seeds.items():
            with self.subTest(name=name):self.assertGreater(len(render_plan(plan(name,seed))),0)
        self.assertEqual(render_plan(plan('truth_table',seeds['truth_table']))[3]['table']['rows'][1][2],'假')
    def test_structure_and_unknown_fields_rejected(self):
        bad=[('sets',{'universe':['1'],'a':['2'],'b':[],'operation':'union'}),
             ('mapping',{'domain':['a','b'],'codomain':['1'],'pairs':[['a','1'],['a','1']]}),
             ('tree',{'nodes':[{'id':'n1','label':'循环','parent':'n1'}],'steps':[{'node':'n1','text':'循环'}]}),
             ('formula',{'steps':[{'before':'a','after':'b','rule':'无依据','html':'<script>'}]}),
             ('flow',{'nodes':[{'id':'n1','label':'节点'}],'edges':[],'steps':[{'node':'other','text':'不存在'}]})]
        for name,payload in bad:
            with self.subTest(name=name),self.assertRaises(ValueError):render_plan(plan(name,payload))


class AnswerPresentationTests(unittest.TestCase):
    def test_answer_emphasis_survives_generation(self):
        from agents.response_generator import ResponseGenerator
        from agents.teaching_planner import TeachingPlan
        from models.student_state import StudentState
        reply='**交集**是共同元素；==只有2同时属于两者==。'
        llm=Mock();llm.chat.return_value=reply
        answer=ResponseGenerator(llm).generate(StudentState(),TeachingPlan(goal='交集',strategy='worked_example',action='explain',difficulty='easy'),'解释交集',[])
        self.assertEqual(answer,reply)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        CACHE.clear()
        self.env=patch.dict(os.environ,{'VISUALIZATION_ON_DEMAND':'1'});self.env.start();self.addCleanup(self.env.stop)
        self.source=textbook_fixtures.TextbookGuideTests().source(9,'定义9.5')
        self.ref={'document_id':'chapter-09','chapter_id':9,'section_id':self.source.section_id,'version':units_for(9)['定义9.5'].record['version'],'rects':[{'page':8,'x1':.1,'y1':.1,'x2':.8,'y2':.3}]}
        self.execution=SimpleNamespace(hint_only=False,learning_intents=['explain'])
        self.raw={'template':'mapping','title':'本题映射','source_index':0,'evidence_quote':self.source.text[:20],'origin':'teaching_example',
                  'payload':{'domain':['a','b'],'codomain':['1','2'],'pairs':[['a','1'],['b','2']]}}
    def run_guide(self,llm,**options):
        return generate_guide(llm,options.pop('message','用辅助例解释映射'), '根据教材解释映射。',[self.source],self.execution,
            student_id=options.pop('student_id','isolated'),turn_id=options.pop('turn_id','turn'),references=[{'source_index':0,'selection_ref':self.ref}],**options)
    def test_lazy_skill_loading_and_private_cache(self):
        llm=Mock();llm.chat_json.side_effect=[{'templates':['mapping']},{'plans':[self.raw]},{'passed':True,'issues':[]}]
        with patch('visualization.on_demand.read_skill',wraps=read_skill) as read:
            guide=self.run_guide(llm)
            self.assertEqual(read.call_args.args,('finite-structures',))
        self.assertEqual(guide['generation']['method'],'skill-template');self.assertEqual(llm.chat_json.call_count,3)
        again=self.run_guide(llm,turn_id='new-turn')
        self.assertNotEqual(guide['id'],again['id']);self.assertEqual(llm.chat_json.call_count,3)
        llm.chat_json.side_effect=[{'templates':[]}]
        self.assertIsNone(self.run_guide(llm,student_id='other'))
        self.assertEqual(llm.chat_json.call_count,4)
    def test_ordinary_explanation_selects_visual_without_confirmation(self):
        llm=Mock();llm.chat_json.side_effect=[{'templates':['mapping']},{'plans':[self.raw]},{'passed':True,'issues':[]}]
        self.assertIsNotNone(self.run_guide(llm,message='解释单射和满射的区别'))
        self.assertIn('无需用户提出',llm.chat_json.call_args_list[0].args[0][0]['content'])
    def test_location_wrapper_is_unpacked_before_publishing(self):
        llm=Mock();llm.chat_json.side_effect=[{'templates':['mapping']},{'plans':[self.raw]},{'passed':True,'issues':[]}]
        with patch('knowledge.citation_locations.locate_source',return_value={'label':'定义','selection_ref':self.ref}):
            guide=generate_guide(llm,'解释映射','根据教材解释映射。',[self.source],self.execution,student_id='isolated',turn_id='turn')
        self.assertEqual(guide['frames'][0]['selection_ref'],self.ref)
    def test_one_repair_and_invalid_quote_never_published(self):
        invalid=copy.deepcopy(self.raw);invalid['evidence_quote']='这句话不在教材中'
        llm=Mock();llm.chat_json.side_effect=[{'templates':['mapping']},{'plans':[invalid]},{'plans':[self.raw]},{'passed':True,'issues':[]}]
        self.assertIsNotNone(self.run_guide(llm));self.assertEqual(llm.chat_json.call_count,4)
        CACHE.clear();llm.chat_json.side_effect=[{'templates':['mapping']},{'plans':[invalid]},{'plans':[invalid]}]
        self.assertIsNone(self.run_guide(llm))
    def test_content_audit_rejects_math_mismatch(self):
        llm=Mock();llm.chat_json.side_effect=[{'templates':['mapping']},{'plans':[self.raw]},{'passed':False,'issues':['替换了本题映射']},{'plans':[self.raw]},{'passed':False,'issues':['仍不一致']}]
        self.assertIsNone(self.run_guide(llm));self.assertFalse(CACHE)
    def test_evidence_number_binds_exact_source_without_model_copy(self):
        raw=copy.deepcopy(self.raw);raw.pop('evidence_quote');raw['evidence_index']=0
        llm=Mock();llm.chat_json.side_effect=[{'templates':['mapping']},{'plans':[raw]},{'passed':True,'issues':[]}]
        self.assertIsNotNone(self.run_guide(llm))
        import json
        audited=json.loads(llm.chat_json.call_args.args[0][-1]['content'])
        self.assertEqual(audited['plans'][0]['evidence_quote'],self.source.text[:300])
        CACHE.clear();raw['evidence_index']=999
        llm.chat_json.side_effect=[{'templates':['mapping']},{'plans':[raw]},{'plans':[raw]}]
        self.assertIsNone(self.run_guide(llm))
    def test_hint_and_missing_source_never_call_model(self):
        llm=Mock();self.execution.hint_only=True
        self.assertIsNone(self.run_guide(llm))
        self.execution.hint_only=False
        self.assertIsNone(self.run_guide(llm,message='只给提示，不要答案'))
        self.assertFalse(llm.chat_json.called)

    def test_missing_json_capability_skips_optional_guide(self):
        self.assertIsNone(self.run_guide(SimpleNamespace()))

    def test_multiple_templates_keep_per_frame_sources(self):
        second=dict(self.raw,template='formula',payload={'steps':[{'before':'a+b','after':'b+a','rule':'交换律'}]})
        llm=Mock();llm.chat_json.side_effect=[{'templates':['mapping','formula']},{'plans':[self.raw,second]},{'passed':True,'issues':[]}]
        g=self.run_guide(llm)
        self.assertEqual(g['generation']['templates'],['mapping','formula'])
        self.assertIn('formula',g['frames'][-1]);self.assertEqual(g['frames'][-1]['selection_ref'],self.ref)
    def test_multiple_templates_accept_valid_reversed_model_order(self):
        second=dict(self.raw,template='formula',payload={'steps':[{'before':'a+b','after':'b+a','rule':'交换律'}]})
        llm=Mock();llm.chat_json.side_effect=[{'templates':['mapping','formula']},{'plans':[second,self.raw]},{'passed':True,'issues':[]}]
        g=self.run_guide(llm)
        self.assertEqual(g['generation']['templates'],['mapping','formula'])
        self.assertIn('formula',g['frames'][-1])
    def test_practice_explanation_attaches_guide_but_hint_does_not(self):
        import sys
        import practice_api as practice
        from tests import test_task_resource_execution as task_fixtures
        fixture=task_fixtures.TaskResourceExecutionTests();fixture.memory=Mock()
        tutor=fixture.practice_tutor()
        question=practice.catalog()['questions'][0];part=question['parts'][0]
        reference=dict(self.ref,source='教材',image_refs=[])
        resolved={'context':'相关教材','text':'原题条件','images':[],'reference':reference}
        with patch.dict(sys.modules,{'main':SimpleNamespace(orchestrator=tutor)}),patch.object(practice,'exercise_context',return_value=resolved),patch.object(practice,'memory_for',return_value={'summary':'无记录'}),patch('visualization.service.rollout_settings',return_value=('test',set())),patch('visualization.service.VisualizationService.enabled',return_value=True),patch('visualization.on_demand.generate_guide',return_value={'id':'practice-test','frames':[]}) as generate:
            answer=practice.ai_parts(question,[part],{},'isolated','explain')
            self.assertEqual(answer['guided_visualization']['exercise_target']['part_id'],part['id'])
            self.assertEqual(generate.call_count,1)
            hint=practice.ai_parts(question,[part],{},'isolated','hint')
            self.assertIsNone(hint['guided_visualization']);self.assertEqual(generate.call_count,1)


if __name__=='__main__':unittest.main()
