"""AI测试题只能显式加载，来源不能伪装，未审核题不得正式评分。"""
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from knowledge.ai_practice_test import LABEL, load_catalog

FIXTURE = Path(__file__).parent/'fixtures/ai_practice_sample.json'
COURSE = 'experimental-psychology-3'


class AIPracticeTests(unittest.TestCase):
    def test_generated_sample_is_labelled_and_versioned(self):
        data=load_catalog(FIXTURE,COURSE)
        self.assertEqual(len(data['questions']),3)
        self.assertEqual(len(data['version']),64)
        self.assertTrue(all(q['origin_label']==LABEL for q in data['questions']))
        self.assertTrue(all('AI生成' in q['text'] for q in data['questions']))

    def test_bad_origin_review_course_and_duplicate_identity_are_rejected(self):
        original=json.loads(FIXTURE.read_text(encoding='utf8'))
        changes=[lambda d:d.update(origin='textbook'),lambda d:d.update(test_only=False),
                 lambda d:d.update(review_status='approved'),lambda d:d.update(course_id='other'),
                 lambda d:d['questions'][0].update(origin='textbook'),
                 lambda d:d['questions'][0].update(source_version='changed'),
                 lambda d:d['questions'].append(copy.deepcopy(d['questions'][0]))]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fixture.json'
            for change in changes:
                data=copy.deepcopy(original);change(data);path.write_text(json.dumps(data),encoding='utf8')
                with self.subTest(change=changes.index(change)), self.assertRaises(ValueError):
                    load_catalog(path,COURSE)

    def test_default_catalog_stays_empty_and_opt_in_has_only_test_items(self):
        import practice_api as api
        try:
            with patch.dict('os.environ',{},clear=False):
                import os
                with patch.dict(os.environ,AI_PRACTICE_TEST_CATALOG=''):
                    api.catalog.cache_clear();self.assertEqual(api.catalog()['questions'],[])
                with patch.dict(os.environ,AI_PRACTICE_TEST_CATALOG=str(FIXTURE)):
                    api.catalog.cache_clear();self.assertEqual(len(api.catalog()['questions']),3)
        finally:api.catalog.cache_clear()

    def test_test_submit_cannot_schedule_grading(self):
        import practice_api as api
        from fastapi import BackgroundTasks,HTTPException
        tasks=BackgroundTasks()
        body=api.SubmitRequest(student_id='isolated',version='0'*64,answers={'p1':{'text':'答复'}},request_id='test-only-123')
        with patch.object(api,'question',return_value={'origin':'ai_generated'}),self.assertRaises(HTTPException) as result:
            api.submit('ai-test-01-001',body,tasks)
        self.assertEqual(result.exception.status_code,409)
        self.assertEqual(tasks.tasks,[])

    def test_basis_selection_not_generated_text_drives_pdf_lookup(self):
        import practice_api as api
        q=load_catalog(FIXTURE,COURSE)['questions'][0]
        with patch.object(api,'resolve_selection',return_value={'context':'真实原文'}) as resolve:
            self.assertEqual(api.exercise_context(q)['context'],'真实原文')
        self.assertEqual(resolve.call_args.args[0].document_id,q['source']['document_id'])
        self.assertNotIn('AI生成',resolve.call_args.args[0].text)

    def test_invalid_citations_reject_hint_and_explanation_even_after_quality_passes(self):
        import practice_api as api
        from agents.quality_checker import QualityResult
        from knowledge.grounded_citations import EvidenceBundle
        q=load_catalog(FIXTURE,COURSE)['questions'][0]
        tutor=SimpleNamespace(llm=Mock(),quality_checker=Mock(),memory=Mock())
        tutor.quality_checker.check.return_value=QualityResult(passed=True)
        resolved={'context':'教材原文','images':[],'reference':{'image_refs':[]}}
        for action in ['hint','explain']:
            for reply in ['没有引用编号的解释','越界引用[99]']:
                tutor.llm.chat.return_value=reply
                bundle=EvidenceBundle(sources=[],evidence=[],backgrounds=[])
                with self.subTest(action=action,reply=reply), patch.dict(sys.modules,{'main':SimpleNamespace(orchestrator=tutor)}), \
                     patch('knowledge.course_config.PSYCHOLOGY',True), patch('knowledge.grounded_citations.settings',return_value='fixture'), \
                     patch('knowledge.grounded_citations.selection_evidence',return_value=bundle), \
                     patch.object(api,'exercise_context',return_value=resolved), patch.object(api,'memory_for',return_value={'summary':''}):
                    result=api.ai_parts(q,[q['parts'][0]],{},'isolated',action)
                self.assertEqual(result['answer_status'],'quality_rejected')
                self.assertEqual(result['reason'],'citation_grounding_failed')
                self.assertFalse(result['quality']['passed'])
                self.assertFalse(result['step_advanced'])
                self.assertEqual(result['pdf_references'],[])
                self.assertNotIn(reply,result['reply'])

    def test_stale_citation_is_rejected_but_unexpected_failures_are_not_hidden(self):
        import practice_api as api
        from agents.quality_checker import QualityResult
        from knowledge.grounded_citations import CitationGroundingError
        q=load_catalog(FIXTURE,COURSE)['questions'][0]
        tutor=SimpleNamespace(llm=Mock(),quality_checker=Mock(),memory=Mock())
        tutor.llm.chat.return_value='解释[1]'
        tutor.quality_checker.check.return_value=QualityResult(passed=True)
        bundle=SimpleNamespace(sources=[],evidence=[],references=Mock())
        with patch.dict(sys.modules,{'main':SimpleNamespace(orchestrator=tutor)}), \
             patch('knowledge.course_config.PSYCHOLOGY',True), patch('knowledge.grounded_citations.settings',return_value='fixture'), \
             patch('knowledge.grounded_citations.selection_evidence',return_value=bundle), \
             patch.object(api,'exercise_context',return_value={'context':'原文','images':[],'reference':{'image_refs':[]}}), \
             patch.object(api,'memory_for',return_value={'summary':''}):
            bundle.references.side_effect=CitationGroundingError('引用教材版本已失效')
            self.assertEqual(api.ai_parts(q,[q['parts'][0]],{},'isolated','hint')['answer_status'],'quality_rejected')
            failure=RuntimeError('unexpected storage failure')
            bundle.references.side_effect=failure
            with self.assertRaises(RuntimeError) as raised:
                api.ai_parts(q,[q['parts'][0]],{},'isolated','hint')
            self.assertIs(raised.exception,failure)


if __name__=='__main__':unittest.main()
