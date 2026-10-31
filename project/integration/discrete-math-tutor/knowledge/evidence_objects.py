"""第四层内部只读对象读取；不发布、不执行OMML、不声称理解公式或取得像素。"""
import hashlib
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from pydantic import Field
from models.input_understanding import StrictModel
from typing import Literal

from agents.q3_navigation import SourceRef
from knowledge.source_mapping import block_text, source_spans
from scripts.parse_converted_textbook import NS, open_word_package, paragraph_text, block_paragraphs


class ObjectReadRequest(StrictModel):
    document_id: str = Field(pattern=r'^experimental-psychology-3:chapter-(?:0[1-9]|1[01])$')
    version: str = Field(pattern=r'^[a-f0-9]{64}$')
    object_id: str = Field(min_length=1, max_length=100)
    kind: Literal['table', 'formula']


def read_object(request: ObjectReadRequest):
    from knowledge.course_config import PSYCHOLOGY_DIR
    from knowledge.pdf_reader import document, pdf_path
    from knowledge.citation_index import LiveCitationIndex
    from knowledge.fixed_book import digest

    record = document(request.document_id)
    if not record or record['version'] != request.version or digest(pdf_path(record)) != request.version:
        raise ValueError('stale_document_version')
    chapter = record['chapter_id']
    directory = PSYCHOLOGY_DIR/'chapters'/f'chapter_{chapter:02d}'
    manifest = json.loads((PSYCHOLOGY_DIR/'manifest.json').read_bytes())
    registered = next(item for item in manifest['full_import']['chapters'] if item['chapter_id'] == chapter)
    original = (PSYCHOLOGY_DIR/registered['docx']).resolve()
    if not original.is_relative_to(PSYCHOLOGY_DIR.resolve()) or digest(original) != registered['source_sha256']:
        raise ValueError('stale_original_source')
    document_path = directory/'document.json'
    document_hash = digest(document_path)
    structured = json.loads(document_path.read_bytes())
    if structured['docx_sha256'] != registered['source_sha256'] or structured['chapter_id'] != chapter:
        raise ValueError('structured_source_mismatch')
    blocks = structured['blocks']
    formula = None
    if request.kind == 'table':
        match = re.fullmatch(re.escape(request.document_id)+r':b(\d+)', request.object_id)
        if not match:
            raise ValueError('invalid_table_identity')
        number = int(match[1])
    else:
        formula = next((f for f in structured.get('omml_objects', []) if f['id'] == request.object_id), None)
        if formula is None:
            raise ValueError('unknown_formula')
        number = formula['block_index']
    block = next((b for b in blocks if b['block_index'] == number), None)
    if block is None or (request.kind == 'table' and block['kind'] != 'table'):
        raise ValueError('object_kind_mismatch')
    # 复用导入器的序列化，逐块比对原DOCX；JSON和PDF版本相同也不能免除原文校验。
    with open_word_package(original) as package:
        raw_blocks = list(ET.fromstring(package.read('word/document.xml')).find('w:body', NS))
    selected = [b for b in blocks if abs(b['block_index']-number) <= 1 and b.get('section_id') == block.get('section_id')]
    for item in selected:
        if type(item['block_index']) is not int or not 0 <= item['block_index'] < len(raw_blocks):
            raise ValueError('invalid_original_block_index')
        node = raw_blocks[item['block_index']]
        text = '\n'.join(t for p in block_paragraphs(node) if (t := paragraph_text(p)))
        if text != item['text']:
            raise ValueError('original_block_mismatch')
        if item['kind'] == 'table':
            if node.tag != '{'+NS['w']+'}tbl':
                raise ValueError('original_table_kind_mismatch')
            rows = [[' / '.join(t for p in cell.findall('.//w:p', NS) if (t := paragraph_text(p)))
                     for cell in row.findall('w:tc', NS)] for row in node.findall('w:tr', NS)]
            if [row for row in rows if any(row)] != item['rows']:
                raise ValueError('original_table_mismatch')
    payload = {'rows': block['rows']} if request.kind == 'table' else {}
    if formula:
        path = (directory/formula['path']).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError('formula_path_outside_chapter')
        raw = path.read_bytes()
        originals = [(position, ET.tostring(node, encoding='utf-8'))
                     for position, item in enumerate(raw_blocks) for node in item.findall('.//m:oMath', NS)]
        match = re.fullmatch(re.escape(request.document_id)+r':omml-(\d{3,})', request.object_id)
        ordinal = int(match[1])-1 if match else -1
        if not 0 <= ordinal < len(originals) or originals[ordinal] != (number, raw):
            raise ValueError('original_formula_mismatch')
        payload = {'raw_omml': raw.decode('utf-8'), 'sha256': hashlib.sha256(raw).hexdigest(),
                   'status': 'raw_omml_requires_pdf_verification', 'semantic_verified': False}
    index = LiveCitationIndex()
    sources = []
    try:
        for item in selected:
            text = block_text(item)
            if not text.strip():
                continue
            located = index.locate(request.document_id, request.version, text, block_id=item['block_index'])
            rects = located.get('rects', []) if located['status'] == 'exact' else []
            key = hashlib.sha256(f'{request.document_id}:{request.version}:{document_hash}:{item["block_index"]}'.encode()).hexdigest()
            sources.append(SourceRef(key, request.document_id, text, request.version, chapter,
                item.get('section_id'), min((r['page'] for r in rects), default=None), text,
                location={'origin': 'layer4_object_read', 'kind': item['kind'],
                          'object_id': request.object_id if item is block else None,
                          'object_kind': request.kind if item is block else None,
                          'document_sha256': document_hash, 'original_sha256': registered['source_sha256'],
                          'source_spans': list(source_spans([item], text)),
                          'location_status': located['status'], 'rects': rects,
                          'semantic_verified': False, 'model_saw_pixels': False}))
    finally:
        index.close()
    if (digest(original) != registered['source_sha256'] or digest(document_path) != document_hash
            or digest(pdf_path(record)) != request.version):
        raise ValueError('source_changed_during_read')
    return {'object_id': request.object_id, 'kind': request.kind, 'payload': payload,
            'sources': sources, 'scope': 'read_only_original_object_and_adjacent_blocks',
            'semantic_verified': False, 'model_saw_pixels': False}
