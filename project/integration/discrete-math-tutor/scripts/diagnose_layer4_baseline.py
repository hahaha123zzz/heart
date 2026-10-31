"""只读区分索引、候选、排序和来源映射缺口；块范围命中仅是诊断线索。"""
import argparse
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.build_layer4_benchmark import digest
from scripts.evaluate_layer4_benchmark import matches
from knowledge.grounding_text import normalized


def diagnose(data, report, index):
    if report['manifest']['benchmark_sha256'] != digest(data):
        raise ValueError('benchmark_report_mismatch')
    if report['manifest']['index_sha256'] != digest(index):
        raise ValueError('index_report_mismatch')
    cases = {c['id']: c for c in json.loads(data.read_text(encoding='utf-8'))['cases']}
    with closing(sqlite3.connect(index.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        indexed = [dict(r) for r in db.execute('SELECT id,chapter_id,block_start,block_end,text FROM chunks')]
    missed = []
    for run in report['runs']:
        for support in cases[run['case_id']]['supports']:
            if any(matches(source, support) for source in run['sources']):
                continue
            possible = {row['id'] for row in indexed if row['chapter_id'] == support['chapter_id']
                        and row['block_start'] is not None and row['block_end'] is not None
                        and row['block_start'] <= support['block_id'] <= row['block_end']}
            trace = run.get('trace', {}).get('retrieval', {})
            candidates, selected = set(trace.get('candidates', [])), set(trace.get('selected', []))
            reason = ('not_covered_by_index_block_range' if not possible else
                      'outside_recall_candidates' if not possible & candidates else
                      'outside_final_topk_or_gate' if not possible & selected else
                      'selected_range_without_matching_provenance')
            missed.append({'case_id': run['case_id'], 'category': run['category'],
                           'object_id': support['object_id'], 'block_id': support['block_id'],
                           'reason': reason, 'possible_index_ids': sorted(possible),
                           'candidate_ids': sorted(possible & candidates),
                           'selected_ids': sorted(possible & selected),
                           'normalized_quote_in_possible_chunk': any(support['quote'] and normalized(support['quote'])
                               in normalized(row['text'].replace(' | ', ' ')) for row in indexed if row['id'] in possible),
                           'note': '索引块范围不等于实际文本包含，尚须原文交集核验'})
    return {'benchmark_sha256': digest(data), 'index_sha256': digest(index),
            'missing_anchors': len(missed), 'reasons': dict(Counter(r['reason'] for r in missed)), 'rows': missed}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--index', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError('不能覆盖诊断证据')
    result = diagnose(args.data, json.loads(args.report.read_text(encoding='utf-8')), args.index)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'missing_anchors': result['missing_anchors'], 'reasons': result['reasons']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
