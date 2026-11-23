from types import SimpleNamespace
from unittest.mock import patch

import pytest

from integrations.deeptutor.legacy_reader_turn import verify_legacy_reader_turn


@pytest.mark.asyncio
async def test_viewport_requires_authorized_unchanged_material():
    row = {'document_id': 'chapter-01', 'chapter_id': 1, 'version': 'a' * 64, 'page_count': 4}
    manifest = SimpleNamespace(version='a' * 64, revision=1)
    payload = {'reading_material_id': 'a' * 16, 'reading_material_revision': 1,
               'reading_viewport': {'document_id': 'chapter-01', 'chapter_id': 1, 'locator': 2}}
    with patch('knowledge.pdf_reader.document', return_value=row), \
         patch('knowledge.pdf_reader.pdf_path', return_value='book.pdf'), \
         patch('knowledge.fixed_book.digest', return_value='a' * 64), \
         patch('deeptutor.multi_user.learning_access.assert_learning_material') as authorize, \
         patch('deeptutor.reading.ReadingStore') as store:
        store.return_value.manifest.return_value = manifest
        assert (await verify_legacy_reader_turn(payload))['reading_viewport']['locator'] == 2
        authorize.assert_called_with('a' * 16)
        with pytest.raises(RuntimeError):
            await verify_legacy_reader_turn({**payload, 'reading_material_revision': 2})
        with pytest.raises(RuntimeError):
            await verify_legacy_reader_turn({**payload, 'reading_viewport': {**payload['reading_viewport'], 'locator': 5}})
        authorize.side_effect = PermissionError('未授权')
        with pytest.raises(RuntimeError):
            await verify_legacy_reader_turn(payload)


@pytest.mark.asyncio
async def test_selection_replaces_client_text_with_verified_pdf_text():
    row = {'document_id': 'chapter-01', 'chapter_id': 1, 'version': 'a' * 64, 'page_count': 4}
    selection = {'document_id': 'chapter-01', 'version': 'a' * 64, 'kind': 'text',
                 'rects': [{'page': 2, 'x1': .1, 'y1': .1, 'x2': .2, 'y2': .2}]}
    payload = {'reading_material_id': 'a' * 16, 'reading_material_revision': 1,
               'reading_viewport': {'document_id': 'chapter-01', 'chapter_id': 1, 'locator': 2,
                                    'selection': '伪造内容', 'legacy_reader_selection': selection}}
    with patch('knowledge.pdf_reader.document', return_value=row), \
         patch('knowledge.pdf_reader.pdf_path', return_value='book.pdf'), \
         patch('knowledge.fixed_book.digest', return_value='a' * 64), \
         patch('knowledge.pdf_reader.resolve_selection', return_value={'text': '核实的教材原文'}), \
         patch('deeptutor.multi_user.learning_access.assert_learning_material'), \
         patch('deeptutor.reading.ReadingStore') as store:
        store.return_value.manifest.return_value = SimpleNamespace(version='a' * 64, revision=1)
        result = await verify_legacy_reader_turn(payload)
        assert result['reading_viewport']['selection'] == '核实的教材原文'
        assert result['reading_viewport']['legacy_reader_selection']['rects'] == selection['rects']


def test_selection_survives_websocket_protocol_validation():
    from deeptutor.api.contracts.turn_protocol import StartTurnCommand
    selection = {'document_id': 'chapter-01', 'version': 'a' * 64, 'kind': 'text',
                 'rects': [{'page': 2, 'x1': .1, 'y1': .1, 'x2': .2, 'y2': .2}]}
    command = StartTurnCommand.model_validate({
        'type': 'start_turn', 'protocol_version': '2.0', 'content': '解释这段',
        'reading_material_id': 'a' * 16, 'reading_material_revision': 1,
        'reading_viewport': {'locator': 2, 'document_id': 'chapter-01', 'chapter_id': 1,
                             'selection': '文字', 'legacy_reader_selection': selection},
    })
    assert command.to_payload()['reading_viewport']['legacy_reader_selection'] == selection
