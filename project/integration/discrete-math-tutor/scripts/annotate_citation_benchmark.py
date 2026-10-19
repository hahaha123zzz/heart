"""用独立 PDF 词级读取补充冻结基准的预期页/行范围；不调用待测字符索引。"""
import argparse,hashlib,json
from pathlib import Path
import fitz
from knowledge.grounding_text import normalized
from knowledge.pdf_reader import documents,pdf_path

ROOT=Path(__file__).resolve().parents[3]/'docs/research/2026-10-16-citation-grounding'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise ValueError('预期位置标注已存在，不覆盖')
    texts={};words_by_document={}
    for record in documents():
        words=[];text='';mapping=[]
        with fitz.open(pdf_path(record)) as pdf:
            for number,page in enumerate(pdf,1):
                for word in page.get_text('words',sort=True):
                    folded=normalized(word[4]);box=fitz.Rect(word[:4])*page.rotation_matrix
                    words.append({'page':number,'line':(word[5],word[6]),'text':word[4],
                        'x1':box.x0/page.rect.width,'y1':box.y0/page.rect.height,'x2':box.x1/page.rect.width,'y2':box.y1/page.rect.height})
                    text+=folded;mapping.extend([len(words)-1]*len(folded))
        texts[record['document_id']]=(text,mapping);words_by_document[record['document_id']]=words
    cases=[]
    for case in json.loads((ROOT/'benchmark.json').read_text(encoding='utf-8'))['cases']:
        row={'id':case['id'],'expected_status':case.get('expected_status','exact'),'supports':[]}
        for support in case['support']:
            annotation={'document_id':support['document_id'],'version':support['version'],
                'quote_sha256':hashlib.sha256(support['quote'].encode()).hexdigest(),'pages':support['pages'],'rects':[]}
            if case['category']!='negative':
                text,mapping=texts[support['document_id']];needle=normalized(support['quote']);start=text.find(needle)
                if start<0 or text.find(needle,start+1)>=0:
                    annotation['review_required']='独立词级读取未唯一匹配；不能用待测索引补成真值'
                else:
                    ids=list(dict.fromkeys(mapping[start:start+len(needle)]));words=[words_by_document[support['document_id']][i] for i in ids]
                    grouped={}
                    for word in words:
                        key=(word['page'],word['line'])
                        if key not in grouped:grouped[key]={k:word[k] for k in ('page','x1','y1','x2','y2')}
                        else:
                            box=grouped[key]
                            for key2 in ('x1','y1'):box[key2]=min(box[key2],word[key2])
                            for key2 in ('x2','y2'):box[key2]=max(box[key2],word[key2])
                    annotation['rects']=list(grouped.values())
                    annotation['boundary_extra_characters']=len(normalized(''.join(w['text'] for w in words)))-len(needle)
                    assert sorted({r['page'] for r in annotation['rects']})==support['pages']
            row['supports'].append(annotation)
        cases.append(row)
    report={'method':'独立MuPDF词级读取，未调用CitationIndex；预期为行/词范围，边界可能包含额外字符；须逐条视觉复核后才能作为像素精度真值',
        'benchmark_sha256':hashlib.sha256((ROOT/'benchmark.json').read_bytes()).hexdigest(),'human_reviewed':False,'cases':cases}
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    args.output.with_suffix('.sha256').write_text(hashlib.sha256(args.output.read_bytes()).hexdigest()+'\n',encoding='utf-8')
    print('saved',len(cases),'cases; independent word/line ranges, not human labels')


if __name__=='__main__':main()
