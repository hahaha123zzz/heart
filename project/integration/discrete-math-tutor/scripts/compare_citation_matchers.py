"""同一开发集比较已审阅的纯匹配函数；不把文本候选当作几何或语义证据。"""
import argparse,ast,json
from difflib import SequenceMatcher
from pathlib import Path
from knowledge.citation_index import CitationIndex
from knowledge.grounding_text import normalized
from knowledge.pdf_reader import documents

ROOT=Path(__file__).resolve().parents[3]/'docs/research/2026-10-16-citation-grounding'


def functions(path,names):
    # 只加载已逐行审阅的独立函数，不导入上游运行时及其其他代码。
    tree=ast.parse(path.read_text(encoding='utf-8'))
    selected=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
    if {node.name for node in selected}!=set(names):raise ValueError('上游函数与审计清单不同')
    scope={'SequenceMatcher':SequenceMatcher}
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(path),'exec',dont_inherit=True),scope)
    return scope


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--index',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('报告已存在，不覆盖')
    deep=functions(ROOT/'upstream/DeepTutor/deeptutor/reading/_grounding.py',['normalized_with_map','selection_range'])
    kota=functions(ROOT/'upstream/kotaemon/libs/kotaemon/kotaemon/indices/qa/utils.py',['find_text'])
    index=CitationIndex(args.index);registry={r['document_id']:r for r in documents()};rows=[]
    try:
        for case in json.loads((ROOT/'benchmark.json').read_text(encoding='utf-8'))['cases']:
            if case['split']!='development':continue
            for item in case['support']:
                context=index.document(item['document_id'],registry[item['document_id']]['version'])['text']
                if item['block_id'] is not None:
                    blocks=index.blocks(item['document_id'],item['block_id'],item['block_id'])
                    if blocks and blocks[0]['status']=='exact':context=context[blocks[0]['start']:blocks[0]['end']]
                bounds=deep['selection_range'](context,item['quote'])
                spans=kota['find_text'](item['quote'],context)
                row={'id':case['id'],'category':case['category'],'quote':item['quote'],
                    'DeepTutor':{'candidate':bounds,'complete_quote':bool(bounds and normalized(context[slice(*bounds)])==normalized(item['quote']))},
                    'Kotaemon':{'candidate':spans,'complete_quote':bool(len(spans)==1 and normalized(context[slice(*spans[0])])==normalized(item['quote']))}}
                try:row['adapted']=index.locate(item['document_id'],item['version'],item['quote'],block_id=item['block_id'])['status']
                except ValueError:row['adapted']='stale'
                rows.append(row)
    finally:index.close()
    result={'method':'开发集纯文本候选比较；全部函数使用相同已对齐块窗口（无块则全文）。DeepTutor首次匹配及Kotaemon模糊跨度不自带版本、歧义或PDF几何保障，不能直接解读为上游平台整体准确率',
            'counts':{'supports':len(rows),'positive_supports':sum(r['category']!='negative' for r in rows),
                'DeepTutor_complete_positive':sum(r['category']!='negative' and r['DeepTutor']['complete_quote'] for r in rows),
                'Kotaemon_complete_positive':sum(r['category']!='negative' and r['Kotaemon']['complete_quote'] for r in rows),
                'adapted_exact_positive':sum(r['category']!='negative' and r['adapted']=='exact' for r in rows)},'results':rows}
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result['counts']))


if __name__=='__main__':main()
