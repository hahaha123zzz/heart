"""第一问采样：事件分类只留类型/阶段/数量，派生首个检索、正文、来源与 done。"""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from scripts.sample_startup_first_answer import (
    TurnRejected, await_acceptable, marks, password_from, run_second_turn, run_turn,
)


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

    def test_marks_keep_token_counts_from_the_final_summary(self):
        self.assertEqual(marks({'type': 'done', 'metadata': {'cost_summary': {
            'prompt_tokens': 120, 'completion_tokens': 30}}}), {
            'kind': 'done', 'event_stage': '', 'event_source': '',
            'prompt_tokens': 120, 'completion_tokens': 30})
        self.assertEqual(marks({'type': 'done', 'metadata': {'usage_summary': {
            'prompt_tokens': 7, 'completion_tokens': 3}}})['completion_tokens'], 3)

    def test_marks_drop_oversized_stage_and_source(self):
        long = 'x' * 81
        row = marks({'type': 'progress', 'stage': long, 'source': long})
        self.assertEqual(row['event_stage'], '')
        self.assertEqual(row['event_source'], '')

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
                               '自变量是什么', submission='first-1')
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

    async def test_second_turn_sends_the_session_id(self):
        ws = FakeWebSocket([{'type': 'done'}])
        await run_turn(ws, lambda stage, **fields: None, '同一道题', 'session-9', label='second',
                       submission='second-1')
        self.assertEqual(ws.sent, [{'type': 'start_turn', 'protocol_version': '2.0',
                                    'client_submission_id': 'second-1', 'content': '同一道题',
                                    'session_id': 'session-9'}])

    async def test_omitted_submission_ids_are_unique_so_no_turn_is_replayed(self):
        first, second = FakeWebSocket([{'type': 'done'}]), FakeWebSocket([{'type': 'done'}])
        await run_turn(first, lambda stage, **fields: None, '同一道题')
        await run_turn(second, lambda stage, **fields: None, '同一道题')
        self.assertNotEqual(first.sent[0]['client_submission_id'],
                            second.sent[0]['client_submission_id'])

    async def test_turn_records_usage_counts_and_protocol_error_code(self):
        ws = FakeWebSocket([
            {'type': 'tool_call', 'metadata': {'name': 'rag'}},
            {'type': 'content', 'content': '第一段'},
            {'type': 'sources', 'metadata': {'sources': ['a', 'b', 'c']}},
            {'type': 'tool_call', 'metadata': {'name': 'read'}},
            {'type': 'done', 'metadata': {'cost_summary': {'prompt_tokens': 50, 'completion_tokens': 9}}},
        ])
        recorded = []
        found = await run_turn(ws, lambda stage, **fields: recorded.append({'stage': stage, **fields}),
                               '题', submission='run-1')
        self.assertEqual((found['tool_calls'], found['sources'], found['prompt_tokens'],
                          found['completion_tokens']), (2, 3, 50, 9))
        usage = next(item for item in recorded if item['stage'] == 'sample.usage')
        self.assertEqual((usage['tool_calls'], usage['sources']), (2, 3))

        failing = FakeWebSocket([{'type': 'protocol_error', 'error_code': 'turn_rejected'}])
        recorded = []
        with self.assertRaises(TurnRejected):
            await run_turn(failing, lambda stage, **fields: recorded.append({'stage': stage, **fields}),
                           '题', submission='run-2')
        self.assertEqual(recorded[-1]['error_code'], 'turn_rejected')

    async def test_second_turn_retries_a_rejected_lease_until_accepted(self):
        ws = FakeWebSocket([
            {'type': 'protocol_error', 'error_code': 'start_turn_rejected'},
            {'type': 'done'},
        ])
        recorded = []
        await run_second_turn(ws, lambda stage, **fields: recorded.append({'stage': stage, **fields}),
                              '同一道题', 'session-1', 'run-1', done_at=time.perf_counter())
        self.assertEqual(len([row for row in recorded if row['stage'] == 'sample.second_retry']), 1)
        self.assertEqual([row for row in recorded if row['stage'] == 'sample.second_accepted'][-1]['attempts'], 2)
        self.assertEqual(len([sent for sent in ws.sent if sent['type'] == 'start_turn']), 2)

    async def test_acceptable_is_measured_from_done_until_no_active_turn(self):
        ws = FakeWebSocket([{'type': 'active_turn_info', 'status': 'none'}])
        recorded = []
        waited = await await_acceptable(ws, 'session-1',
                                        lambda stage, **fields: recorded.append({'stage': stage, **fields}),
                                        since=0.0)
        self.assertEqual(ws.sent, [{'type': 'check_active_turn', 'protocol_version': '2.0',
                                    'session_id': 'session-1'}])
        self.assertGreaterEqual(waited, 0)
        self.assertEqual(recorded[-1]['stage'], 'sample.acceptable')

    async def test_acceptable_records_a_protocol_error_instead_of_blocking(self):
        ws = FakeWebSocket([{'type': 'protocol_error', 'error_code': 'invalid_command'}])
        recorded = []
        await await_acceptable(ws, 'session-1',
                               lambda stage, **fields: recorded.append({'stage': stage, **fields}))
        self.assertEqual(recorded[-1]['status'], 'protocol_error:invalid_command')


if __name__ == '__main__':
    unittest.main()
