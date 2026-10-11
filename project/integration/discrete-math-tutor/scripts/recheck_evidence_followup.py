import json
from concurrent.futures import ThreadPoolExecutor
from scripts.evaluate_evidence import BASE,check_case
old=json.loads((BASE/'artifacts/evidence-followup-first.json').read_text(encoding='utf8'))
cases=[dict(id=r['case']['id'],question=r['case']['question'],evidence=r['sources'],expected='sufficient' if r['case'].get('chapter') else 'deny') for r in old]
with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(check_case,cases))
(BASE/'artifacts/evidence-followup-recheck.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
print('RECHECK',sum(r['correct'] for r in results),len(results),flush=True)
