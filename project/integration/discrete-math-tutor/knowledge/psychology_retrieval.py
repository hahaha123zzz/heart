"""正式教材概念标题补召回及父块上下文，复用混合检索。"""
import json,re,os
from dataclasses import replace
from functools import lru_cache
from knowledge.course_config import PSYCHOLOGY_DIR
from knowledge.textbook import TextbookChunk,terms_for
from knowledge.hybrid_retrieval import retrieve_hybrid
from knowledge.source_mapping import source_spans

HEADING=re.compile(r'^(?:[一二三四五六七八九十]+、|\([一二三四五六七八九十]+\)|\d+\.)')

def _group(blocks,index):
    first=blocks[index];text=first['text'].strip()
    level=1 if re.match(r'^[一二三四五六七八九十]+、',text) else 2 if text.startswith('(') else 3
    group=[first]
    for block in blocks[index+1:]:
        heading=HEADING.match(block['text'].strip())
        depth=1 if re.match(r'^[一二三四五六七八九十]+、',block['text'].strip()) else 2 if block['text'].strip().startswith('(') else 3
        if block.get('section_id')!=first.get('section_id') or (heading and depth<=level):break
        group.append(block)
        if sum(len(b['text']) for b in group)>2000:break
    return group

@lru_cache(maxsize=1)
def documents():
    return [json.loads((PSYCHOLOGY_DIR/'chapters'/f'chapter_{n:02d}'/'document.json').read_text(encoding='utf-8')) for n in range(1,12)]

def retrieve(query,fallback_chunks,*,limit=6,preferred_types=()):
    query=query.replace('配对设计','配对组设计')
    engine = os.getenv('RAG_RETRIEVAL_ENGINE', 'legacy')
    if engine not in ('legacy', 'local_llamaindex'): raise ValueError('RAG_RETRIEVAL_ENGINE无效')
    if engine == 'local_llamaindex':
        from knowledge.local_rag.course_retrieval import retrieve as retrieve_local
        chunks=retrieve_local(query,limit=max(limit,6),preferred_types=preferred_types,
                            index_path=PSYCHOLOGY_DIR/'rag_index.sqlite3')
    else:
        chunks=retrieve_hybrid(query,fallback_chunks,limit=max(limit,6),preferred_types=preferred_types,
                               index_path=PSYCHOLOGY_DIR/'rag_index.sqlite3')
    registry=json.loads((PSYCHOLOGY_DIR/'pdf_manifest.json').read_text(encoding='utf-8'))
    pages={(r['chapter_id'],s['id']):s['page'] for r in registry for s in r['sections']}
    anchors=[];by_chapter={}
    for document in documents():
        chapter=document['chapter_id'];blocks=document['blocks'];by_chapter[chapter]=blocks
        for index,block in enumerate(blocks):
            text=block['text'].strip()
            if len(text)>65 or not HEADING.match(text):continue
            title=''.join(HEADING.sub('',text).split()).removeprefix('什么是')
            title=re.sub(r'(?:的)?(?:含义|定义|基本模式)$','',title)
            matched={term for term in title.split('和') if len(term)>=3 and term in ''.join(query.split())}
            if not matched:continue
            group=_group(blocks,index)
            if len(group)<2:continue
            content='\n'.join('\n'.join(' | '.join(row) for row in b['rows']) if b['kind']=='table' else b['text'] for b in group)
            parent=f'experimental-psychology-3:ch{chapter:02d}:b{block["block_index"]}'
            anchors.append((len(title),matched,TextbookChunk(document['source'],block['section'],content,terms_for(content),
                section_id=block['section_id'],chunk_id=parent+':anchor',parent_id=parent,chapter_id=chapter,
                page=pages[(chapter,block['section_id'])],block_start=block['block_index'],block_end=group[-1]['block_index'],
                source_spans=source_spans(group,content))))
    ranked=sorted(anchors,key=lambda a:a[0],reverse=True)
    selected=[];covered=set()
    # 先覆盖本轮每个显式概念，再补同一概念的定义/基本模式。
    for anchor in ranked:
        if any(not any(term in seen for seen in covered) for term in anchor[1]):
            selected.append(anchor);covered.update(anchor[1])
        if len(selected)>=limit:break
    budget=min(limit,max(2,len(selected)+1))
    for anchor in ranked:
        if len(selected)>=budget:break
        if anchor not in selected:selected.append(anchor)
    result=[chunk for _,_,chunk in selected]
    for chunk in chunks:
        blocks=by_chapter.get(chunk.chapter_id,[])
        group=[b for b in blocks if chunk.block_start<=b['block_index']<=chunk.block_end]
        if chunk.kind=='text':
            if len(group)==1 and HEADING.match(group[0]['text'].strip()):
                group=_group(blocks,blocks.index(group[0]))
                if len(group)==1:continue
            if group:
                text='\n'.join(b['text'] for b in group)[:3000]
                chunk=replace(chunk,text=text,terms=terms_for(text),block_end=group[-1]['block_index'],source_spans=source_spans(group,text))
        elif group:
            # 表格也有原文范围，保留原序列化文字及单元格顺序，不作为普通段落重写。
            chunk=replace(chunk,source_spans=source_spans(group,chunk.text))
        if any(chunk.chapter_id==s.chapter_id and chunk.block_start>=s.block_start and chunk.block_end<=s.block_end for s in result):continue
        result.append(chunk)
        if len(result)>=limit:break
    return result[:limit]
