"""核对文本法漏定位的对象，复用现有原图定位；不把邻文页候选当精确坐标。"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from knowledge.citation_index import LiveCitationIndex
from knowledge.source_visuals import get_visual
from knowledge.visual_locations import resolve_figure
from scripts.build_layer4_benchmark import data_table, digest
from scripts.evaluate_layer4_benchmark import validate


def audit(data, course_dir):
    validate(data, course_dir)
    index = LiveCitationIndex()
    rows = []
    try:
        for case in data['cases']:
            for support in case['supports']:
                if support['location_status'] != 'unlocated':
                    continue
                base = {key: support[key] for key in ('document_id', 'version', 'chapter_id', 'block_id', 'asset_id')}
                row = dict(base, case_id=case['id'], category=case['category'])
                doc_path = course_dir/'chapters'/f"chapter_{support['chapter_id']:02d}"/'document.json'
                blocks = json.loads(doc_path.read_text(encoding='utf-8'))['blocks']
                block = next(b for b in blocks if b['block_index'] == support['block_id'])
                if case['category'] == 'table' and not data_table(block):
                    row.update(status='excluded_layout_table', basis='单格栏框或缺少多行多列', rects=[])
                elif case['category'] == 'image':
                    visual = get_visual(support['asset_id'])
                    if visual is None or not visual.is_valid():
                        row.update(status='rejected_asset', basis='现有原图服务不接纳该素材或来源已失效', rects=[])
                    else:
                        result = resolve_figure(visual.id, visual.sha256, support['document_id'], support['version'])
                        row.update(status=result['status'], basis=result['basis'], rects=result.get('rects', []))
                else:
                    number = support['block_id']
                    neighbors = index.blocks(support['document_id'], max(0, number-6), number+6)
                    before = next((b for b in reversed(neighbors) if b['block_id'] < number and b['status'] == 'exact'), None)
                    after = next((b for b in neighbors if b['block_id'] > number and b['status'] == 'exact'), None)
                    doc = index.document(support['document_id'], support['version'])
                    pages = sorted({g[0] for b in (before, after) if b is not None
                                    for g in doc['glyphs'][b['start']:b['end']] if g is not None})
                    row.update(status='page_candidate' if pages else 'unlocated',
                               basis='邻文原文可定位；未证明对象自身坐标', candidate_pages=pages, rects=[],
                               neighbor_blocks=[b['block_id'] for b in (before, after) if b is not None])
                rows.append(row)
    finally:
        index.close()
    validate(data, course_dir)
    return {'statuses': dict(Counter(r['status'] for r in rows)), 'objects': len(rows),
            'rows': rows, 'teacher_reviewed': False, 'reader_applied_tested': False}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--course-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError('产物已存在，禁止覆盖')
    from knowledge.course_config import PSYCHOLOGY_DIR
    if args.course_dir.resolve() != PSYCHOLOGY_DIR.resolve():
        raise ValueError('现有定位服务只读取当前课程默认路径；请使用相同快照的独立worktree教材副本')
    data = json.loads(args.data.read_text(encoding='utf-8'))
    report = audit(data, args.course_dir)
    report['benchmark_sha256'] = digest(args.data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'objects': report['objects'], 'statuses': report['statuses']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
