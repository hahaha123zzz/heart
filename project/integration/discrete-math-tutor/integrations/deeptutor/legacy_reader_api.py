"""旧教材阅读器的受控数据接口，沿用当前学生教材授权。"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
import base64
from fastapi.responses import FileResponse
from deeptutor.api.routers.auth import require_auth
from deeptutor.multi_user.learning_access import learning_material_allowed
from knowledge.pdf_reader import documents, document, pdf_path, public_document, PDFSelection, resolve_selection


def _permitted(record):
    return bool(record and learning_material_allowed(record['version'][:16]))


def _authorized(document_id):
    record = document(document_id)
    if not _permitted(record):
        raise HTTPException(404, '教材不存在或未授权')
    return record


def install_legacy_reader(app):
    router = APIRouter(prefix='/api/heart/legacy-reader', dependencies=[Depends(require_auth)])

    @router.get('/chapters')
    def chapters(response: Response):
        response.headers['Cache-Control'] = 'no-store'
        rows = []
        for row in documents():
            if not _permitted(row):
                continue
            material_id = row['version'][:16]
            try:
                from deeptutor.reading import ReadingStore
                revision = ReadingStore().manifest(material_id).revision
            except Exception:
                # New imports start at revision one. The turn bridge verifies
                # the actual revision before accepting a request.
                revision = 1
            rows.append({
                'document_id': row['document_id'], 'chapter_id': row['chapter_id'],
                'title': row.get('title', ''), 'version': row['version'],
                'page_count': row['page_count'], 'sections': row.get('sections', []),
                'reading_material_id': material_id,
                'reading_material_revision': revision,
            })
        return rows

    @router.get('/documents/{document_id}')
    def metadata(document_id: str, response: Response):
        record = _authorized(document_id)
        response.headers['Cache-Control'] = 'no-store'
        return public_document(record) | {'url': f'/api/heart/legacy-reader/documents/{document_id}/file'}

    @router.get('/documents/{document_id}/file')
    def pdf_file(document_id: str):
        record = _authorized(document_id)
        path = pdf_path(record)
        if not path.is_file():
            raise HTTPException(404, '教材文件暂不可用')
        return FileResponse(path, media_type='application/pdf', headers={'Cache-Control': 'private, no-store'})

    @router.get('/citation-target')
    def citation_target(material_id: str, locator: int, revision: int | None = None,
                        quote: str = Query(default='', max_length=2000)):
        from deeptutor.reading import ReadingStore
        rows = [row for row in documents() if row['version'][:16] == material_id and _permitted(row)]
        if len(rows) != 1:
            raise HTTPException(404, '引用的教材不存在或未授权')
        row = rows[0]
        if not 1 <= locator <= row['page_count']:
            raise HTTPException(400, '引用页码超出教材范围')
        try:
            manifest = ReadingStore().manifest(material_id)
        except Exception:
            raise HTTPException(404, '引用的教材版本不可用') from None
        if (manifest.version != row['version'] or manifest.document_id != row['document_id']
                or (revision is not None and manifest.revision != revision)):
            raise HTTPException(409, '引用的教材版本已变化')
        from knowledge.fixed_book import digest
        path = pdf_path(row)
        if digest(path) != row['version']:
            raise HTTPException(409, '教材文件已变化')
        rects = []
        if quote.strip():
            from knowledge.citation_index import locate_pdf_page_quote
            rects = locate_pdf_page_quote(path, locator, quote)
        return {'document_id': row['document_id'], 'version': row['version'],
                'locator': locator, 'rects': rects}

    @router.post('/selection')
    def selection(body: PDFSelection):
        _authorized(body.document_id)
        try:
            result = resolve_selection(body)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        return {'reference': result['reference'], 'text': result['text'], 'images': [{'filename': image_path.name, 'base64': base64.b64encode(image_path.read_bytes()).decode('ascii')} for image_path in result['images']]}

    app.include_router(router)
