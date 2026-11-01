"""C4自动结构与成本统计；语义和教学效果留给人工审查。"""
import argparse
import json
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.benchmark_output_speed import effective_first_answer, summary


def audit(directory):
    rows=[]
    for path in sorted(directory.glob('[0-9]*-*.json')):
        data=json.loads(path.read_text(encoding='utf-8'))
        pair,case,version=path.stem.split('-',2)
        result=data.get('result') or {};text=str(result.get('reply') or '')
        refs=result.get('pdf_references') or []
        markers={int(n) for n in re.findall(r'\[(\d+)\]',text)}
        indices={r.get('source_index',-1)+1 for r in refs if type(r.get('source_index')) is int}
        usage=(result.get('loop_summary') or {}).get('usage') or {}
        row={'case':case,'version':version,'pair':int(pair),'passed':data.get('passed',False),
            'seconds':data['seconds'],'effective_first_answer':effective_first_answer(data['events']) if data.get('passed') else None,
            'answer_status':result.get('answer_status'),'citation_indices_valid':markers<=indices if markers else None,
            'has_citation':bool(markers),'format_leak':bool(re.search(r'DSML|"(?:source_ids|claims|block_id)"',text,re.I)),
            'prompt_tokens':usage.get('prompt_tokens'),'completion_tokens':usage.get('completion_tokens'),
            'total_tokens':usage.get('total_tokens'),'semantic_review':'待人工审核','artifact':path.name}
        rows.append(row)
    return {'summary':summary(rows),'cases':rows,'semantic_passed':None,
        'note':'自动检查不证明教材支持、教学效果或价格；token仅含Loop上报部分。'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);args=parser.parse_args()
    output=args.directory/'c4-audit.json'
    output.write_text(json.dumps(audit(args.directory),ensure_ascii=False,indent=2),encoding='utf-8')
    print(output)
