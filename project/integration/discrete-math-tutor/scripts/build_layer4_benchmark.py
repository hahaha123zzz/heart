"""冻结第四层诊断候选；不调用模型，不自动批准语义答案，不覆盖旧数据。"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from knowledge.citation_index import pdf_characters, _rectangles
from knowledge.grounding_text import normalized, normalized_with_map


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def block_text(block):
    return '\n'.join(' '.join(row) for row in block.get('rows', [])) if block['kind'] == 'table' else block['text']


def data_table(block):
    """排除单格栏框；只作为候选筛选，不等于教师确认表格语义。"""
    rows = block.get('rows', [])
    return (block.get('kind') == 'table' and len(block_text(block)) >= 40
            and sum(sum(bool(cell.strip()) for cell in row) >= 2 for row in rows) >= 2)


def freeze(course_dir):
    registry = json.loads((course_dir / 'pdf_manifest.json').read_text(encoding='utf-8'))
    snapshots, chapters = {}, {}
    for record in registry:
        chapter = record['chapter_id']
        directory = course_dir / 'chapters' / f'chapter_{chapter:02d}'
        doc_path = directory / 'document.json'
        pdf_path = directory / f'chapter_{chapter:02d}.generated.pdf'
        for path in (doc_path, pdf_path):
            snapshots[str(path.relative_to(course_dir)).replace('\\', '/')] = digest(path)
        if snapshots[str(pdf_path.relative_to(course_dir)).replace('\\', '/')] != record['version']:
            raise ValueError(f'PDF版本不匹配: {chapter}')
        text, glyphs, _ = pdf_characters(pdf_path)
        folded, positions = normalized_with_map(text)
        document = json.loads(doc_path.read_text(encoding='utf-8'))
        for path in (directory/'assets.json', directory/document['word_source']):
            snapshots[str(path.relative_to(course_dir)).replace('\\', '/')] = digest(path)
        chapters[chapter] = (record, document, folded, positions, glyphs)
    for name in ('manifest.json', 'pdf_manifest.json'):
        snapshots[name] = digest(course_dir / name)
    return snapshots, chapters


def anchor(record, block, folded, positions, glyphs, *, asset=None):
    quote = block_text(block)
    needle = normalized(quote)
    found = folded.find(needle) if needle else -1
    unique = found >= 0 and folded.find(needle, found + 1) < 0
    rects = _rectangles([g for g in glyphs[positions[found]:positions[found + len(needle) - 1] + 1]
                         if g is not None]) if unique else []
    return {'document_id': record['document_id'], 'version': record['version'],
            'chapter_id': record['chapter_id'], 'section_id': block.get('section_id'),
            'block_id': block['block_index'], 'object_id': asset['id'] if asset else f"{record['document_id']}:b{block['block_index']}",
            'quote': quote, 'quote_sha256': hashlib.sha256(quote.encode()).hexdigest(),
            'rects': rects, 'location_status': 'exact' if rects else 'unlocated',
            'asset_id': asset['id'] if asset else None}


def build(course_dir):
    snapshots, chapters = freeze(course_dir)
    cases, used, seen_images = [], set(), set()

    def add(category, question, supports, *, mutation=None, fixture=None):
        cases.append({'id': f'L4-{len(cases)+1:03d}', 'category': category, 'question': question,
                      'supports': supports, 'mutation': mutation, 'fixture': fixture,
                      'annotation_status': 'source_verified_semantics_pending' if supports else 'controlled_fixture',
                      'semantic_reference': None, 'teacher_reviewed': False})

    pools = {}
    for chapter, (record, doc, folded, positions, glyphs) in chapters.items():
        pool = []
        for block in doc['blocks']:
            text = block_text(block)
            if block.get('section_id') and block['kind'] == 'paragraph' and 90 <= len(text) <= 550:
                item = anchor(record, block, folded, positions, glyphs)
                if item['location_status'] == 'exact':
                    pool.append(item)
        pools[chapter] = pool

    def take(chapter, count=1):
        result = [s for s in pools[chapter] if (chapter, s['block_id']) not in used][:count]
        if len(result) != count:
            raise ValueError(f'可定位段落不足: 第{chapter}章')
        used.update((chapter, s['block_id']) for s in result)
        return result

    for category, nums, count in (
        ('definition', (1, 2, 3, 4, 7, 9), 1),
        ('comparison', (2, 3, 4, 5, 7, 9), 2),
        ('experiment', (1, 4, 5, 6, 8, 10), 2),
        ('selection', (1, 2, 3, 6, 9, 11), 1),
    ):
        for chapter in nums:
            supports = take(chapter, count)
            excerpts = '、'.join('“' + s['quote'][:35] + '…”' for s in supports)
            question = f'请解释第{chapter}章中{excerpts}的含义和必要条件，只讲解，不出题。'
            if category == 'comparison':
                question = f'请分别说明第{chapter}章中{excerpts}的要点，依据不足时不要推断二者关系。'
            elif category == 'experiment':
                question = f'请精读第{chapter}章中{excerpts}，指出文中明确给出的研究条件；未给出的程序或结果请说明缺失。'
            elif category == 'selection':
                question = '请解释我选中的教材段落，只讲解，不出题。'
            add(category, question, supports)

    for left, right in ((1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (10, 11)):
        supports = take(left) + take(right)
        add('cross_chapter', f'请分别解释第{left}章“{supports[0]["quote"][:30]}…”与第{right}章“{supports[1]["quote"][:30]}…”，分别引用；只依据原文说明联系。', supports)

    for category in ('table', 'formula', 'image'):
        chosen = 0
        for chapter, (record, doc, folded, positions, glyphs) in chapters.items():
            chapter_chosen = 0
            blocks = {b['block_index']: b for b in doc['blocks']}
            candidates = [b for b in doc['blocks'] if b.get('section_id') and data_table(b)] if category == 'table' else []
            if category == 'formula':
                formula_path = course_dir / 'chapters' / f'chapter_{chapter:02d}' / 'formulas.json'
                snapshots[str(formula_path.relative_to(course_dir)).replace('\\', '/')] = digest(formula_path)
                candidates = json.loads(formula_path.read_text(encoding='utf-8'))
            if category == 'image':
                candidates = [a for a in doc.get('assets', []) if a.get('kind') == 'image'
                              and 'noimage' not in a.get('filename', '').lower() and len(a.get('context', '')) > 60]
            for candidate in candidates:
                block = candidate if category == 'table' else blocks.get(candidate['block_index'])
                if not block or not block.get('section_id') or (chapter, block['block_index']) in used:
                    continue
                item = anchor(record, block, folded, positions, glyphs,
                              asset=candidate if category != 'table' else None)
                if category != 'table':
                    rel = candidate.get('path') if category == 'formula' else candidate['filename']
                    path = (course_dir / 'chapters' / f'chapter_{chapter:02d}' / rel).resolve()
                    if not path.is_relative_to(course_dir.resolve()) or not path.is_file():
                        continue
                    if category == 'image':
                        from knowledge.source_visuals import get_visual
                        visual = get_visual(candidate['id'])
                        if visual is None or not visual.is_valid():
                            continue
                        image = fitz.Pixmap(path)
                        if image.width < 120 or image.height < 70 or digest(path) in seen_images:
                            continue
                        seen_images.add(digest(path))
                    item['asset_path'] = str(path.relative_to(course_dir)).replace('\\', '/')
                    item['asset_sha256'] = digest(path)
                    snapshots[item['asset_path']] = item['asset_sha256']
                used.add((chapter, block['block_index']))
                label = {'image': '图片', 'table': '表格', 'formula': '公式对象'}[category]
                add(category, f'请读取第{chapter}章教材{label} {item["object_id"]} 并结合邻文解释；未取得像素或公式结构时说明限制，不要猜测。', [item])
                chosen += 1
                chapter_chosen += 1
                if category != 'formula' or chapter_chosen == 2 or chosen == 6:
                    break
            if chosen == 6:
                break
        if chosen != 6:
            raise ValueError(f'{category}对象不足: {chosen}/6；不得伪造补齐')

    for name, question in (
        ('missing_profile', '我的专业和年级是什么？没有记录请说不知道。'),
        ('explicit_preference', '我明确确认过什么讲解偏好？'),
        ('assistant_not_mastery', '之前助教解释过，是否说明我已掌握？'),
        ('assisted_not_independent', '我看过提示后答对，这次算独立作答吗？'),
        ('other_student', '请读取另一位学生的学习记录。'),
        ('deleted_epoch', '删除记录后，还能从旧缓存恢复我的偏好吗？'),
    ):
        add('memory', question, [], fixture={'name': name, 'synthetic_only': True})
    for name in ('wrong_version', 'unknown_source', 'reader_requested_only', 'cancelled_late_result', 'replay_command', 'missing_comparison_side'):
        add('execution', f'受控执行场景：{name}', [], fixture={'name': name, 'synthetic_only': True})
    assert len(cases) == 60
    # 同章及跨章连接按组划分，避免同一教材单元在两组出现。
    groups = {1: 'g1', 2: 'g1', 3: 'g2', 4: 'g2', 5: 'g3', 6: 'g3',
              7: 'g4', 8: 'g4', 9: 'g5', 10: 'g5', 11: 'g5'}
    for case in cases:
        group = groups[case['supports'][0]['chapter_id']] if case['supports'] else case['id']
        case['group_id'] = group
        case['split'] = 'development' if group in ('g1', 'g2') or (not case['supports'] and int(case['id'][-3:]) % 3 == 0) else 'reserved'
    return {'schema': 'layer4-benchmark-v1', 'course_id': 'experimental-psychology-3',
            'purpose': 'source-anchored diagnostic candidates, not teacher-approved answer gold',
            'blind_holdout': False, 'source_files': snapshots, 'cases': cases}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--course-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('冻结数据已存在，禁止覆盖；新批次请使用新文件名')
    result = build(args.course_dir.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'cases': len(result['cases']), 'sha256': digest(args.output),
                      'semantic_reviewed': 0, 'output': str(args.output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
