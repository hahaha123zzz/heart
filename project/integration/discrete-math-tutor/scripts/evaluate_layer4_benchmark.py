"""只读检查冻结教材候选及已有检索结果，不调用LLM、不写业务数据库。"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.build_layer4_benchmark import block_text, digest


def validate(data, course_dir):
    if data.get('schema') != 'layer4-benchmark-v1':
        raise ValueError('unsupported_benchmark_schema')
    course_dir = course_dir.resolve()
    if not {'manifest.json', 'pdf_manifest.json'} <= data['source_files'].keys():
        raise ValueError('course_manifest_not_frozen')
    for relative, expected in data['source_files'].items():
        path = (course_dir / relative).resolve()
        if not path.is_relative_to(course_dir):
            raise ValueError('source_path_outside_course')
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f'source_snapshot_changed: {relative}')
    documents = {r['document_id']: r for r in json.loads((course_dir/'pdf_manifest.json').read_text(encoding='utf-8'))}
    loaded, seen, groups = {}, set(), {}
    locations = Counter()
    for case in data['cases']:
        if case['id'] in seen:
            raise ValueError('duplicate_case_id')
        seen.add(case['id'])
        previous = groups.setdefault(case['group_id'], case['split'])
        if previous != case['split']:
            raise ValueError('group_crosses_splits')
        if case['teacher_reviewed'] or case['semantic_reference'] is not None:
            raise ValueError('this_candidate_schema_requires_separate_semantic_review')
        for support in case['supports']:
            record = documents.get(support['document_id'])
            if not record or record['version'] != support['version'] or record['chapter_id'] != support['chapter_id']:
                raise ValueError('anchor_document_identity')
            if record['chapter_id'] not in loaded:
                path = course_dir/'chapters'/f"chapter_{record['chapter_id']:02d}"/'document.json'
                pdf_relative = f"chapters/chapter_{record['chapter_id']:02d}/chapter_{record['chapter_id']:02d}.generated.pdf"
                if data['source_files'].get(pdf_relative) != record['version'] or str(path.relative_to(course_dir)).replace('\\', '/') not in data['source_files']:
                    raise ValueError('document_or_pdf_not_frozen')
                loaded[record['chapter_id']] = {b['block_index']: b for b in json.loads(path.read_text(encoding='utf-8'))['blocks']}
            block = loaded[record['chapter_id']].get(support['block_id'])
            if not block or block_text(block) != support['quote'] or block.get('section_id') != support['section_id']:
                raise ValueError('anchor_quote_mismatch')
            if hashlib.sha256(support['quote'].encode()).hexdigest() != support['quote_sha256']:
                raise ValueError('anchor_quote_hash_mismatch')
            for rect in support['rects']:
                if not (1 <= rect['page'] <= record['page_count'] and
                        0 <= rect['x1'] < rect['x2'] <= 1 and 0 <= rect['y1'] < rect['y2'] <= 1):
                    raise ValueError('invalid_normalized_rect')
            if support.get('asset_path') and data['source_files'].get(support['asset_path']) != support['asset_sha256']:
                raise ValueError('asset_not_in_snapshot')
            locations[support['location_status']] += 1
    return {'cases': len(seen), 'categories': dict(Counter(c['category'] for c in data['cases'])),
            'splits': dict(Counter(c['split'] for c in data['cases'])), 'anchor_locations': dict(locations),
            'source_snapshot_valid': True, 'teacher_reviewed': 0, 'semantic_quality_passed': False,
            'blind_holdout': data.get('blind_holdout', False)}


def matches(source, support):
    if source.get('document_id') != support['document_id'] or source.get('version') != support['version']:
        return False
    if support.get('asset_id') and support.get('asset_sha256'):
        if any(item.get('id') == support['asset_id'] and item.get('sha256') == support['asset_sha256']
               and item.get('document_id') == support['document_id'] and item.get('version') == support['version']
               for item in source.get('image_refs', [])):
            return True
    location = source.get('location') or {}
    evidence = location.get('evidence') or {}
    block_id = evidence.get('source_block_id')
    if block_id is not None:
        return block_id == support['block_id']
    spans = location.get('source_spans') or source.get('source_spans') or []
    return any(span.get('block_id') == support['block_id'] for span in spans)


def score(data, runs, k=6):
    cases = {case['id']: case for case in data['cases']}
    seen, rows = set(), []
    for run in runs:
        case_id = run['case_id']
        if case_id in seen or case_id not in cases:
            raise ValueError('unknown_or_duplicate_run')
        seen.add(case_id)
        case = cases[case_id]
        if not case['supports']:
            continue
        sources = run.get('sources', [])[:k]
        hit = [any(matches(source, support) for source in sources) for support in case['supports']]
        rank = next((i for i, source in enumerate(sources, 1)
                     if any(matches(source, support) for support in case['supports'])), None)
        rows.append({'case_id': case_id, 'status': run.get('status', 'not_reported'),
                     'anchor_recall': sum(hit)/len(hit), 'all_anchors_found': all(hit),
                     'reciprocal_rank': 1/rank if rank else 0})
    expected = [case for case in cases.values() if case['supports']]
    evaluated = {row['case_id'] for row in rows}
    missing = [case['id'] for case in expected if case['id'] not in evaluated]
    # 未执行场景按0计入整体分母，另列缺口，不能靠少跑难题抬高分数。
    denominator = len(expected)
    return {'metric_scope': 'diagnostic_original_block_or_registered_asset_presence_not_semantic_support', 'k': k,
            'expected_retrieval_cases': denominator, 'evaluated': len(rows), 'missing_runs': missing,
            'anchor_recall': sum(r['anchor_recall'] for r in rows)/denominator if denominator else None,
            'all_anchors_rate': sum(r['all_anchors_found'] for r in rows)/denominator if denominator else None,
            'mrr': sum(r['reciprocal_rank'] for r in rows)/denominator if denominator else None,
            'rows': rows, 'semantic_quality_passed': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--course-dir', type=Path, required=True)
    parser.add_argument('--runs', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('验收产物已存在，禁止覆盖')
    data = json.loads(args.data.read_text(encoding='utf-8'))
    result = {'benchmark_sha256': digest(args.data), 'validation': validate(data, args.course_dir)}
    if args.runs:
        result['runs_sha256'] = digest(args.runs)
        result['diagnostic'] = score(data, json.loads(args.runs.read_text(encoding='utf-8')))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(result['validation'], ensure_ascii=False))


if __name__ == '__main__':
    main()
