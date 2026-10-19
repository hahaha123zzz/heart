"""样章独立结构/语义索引，不使用旧教材目录或逻辑公式索引。"""
import json,sys,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.build_rag_index import build_index
from knowledge.structured_index import _parts
COURSE='experimental-psychology-3'
SAMPLE=ROOT/'knowledge/courses'/COURSE/'sample'
def records(sample=SAMPLE,chapter_id=4):
    doc=json.loads((sample/'document.json').read_text(encoding='utf-8'))
    locations=json.loads((sample/'pdf_locations.json').read_text(encoding='utf-8'))
    sections={s['id']:s for s in locations['sections']};output=[];pending=[]
    def emit(blocks,kind='text',text=None):
        if not blocks:return
        section=sections.get(blocks[0].get('section_id'),sections[1]);index=blocks[0]['block_index']
        parent=f'{COURSE}:ch{chapter_id:02d}:b{index}'
        text=text if text is not None else '\n'.join(b['text'] for b in blocks)
        for number,part in enumerate([text] if kind=='table' else _parts(text)):
            if len(part.strip())<12:continue
            output.append({'id':f'{parent}:{number}','parent_id':parent,'chapter_id':chapter_id,
                'source':locations.get('source','实验心理学（第3版）/第四章被试间设计'),'section':section['title'],
                'section_id':section['id'],'page':section['generated_page'],
                'block_start':index,'block_end':blocks[-1]['block_index'],'kind':kind,
                'text':part,'asset_ids':list(dict.fromkeys(a for b in blocks for a in b['image_ids']))})
    for block in doc['blocks']:
        text=block['text'].strip()
        if not text:continue
        if text=='【推荐阅读】':break
        if block['kind']=='table':
            caption=pending[-1]['text'] if pending and re.match(r'^表\s*\d+-',pending[-1]['text']) else ''
            emit(pending);pending=[]
            emit([block],kind='table',text=caption+'\n'+'\n'.join(' | '.join(row) for row in block['rows']))
            continue
        heading=len(text)<65 and re.match(r'^(?:第[一二三四五]+节|[一二三四五六七八九十]+、|\([一二三四五六七八九十]+\)|\d+\.)',text)
        if pending and (heading or pending[0].get('section_id')!=block.get('section_id') or sum(len(b['text']) for b in pending)+len(text)>760):
            emit(pending);pending=[]
        pending.append(block)
    emit(pending)
    return output
if __name__=='__main__':
    target=SAMPLE/'rag_index.sqlite3';rows=records() if '--all' not in sys.argv else []
    if '--all' in sys.argv:
        course=SAMPLE.parent;target=course/'rag_index.sqlite3'
        for chapter in range(1,12):rows.extend(records(course/'chapters'/f'chapter_{chapter:02d}',chapter))
    result=build_index(target,records=rows,embed='--embed' in sys.argv,index_logic_formulas=False)
    print(json.dumps(result,ensure_ascii=False))
