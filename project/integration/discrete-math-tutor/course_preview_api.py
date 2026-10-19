"""正式教材样章的独立只读入口；不访问学生数据库。"""
import hashlib,json,re
from dataclasses import replace
from types import SimpleNamespace
from typing import Literal
import fitz
from functools import lru_cache
from pathlib import Path
from fastapi import APIRouter,HTTPException,Query
from fastapi.responses import FileResponse
from knowledge.hybrid_retrieval import retrieve_hybrid
from pydantic import BaseModel, ConfigDict, Field, model_validator
from agents.psychology_qa import explain
from llm.client import LLMClient
ROOT=Path(__file__).parent
SAMPLE=ROOT/'knowledge/courses/experimental-psychology-3/sample'
router=APIRouter()
def locations():
    record=json.loads((SAMPLE/'pdf_locations.json').read_text(encoding='utf-8'))
    path=SAMPLE/'chapter_04.generated.pdf'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=record['version']:raise HTTPException(409,'教材版面已变更，请重新建立定位')
    return record
def reference(section):
    data=locations()
    return {'course_id':data['course_id'],'document_id':data['document_id'],'version':data['version'],
        'kind':'text','rects':[section['rect']],'text':section['title'],'chapter_id':4,'section_id':section['id'],
        'location_kind':'section_heading','page_policy':'generated_pdf_pages'}
@lru_cache(maxsize=2)
def lines(version):
    result=[]
    with fitz.open(SAMPLE/'chapter_04.generated.pdf') as pdf:
        for number,page in enumerate(pdf,1):
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines',[]):
                    text=''.join(s['text'] for s in line['spans'])
                    box=line['bbox']
                    result.append((number,''.join(text.split()),{'page':number,'x1':box[0]/page.rect.width,'y1':box[1]/page.rect.height,'x2':box[2]/page.rect.width,'y2':box[3]/page.rect.height}))
    return result
def chunk_reference(chunk,section):
    ref=reference(section)
    document=json.loads((SAMPLE/'document.json').read_text(encoding='utf-8'))
    block=next((b for b in document['blocks'] if b['block_index']==chunk.block_start),None)
    text=chunk.text.split('\n')[0] if chunk.kind=='table' else (block or {}).get('text','')
    prefix=''.join(text.split())[:28]
    if len(prefix)<12:return ref
    upper=next((s['generated_page'] for s in locations()['sections'] if s['id']==section['id']+1),locations()['page_count'])
    matches=[rect for page,line,rect in lines(ref['version']) if section['generated_page']<=page<=upper and line.startswith(prefix)]
    if len(matches)==1:
        return ref|{'rects':matches,'text':text[:200],'location_kind':'table_caption' if chunk.kind=='table' else 'paragraph_anchor'}
    return ref
@router.get('/textbook-preview/psychology',include_in_schema=False)
def preview_page():return FileResponse(ROOT/'frontend/psychology-preview.html')
@router.get('/api/textbook-preview/psychology/pdf')
def preview_pdf():
    locations();return FileResponse(SAMPLE/'chapter_04.generated.pdf',media_type='application/pdf')
@router.get('/api/textbook-preview/psychology/catalog')
def catalog():return locations()
@router.get('/api/textbook-preview/psychology/search')
def search(q:str=Query(min_length=1,max_length=400)):
    sections={s['id']:s for s in locations()['sections']}
    chunks=retrieve_hybrid(q,[],index_path=SAMPLE/'rag_index.sqlite3',limit=3)
    return [{'text':c.text,'kind':c.kind,'section':c.section,'source':c.source,
        'reference':chunk_reference(c,sections[c.section_id])} for c in chunks if c.section_id in sections]

class Rect(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    page:int=Field(ge=1,le=32)
    x1:float=Field(ge=0,le=1)
    y1:float=Field(ge=0,le=1)
    x2:float=Field(ge=0,le=1)
    y2:float=Field(ge=0,le=1)

    @model_validator(mode='after')
    def ordered(self):
        if self.x2<=self.x1 or self.y2<=self.y1:raise ValueError('选区坐标无效')
        return self

class Selection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    document_id:str=Field(max_length=100)
    version:str=Field(max_length=64)
    kind:Literal['text','area']
    rects:list[Rect]=Field(min_length=1,max_length=80)
    text:str=Field(default='',max_length=4000)

class Question(BaseModel):
    model_config=ConfigDict(extra='forbid')
    question:str=Field(min_length=1,max_length=400)
    version:str=Field(max_length=64)
    selection:Selection|None=None

def qa_sources(question):
    data=locations();sections={s['id']:s for s in data['sections']}
    document=json.loads((SAMPLE/'document.json').read_text(encoding='utf-8'))
    blocks=document['blocks']
    # 教材用语是“配对组设计”；保留原问题，只在召回时补齐名称。
    query=question.replace('配对设计','配对组设计')
    chunks=retrieve_hybrid(query,[],index_path=SAMPLE/'rag_index.sqlite3',limit=6)
    anchors=[]
    for index,block in enumerate(blocks):
        text=block['text'].strip()
        if len(text)>65 or not re.match(r'^(?:[一二三四五六七八九十]+、|\([一二三四五六七八九十]+\)|\d+\.)',text):continue
        title=re.sub(r'^(?:[一二三四五六七八九十]+、|\([一二三四五六七八九十]+\)|\d+\.)','',text)
        title=title.removeprefix('什么是')
        if any(len(term)>=5 and term in query for term in title.split('和')):
            # 精确概念标题与其后正文共同构成依据，不能仅传入孤立标题。
            group=[block]
            for following in blocks[index+1:]:
                if following.get('section_id')!=block.get('section_id') or following['kind']=='table':break
                if re.match(r'^(?:[一二三四五六七八九十]+、|\([一二三四五六七八九十]+\)|\d+\.)',following['text'].strip()):break
                group.append(following)
                if sum(len(b['text']) for b in group)>2000:break
            if len(group)>1:anchors.append((len(title),'\n'.join(b['text'] for b in group),block))
    sources=[]
    for _,text,block in sorted(anchors,key=lambda item:item[0],reverse=True)[:2]:
        section=sections[block['section_id']]
        stub=SimpleNamespace(text=text,kind='text',block_start=block['block_index'])
        sources.append({'text':text,'kind':'text','section':section['title'],
                        'source':'实验心理学（第3版）/第四章被试间设计','reference':chunk_reference(stub,section)})
    for chunk in chunks:
        section=sections.get(chunk.section_id)
        if not section:continue
        if chunk.kind=='text':
            group=[b['text'] for b in blocks if chunk.block_start<=b['block_index']<=chunk.block_end]
            if group:chunk=replace(chunk,text='\n'.join(group)[:3000])
        if any(chunk.text==s['text'] for s in sources):continue
        sources.append({'text':chunk.text,'kind':chunk.kind,'section':chunk.section,'source':chunk.source,
                        'reference':chunk_reference(chunk,section)})
        if len(sources)>=6:break
    return sources

def selected_source(selection, data):
    if selection.document_id!=data['document_id'] or selection.version!=data['version']:
        raise HTTPException(409,'所选内容不属于当前教材版本，请重新选择')
    pages=sorted({r.page for r in selection.rects})
    if len(pages)>2 or pages[-1]-pages[0]>1:raise HTTPException(422,'每次请选择相邻两页以内的内容')
    selected=[];context=[]
    with fitz.open(SAMPLE/'chapter_04.generated.pdf') as pdf:
        for rect in selection.rects:
            page=pdf[rect.page-1];size=page.rect
            box=fitz.Rect(rect.x1*size.width,rect.y1*size.height,rect.x2*size.width,rect.y2*size.height)
            selected.append(page.get_textbox(box))
            # 仅从服务端原页取上下文，客户端text不能冒充教材事实。
            context.append(page.get_textbox(fitz.Rect(0,max(0,box.y0-80),size.width,min(size.height,box.y1+100))))
    text='\n'.join(selected).strip()
    if not text:raise HTTPException(422,'此选区没有可读取的文字；图片和公式视觉核验尚未接入，请选择相邻说明文字')
    section=next(s for s in reversed(data['sections']) if s['generated_page']<=pages[0])
    ref=reference(section)|{'rects':[r.model_dump() for r in selection.rects], 'kind':selection.kind,
                            'text':text[:200],'location_kind':'selection'}
    return {'text':'所选原文：'+text[:4000]+'\n邻近正文：'+'\n'.join(dict.fromkeys(context))[:6000],
            'kind':'text','section':section['title'],'source':'实验心理学（第3版）/第四章被试间设计','reference':ref}

@router.post('/api/textbook-preview/psychology/ask')
def ask(body:Question):
    data=locations()
    if body.version!=data['version']:raise HTTPException(409,'教材版本已变更，请刷新后提问')
    question=body.question.strip()
    if not question:raise HTTPException(422,'请输入问题')
    selected=selected_source(body.selection,data) if body.selection else None
    sources=qa_sources((question+' '+selected['reference']['text'])[:400] if selected else question)
    if selected:sources.insert(0,selected)
    return explain(LLMClient(),question,sources)
