import json
from concurrent.futures import ThreadPoolExecutor
from scripts.evaluate_evidence import BASE,check_case
cases=json.loads((BASE/'tests/data/rag_evidence_fresh_2026_10_10.json').read_text(encoding='utf8'))
with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(check_case,cases))
out={'cases':results,'correct':sum(r['correct'] for r in results),'total':len(results)}
(BASE/'artifacts/evidence-fresh.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
print('FRESH',out['correct'],out['total'],flush=True)
