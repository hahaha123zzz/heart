"""点名原图先读取其登记原文，避免图片依赖语义召回命中同一小节。"""
import json

from knowledge.figures import FIGURE_NUMBER, get_figure, retrieve_figures
from knowledge.source_visuals import get_visual
from knowledge.course_config import PSYCHOLOGY, PSYCHOLOGY_DIR
from knowledge.source_mapping import block_text, source_spans
from knowledge.textbook import TextbookChunk, terms_for


def named_figures(message, asset_id=None):
    if asset_id:
        figure = get_figure(asset_id)
        return [figure] if figure else []
    return retrieve_figures(message, [], limit=20) if FIGURE_NUMBER.search(message) else []


def read_figure(figure):
    """原文仍进入现有 choose_evidence，不把资产上下文字符串直接当引文。"""
    if not PSYCHOLOGY or not figure.is_valid():
        return []
    asset = get_visual(figure.id)
    if asset is None or asset.block_index is None:
        return []
    doc = json.loads((PSYCHOLOGY_DIR / 'chapters' / f'chapter_{figure.chapter_id:02d}' / 'document.json').read_bytes())
    blocks = doc['blocks']
    position = next((i for i, block in enumerate(blocks) if block['block_index'] == asset.block_index), None)
    if position is None or figure.id not in blocks[position].get('image_ids', []):
        return []
    selected, size = [], 0
    for block in blocks[max(0, position - 1):position + 5]:
        text = block_text(block)
        if block.get('section_id') != figure.section_id or not text.strip():
            continue
        if size + len(text) > 5000:
            break
        selected.append(block)
        size += len(text)
    if not selected:
        return []
    text = '\n'.join(block_text(block) for block in selected)
    return [TextbookChunk(source=figure.source, section=asset.section, text=text, terms=terms_for(text),
        asset_ids=(figure.id,), chapter_id=figure.chapter_id, section_id=figure.section_id,
        chunk_id='figure:' + figure.id, block_start=selected[0]['block_index'],
        block_end=selected[-1]['block_index'], source_spans=source_spans(selected, text))]
