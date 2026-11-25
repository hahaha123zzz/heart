"""第一问采样：事件分类只留类型/阶段/数量，派生首个检索、正文、来源与 done。"""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.sample_startup_first_answer import marks, password_from, run_turn


class FakeWebSocket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.sent = []

    async def send(self, payload):
        self.sent.append(json.loads(payload))

    async def recv(self):
        return json.dumps(self.messages.pop(0), ensure_ascii=False)


class FirstAnswerSampleTests(unittest.IsolatedAsyncioTestCase):
    def test_marks_drop_text_but_keep_counts_and_tool_identity(self):
        self.assertEqual(marks({'type': 'content', 'content': '教材正文'}), {
            'kind': 'content', 'event_stage': '', 'event_source': '', 'chars': 4})
        self.assertEqual(marks({'type': 'tool_call', 'stage': 'retrieval',
                                'metadata': {'name': 'rag', 'query': '原文'}}), {
            'kind': 'tool_call', 'event_stage': 'retrieval', 'event_source': '', 'tool': 'rag'})
        self.assertEqual(marks({'type': 'sources', 'metadata': {'sources': [1, 2]}})['source_count'], 2)

    def test_password_reads_the_last_line_for_the_account(self):
        with TemporaryDirectory() as folder:
            creds = Path(folder) / 'accounts.txt'
            creds.write_text('heart-review-01\told\nheart-review-01\tnew\n', encoding='utf-8')
            self.assertEqual(password_from(creds, 'heart-review-01'), 'new')
            with self.assertRaises(SystemExit):
                password_from(creds, 'missing')

    async def test_turn_records_firsts_without_writing_answer_text(self):
        ws = FakeWebSocket([
            {'type': 'session', 'session_id': 'session-1'},
            {'type': 'stage_start', 'stage': 'retrieval'},
            {'type': 'tool_call', 'stage': 'retrieval', 'metadata': {'name': 'rag'}},
            {'type': 'content', 'content': '第一段正文'},
            {'type': 'sources', 'metadata': {'sources': ['a', 'b']}},
            {'type': 'content', 'content': '第二段正文'},
            {'type': 'done'},
        ])
        recorded = []
        found = await run_turn(ws, lambda stage, **fields: recorded.append({'stage': stage, **fields}),
                               '自变量是什么')
        self.assertEqual(ws.sent, [{'type': 'start_turn', 'protocol_version': '2.0',
                                    'client_submission_id': 'first-1', 'content': '自变量是什么'}])
        self.assertEqual(found['session_id'], 'session-1')
        stages = {item['stage'] for item in recorded}
        self.assertTrue({'sample.first_event', 'sample.first_tool_call', 'sample.first_text',
                         'sample.first_sources', 'sample.done'} <= stages)
        tool = next(item for item in recorded if item['stage'] == 'sample.first_tool_call')
        self.assertEqual(tool['tool'], 'rag')
        text = next(item for item in recorded if item['stage'] == 'sample.first_text')
        self.assertEqual(text['chars'], 5)
        self.assertNotIn('第一段正文', json.dumps(recorded, ensure_ascii=False))


if __name__ == '__main__':
    unittest.main()
