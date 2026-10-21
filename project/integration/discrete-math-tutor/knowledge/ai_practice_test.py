"""显式启用的AI练习测试输入；不导入正式题库或评分。"""
import hashlib
import json
from pathlib import Path

LABEL = 'AI生成 · 测试用 · 未人工审核'


def load_catalog(path, course_id):
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    if (data.get('schema') != 'ai-practice-test-v1' or data.get('course_id') != course_id
            or data.get('origin') != 'ai_generated' or data.get('test_only') is not True
            or data.get('review_status') != 'unreviewed'):
        raise ValueError('AI测试题来源、课程或审核状态无效')
    questions = data['questions']
    if not 1 <= len(questions) <= 20 or len({q['id'] for q in questions}) != len(questions):
        raise ValueError('AI测试题数量或身份无效')
    for q in questions:
        selection = q['basis_selection']
        if (not q['id'].startswith('ai-test-') or q.get('origin') != 'ai_generated'
                or q.get('test_only') is not True or q.get('review_status') != 'unreviewed'
                or selection['document_id'] != q['source']['document_id']
                or selection['version'] != q['source_version']
                or not 1 <= q['chapter_id'] <= 11 or not q['parts']
                or len({p['id'] for p in q['parts']}) != len(q['parts'])
                or any(p['type'] != 'written' for p in q['parts'])):
            raise ValueError('AI测试题身份或知识依据无效')
        q['origin_label'] = LABEL
    version = hashlib.sha256(raw).hexdigest()
    return {'version': version, '_catalog_source_version': version, 'questions': questions,
            'by_id': {q['id']: q for q in questions}, 'note': LABEL,
            'origin': 'ai_generated', 'test_only': True}
