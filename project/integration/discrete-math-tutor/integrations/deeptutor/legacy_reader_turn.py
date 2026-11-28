"""在原生聊天入口重新核验旧教材阅读器提交的来源。"""
from __future__ import annotations

import asyncio
import base64


def verified_reader_crop_filename(viewport) -> str:
    """提取经过应用入口核验的教材区域附件名。"""
    if not isinstance(viewport, dict) or not viewport.get('document_id'):
        return ''
    selection = viewport.get('legacy_reader_selection')
    if not isinstance(selection, dict) or selection.get('kind') != 'area':
        return ''
    return str(selection.get('attachment_filename') or '')


async def verify_legacy_reader_turn(payload: dict) -> dict:
    viewport = payload.get('reading_viewport')
    if not isinstance(viewport, dict) or not viewport.get('document_id'):
        return payload

    from deeptutor.multi_user.learning_access import assert_learning_material
    from deeptutor.reading import ReadingStore
    from knowledge.fixed_book import digest
    from knowledge.pdf_reader import PDFSelection, document, pdf_path, resolve_selection

    doc = document(viewport['document_id'])
    material_id = str(payload.get('reading_material_id') or '')
    if (not doc or doc['version'][:16] != material_id
            or doc['chapter_id'] != viewport.get('chapter_id')):
        raise RuntimeError('教材引用不匹配，请重新打开教材。')
    try:
        assert_learning_material(material_id)
        manifest = await asyncio.to_thread(ReadingStore().manifest, material_id)
        if (manifest.revision != payload.get('reading_material_revision')
                or manifest.version != doc['version']
                or await asyncio.to_thread(digest, pdf_path(doc)) != doc['version']):
            raise ValueError('教材版本已变化，请重新选择。')
        locator = viewport.get('locator')
        if not isinstance(locator, int) or not 1 <= locator <= doc['page_count']:
            raise ValueError('教材页码无效，请重新选择。')
        selected = viewport.get('legacy_reader_selection')
        clean_viewport = {'locator': locator, 'document_id': doc['document_id'],
                          'chapter_id': doc['chapter_id']}
        if selected:
            if not isinstance(selected, dict) or selected.get('document_id') != doc['document_id'] or selected.get('version') != doc['version']:
                raise ValueError('教材选区已失效，请重新选择。')
            selection = PDFSelection.model_validate({
                'document_id': selected.get('document_id'), 'version': selected.get('version'),
                'kind': selected.get('kind'), 'rects': selected.get('rects'), 'text': '',
            })
            result = await asyncio.to_thread(resolve_selection, selection)
            clean_viewport['locator'] = selection.rects[0].page
            clean_viewport['selection'] = result['text']
            if selection.kind == 'text' and result['text']:
                legacy_prompt = f"请结合教材解释这段内容：\n{result['text']}"
                if payload.get('content') == legacy_prompt:
                    payload = {**payload, 'content': '请结合教材解释这段内容。'}
            clean_viewport['legacy_reader_selection'] = {
                **selection.model_dump(exclude={'text'}),
                **({'attachment_filename': selected.get('attachment_filename')}
                   if selected.get('attachment_filename') else {}),
            }
            if selection.kind == 'area':
                filename = str(selected.get('attachment_filename') or '')
                images = result['images']
                attachments = list(payload.get('attachments') or [])
                matches = [i for i, item in enumerate(attachments)
                           if isinstance(item, dict) and item.get('filename') == filename
                           and item.get('type') == 'image']
                if len(images) != 1 or images[0].name != filename or len(matches) != 1:
                    raise ValueError('选区图片已失效，请重新框选。')
                data = await asyncio.to_thread(images[0].read_bytes)
                attachments[matches[0]] = {'type': 'image', 'filename': filename,
                    'base64': base64.b64encode(data).decode('ascii'), 'mime_type': 'image/png'}
                payload = {**payload, 'attachments': attachments}
        return {**payload, 'reading_viewport': clean_viewport}
    except (ValueError, PermissionError) as exc:
        raise RuntimeError(str(exc) or '教材引用已失效，请重新选择。') from exc
