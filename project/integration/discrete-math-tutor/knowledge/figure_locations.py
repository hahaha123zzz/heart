"""人工核对的图片位置；文件、版本、哈希或图注不一致时不启用。"""
import json
import re
from pathlib import Path
from dataclasses import replace
import fitz
from knowledge.pdf_reader import document, pdf_path, PDFSelection, resolve_selection
from knowledge.pdf_evidence import compact, _lines

LOCATIONS = Path(__file__).with_name('figure_locations.json')


def apply_figure_location(figure):
    try:
        records = json.loads(LOCATIONS.read_text(encoding='utf8'))
        item = next((r for r in records if r.get('asset_id') == figure.id and r.get('review_status') == 'approved'), None)
        if not item or item['asset_sha256'] != figure.sha256 or not figure.is_valid():
            return figure
        record = document(item['document_id'])
        if not record or record['version'] != item['version'] or record['chapter_id'] != figure.chapter_id:
            return figure
        if Path(record['source']).stem != Path(figure.source).stem:
            return figure
        section = next((s for s in record['sections'] if s['id'] == item['section_id']), None)
        if not section or not section.get('verified') or compact(section['title']) != compact(item['section_title']):
            return figure
        if not re.fullmatch(r'图[0-9]+\.[0-9]+', item['label']):
            return figure
        with fitz.open(pdf_path(record)) as pdf:
            found = any(compact(text) == item['label'] and rect['y1'] <= y <= rect['y2']
                        for rect in item['rects'] for y, text, _ in _lines(pdf[rect['page']-1]))
        if not found:
            return figure
        selected = resolve_selection(PDFSelection(document_id=record['document_id'], version=record['version'], kind='area', rects=item['rects']))
        if selected['section']['id'] != item['section_id']:
            return figure
        reference = selected['reference'] | {'origin':'retrieval'}
        return replace(figure, label=item['label'], caption=item['caption'], section_id=item['section_id'], kind='figure', selection_ref=reference)
    except (OSError, ValueError, KeyError, RuntimeError, IndexError, TypeError):
        return figure
