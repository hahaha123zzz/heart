import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class PsychologyVisualizationTests(unittest.TestCase):
    def test_templates_generation_and_validation_reuse_existing_deck(self):
        script='''
from visualization.templates import CATALOG,VisualPlan,render_plan
from visualization.on_demand import generate_guide,read_skill
from knowledge.psychology_retrieval import retrieve
from knowledge.citation_locations import locate_source
from unittest.mock import Mock,patch
from types import SimpleNamespace
assert set(CATALOG)=={'experiment_flow','variable_map','design_matrix'}
assert '被试间因素' in read_skill('experimental-design')
with patch('knowledge.psychology_retrieval.retrieve_hybrid',return_value=[]):
 sources=retrieve('单因素随机区组设计为什么能控制个体差异？',[])
ref=locate_source(sources[0])['selection_ref']
matrix={'columns':['区组','条件A','条件B'],'rows':[['区组1','被试1','被试2'],['区组2','被试3','被试4']],
        'steps':[{'row':0,'columns':[1,2],'text':'同一区组的不同被试分别接受不同水平'},{'row':1,'columns':[1,2],'text':'下一组也分别分配'}]}
raw={'template':'design_matrix','title':'辅助分组示例','source_index':0,'evidence_index':0,'origin':'teaching_example','payload':matrix}
llm=Mock();llm.chat_json.side_effect=[{'templates':['design_matrix']},{'plans':[raw]},{'passed':True,'issues':[]}]
import json
original_sources=list(sources)
late_sources=[sources[0]]*6+original_sources
probe=Mock();probe.chat_json.return_value={'templates':[]}
assert generate_guide(probe,'解释区组设计','核验后的讲解引用第7条依据。[7]',late_sources,SimpleNamespace(hint_only=False,learning_intents=['explain']),student_id='late-source',turn_id='late-source') is None
selector_payload=json.loads(probe.chat_json.call_args.args[0][-1]['content'])
assert len(selector_payload['materials'])==len(late_sources[:9])
assert selector_payload['materials'][6]['source_index']==6
assert selector_payload['materials'][6]['text']==original_sources[0].text[:2600]
guide=generate_guide(llm,'为什么需要匹配被试','区组内不同被试分别接受各水平。',sources,
 SimpleNamespace(hint_only=False,learning_intents=['explain']),student_id='isolated',turn_id='new',references=[{'source_index':0,'selection_ref':ref}])
assert guide and guide['generation']['skills']==['experimental-design']
assert guide['frames'][0]['table']['active_row']==0 and guide['frames'][1]['table']['active_row']==1
assert guide['selection_ref']['document_id'].startswith('experimental-psychology-3:')
assert '实验心理学' in llm.chat_json.call_args_list[0].args[0][0]['content']
assert generate_guide(Mock(),'只给提示','提示',sources,SimpleNamespace(hint_only=True,learning_intents=['hint']),student_id='s',turn_id='hint') is None
plan=lambda name,payload:VisualPlan(template=name,title='图解',source_index=0,evidence_quote='原文依据',origin='teaching_example',payload=payload)
flow={'nodes':[{'id':'iv','label':'操纵自变量'},{'id':'dv','label':'测量因变量'}],'edges':[{'source':'iv','target':'dv','label':'实验程序'}],'steps':[{'node':'iv','text':'设置条件'},{'node':'dv','text':'测量反应'}]}
assert render_plan(plan('experiment_flow',flow))[0]['graph']['focus_nodes']==['iv']
assert render_plan(plan('variable_map',flow))[1]['graph']['focus_nodes']==['dv']
for payload in [matrix|{'rows':[['少一列']]},matrix|{'steps':[{'row':3,'columns':[1],'text':'越界'}]},matrix|{'html':'<script>'}]:
 try:render_plan(plan('design_matrix',payload));raise AssertionError('接受无效矩阵')
 except ValueError:pass
try:render_plan(plan('euler',{}));raise AssertionError('心理学目录接受旧数学模板')
except ValueError:pass
print('PASS: 心理学三种模板、自动生成与来源绑定、分步高亮、提示保护及无效参数拒绝')
'''
        with tempfile.TemporaryDirectory() as directory:
            env=os.environ|{'TUTOR_COURSE':'experimental-psychology-3','VISUALIZATION_ON_DEMAND':'1','DATABASE_URL':'sqlite:///'+str(Path(directory)/'test.db')}
            result=subprocess.run([sys.executable,'-X','utf8','-c',script],cwd=ROOT,env=env,text=True,capture_output=True,encoding='utf-8',timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)

if __name__=='__main__':unittest.main()
