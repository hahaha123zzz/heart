"""用已保存的失败样例核对证明审核，不作为独立泛化评测。"""
import json
from pathlib import Path
from agents.proof_checker import ProofChecker
from llm.client import LLMClient
from knowledge.proof_units import units_for
BASE=Path(__file__).resolve().parents[1]
old=json.loads((BASE/'artifacts/long-proofs-quality-gate-gpu.json').read_text(encoding='utf8'))
tree=next(c for c in old if c['case']['id']=='tree-omitted')
unit=units_for(8)['定理8.16']
correct='教材在（3）⇒（4）处留给读者证明[1]。以下为补充推导：若T不连通，取不同分支顶点u,v，添加uv前没有u到v通路，故添加uv不能形成回路，矛盾。因此T连通。任取原图边e={x,y}，若T−e仍连通，则T−e中存在x到y的通路P，且P不含e。P与e构成T中的回路，违背T无回路。因此删去任意边后不连通，即（4）。'
bad='以下为补充推导：若T不连通，取不同分支顶点u,v，添加边uv后两端点间仍无通路，所以不产生回路，矛盾。故T连通。任取e={x,y}，若T−e连通，则其中有x到y的通路P；P与e构成回路，矛盾，所以每条边是割边。'
cases=[('old-undefined-endpoints',tree['response']['reply'],False),('correct-local-bindings',correct,True),('bad-added-edge-claim',bad,False)]
checker=ProofChecker(LLMClient(mock=False));results=[]
for label,response,expected in cases:
    audit=checker.check(response,tree['case']['question'],unit.text)
    results.append({'id':label,'response':response,'expected_pass':expected,'audit':audit.model_dump(),'matches_expected':audit.passed==expected and audit.status!='unavailable'})
    print(label,audit.model_dump(),flush=True)
(BASE/'artifacts/proof-audit-counterexamples.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
