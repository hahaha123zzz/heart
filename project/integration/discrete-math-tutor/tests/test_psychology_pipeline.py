"""心理学原Agent提示词、检索及充分性核验的隔离回归。"""
import os,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class PsychologyPipelineTests(unittest.TestCase):
    def test_original_agents_use_psychology_rules_and_structural_evidence(self):
        script='''
from agents.course_prompts import SCOPE
from agents.response_generator import SYSTEM_PROMPT as response
from agents.quality_checker import SYSTEM_PROMPT as quality
from agents.lesson_planner import SYSTEM_PROMPT as lesson
from agents.question_designer import SYSTEM_PROMPT as question
from agents.pdf_selection_tutor import SYSTEM as selection
from agents.proof_checker import needs_proof_audit
from knowledge.hybrid_retrieval import _chapter_hint
from knowledge.psychology_retrieval import retrieve
from knowledge.retriever import retrieve_knowledge
from unittest.mock import patch
assert all('实验心理学' in p and '离散数学' not in p for p in [response,quality,lesson,question,selection])
assert not needs_proof_audit('证明随机化有助于控制混淆变量','解释推导','explain')
assert _chapter_hint('变量之间的关系',psychology=True) is None
assert _chapter_hint('表4-6',psychology=True)==4
assert retrieve_knowledge('关系')==[]
from unittest.mock import Mock
from types import SimpleNamespace
from agents.quality_checker import QualityChecker
from agents.teaching_planner import TeachingPlan
from models.student_state import StudentState
llm=SimpleNamespace(mock=False,chat_json=Mock(return_value={'passed':True,'issues':[],'suggestions':''}))
checker=QualityChecker(llm);checker.proof_checker=Mock()
checked=checker.check('随机化有助于控制混淆变量。[1]',StudentState(),TeachingPlan(goal='实验控制',strategy='worked_example',action='explain',difficulty='medium'),'证明随机化为什么有助于控制混淆变量',textbook_excerpts='[1] 随机化可平衡额外变量。')
assert checked.passed and checked.timings['mode']=='single'
checker.proof_checker.check.assert_not_called()
wrong=checker.check('再让每名被试接受自变量的所有水平。[1]',StudentState(),TeachingPlan(goal='区组设计',strategy='worked_example',action='explain',difficulty='medium'),'解释随机区组设计',textbook_excerpts='[1] 区组内每名被试随机接受一种处理水平。')
assert not wrong.passed and any('每名被试接受所有水平' in issue for issue in wrong.issues)
correct=checker.check('不是每名被试接受所有水平，而是区组内不同被试分别接受不同水平。[1]',StudentState(),TeachingPlan(goal='区组设计',strategy='worked_example',action='explain',difficulty='medium'),'解释随机区组设计',textbook_excerpts='[1] 每名被试随机接受一种处理水平。')
assert correct.passed
for answer in ['让区组整体覆盖所有处理水平。[1]','被试间每名被试只接受一个水平，而被试内每名被试接受所有水平。[1]']:
 assert checker.check(answer,StudentState(),TeachingPlan(goal='设计',strategy='worked_example',action='explain',difficulty='medium'),'解释被试间设计',textbook_excerpts='[1] 实验设计的分组原则。').passed
with patch('knowledge.psychology_retrieval.retrieve_hybrid',return_value=[]):
 sources=retrieve('单因素随机区组设计为什么能控制个体差异？',[])
 assert any('每个区组的被试同质' in s.text for s in sources)
 assert any('每名被试随机接受一种处理水平' in s.text for s in sources)
 from knowledge.citation_locations import locate_source
 reference=locate_source(sources[0])['selection_ref']
 assert reference['location_kind']=='paragraph_anchor' and reference['rects'][0]['page']==7
 sources=retrieve('什么是自变量？',[])
 assert any(s.chapter_id==2 and '自变量' in s.text for s in sources)
print('PASS: 原Agent心理学规则、旧误解目录隔离、章节偏置关闭、完整概念上下文')
'''
        with tempfile.TemporaryDirectory() as directory:
            env=os.environ|{'TUTOR_COURSE':'experimental-psychology-3','DATABASE_URL':'sqlite:///'+str(Path(directory)/'test.db')}
            result=subprocess.run([sys.executable,'-X','utf8','-c',script],cwd=ROOT,env=env,text=True,capture_output=True,encoding='utf-8',timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)

if __name__=='__main__':unittest.main()
