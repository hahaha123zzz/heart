"""冻结样本的几何对照；不运行生成模型，不把位置通过当语义通过。"""
import argparse,json,time
from pathlib import Path
from unittest.mock import patch
from knowledge.citation_index import CitationIndex
from knowledge.citation_locations import locate_source
from knowledge.grounding_text import normalized
from knowledge.textbook import load_textbook,TextbookChunk,terms_for
from knowledge.pdf_reader import PDFSelection,resolve_selection,evidence_text

ROOT=Path(__file__).resolve().parents[3]/'docs/research/2026-10-16-citation-grounding'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--index',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--split',choices=['development','holdout','all'],default='all');args=parser.parse_args()
    if args.output.exists():raise ValueError('报告已存在，不覆盖')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    cases=json.loads((ROOT/'benchmark.json').read_text(encoding='utf-8'))['cases']
    corpus=load_textbook();index=CitationIndex(args.index.resolve());report={'method':'原文存在性/几何对照；没有测生成语义支持','results':[]}
    crops=args.output.parent/'baseline-crops';crops.mkdir(exist_ok=True)
    for case in cases:
        if args.split!='all' and case['split']!=args.split:continue
        row={'id':case['id'],'split':case['split'],'category':case['category'],'supports':[]}
        for item in case['support']:
            result={'document_id':item['document_id'],'block_id':item['block_id'],'quote':item['quote'],'expected_pages':item['pages']}
            try:
                located=index.locate(item['document_id'],item['version'],item['quote'],block_id=item['block_id'])
                result['candidate']=located
                if located['status']=='exact':
                    with patch('knowledge.pdf_reader.CROPS',crops):
                        selection=resolve_selection(PDFSelection(document_id=item['document_id'],version=item['version'],kind='text',rects=located['rects']))
                    result['candidate_crop_contains_quote']=normalized(item['quote']) in normalized(evidence_text(item['document_id'],item['version'],located['rects']))
                    result['candidate_pages_correct']=sorted({r['page'] for r in located['rects']})==item['pages']
                else:result['candidate_crop_contains_quote']=False
            except ValueError as exc:result['candidate']={'status':'stale' if '版本' in str(exc) else 'unlocated','reason':str(exc)}
            if case['category']!='negative':
                source=next((c for c in corpus if c.chapter_id==item['chapter'] and c.block_start is not None and c.block_start<=item['block_id']<=c.block_end),None)
                if source:
                    try:
                        with patch('knowledge.pdf_reader.CROPS',crops):old=locate_source(source,'解释教材[1]')
                        result['legacy']=old
                        text=((old or {}).get('selection_ref') or {}).get('text','')
                        result['legacy_crop_contains_quote']=normalized(item['quote']) in normalized(text)
                    except (ValueError,RuntimeError) as exc:result['legacy']={'error':str(exc)}
            row['supports'].append(result)
        report['results'].append(row)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(case['id'],','.join(r['candidate']['status'] for r in row['supports']),flush=True)
    exact=[s for row in report['results'] for s in row['supports'] if s['candidate']['status']=='exact']
    positives=[s for row in report['results'] if row['category']!='negative' for s in row['supports']]
    report['counts']={'cases':len(report['results']),'positive_supports':len(positives),'candidate_exact':len(exact),
        'candidate_correct':sum(s.get('candidate_crop_contains_quote',False) and s.get('candidate_pages_correct',False) for s in exact),
        'legacy_complete_quotes':sum(s.get('legacy_crop_contains_quote',False) for s in positives)}
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');index.close()
    print(json.dumps(report['counts'],ensure_ascii=False))


if __name__=='__main__':main()
