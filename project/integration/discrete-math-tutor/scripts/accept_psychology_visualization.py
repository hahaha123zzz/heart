"""仅对合成验收问答和教材依据调用真实模型，验收自动图解。"""
import json,os,sys
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env');load_dotenv(ROOT/'deepseek.env')
os.environ['TUTOR_COURSE']='experimental-psychology-3';os.environ['VISUALIZATION_ON_DEMAND']='1';os.environ['LLM_MOCK']='0'
from llm.client import LLMClient
from knowledge.psychology_retrieval import retrieve
from visualization.on_demand import generate_guide

def main():
    accepted=json.loads((ROOT/'artifacts/psychology-original-pipeline-acceptance.json').read_text(encoding='utf-8'))
    results=[]
    for index,case in enumerate(accepted):
        assert case['answer_status']=='answered'
        sources=retrieve(case['question'],[])
        guide=generate_guide(LLMClient(),case['question'],case['reply'],sources,
            SimpleNamespace(hint_only=False,learning_intents=['explain']),student_id='isolated-visualization',turn_id='visual-case-'+str(index))
        results.append({'question':case['question'],'guide':guide})
        (ROOT/'artifacts/psychology-visualization-acceptance.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'case':index+1,'templates':guide['generation']['templates'] if guide else [],'steps':len(guide['frames']) if guide else 0},ensure_ascii=False),flush=True)
    assert all(r['guide'] for r in results),'自动图解未全部生成，请检查教材支持或模型核验结果'

if __name__=='__main__':main()
