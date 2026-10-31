"""将真人填写的盲标TSV导入JSONL；任何未审核样本均阻止导入。"""
import argparse
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agents.input_understanding import ontology


def convert(rows):
    output = []
    seen = set()
    for row in rows:
        identity = row['case_id'].strip()
        if not identity or identity in seen:
            raise ValueError('缺少或重复case_id')
        if row.get('reviewed','').strip() != '1' or not row.get('annotator_id','').strip():
            raise ValueError(f'{identity}: 请完成审核并填写annotator_id')
        labels = {}
        for dimension,spec in ontology.labels().items():
            values = [value.strip() for value in row.get(dimension,'').split('|') if value.strip()]
            if len(values) != len(set(values)) or len(values) > int(spec.get('max_labels',1)):
                raise ValueError(f'{identity}: {dimension}标签重复或过多')
            if any(not ontology.valid_label(dimension,value) for value in values):
                raise ValueError(f'{identity}: {dimension}包含非法标签')
            labels[dimension] = values
        output.append({'case_id':identity,'labels':labels,'reviewed':True,
                       'annotator_id':row['annotator_id'].strip(),'note':row.get('note','')})
        seen.add(identity)
    if not output:
        raise ValueError('没有标注样本')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('output',type=Path)
    args = parser.parse_args()
    with args.input.open(encoding='utf-8-sig',newline='') as handle:
        rows = convert(csv.DictReader(handle,delimiter='\t'))
    if args.output.exists():
        parser.error('输出文件已存在，请使用新文件名保存本次独立标注')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as handle:
        handle.write('\n'.join(json.dumps(row,ensure_ascii=False) for row in rows)+'\n')
    print(f'已导入{len(rows)}条真人标注')


if __name__ == '__main__':
    main()
