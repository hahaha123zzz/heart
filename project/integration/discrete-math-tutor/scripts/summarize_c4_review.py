"""汇总盲审结果；未审、无法判定与通过分别统计。"""
import argparse
from collections import Counter
import json
from pathlib import Path


CRITERIA = ('source_support', 'concept_accuracy', 'follows_request', 'example_and_continuity')
VERDICTS = ('通过', '不通过', '无法判定')


def summarize(sheet):
    rows = sheet.get('rows')
    if not isinstance(rows, list) or not rows:
        raise ValueError('复核表没有样本')
    counts = {criterion: Counter() for criterion in CRITERIA}
    ids = set()
    complete = 0
    for row in rows:
        review_id = row.get('review_id')
        if not isinstance(review_id, str) or not review_id.strip() or review_id in ids:
            raise ValueError('复核编号缺失或重复')
        ids.add(review_id)
        values = [row.get(criterion) for criterion in CRITERIA]
        if any(value is not None and value not in VERDICTS for value in values):
            raise ValueError(f'{review_id}: 复核值无效')
        if any(value is not None for value in values):
            if not str(row.get('reviewer') or '').strip() or not str(row.get('reviewed_at') or '').strip():
                raise ValueError(f'{review_id}: 已评分样本需要审核人和审核时间')
            if any(value in ('不通过', '无法判定') for value in values) and not str(row.get('notes') or '').strip():
                raise ValueError(f'{review_id}: 不通过或无法判定需要说明')
        for criterion, value in zip(CRITERIA, values):
            counts[criterion][value if value is not None else '未审核'] += 1
        complete += all(value is not None for value in values)
    return {'samples': len(rows), 'fully_reviewed': complete,
            'criteria': {name: {verdict: counts[name][verdict] for verdict in (*VERDICTS, '未审核')}
                         for name in CRITERIA},
            'note': '此统计仅反映填写的标注；不验证审核人资质，也不将无法判定视为通过。'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('sheet', type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(json.loads(args.sheet.read_text(encoding='utf-8'))), ensure_ascii=False, indent=2))
