"""分开汇总检索、证据文字/几何、回答覆盖和待复核语义；保留全部失败。"""
import argparse,collections,hashlib,json,math
from pathlib import Path
from knowledge.grounding_text import normalized
from knowledge.pdf_reader import documents,evidence_text,pdf_path

ROOT=Path(__file__).resolve().parents[1]
BENCHMARK=ROOT.parents[1]/'docs/research/2026-10-16-citation-grounding/benchmark.json'


def percentile(values,p):
    if not values:return None
    values=sorted(values);at=(len(values)-1)*p;lo=math.floor(at);hi=math.ceil(at)
    return round(values[lo]+(values[hi]-values[lo])*(at-lo),3)


def analyze(raw):
    cases={c['id']:c for c in json.loads(BENCHMARK.read_text(encoding='utf-8'))['cases']}
    registry={r['document_id']:r for r in documents()};rows=[]
    for row in raw['results']:
        case=cases[row['id']];result=row.get('result',{});refs=result.get('pdf_references',[]);checks=[];legacy_text=[]
        for ref in refs:
            evidence=ref.get('evidence')
            if not evidence:
                selection=ref.get('selection_ref') or {}
                if selection.get('rects'):
                    try:legacy_text.append({'document_id':selection['document_id'],
                        'text':evidence_text(selection['document_id'],selection['version'],selection['rects'])})
                    except (ValueError,OSError):pass
                continue
            check={'evidence_id':evidence['evidence_id'],'quote':evidence['quote'],'status':evidence['location_status']}
            if evidence['location_status']=='exact':
                record=registry.get(evidence['document_id'])
                try:
                    text='\n'.join(evidence_text(evidence['document_id'],evidence['document_version'],s['rects']) for s in evidence['selections'])
                    check['geometry_text_pass']=bool(record and record['version']==evidence['document_version'] and
                        normalized(evidence['quote']) in normalized(text))
                except (ValueError,OSError):check['geometry_text_pass']=False
            checks.append(check)
        supports=[]
        for target in case['support'] if case['category']!='negative' else []:
            retrieval=[s for call in row.get('retrievals',[]) for s in call['sources'] if s['chapter_id']==target['chapter']]
            recalled=any(normalized(target['quote']) in normalized(s['text'].replace(' | ',' ')) for s in retrieval)
            selected=[r['evidence'] for r in refs if r.get('evidence',{}).get('document_id')==target['document_id']
                and r['evidence'].get('document_version')==target['version'] and r['evidence'].get('source_block_id')==target['block_id']
                and r['evidence'].get('location_status')=='exact']
            selected.sort(key=lambda e:e.get('block_start',0))
            covered=normalized(target['quote']) in normalized(''.join(e['quote'] for e in selected))
            if raw['mode']=='legacy':
                covered=any(t['document_id']==target['document_id'] and normalized(target['quote']) in normalized(t['text']) for t in legacy_text)
            supports.append({'block_id':target['block_id'],'retrieved_full_support':recalled,'covered_full_support':covered})
        negative_ok=None
        if case['category']=='negative':
            negative_ok=not refs and (bool(row.get('error')) or result.get('answer_status')!='answered')
        rows.append({'id':row['id'],'order':row['order'],'split':row['split'],'category':row['category'],
            'status':result.get('answer_status','error'),'seconds':row['seconds'],'logical_calls':len(row.get('calls',[])),
            'network_attempts':len(row.get('raw_calls',[])) if 'raw_calls' in row else None,'regenerated':result.get('regenerated',0),
            'geometry':checks,'supports':supports,'negative_rejected':negative_ok,
            'semantic_review':'pending_independent_review','failure':row.get('error') or result.get('quality') or result.get('evidence_check')})
    first={}
    for row in rows:first.setdefault(row['id'],row)
    initial=list(first.values());positives=[s for r in initial for s in r['supports']]
    exact=[c for r in rows for c in r['geometry'] if c['status']=='exact']
    summary={'unique_cases':len(first),'runs':len(rows),'statuses':dict(collections.Counter(r['status'] for r in rows)),
        'initial_statuses':dict(collections.Counter(r['status'] for r in initial)),
        'positive_gold_supports':len(positives),'fully_retrieved_supports':sum(s['retrieved_full_support'] for s in positives),
        'fully_covered_supports':sum(s['covered_full_support'] for s in positives),
        'exact_support_coverage':sum(s['covered_full_support'] for s in positives)/len(positives) if positives else None,
        'published_exact_evidence':len(exact) if raw['mode']=='candidate' else None,
        'geometry_text_pass':sum(c['geometry_text_pass'] for c in exact) if raw['mode']=='candidate' else None,
        'semantic_support_rate':None,'independent_human_reviews':0,
        'negative_unique_passed':sum(r['negative_rejected'] is True for r in initial),
        'negative_unique_total':sum(r['category']=='negative' for r in initial),
        'latency_seconds':{'all_p50':percentile([r['seconds'] for r in rows],.5),'all_p95':percentile([r['seconds'] for r in rows],.95),
            'answered_p50':percentile([r['seconds'] for r in rows if r['status']=='answered'],.5),
            'answered_p95':percentile([r['seconds'] for r in rows if r['status']=='answered'],.95)},
        'calls':{'logical_p50':percentile([r['logical_calls'] for r in rows],.5),'logical_p95':percentile([r['logical_calls'] for r in rows],.95),
            'network_total':sum(r['network_attempts'] or 0 for r in rows)}}
    return {'mode':raw['mode'],'method':'文字和几何核验不是语义或人工图像验收；覆盖要求完整金标准支持原文，拒绝与降级计未覆盖；所有失败保留',
        'performance_limit':'旧/新试验存在并行时段；耗时是本机该次运行实测，不能解读为独立同负载提速对比。',
        'summary':summary,'results':rows}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('报告已存在，不覆盖')
    raw=json.loads(args.input.read_text(encoding='utf-8'))
    if raw['benchmark_sha256']!=hashlib.sha256(BENCHMARK.read_bytes()).hexdigest():raise ValueError('基准已变化')
    report=analyze(raw);report['input_sha256']=hashlib.sha256(args.input.read_bytes()).hexdigest()
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report['summary'],ensure_ascii=False))


if __name__=='__main__':main()
