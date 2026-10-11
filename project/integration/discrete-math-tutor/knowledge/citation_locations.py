"""为回答实际引用的普通编号单元与已审核图片补齐 PDF 跳转。"""
import re
from pathlib import Path
from knowledge.pdf_reader import PDFSelection, resolve_selection
from knowledge.proof_units import REF, key, units_for
from knowledge.pdf_evidence import compact


def complete_pdf_references(sources, response, existing, *, figures=()):
    refs = list(existing)
    occupied = {r['source_index'] for r in refs}
    used = {int(i)-1 for i in re.findall(r'\[(\d+)\]', response)}
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
        heading = REF.match(source.text.lstrip())
        if not heading:
            continue
        try:
            unit = units_for(source.chapter_id).get(key(heading))
            if not unit or unit.truncated or source.section_id != unit.section['id']:
                continue
            if compact(source.section) != compact(unit.section['title']) or Path(source.source).stem != Path(unit.record['source']).stem:
                continue
            selected = resolve_selection(PDFSelection(document_id=unit.record['document_id'], version=unit.record['version'], kind='text', rects=list(unit.rects[:2])))
            if selected['section']['id'] != source.section_id:
                continue
            refs.append({'source_index':index, 'label':unit.label, 'selection_ref':selected['reference'] | {'origin':'retrieval'}})
            occupied.add(index)
        except (OSError, ValueError, KeyError, RuntimeError):
            continue
    return refs
