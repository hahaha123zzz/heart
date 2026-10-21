"""隔离检索专项；每次尝试独立保存，不生成答案、不修改学习状态。"""
import argparse,json,time,sys
from pathlib import Path
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def verify_source_identity(candidate,sources):
    from knowledge.source_mapping import block_text
    from knowledge.grounding_text import normalized
    root=Path(candidate)/'input'
    registry={r['document_id']:r for r in json.loads((root/'pdf_manifest.json').read_text(encoding='utf-8'))}
    for source in sources:
        record=registry[source['document_id']]
        assert record['version']==source['version'] and record['chapter_id']==source['chapter_id'],'来源版本/章节不符'
        raw=json.loads((root/'chapters'/f"chapter_{record['chapter_id']:02d}"/'document.json').read_text(encoding='utf-8'))
        blocks={b['block_index']:b for b in raw['blocks']};spans=source['location']['source_spans']
        assert spans,'缺少原文范围'
        actual=[]
        for span in spans:
            text=block_text(blocks[span['block_id']]);start,end=span['block_start'],span['block_end']
            assert 0<=start<end<=len(text),'原文范围越界'
            actual.append(text[start:end])
        assert normalized(source['quote'] or source['text']) in normalized(''.join(actual)),'引句不在实际原文范围'
    return len(sources)

def main():
    p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:18978');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--case',action='append',default=[])
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);run=str(time.time_ns());rows=[]
    health=requests.get(a.url+'/health',timeout=120);health.raise_for_status();candidate=health.json()['candidate']
    original='第一章的实验程序和第二章的自变量控制有哪些联系？'
    cases=[('legacy_baseline','第一章 实验程序 第二章 自变量控制 联系',{'backend':'baseline','coverage':False}),
       ('legacy_lightrag','第一章 实验程序 第二章 自变量控制 联系',{'coverage':False}),
       ('cross_chapter',original,{}),('single','什么是自变量？',{}),
       ('single_chapter','实验程序是什么？',{'current_target':{'target_id':'query','name':'实验程序','chapter_id':1}}),
       ('comparison','被试内设计和被试间设计有什么区别？',{}),
       ('same_chapter','第二章的自变量和因变量有什么区别？',{}),
       ('missing_object','第一章的实验程序和第二章的火星玄武岩晶体结构有哪些联系？',{}),
       ('q5_interjection',original,{'q5_path':True}),
       ('duplicate_sources','第二章的自变量和自变量的操作定义有什么关系？',{}),
       ('overlapping_sources','第二章的自变量定义和自变量的含义有哪些联系？',{}),
       ('cancel',original,{'fault':'cancel'}),('backend_unavailable',original,{'fault':'backend_unavailable'}),
       ('source_stale',original,{'fault':'source_stale'})]
    if a.case:
        if not set(a.case)<={c[0] for c in cases}:raise ValueError('未知专项用例')
        cases=[c for c in cases if c[0] in a.case]
    for case,question,extra in cases:
        body={'case':'coverage-'+case,'backend':'lightrag','question':question,'coverage':True,'retrieval_only':True,**extra}
        started=time.monotonic()
        try:
            response=requests.post(a.url+'/turn',json=body,timeout=400);response.raise_for_status();d=response.json()
            (a.output/f'attempt-{run}-{case}.json').write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
            sources=d.get('sources',[]);verify_source_identity(candidate,sources);report=d.get('coverage') or {};calls=d.get('retrieval_calls',[])
            model_calls=d.get('model_calls',[])
            tokens=sum((c.get('usage') or {}).get('total_tokens',0) or 0 for c in model_calls)+sum(c.get('usage',{}).get('usage',{}).get('total_tokens',0) or 0 for c in calls)
            identities=[json.dumps([r['document_id'],r['version'],r['location']['source_spans']],sort_keys=True) for r in sources]
            passed=bool(d.get('retrieval_completed') and sources and not d.get('fallback') and len(identities)==len(set(identities)))
            if not case.startswith('legacy') and case not in ('single','single_chapter','cancel','backend_unavailable','source_stale','missing_object'):
                passed=passed and report.get('status')=='covered' and report.get('supplemental_calls',99)<=len(report.get('required',[]))
            if case in ('single','single_chapter'):passed=passed and len(calls)==1 and report.get('retrieval_calls')==1
            if case=='missing_object':passed=passed and report.get('status')=='partial' and any('玄武岩' in m['query'] for m in report.get('missing',[]))
            if case=='overlapping_sources':passed=passed and any(e['stage']=='merged_dedupe' and any(not r['accepted'] for r in e['rows']) for e in d.get('coverage_trace',[]))
            if case=='q5_interjection':passed=passed and d.get('q5_unchanged') is True and d.get('q5_before',{}).get('path_id') is not None
            if case in ('cancel','backend_unavailable','source_stale'):
                expected={'cancel':'CancelledError','backend_unavailable':'FileNotFoundError','source_stale':'ValueError'}[case]
                passed=bool(d.get('error') and not sources and not d.get('fallback') and (d.get('error_type')==expected or (case=='source_stale' and '教材已更新' in d.get('error',''))))
            row={'case':case,'passed':passed,'attempt_id':d.get('attempt_id'),'error':d.get('error'),
              'scope':'legacy diagnosis only' if case.startswith('legacy') else 'retrieval coverage only',
              'coverage_passed':report.get('status')=='covered',
              'actual_backends':d.get('actual_backends'),'fallback':d.get('fallback'),'source_count':len(sources),'source_identity_verified':bool(sources),
              'chapters':sorted({r['chapter_id'] for r in sources}),'coverage':report,'q5_unchanged':d.get('q5_unchanged'),
              'retrieval_seconds':sum(c.get('seconds',0) for c in calls),'total_seconds':d.get('total_seconds'),
              'model_create_calls':len(model_calls)+sum(c.get('usage',{}).get('llm_calls',0) for c in calls),
              'returned_tokens':tokens,'cost':None,'original_question':original if case.startswith('legacy') else question}
        except Exception as exc:
            row={'case':case,'passed':False,'error':str(exc),'error_type':type(exc).__name__,'http_seconds':time.monotonic()-started}
        rows.append(row)
        (a.output/f'matrix-{run}.json').write_text(json.dumps({'run':run,'rows':rows,'all_passed':all(r['passed'] for r in rows),
            'scope':'isolated retrieval/Q2/tool only; no final answer or page acceptance'},ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(row,ensure_ascii=False),flush=True)
    return 0 if all(r['passed'] for r in rows) else 1
if __name__=='__main__':raise SystemExit(main())
