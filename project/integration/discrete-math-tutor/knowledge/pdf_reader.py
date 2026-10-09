"""PDF 选区验证、正文上下文与服务端裁图；浏览器文字仅作为预览。"""
from __future__ import annotations
from pathlib import Path
from functools import lru_cache
from typing import Literal
import hashlib, json, re, math
import fitz
from pydantic import BaseModel, Field, ConfigDict
from knowledge.course import get_section
ROOT = Path(__file__).resolve().parent / 'pdf'
CROPS = ROOT / 'crops'
class PDFRect(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    page: int = Field(ge=1)
    x1: float = Field(ge=0,lt=1)
    y1: float = Field(ge=0,lt=1)
    x2: float = Field(gt=0,le=1)
    y2: float = Field(gt=0,le=1)
class PDFSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    document_id: str = Field(pattern=r'^chapter-(?:0[1-9]|10)$')
    version: str = Field(pattern=r'^[a-f0-9]{64}$')
    kind: Literal['text','area']
    rects: list[PDFRect] = Field(min_length=1,max_length=80)
    text: str = Field(default='',max_length=4000)
@lru_cache(maxsize=1)
def documents():
    return json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
def document(document_id):
    return next((d for d in documents() if d['document_id']==document_id), None)
def pdf_path(record): return ROOT / f"chapter_{record['chapter_id']:02d}.pdf"
def public_document(record):
    return {k:v for k,v in record.items() if k not in ('pages','source_sha256')} | {'url':f"/api/pdf/documents/{record['document_id']}/file"}
def section_pdf(chapter_id, section_id):
    record = document(f'chapter-{chapter_id:02d}')
    section = next((s for s in record['sections'] if s['id']==section_id),None) if record else None
    return public_document(record) | {'section':section} if section else None
def validate_selection(selection: PDFSelection):
    record = document(selection.document_id)
    if not record: raise ValueError('教材不存在')
    if record['version'] != selection.version: raise ValueError('教材已更新，请重新选择内容')
    pages = {r.page for r in selection.rects}
    if len(pages)>2 or max(pages)-min(pages)>1: raise ValueError('每次最多选择相邻两页，请缩小选区')
    if selection.kind=='area' and (len(pages)!=1 or len(selection.rects)!=1): raise ValueError('区域框选请限制在一页内')
    for r in selection.rects:
        if r.page > record['page_count'] or r.x2 <= r.x1 or r.y2 <= r.y1:
            raise ValueError('选区页码或坐标无效，请重新选择')
        if (r.x2-r.x1)*(r.y2-r.y1) > .65: raise ValueError('选区过大，请选择具体的段落、图或公式')
    return record
def crop_path(crop_id):
    if not re.fullmatch(r'[a-f0-9]{64}',crop_id): return None
    path = CROPS/(crop_id+'.png')
    metadata = path.with_suffix('.json')
    if not path.is_file() or not metadata.is_file(): return None
    data = json.loads(metadata.read_text(encoding='utf-8'))
    record = document(data['document_id'])
    if not record or record['version'] != data['version']: return None
    if hashlib.sha256(path.read_bytes()).hexdigest() != data['image_sha256']: return None
    return path

def resolve_selection(selection):
    record = validate_selection(selection)
    # 文件哈希校验阻止在未重建清单时使用已替换的 PDF。
    if hashlib.sha256(pdf_path(record).read_bytes()).hexdigest() != record['version']:
        raise ValueError('教材文件已变化，请重新建立页码索引')
    selected, images, refs = [], [], []
    page_numbers = sorted({r.page for r in selection.rects})
    CROPS.mkdir(exist_ok=True)
    with fitz.open(pdf_path(record)) as pdf:
        for page_number in page_numbers:
            page = pdf[page_number-1]
            ranges = [r for r in selection.rects if r.page==page_number]
            actual = [fitz.Rect(r.x1*page.rect.width,r.y1*page.rect.height,r.x2*page.rect.width,r.y2*page.rect.height) for r in ranges]
            for rect in actual:
                selected.append(page.get_text('text',clip=rect,sort=True).strip())
            bound = fitz.Rect(actual[0])
            for rect in actual[1:]: bound |= rect
            if bound.width < 3 or bound.height < 3: raise ValueError('选区过小，请重新选择')
            # 文本跨行合成一张页面内裁图；保证公式和上下标一同进入模型。
            key = hashlib.sha256(json.dumps({'document_id':record['document_id'],'version':record['version'],
                'page':page_number,'bounds':list(bound)},sort_keys=True).encode()).hexdigest()
            path = CROPS/(key+'.png')
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2,2),clip=bound,alpha=False)
            image_bytes = pixmap.tobytes('png')
            if len(image_bytes)>8*1024*1024: raise ValueError('选区图片过大，请缩小范围')
            # 同一选区内容寻址；原子替换防止并发请求读取半张图片。
            import os, tempfile
            def atomic_write(target,data):
                with tempfile.NamedTemporaryFile(dir=CROPS,delete=False) as tmp:
                    tmp.write(data); name=tmp.name
                os.replace(name,target)
            atomic_write(path,image_bytes)
            atomic_write(path.with_suffix('.json'),json.dumps({'document_id':record['document_id'],'version':record['version'],
                'image_sha256':hashlib.sha256(image_bytes).hexdigest()}).encode())
            images.append(path)
            refs.append({'id':key,'image_url':f'/api/pdf/crops/{key}/image','label':f'教材第 {page_number} 页选区'})
        first = selection.rects[0]
        candidates = [s for s in record['sections'] if (s['page'],s['y']) <= (first.page,first.y1+.015)]
        section = candidates[-1] if candidates else record['sections'][0]
        context_pages = sorted(set(n for p in page_numbers for n in (p-1,p,p+1) if 1<=n<=len(pdf)))
        context = []
        for n in context_pages:
            text = pdf[n-1].get_text(sort=True)
            if n not in page_numbers: text = text[-1600:] if n<min(page_numbers) else text[:1600]
            context.append(f'[教材第{n}页]\n'+text[:6500])
    text = '\n'.join(dict.fromkeys(t for t in selected if t))[:4000]
    if selection.kind=='text' and not text: raise ValueError('未能读取选中文字，可改用区域框选')
    reference = selection.model_dump() | {'text':text,'chapter_id':record['chapter_id'],'section_id':section['id'],
        'section_title':section['title'],'source':record['source'],'image_refs':refs}
    structured = get_section(record['chapter_id'],section['id'])
    context_text = '\n'.join(context)[:12000]
    if structured: context_text += '\n[对应小节结构化正文，仅补充背景，公式以原图为准]\n'+structured['content'][:2200]
    return {'reference':reference,'text':text,'context':context_text,'images':images,'record':record,'section':section}
