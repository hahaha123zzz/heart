import os,sys,tempfile,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
temp=tempfile.TemporaryDirectory(prefix="memory-browser-acceptance-")
parser=argparse.ArgumentParser()
parser.add_argument("--port",type=int,default=8011)
port=parser.parse_args().port
os.environ.update(DATABASE_URL="sqlite:///"+str(Path(temp.name)/"acceptance.db"),LLM_MOCK='1',MEMORY_EMBED_MODEL='',RAG_RERANK_MODEL='',MEMORY_WORKER_ENABLED='1',MEMORY_REFLECTION_LLM='0')
import knowledge.hybrid_retrieval as hybrid
# 本轮只验收记忆流程，教材 dense 分支不加载模型。
hybrid._vectors=lambda *args:(None,[])
import main
import orchestrator as orchestrator_module
from knowledge.textbook import TextbookChunk, terms_for
fixture_text="集合是确定对象的整体；集合的交集由两个集合的公共元素组成。"
fixture=TextbookChunk(source="本地联调夹具",section="集合",text=fixture_text,terms=terms_for(fixture_text))
orchestrator_module.retrieve_hybrid=lambda *args,**kwargs:[fixture]
from models.student_state import StudentState
from models.lesson_plan import LessonPlan,LessonStep
from models.evidence import Evidence
from memory.evidence_policy import EvidenceDecision
from uuid import uuid4
m=main.orchestrator.memory
sid='demo-memory-acceptance'
m.accounts.create_test_account(sid,24)
m.set_preferences(sid,{'answer_length':1,'example_density':0.5,'learning_pace':0})
for point in ('集合','关系'):
    st=StudentState(student_id=sid,current_concept=point,mastery=.5)
    plan=LessonPlan(goal=point,steps=[LessonStep(step_id='S1',objective='辨认'+point)],current_step='S1')
    quote='我正在学习'+point+'，请用小例子说明'
    m.commit_learning_turn(student_id=sid,point=point,event_id=str(uuid4()),expected_token=m.get_version(sid,point),message=quote,reply='本地模拟解释',state=st,lesson_plan=plan,decision=EvidenceDecision(False,False,'提问不作为独立作答'),evidence=[Evidence(content=quote,source_quote=quote,confidence=.9)],hypotheses=[],strategy='socratic_questioning',success=None,instructional_move='worked_example')
m.add_hypothesis(sid,'集合','set_element_confusion','混淆元素与集合',.9)
m.add_hypothesis(sid,'集合','set_subset_confusion','混淆属于与包含',.9)
import uvicorn
uvicorn.run(main.app,host='127.0.0.1',port=port)
