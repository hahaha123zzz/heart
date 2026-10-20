"""引用点击只复核旧版本；测试完全使用独立 PDF。"""
from unittest.mock import patch
import unittest
from fastapi import HTTPException
from tests.test_grounded_citations import GroundingTests
from web_api import citation_state, CitationStateRequest


class CitationStateTests(unittest.TestCase):
    setUp = GroundingTests.setUp

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
