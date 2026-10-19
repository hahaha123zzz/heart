"""冻结100个原文场景；标注来自教材和独立PDF文本搜索，不使用模型答案。"""
import bisect,hashlib,json,random,re
from pathlib import Path
import fitz
from knowledge.course_config import PSYCHOLOGY_DIR
from knowledge.grounding_text import normalized,normalized_with_map
from knowledge.pdf_reader import documents,pdf_path

ROOT=Path(__file__).resolve().parents[3]/'docs/research/2026-10-16-citation-grounding'


def main():
    target=ROOT/'benchmark.json'
    if target.exists():raise ValueError('冻结样本已存在，不允许重新抽样覆盖')
    paragraphs=[];assets=[];cross=[];registry=documents()
    for record in registry:
        directory=PSYCHOLOGY_DIR/'chapters'/f"chapter_{record['chapter_id']:02d}"
        doc=json.loads((directory/'document.json').read_text(encoding='utf-8'))
        with fitz.open(pdf_path(record)) as pdf:
            texts=[page.get_text('text',sort=True) for page in pdf]
        joined='';ends=[]
        for text in texts:joined+=text+'\n';ends.append(len(joined))
        folded,mapping=normalized_with_map(joined)
        for block in doc['blocks']:
            text=block['text'] if block['kind']!='table' else '\n'.join(' '.join(row) for row in block['rows'])
            if not 60<=len(text)<=950:continue
            needle=normalized(text);first=folded.find(needle)
            if first<0 or folded.find(needle,first+1)>=0:continue
            start,end=mapping[first],mapping[first+len(needle)-1]+1
            pages=list(range(bisect.bisect_right(ends,start)+1,bisect.bisect_left(ends,end)+2))
            item={'chapter':record['chapter_id'],'section_id':block.get('section_id',1),'section':block['section'],
                'document_id':record['document_id'],'version':record['version'],'block_id':block['block_index'],
                'quote':text,'pages':pages,'kind':block['kind'],'formula_ids':block.get('formula_ids',[])}
            if block['kind']=='table' or block.get('formula_ids'):assets.append(item)
            elif len(pages)>1:cross.append(item)
            else:paragraphs.append(item)
    rng=random.Random(20261016)
    for pool in (paragraphs,assets,cross):rng.shuffle(pool)
    used=set();cases=[]
    def choose(pool,count,category,multi=False):
        chosen=[]
        # 先按章轮转，避免样本集中在少数长章。
        for turn in range(100):
            chapter=turn%11+1
            item=next((x for x in pool if x['chapter']==chapter and (x['chapter'],x['block_id']) not in used),None)
            if item is None:continue
            used.add((item['chapter'],item['block_id']))
            support=[item]
            if multi:
                partner=next((x for x in paragraphs if x['chapter']==chapter and x['section_id']==item['section_id'] and x['block_id']!=item['block_id'] and (x['chapter'],x['block_id']) not in used),None)
                if partner is None:continue
                support.append(partner);used.add((partner['chapter'],partner['block_id']))
            names=[''.join(x['quote'].split())[:28] for x in support]
            question=f"请解释第{chapter}章“{item['section']}”里“{names[0]}”这段内容的含义和关键条件。"
            if multi:question=f"请结合第{chapter}章“{item['section']}”，分别解释“{names[0]}”和“{names[1]}”，并说明二者的联系。"
            if category=='assets':question=f"请结合第{chapter}章“{item['section']}”的表格或公式，解释“{names[0]}”所表达的内容与条件。"
            if category=='summary':question=f"请概括第{chapter}章“{item['section']}”中“{names[0]}”与“{names[1]}”的要点，给出各自依据。"
            chosen.append({'category':category,'question':question+'不要出题。','support':support,
                'expected_status':'exact','annotation':'教材原文+独立PDF纯文本全引文唯一匹配；尚未教师审核'})
            if len(chosen)==count:break
        if len(chosen)!=count:raise ValueError(f'{category} 样本不足：{len(chosen)}/{count}')
        cases.extend(chosen)
    choose(paragraphs,20,'definition')
    choose(paragraphs,20,'comparison',True)
    choose(cross,20,'cross_page')
    choose(paragraphs,15,'summary',True)
    choose(assets,15,'assets')
    for i,kind in enumerate(['wrong_version']*3+['invented_quote']*3+['ambiguous']*4):
        original=paragraphs[i]
        support=dict(original)
        if kind=='wrong_version':support['version']='0'*64
        elif kind=='invented_quote':support['quote']='本教材没有这句引文，结果为负99999。'
        else:
            # 未限定块范围的重复短语不能取第一次命中作为精确证据。
            support['quote']='实验';support['block_id']=None
        cases.append({'category':'negative','mutation':kind,'question':f"请核对“{support['quote'][:35]}”的教材出处。",
            'support':[support],'expected_status':'stale' if kind=='wrong_version' else 'ambiguous' if kind=='ambiguous' else 'unlocated',
            'annotation':'人工设定的错误版本/虚构引文/未消歧重复短语，不得给精确坐标'})
    counts={};dev={'definition':14,'comparison':14,'cross_page':14,'summary':11,'assets':10,'negative':7}
    for i,case in enumerate(cases,1):
        category=case['category'];counts[category]=counts.get(category,0)+1
        case.update(id=f'CG{i:03d}',split='development' if counts[category]<=dev[category] else 'holdout')
        case['high_risk']=category in ('cross_page','negative')
    assert len(cases)==100 and sum(c['split']=='development' for c in cases)==70
    data={'schema':'citation-benchmark-v1','seed':20261016,'documents':{r['document_id']:r['version'] for r in registry},
        'annotation_policy':'真值为教材原文及独立PDF文字位置；生成模型不参与标注；最终应分开报告机器核验、Codex复核与教师审核。','cases':cases}
    target.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    (ROOT/'benchmark.sha256').write_text(digest+'  benchmark.json\n',encoding='utf-8')
    print(json.dumps({'cases':len(cases),'categories':counts,'development':70,'holdout':30,'sha256':digest},ensure_ascii=False))


if __name__=='__main__':main()
