"""用经版本校验的 PDF 原页补足丢失的公式，不改动召回排名或模型门槛。"""
from __future__ import annotations
from dataclasses import dataclass, replace
from pathlib import Path
import logging
import re
import fitz
from knowledge.pdf_reader import document, pdf_path, PDFSelection, resolve_selection
from knowledge.textbook import terms_for

REFERENCE = re.compile(r'(定义|定理|例)\s*(\d+)\s*[.．]\s*(\d+)')
NUMBERED = re.compile(r'(表|定义|定理|例)\s*(\d+)\s*[.．]\s*(\d+)')

def compact(text):
    return re.sub(r'\s+', '', text).replace('．','.')

@dataclass
class PdfSupplement:
    images: list
    reference: dict
    pages: list[int]
    source_index: int
    anchor_method: str = "numbered_reference_or_body_phrase"
    def public(self):
        return {'document_id':self.reference['document_id'], 'version':self.reference['version'],
                'pages':self.pages,'source_index':self.source_index,
                'anchor_method':self.anchor_method}

def needs_pdf(source):
    return getattr(source,'kind','') == 'formula' or '[公式或对象]' in source.text or any(
        str(asset).startswith('formula-') for asset in getattr(source,'asset_ids',()))

def _ref_key(match):
    return (match.group(1), int(match.group(2)), int(match.group(3)))

def _lines(page):
    """使用行坐标；PDF 的同一块可能含正文、表号和下一个定理。"""
    result=[]
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            text=''.join(span['text'] for span in line['spans']).strip()
            result.append((line['bbox'][1]/page.rect.height, text, block))
    return sorted(result, key=lambda item:item[0])

def _requested_anchor(pdf, section, next_section, end_page, target):
    key=_ref_key(target)
    for number in range(section['page'], end_page+1):
        page=pdf[number-1]
        for y,text,block in _lines(page):
            if number==section['page'] and y<section['y']-.025: continue
            if next_section and number==next_section['page'] and y>=next_section['y']-.008: continue
            # 表号必须是独立表题；定理必须在定义正文开头，不能借用“据定理…”等引用。
            heading=compact(text)
            match=NUMBERED.fullmatch(heading) if key[0]=='表' else NUMBERED.match(heading)
            if not match or _ref_key(match)!=key: continue
            start=y
            # 带入同块的近邻说明；禁止一个大块把选区起点退到另一知识单元。
            block_y=block['bbox'][1]/page.rect.height
            if y-block_y<=.15: start=block_y
            if key[0]=='表':
                for previous in page.get_text('blocks',sort=True):
                    prev_y=previous[1]/page.rect.height
                    if 0 < y-prev_y<=.15 and any(_ref_key(m)==key for m in NUMBERED.finditer(compact(previous[4]))):
                        start=min(start,prev_y)
            start=max(.085,start-.008)
            if number==section['page']: start=max(start,section['y']-.008)
            return number,start,y
    return None

def _supplement(source, index, query=None):
    chapter=getattr(source,'chapter_id',None)
    section_id=getattr(source,'section_id',None)
    anchor_text=source.text.split("公式前文")[0].split("公式后文")[0]
    requested=list(NUMBERED.finditer(query or ''))
    available={_ref_key(m) for m in NUMBERED.finditer(anchor_text)}
    target=next((m for m in requested if _ref_key(m) in available),None)
    if requested and not target: return None
    requested_unit=bool(target and (target.group(1)=='表' or re.search(r'证明|反证|解释|为什么|为何|推导|说明',query or '')))
    requested_set_formula = bool(re.search(r'[∈∉⊆⊂⊇⊃∩∪]',query or ''))
    numbered_set_text = requested_set_formula and getattr(source,'kind','')=='text' and REFERENCE.search(source.text)
    if not chapter or not section_id or not (needs_pdf(source) or numbered_set_text or requested_unit): return None
    record=document(f'chapter-{chapter:02d}')
    if not record or Path(source.source).stem != Path(record['source']).stem: return None
    sections=record['sections']
    section=next((s for s in sections if s['id']==section_id),None)
    if not section or not section.get('verified') or compact(section['title']) != compact(source.section): return None
    next_section=next((s for s in sections if (s['page'],s['y'])>(section['page'],section['y'])),None)
    end_page=next_section['page'] if next_section else record['page_count']
    ref=target if requested_unit else REFERENCE.search(anchor_text)
    # 正文中的完整中文短语是备用锚点；有编号但编号缺失时不退回泛化匹配。
    phrases=[] if ref else [p for p in re.findall(r'[\u4e00-\u9fff]{8,}',anchor_text)
                            if p not in ('公式前文仅提供背景','公式所在段落')][:4]
    if not ref and not phrases: return None
    anchor=None
    with fitz.open(pdf_path(record)) as pdf:
        if requested_unit:
            anchor=_requested_anchor(pdf,section,next_section,end_page,target)
            if not anchor: return None
        for number in (() if requested_unit else range(section['page'],end_page+1)):
            page=pdf[number-1]
            for block in page.get_text('blocks',sort=True):
                y=block[1]/page.rect.height
                if number==section['page'] and y<section['y']-.025: continue
                if next_section and number==next_section['page'] and y>=next_section['y']-.008: continue
                text=compact(block[4])
                matches=any((m.group(1),m.group(2),m.group(3)) == (ref.group(1),ref.group(2),ref.group(3))
                            for m in REFERENCE.finditer(text)) if ref else any(p in text for p in phrases)
                if matches:
                    anchor=(number,max(.085,y-.008),None); break
            if anchor: break
        if not anchor: return None
        rects=[]
        for number in range(anchor[0],min(anchor[0]+1,end_page)+1):
            y1=anchor[1] if number==anchor[0] else .085
            y2=min(.9,next_section['y']-.008) if next_section and number==next_section['page'] else .9
            # 习题由练习页承载，不能作为相邻正文自动带进阅读问答。
            cutoffs=[]
            for line_y,heading,_ in _lines(pdf[number-1]):
                if re.fullmatch(r'(?:练习|习题)\s*\d+(?:\s*[.．]\s*\d+)?',heading) and line_y >= y1:
                    cutoffs.append(line_y-.008)
                if requested_unit and target.group(1)=='定理' and (number,line_y)>(anchor[0],anchor[2]+.001):
                    next_unit=NUMBERED.match(compact(heading))
                    if next_unit and next_unit.group(1)!='表' and _ref_key(next_unit)!=_ref_key(target):
                        cutoffs.append(line_y-.008)
            if cutoffs: y2=min(y2,min(cutoffs))
            if y2-y1>=.015:
                rects.append(dict(page=number,x1=.11,y1=y1,x2=.9,y2=y2))
            if cutoffs: break
    if not rects: return None
    # resolve_selection 校验源文件 SHA256、版本、页码、坐标并生成带哈希的原页裁图。
    resolved=resolve_selection(PDFSelection(document_id=record['document_id'],version=record['version'],kind='text',rects=rects))
    if resolved['section']['id'] != section_id: return None
    reference=resolved['reference']|{'origin':'retrieval'}
    pages=sorted({r['page'] for r in rects})
    replacement='[原 PDF 补充证据，第'+ '、'.join(map(str,pages)) +'页；公式以随附原图为准]\n'+resolved['text']
    return replace(source,text=replacement,terms=terms_for(replacement),page=pages[0]),PdfSupplement(
        images=resolved['images'],reference=reference,pages=pages,source_index=index,
        anchor_method=('table_caption' if target.group(1)=='表' else 'numbered_unit') if requested_unit else 'numbered_reference_or_body_phrase')

def enrich_sources(sources, query=None):
    """最多补充一个已召回片段、相邻两页；无法精确定位时保留原证据。"""
    for index,source in enumerate(sources):
        try:
            result=_supplement(source,index,query)
        except (OSError,ValueError,KeyError,RuntimeError) as exc:
            logging.getLogger(__name__).warning('原 PDF 证据补充失败：%s',type(exc).__name__)
            continue
        if result:
            updated,supplement=result
            output=list(sources); output[index]=updated
            return output,supplement
    return sources,None
