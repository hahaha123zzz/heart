"""冻结受控证据测试 + 旧检索问题诊断；不修改真实学生数据。"""
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
load_dotenv(override=True)
from llm.client import LLMClient
from agents.context_sufficiency import ContextSufficiency
BASE=Path(__file__).resolve().parents[1]

def check_case(case):
    gate=ContextSufficiency(LLMClient(mock=False))
    decision=gate.check(case['question'],case['evidence'],history=case.get('history',[]))
    result={**case,'decision':decision.model_dump()}
    result['correct']=(decision.allowed if case['expected']=='sufficient' else not decision.allowed and decision.status!='unavailable')
    print(case['id'],decision.status,decision.reason,flush=True)
    return result

if __name__=='__main__':
    data=json.loads((BASE/'tests/data/rag_evidence_holdout_2026_10_10.json').read_text(encoding='utf8'))
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(check_case,data['cases']))
    out={'controlled':results,'correct':sum(r['correct'] for r in results),'total':len(results)}
    (BASE/'artifacts/evidence-controlled.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
    print('CONTROLLED',out['correct'],out['total'],flush=True)
    import sys
    if "--controlled-only" in sys.argv: raise SystemExit(0)
    from knowledge.textbook import load_textbook
    from knowledge.hybrid_retrieval import retrieve_hybrid
    previous=json.loads((BASE/'tests/data/rag_symbol_followup_2026_10_10.json').read_text(encoding='utf8'))
    print('FOLLOWUP_SCHEMA',list(previous) if isinstance(previous,dict) else 'list',flush=True)
    cases=previous.get('cases',previous.get('questions',[])) if isinstance(previous,dict) else previous
    diagnostics=[]
    for item in cases:
        question=item.get('query',item.get('question'))
        if not question: continue
        hits=retrieve_hybrid(question,load_textbook(),limit=2)
        evidence=[{'id':str(i),'source':h.source,'section':h.section,'text':h.text} for i,h in enumerate(hits,1)]
        decision=ContextSufficiency(LLMClient(mock=False)).check(question,evidence)
        diagnostics.append({'case':item,'sources':evidence,'decision':decision.model_dump()})
        print('RETRIEVAL',item.get('id'),decision.status,decision.reason,flush=True)
    (BASE/'artifacts/evidence-followup.json').write_text(json.dumps(diagnostics,ensure_ascii=False,indent=2),encoding='utf8')
