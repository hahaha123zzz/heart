"""AI测试题只能显式加载，来源不能伪装，未审核题不得正式评分。"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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


if __name__=='__main__':unittest.main()
