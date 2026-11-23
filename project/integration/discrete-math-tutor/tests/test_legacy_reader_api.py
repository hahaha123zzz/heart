from unittest.mock import patch
import pytest
from fastapi import HTTPException
from integrations.deeptutor import legacy_reader_api as reader


def test_authorized_document_checks_material_allowlist():
    row = {'document_id': 'chapter', 'version': 'a' * 64}
    with patch.object(reader, 'document', return_value=row), patch.object(reader, 'learning_material_allowed', return_value=True) as allowed:
        assert reader._authorized('chapter') is row
        allowed.assert_called_once_with('a' * 16)
    with patch.object(reader, 'document', return_value=row), patch.object(reader, 'learning_material_allowed', return_value=False):
        with pytest.raises(HTTPException) as error:
            reader._authorized('chapter')
        assert error.value.status_code == 404


def test_missing_document_does_not_access_authorization():
    with patch.object(reader, 'document', return_value=None), patch.object(reader, 'learning_material_allowed') as allowed:
        with pytest.raises(HTTPException) as error:
            reader._authorized('missing')
        assert error.value.status_code == 404
        allowed.assert_not_called()
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch
from integrations.deeptutor import legacy_reader_api as reader


def test_reader_endpoints_enforce_permissions_and_support_ranges(tmp_path):
    path = tmp_path / 'textbook.pdf'
    path.write_bytes(b'%PDF-1.4\n0123456789\n%%EOF')
    allowed = {'document_id':'doc-allowed','chapter_id':1,'page_count':3,'version':'a'*64,'sections':[{'id':1,'page':1,'y':0}]}
    denied = {'document_id':'doc-denied','chapter_id':2,'page_count':3,'version':'b'*64,'sections':[]}
    app=FastAPI()
    reader.install_legacy_reader(app)
    app.dependency_overrides[reader.require_auth]=lambda: {'username':'student'}
    with patch.object(reader,'documents',return_value=[allowed,denied]), patch.object(reader,'document',side_effect=lambda key: {'doc-allowed':allowed,'doc-denied':denied}.get(key)), patch.object(reader,'learning_material_allowed',side_effect=lambda key:key=='a'*16), patch.object(reader,'pdf_path',return_value=path), patch('deeptutor.reading.ReadingStore') as reading_store:
        reading_store.return_value.manifest.return_value.revision = 3
        client=TestClient(app)
        result=client.get('/api/heart/legacy-reader/chapters')
        assert result.status_code==200
        assert [row['document_id'] for row in result.json()]==['doc-allowed']
        assert result.json()[0]['reading_material_id']=='a'*16
        assert result.json()[0]['reading_material_revision']==3
        assert client.get('/api/heart/legacy-reader/documents/doc-denied').status_code==404
        assert client.get('/api/heart/legacy-reader/documents/doc-denied/file').status_code==404
        response=client.get('/api/heart/legacy-reader/documents/doc-allowed/file',headers={'Range':'bytes=0-7'})
        assert response.status_code==206
        assert response.content==b'%PDF-1.4'


def test_reader_requires_authentication():
    app=FastAPI()
    reader.install_legacy_reader(app)
    with patch('deeptutor.api.routers.auth.AUTH_ENABLED', True):
        response=TestClient(app).get('/api/heart/legacy-reader/chapters')
    assert response.status_code in (401,403)


def test_area_selection_serializes_generated_crop_paths(tmp_path):
    crop = tmp_path / 'verified-crop.png'
    crop.write_bytes(b'png-bytes')
    app = FastAPI()
    reader.install_legacy_reader(app)
    app.dependency_overrides[reader.require_auth] = lambda: {'username': 'student'}
    body = {'document_id': 'chapter-01', 'version': 'a' * 64, 'kind': 'area',
            'rects': [{'page': 1, 'x1': 0.1, 'y1': 0.1, 'x2': 0.2, 'y2': 0.2}], 'text': ''}
    result = {'reference': {'image_refs': []}, 'text': '', 'images': [crop]}
    with patch.object(reader, '_authorized', return_value={'version': 'a' * 64}), \
         patch.object(reader, 'resolve_selection', return_value=result):
        response = TestClient(app).post('/api/heart/legacy-reader/selection', json=body)
    assert response.status_code == 200
    assert response.json()['images'] == [{'filename': 'verified-crop.png', 'base64': 'cG5nLWJ5dGVz'}]


def test_citation_target_checks_grant_version_and_page(tmp_path):
    from types import SimpleNamespace
    row = {'document_id': 'chapter-01', 'version': 'a' * 64, 'page_count': 3}
    app = FastAPI()
    reader.install_legacy_reader(app)
    app.dependency_overrides[reader.require_auth] = lambda: {'username': 'student'}
    manifest = SimpleNamespace(version='a' * 64, document_id='chapter-01', revision=2)
    with patch.object(reader, 'documents', return_value=[row]), \
         patch.object(reader, 'learning_material_allowed', return_value=True) as allowed, \
         patch.object(reader, 'pdf_path', return_value=tmp_path / 'book.pdf'), \
         patch('deeptutor.reading.ReadingStore') as store, \
         patch('knowledge.fixed_book.digest', return_value='a' * 64):
        store.return_value.manifest.return_value = manifest
        client = TestClient(app)
        url = '/api/heart/legacy-reader/citation-target?material_id=' + 'a' * 16
        assert client.get(url + '&locator=2&revision=2').json()['locator'] == 2
        assert client.get(url + '&locator=4&revision=2').status_code == 400
        assert client.get(url + '&locator=2&revision=1').status_code == 409
        allowed.return_value = False
        assert client.get(url + '&locator=2&revision=2').status_code == 404
