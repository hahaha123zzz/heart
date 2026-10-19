"""为回答实际引用的普通编号单元与已审核图片补齐 PDF 跳转。"""
import re
import json
from pathlib import Path
from knowledge.pdf_reader import PDFSelection, resolve_selection
from knowledge.proof_units import REF, key, units_for
from knowledge.pdf_evidence import compact
from knowledge.pdf_reader import documents, pdf_path
import fitz


def section_reference(chapter, section_id):
    """仅高亮经验证的小节标题，不把小节起页冒充正文坐标。"""
    record = next((r for r in documents() if r['chapter_id'] == chapter), None)
    section = next((s for s in record['sections'] if s['id'] == section_id), None) if record else None
    if not section or not section.get('verified'):
        raise ValueError('没有已核验的教材小节定位')
    # Word 导出的目录可能在标题后带对象占位；原 PDF 标题不含字段代码。
    title = re.sub(r'\s*EMBED\s+Equation\.\d+\s*\[公式或对象\]\s*$', '', section['title'])
    with fitz.open(pdf_path(record)) as pdf:
        page = pdf[section['page']-1]
        matches = []
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines', []):
                text = ''.join(span['text'] for span in line['spans'])
                if compact(text) == compact(title):
                    box = line['bbox']
                    matches.append(dict(page=section['page'], x1=box[0]/page.rect.width,
                        y1=max(0,box[1]/page.rect.height-.002),x2=box[2]/page.rect.width,
                        y2=min(1,box[3]/page.rect.height+.002)))
        if len(matches) != 1:
            raise ValueError('教材小节标题定位不唯一')
    selected = resolve_selection(PDFSelection(document_id=record['document_id'],version=record['version'],kind='text',rects=matches))
    return selected['reference'] | {'origin':'retrieval','location_kind':'section_heading'}


def locate_source(source, response='', *, allow_section=True):
    """验证文件、小节；优先编号内容，其次明确标记的小节标题。"""
    record = next((r for r in documents() if r['chapter_id'] == source.chapter_id), None)
    section = next((s for s in record['sections'] if s['id'] == source.section_id), None) if record else None
    if not section or Path(source.source).stem != Path(record['source']).stem or compact(source.section) != compact(section['title']):
        return None
    candidates = [key(m) for m in REF.finditer(response) if key(m) in {key(h) for h in REF.finditer(source.text)}]
    heading = REF.match(source.text.lstrip())
    if heading:
        candidates.append(key(heading))
    for label in dict.fromkeys(candidates):
        unit = units_for(source.chapter_id).get(label)
        if not unit or unit.truncated or unit.section['id'] != source.section_id:
            continue
        selected = resolve_selection(PDFSelection(document_id=record['document_id'],version=record['version'],kind='text',rects=list(unit.rects[:2])))
        if selected['section']['id'] == source.section_id:
            return {'label':label,'selection_ref':selected['reference'] | {'origin':'retrieval','location_kind':'numbered_unit'}}
    if record.get('course_id')=='experimental-psychology-3' and source.block_start is not None:
        from knowledge.course_config import PSYCHOLOGY_DIR
        blocks=json.loads((PSYCHOLOGY_DIR/'chapters'/f'chapter_{source.chapter_id:02d}'/'document.json').read_text(encoding='utf-8'))['blocks']
        block=next((b for b in blocks if b['block_index']==source.block_start),None)
        text=source.text.split('\n')[0] if source.kind=='table' else (block or {}).get('text','')
        prefix=compact(text)[:28];matches=[]
        following=next((s for s in record['sections'] if s['id']==section['id']+1),None)
        end=following['page'] if following else record['page_count']
        if len(prefix)>=6:
            with fitz.open(pdf_path(record)) as pdf:
                for number in range(section['page'],end+1):
                    page=pdf[number-1]
                    for block in page.get_text('dict')['blocks']:
                        for line in block.get('lines',[]):
                            if compact(''.join(s['text'] for s in line['spans'])).startswith(prefix):
                                box=line['bbox'];matches.append(dict(page=number,x1=box[0]/page.rect.width,y1=box[1]/page.rect.height,x2=box[2]/page.rect.width,y2=box[3]/page.rect.height))
            if len(matches)==1:
                selected=resolve_selection(PDFSelection(document_id=record['document_id'],version=record['version'],kind='text',rects=matches))
                if selected['section']['id']==source.section_id:
                    return {'label':'教材原文定位','selection_ref':selected['reference']|{'origin':'retrieval','location_kind':'paragraph_anchor'}}
    if allow_section:
        return {'label':'小节标题定位','selection_ref':section_reference(source.chapter_id,source.section_id)}
    return None


def resolve_source_label(source_label, response=''):
    """旧对话来源只允许匹配本地清单，不信任文字中的页码或路径。"""
    parts = re.split(r'[／/]',source_label,maxsplit=1)
    if len(parts) != 2:
        raise ValueError('来源格式无法定位')
    section_title = re.sub(r'\s*[（(]PDF第\d+页起[）)]\s*$','',parts[1]).strip()
    record = next((r for r in documents() if parts[0].strip() in (r['source'],str(Path(r['source']).with_suffix('.txt')))),None)
    section = next((s for s in record['sections'] if compact(s['title']) == compact(section_title)),None) if record else None
    if not section:
        raise ValueError('来源不属于已索引教材')
    # 旧历史没有保存证据范围；只能打开当前教材小节，不能事后猜成旧回答的精确定位。
    return {'label':'旧来源 · 当前教材小节','selection_ref':{
        'document_id':record['document_id'],'version':record['version'],'chapter_id':record['chapter_id'],
        'section_id':section['id'],'section_title':section['title'],'source':record['source'],
        'kind':'text','rects':[],'text':'','image_refs':[],'location_kind':'section',
        'page':section['page'] if section.get('verified') else None}}


def complete_pdf_references(sources, response, existing, *, figures=(), include_primary=False):
    refs = list(existing)
    occupied = {r['source_index'] for r in refs}
    used = {int(i)-1 for i in re.findall(r'\[(\d+)\]', response)}
    if not used and include_primary and sources:
        used.add(0)
    # 先关联图片，避免邻近正文编号代替图片的精确坐标。
    for figure in figures:
        reference = getattr(figure, 'selection_ref', None)
        if not reference or not figure.is_valid():
            continue
        index = next((i for i, source in enumerate(sources) if i in used
                      and Path(source.source).stem == Path(figure.source).stem
                      and (figure.id in source.asset_ids or figure.label in source.text)), None)
        if index is None or index in occupied:
            continue
        try:
            selected = resolve_selection(PDFSelection(document_id=reference['document_id'], version=reference['version'], kind='area', rects=reference['rects']))
            if selected['section']['id'] != figure.section_id:
                continue
            refs.append({'source_index':index, 'label':figure.label, 'selection_ref':selected['reference'] | {'origin':'retrieval'}})
            occupied.add(index)
        except (OSError, ValueError, KeyError, RuntimeError):
            continue
    for index, source in enumerate(sources):
        if index not in used or index in occupied or source.kind != 'text' or not source.chapter_id:
            continue
        try:
            located = locate_source(source,response)
            if not located:
                continue
            refs.append({'source_index':index, **located})
            occupied.add(index)
        except (OSError, ValueError, KeyError, RuntimeError):
            continue
    return refs
