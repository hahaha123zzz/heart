"""生成不含配置标签的教师复核材料；拒绝覆盖已填写的复核文件。"""
import argparse
import json
import secrets
from pathlib import Path


def prepare(directory, sheet, key):
    if sheet.exists() or key.exists() or sheet.resolve()==key.resolve():
        raise ValueError('复核文件已存在或路径重复，不能覆盖')
    files=sorted(directory.glob('[0-9]*-*.json'))
    if not files:raise ValueError('没有原始回合')
    rows=[];mapping={}
    for path in files:
        raw=json.loads(path.read_text(encoding='utf-8'));result=raw.get('result') or {}
        alias=secrets.token_hex(8);mapping[alias]=path.name
        rows.append({'review_id':alias,'question':raw['request']['message'],
            'status':result.get('answer_status'),'reply':result.get('reply',''),
            'source_quotes':[{'index':r.get('source_index',-1)+1,
                'document_id':(r.get('evidence') or {}).get('document_id'),
                'version':(r.get('evidence') or {}).get('document_version'),
                'page':(r.get('evidence') or {}).get('page'),
                'quote':(r.get('evidence') or {}).get('quote','')} for r in result.get('pdf_references',[])],
            'source_support':None,'concept_accuracy':None,'follows_request':None,
            'example_and_continuity':None,'notes':'','reviewer':'','reviewed_at':''})
    secrets.SystemRandom().shuffle(rows)
    for path,value in ((sheet,{'instructions':'各项填通过/不通过/无法判定；未审查保持null。','rows':rows}),
                       (key,{'mapping':mapping})):
        with path.open('x',encoding='utf-8') as out:json.dump(value,out,ensure_ascii=False,indent=2)
    return len(rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path)
    parser.add_argument('--sheet',required=True,type=Path);parser.add_argument('--key',required=True,type=Path)
    args=parser.parse_args();print('待复核条数',prepare(args.directory,args.sheet,args.key))
