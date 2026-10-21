"""引用点击只复核旧版本；测试完全使用独立 PDF。"""
from unittest.mock import patch
import unittest
from fastapi import HTTPException
from tests.test_grounded_citations import GroundingTests
from web_api import citation_state, CitationStateRequest


class CitationStateTests(unittest.TestCase):
    setUp = GroundingTests.setUp

    def test_history_batches_validation_without_merging_message_numbering(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from web_api import conversation_history
        repo=Mock();refs=[{'source_index':0,'label':'第一条'},{'source_index':0,'label':'另一消息的第一条'}]
        repo.get_conversation_with_figures.return_value=[{'id':i,'role':'assistant','content':'[1]',
            'selection_ref':{'pdf_references':[ref]},'image_ref_ids':[]} for i,ref in enumerate(refs)]
        with patch.dict('sys.modules',{'main':SimpleNamespace(orchestrator=SimpleNamespace(memory=SimpleNamespace(repo=repo)))}), \
             patch('web_api._student_id'),patch('knowledge.grounded_citations.references_for_display',side_effect=lambda items:items) as validate:
            rows=conversation_history('isolated')
        validate.assert_called_once_with(refs)
        self.assertEqual([row['pdf_references'] for row in rows],[[refs[0]],[refs[1]]])

    def test_history_preserves_bound_media_without_looking_up_new_editions(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from web_api import conversation_history
        image={'id':'image-05-0004','image_url':'/api/figures/image-05-0004/image?sha256=old',
               'version':'old','model_saw_pixels':True,'visual_quality_checked':True}
        repo=Mock();repo.get_conversation_with_figures.return_value=[
            {'id':1,'role':'assistant','content':'原回答','image_ref_ids':[image['id']],
             'selection_ref':{'image_refs':[image]}},
            {'id':2,'role':'assistant','content':'旧回答','image_ref_ids':[image['id']]}]
        with patch.dict('sys.modules',{'main':SimpleNamespace(orchestrator=SimpleNamespace(memory=SimpleNamespace(repo=repo)))}), \
             patch('web_api._student_id'), patch('web_api.get_figure') as lookup:
            rows=conversation_history('isolated')
        self.assertEqual(rows[0]['image_refs'],[image]);lookup.assert_not_called()
        self.assertNotIn('image_url',rows[1]['image_refs'][0])

    def test_current_and_changed_bytes_without_upgrading_reference(self):
        reference = {'selection_ref': {'document_id': self.record['document_id'], 'version': self.record['version']}}
        with patch('knowledge.pdf_reader.document', return_value=self.record):
            self.assertFalse(citation_state(CitationStateRequest(reference=reference))['stale'])
            self.pdf.write_bytes(self.pdf.read_bytes() + b'changed')
            self.assertTrue(citation_state(CitationStateRequest(reference=reference))['stale'])
        self.assertNotIn('evidence', reference)

    def test_incomplete_or_unknown_record_never_opens_another_source(self):
        with patch('knowledge.pdf_reader.document', return_value=None):
            self.assertTrue(citation_state(CitationStateRequest(reference={}))['stale'])
        with self.assertRaises(HTTPException):
            citation_state(CitationStateRequest(reference={'evidence': {'document_id': 'incomplete'}}))
