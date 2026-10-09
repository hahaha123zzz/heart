"""真实模型验证：使用临时数据库验证表格、公式、绘图问答。"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser()
parser.add_argument("--case",type=int,choices=[1,2,3])
args=parser.parse_args()
with tempfile.TemporaryDirectory(prefix='tutor-multimodal-') as temp:
    os.environ['DATABASE_URL']='sqlite:///'+(Path(temp)/'test.sqlite').as_posix()
    os.environ['LLM_MOCK']='0'
    from database.database import engine
    from orchestrator import TutorOrchestrator
    tutor=TutorOrchestrator()
    result_path=ROOT/"knowledge"/"extracted_multimodal"/"real_validation.json"
    results=json.loads(result_path.read_text(encoding="utf-8")) if args.case and result_path.exists() else []
    try:
        for index,question in enumerate(['请根据教材绝对值函数的表格，说明x=-3和x=2时f(x)分别是多少。','请引用教材原公式，解释牛顿二项式定理公式中的C(n,k)。','请结合特殊图章节的完全匹配配图，解释粗边表示什么。']):
            if args.case and index+1 != args.case:
                continue
            results=[r for r in results if r['question'] != question]
            print('START '+str(index+1),flush=True)
            result=tutor.handle_turn('multimodal-real-'+str(index),question,account_type='test')
            results.append(dict(question=question,reply=result['reply'],image_refs=result.get('image_refs',[]),textbook_sources=result.get('textbook_sources',[]),quality=result.get('quality'),step_advanced=result.get('step_advanced')))
            (ROOT/'knowledge'/'extracted_multimodal'/'real_validation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
            print('OK '+str(index+1),flush=True)
    finally:
        engine.dispose()
