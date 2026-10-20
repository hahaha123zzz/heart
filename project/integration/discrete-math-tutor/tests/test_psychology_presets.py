"""预制主题包使用真实教材定位，模型替身只验证无调用及回退。"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMMON = '''
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from knowledge.course_config import PSYCHOLOGY_DIR
from knowledge.textbook import TextbookChunk
from knowledge.pdf_reader import PDFSelection,validate_selection
from visualization.on_demand import build_guide
from visualization.psychology_presets import ROOT,build_preset,match_topic
execution=SimpleNamespace(hint_only=False,learning_intents=['explain','compare'],target_refs=[],targets=[])
def material(ch,sec,index):
 d=json.loads((PSYCHOLOGY_DIR/'chapters'/f'chapter_{ch:02d}'/'document.json').read_text(encoding='utf-8'))
 b=next(b for b in d['blocks'] if b['block_index']==index)
 return TextbookChunk(d['source'],b['section'],b['text'],frozenset(),chapter_id=ch,section_id=sec,block_start=index)
sources=[material(2,2,35),material(4,1,9)]
cases=[('请结合教材解释自变量和因变量的区别，并说明额外变量为什么会干扰结论。',
        '自变量是操纵条件，因变量是测量反应，额外变量也可能影响反应。','variables'),
       ('被试间设计、被试内设计和混合设计有什么区别？',
        '被试间设计每人一个水平；被试内设计同人多个水平；混合设计按因素分别判断。','designs')]
'''


class PsychologyPresetTests(unittest.TestCase):
    def run_script(self, body):
        with tempfile.TemporaryDirectory() as directory:
            env = os.environ | {'TUTOR_COURSE': 'experimental-psychology-3', 'LLM_MOCK': '1',
                                'VISUALIZATION_ON_DEMAND': '1',
                                'DATABASE_URL': 'sqlite:///' + str(Path(directory) / 'isolated.db')}
            env.pop('COURSE_DATABASE_URL', None)
            result = subprocess.run([sys.executable, '-X', 'utf8', '-c', COMMON + body],
                                    cwd=ROOT, env=env, capture_output=True, text=True,
                                    encoding='utf-8', timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + '\n' + result.stderr)

    def test_real_anchors_visual_states_and_model_free_selection(self):
        self.run_script('''
reports=[]
for question,reply,topic in cases:
 llm=Mock()
 guide=build_guide(llm,question,reply,sources,execution,student_id='synthetic',turn_id=topic)
 assert guide and guide['generation']['method']=='textbook-preset'
 llm.chat_json.assert_not_called()
 assert len(guide['frames'])==5
 assert len({f['step_id'] for f in guide['frames']})==5
 pictures=[json.dumps(f['comparison'],ensure_ascii=False,sort_keys=True) for f in guide['frames']]
 assert len(set(pictures))==5
 for frame in guide['frames']:
  ref=frame['selection_ref'];validate_selection(PDFSelection(kind='text',**{k:ref[k] for k in ['document_id','version','rects']}))
  assert ref['location_kind']=='paragraph_anchor'
  assert frame['visual_origin']=='teaching_example'
  assert 1<=len(frame['comparison']['panels'])<=3
  assert all(i['tone'] in ['neutral','focus','warning'] for p in frame['comparison']['panels'] for i in p['items'])
 expected=[2,2,5,8,8] if topic=='variables' else [1,1,1,23,23]
 assert [f['selection_ref']['rects'][0]['page'] for f in guide['frames']]==expected
 if topic=='designs':
  assert {f['selection_ref']['chapter_id'] for f in guide['frames']}=={4,5}
 # 模拟JSON历史存储/回放；不可丢失资产版本、步骤身份或教材引用。
 restored=json.loads(json.dumps({'selection_ref':{'guided_visualization':guide}},ensure_ascii=False))
 assert restored['selection_ref']['guided_visualization']==guide
 reports.append({'question':question,'guide':guide,'method':'合成已核验回答；非真实模型问答'})
Path('artifacts/psychology-preset-acceptance.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
''')

    def test_preset_generation_waits_for_deferred_job(self):
        self.run_script('''
q,reply,_=cases[0]
llm=Mock();jobs=[]
with patch('visualization.psychology_presets.build_preset',wraps=build_preset) as preset:
 assert build_guide(llm,q,reply,sources,execution,student_id='synthetic',turn_id='deferred',deferred=jobs) is None
 preset.assert_not_called()
 assert len(jobs)==1
 guide=jobs[0]()
 assert guide and guide['generation']['method']=='textbook-preset'
 preset.assert_called_once()
 llm.chat_json.assert_not_called()
''')

    def test_generic_diagram_requests_keep_verified_preset(self):
        self.run_script('''
for question,reply,topic in cases:
 for suffix in ['请结合教材和图解说明。','请用示意图解释。']:
  llm=Mock()
  guide=build_guide(llm,question+suffix,reply,sources,execution,student_id='synthetic',turn_id='generic-diagram')
  assert guide and guide['generation']['method']=='textbook-preset',question+suffix
  assert len(guide['frames'])==5
  llm.chat_json.assert_not_called()
 for suffix in ['请严格复现教材图4-999。','不要图解。','请按我的实验设计画图。']:
  assert match_topic(question+suffix,reply,sources,execution) is None,question+suffix
''')

    def test_custom_questions_unrelated_sources_and_gate_fall_back(self):
        self.run_script('''
q,reply,_=cases[0]
for message in ['什么是自变量？','你好','请用做饭例子解释自变量和因变量',
 '我的实验中学习方法是自变量，成绩是因变量，设计是否正确？',
 '第2章第10页的自变量和因变量是什么？','不要图解，解释自变量和因变量']:
 assert match_topic(message,reply,sources,execution) is None,message
assert match_topic(q,reply,[material(5,1,8)],execution) is None
assert match_topic(q,'今天讲反应时法',sources,execution) is None
specific=SimpleNamespace(target_refs=['example:1'],targets=[{'kind':'example'}])
assert match_topic(q,reply,sources,specific) is None
section=SimpleNamespace(target_refs=['section:2:2'],targets=[{'id':'section:2:2','kind':'section'}])
assert match_topic(q+'请结合图解说明',reply,sources,section)=='variables'
for identity in ['section:4:1','invalid']:
 section=SimpleNamespace(target_refs=[identity],targets=[{'id':identity,'kind':'section'}])
 assert match_topic(q+'请结合图解说明',reply,sources,section) is None
q2,reply2,_=cases[1]
section=SimpleNamespace(target_refs=['section:4:1'],targets=[{'id':'section:4:1','kind':'section'}])
assert match_topic(q2+'请结合教材和图解说明',reply2,sources,section)=='designs'

pdf=SimpleNamespace(target_refs=['pdf:1'],targets=[{'kind':'pdf_selection'}])
assert match_topic(q,reply,sources,pdf)=='variables'
with patch('visualization.on_demand.generate_guide',return_value=None) as generate:
 for intents,hint in [(['hint'],True),(['practice'],False),(['check_answer'],False)]:
  blocked=SimpleNamespace(hint_only=hint,learning_intents=intents)
  assert build_guide(Mock(),q,reply,sources,blocked,student_id='test',turn_id='blocked') is None
 with patch.dict('os.environ',{'VISUALIZATION_ON_DEMAND':'0'}):
  assert build_guide(Mock(),q,reply,sources,execution,student_id='test',turn_id='off') is None
 generate.return_value={'fallback':True}
 assert build_guide(Mock(),'用做饭例子解释自变量和因变量',reply,sources,execution,student_id='test',turn_id='custom')=={'fallback':True}
''')

    def test_changed_text_pdf_version_and_missing_anchor_reject_preset(self):
        self.run_script('''
q,reply,_=cases[0]
original=Path.read_text
def changed(path,*args,**kwargs):
 text=original(path,*args,**kwargs)
 if path.name=='variables.json':
  pack=json.loads(text);pack['sources']['iv']['pdf_version']='0'*64;return json.dumps(pack)
 return text
with patch.object(Path,'read_text',changed):assert build_preset(q,reply,sources,execution,turn_id='stale') is None
def changed_text(path,*args,**kwargs):
 text=original(path,*args,**kwargs)
 if path.name=='variables.json':
  pack=json.loads(text);pack['sources']['iv']['text_sha256']='0'*64;return json.dumps(pack)
 return text
with patch.object(Path,'read_text',changed_text):assert build_preset(q,reply,sources,execution,turn_id='changed') is None
with patch('visualization.psychology_presets.locate_source',return_value=None):
 assert build_preset(q,reply,sources,execution,turn_id='missing') is None
with patch('visualization.psychology_presets.locate_source',side_effect=ValueError('缺少位置')),patch('visualization.on_demand.generate_guide',return_value={'fallback':True}):
 assert build_guide(Mock(),q,reply,sources,execution,student_id='test',turn_id='bad')=={'fallback':True}
''')

    def test_pdf_selection_entry_and_database_history_keep_preset(self):
        self.run_script('''
from database.database import init_db
from memory.memory_manager import MemoryManager
from agents.pdf_selection_tutor import explain_selection
from models.task_understanding import TaskUnderstanding
init_db();memory=MemoryManager()
q,reply,_=cases[0]
guide=build_preset(q,reply,sources,execution,turn_id='pdf')
ref=guide['selection_ref']
selection=PDFSelection(kind='text',**{k:ref[k] for k in ['document_id','version','rects']})
tutor=SimpleNamespace(memory=memory,llm=Mock(),conversation_router=Mock(),context_sufficiency=Mock(),quality_checker=Mock())
tutor.conversation_router.route.return_value=TaskUnderstanding(student_move='question',learning_intents=['explain'])
tutor.context_sufficiency.check.return_value=SimpleNamespace(allowed=True,model_dump=lambda:{'allowed':True})
tutor.llm.chat.return_value=reply+'[1]'
def choose_citation(messages,**kwargs):
 candidates=json.loads(messages[1]['content'])['candidates']
 selected=[c for c in candidates if c['selected_target']]
 return {'evidence_ids':[c['evidence_id'] for c in (selected or candidates[:1])]}
tutor.llm.chat_json.side_effect=choose_citation
tutor.quality_checker.check.return_value=SimpleNamespace(passed=True,issues=[],model_dump=lambda:{'passed':True})
with patch('memory.retrieval._model',return_value=(None,None)):
 result=explain_selection(tutor,'synthetic-selection',q,selection,'production',request_id='preset-pdf')
assert result['answer_status']=='answered'
assert result['guided_visualization']['generation']['method']=='textbook-preset'
assert tutor.llm.chat_json.call_count==1
assert '[AGENT:citation_selection]' in tutor.llm.chat_json.call_args.args[0][0]['content']
assert all(r['evidence']['verification']=='source_verified' for r in result['pdf_references'])
history=memory.repo.get_conversation_with_figures('synthetic-selection')
assert history[-1]['selection_ref']['guided_visualization']==result['guided_visualization']
''')

    def test_signal_probabilities_and_geometry_are_consistent(self):
        self.run_script('''
import math,re
from statistics import NormalDist
from visualization.psychology_figures import signal_figure
base={'phase':2,'d_prime':1.5,'criterion':.75}
first=signal_figure(base);strict=signal_figure(base|{'phase':3,'criterion':1.5})
different=signal_figure(base|{'phase':5,'d_prime':2.5,'criterion':1.5})
assert math.isclose(first['rates']['hit'],.7733726476231317)
assert math.isclose(first['rates']['false_alarm'],.22662735237686826)
assert strict['rates']['hit']==.5
assert math.isclose(strict['rates']['false_alarm'],.06680720126885809)
assert math.isclose(different['rates']['hit'],.8413447460685429)
assert strict['rates']['hit']<first['rates']['hit'] and strict['rates']['false_alarm']<first['rates']['false_alarm']
assert strict['noise_path']==first['noise_path'] and strict['signal_path']==first['signal_path']
assert strict['roc_path']==first['roc_path']
assert different['rates']['false_alarm']==strict['rates']['false_alarm']
assert different['roc_path']!=strict['roc_path']
for figure in [first,strict,different]:
 rates=figure['rates']
 assert math.isclose(rates['hit']+rates['miss'],1)
 assert math.isclose(rates['false_alarm']+rates['correct_rejection'],1)
 assert math.isclose(NormalDist().inv_cdf(rates['hit'])-NormalDist().inv_cdf(rates['false_alarm']),figure['d_prime'])
 assert math.isclose(figure['roc_points'][1]['x'],48+290*rates['false_alarm'],abs_tol=.001)
 assert math.isclose(figure['roc_points'][1]['y'],218-190*rates['hit'],abs_tol=.001)
 coordinates=[tuple(map(float,p.split(','))) for p in re.findall(r'[ML]([0-9.]+,[0-9.]+)',figure['roc_path'])]
 assert coordinates[0]==(48,218) and coordinates[-1]==(338,28)
 assert all(x2>=x1 and y2<=y1 for (x1,y1),(x2,y2) in zip(coordinates,coordinates[1:]))
for invalid in [base|{'criterion':float('nan')},base|{'d_prime':True},base|{'d_prime':4},base|{'phase':9},base|{'html':'<script>'}]:
 try:signal_figure(invalid);raise AssertionError('接受无效参数')
 except ValueError:pass
''')

    def test_special_presets_bind_textbook_and_keep_distinct_states(self):
        self.run_script('''
sources=[material(7,3,430),material(9,2,77)]
special=[('请结合教材解释信号检测论中判准、辨别力和ROC曲线的关系。',
          '信号检测论区分判准与辨别力，ROC曲线对应击中率和虚报率。','signal_detection','signal',6),
         ('请结合教材解释视觉空间线索范式，以及有效线索和无效线索的区别。',
          '空间线索范式中，有效线索与无效线索对应目标是否位于先前线索化位置。','spatial_cue','spatial',5)]
reports=[]
for q,reply,topic,kind,count in special:
 llm=Mock();guide=build_guide(llm,q,reply,sources,execution,student_id='synthetic-special',turn_id=topic)
 assert guide and guide['generation']['preset_id']=='psychology:'+topic.replace('_','-'),topic
 assert len(guide['frames'])==count
 llm.chat_json.assert_not_called()
 assert len({json.dumps(f[kind],sort_keys=True) for f in guide['frames']})==count
 for frame in guide['frames']:
  ref=frame['selection_ref'];validate_selection(PDFSelection(kind='text',**{k:ref[k] for k in ['document_id','version','rects']}))
  assert ref['location_kind']=='paragraph_anchor'
  assert ref['chapter_id']==(7 if kind=='signal' else 9)
 if kind=='signal':
  assert guide['frames'][-1]['signal']['previous_point']
  assert [(f['signal']['d_prime'],f['signal']['criterion']) for f in guide['frames']]==[(1.5,.75)]*3+[(1.5,1.5)]*2+[(2.5,1.5)]
 else:assert [f['spatial']['phase'] for f in guide['frames']]==['fixation','cue','valid','invalid','compare']
 for question in ['请用我的实验解释'+q,'SOA=200毫秒，'+q,'不要可视化，'+q]:
  assert match_topic(question,reply,sources,execution) is None
 assert match_topic(q,reply,[material(2,2,35)],execution) is None
 if kind=='signal':
  assert match_topic('请讲解信号检测论',reply,sources,execution)=='signal_detection'
  assert match_topic('ROC曲线如何理解',reply,sources,execution)=='signal_detection'
  assert match_topic('什么是信号检测论',reply,sources,execution) is None
 reports.append({'question':q,'guide':guide,'method':'合成已核验回答与确定性图形；非真实模型问答'})
Path('artifacts/psychology-special-preset-acceptance.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
''')


if __name__ == '__main__':
    unittest.main()
