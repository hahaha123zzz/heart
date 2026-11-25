"""启动分段记录：同 startup_id、父阶段、序号、耗时、状态与已有计数。"""
import asyncio
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from knowledge import startup_trace


def rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines()]


class StartupTraceTests(unittest.TestCase):
    def setUp(self):
        startup_trace.reset()

    tearDown = setUp

    def test_record_has_identity_sequence_parent_and_existing_counts(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'host-1.jsonl'
            trace = startup_trace.Trace('host', path=path, sid='startup-a')
            trace.record('fixed_book.entry', parent='fixed_book', seconds=0, files=0)
            trace.record('fixed_book.hashes', parent='fixed_book', seconds=1.25, files=372)
            first, second = rows(path)
            self.assertEqual(first['startup_id'], 'startup-a')
            self.assertEqual(first['service'], 'host')
            self.assertEqual(first['pid'], os.getpid())
            self.assertEqual([first['seq'], second['seq']], [1, 2])
            self.assertEqual(first['stage'], 'fixed_book.entry')
            self.assertEqual(first['parent'], 'fixed_book')
            self.assertEqual(second['seconds'], 1.25)
            self.assertEqual(second['fields'], {'files': 372})
            self.assertTrue(first['at'].endswith(('Z', '+00:00')) or '+' in first['at'] or '-' in first['at'][10:])

    def test_timed_records_ok_and_merges_detail_counts(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'host.jsonl'
            trace = startup_trace.Trace('host', path=path, sid='startup-b')
            with trace.timed('lightrag.source_map', parent='fixed_book', purpose='source_map') as detail:
                detail['chapters'] = 11
            row, = rows(path)
            self.assertEqual(row['status'], 'ok')
            self.assertGreaterEqual(row['seconds'], 0)
            self.assertEqual(row['fields'], {'purpose': 'source_map', 'chapters': 11})

    def test_nested_stage_points_at_parent_stage_name(self):
        with TemporaryDirectory() as folder:
            trace = startup_trace.Trace('host', path=Path(folder) / 'host.jsonl', sid='startup-c')
            with trace.timed('fixed_book', parent=None):
                with trace.timed('fixed_book.hashes', parent='fixed_book'):
                    pass
            by_stage = {row['stage']: row for row in rows(Path(folder) / 'host.jsonl')}
            self.assertEqual(by_stage['fixed_book.hashes']['parent'], by_stage['fixed_book']['stage'])
            self.assertIsNone(by_stage['fixed_book']['parent'])

    def test_failure_keeps_traversed_stage_and_does_not_report_zero(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'host.jsonl'
            trace = startup_trace.Trace('host', path=path, sid='startup-d')
            with self.assertRaisesRegex(RuntimeError, 'fixture'):
                with trace.timed('fixed_book.release', parent='fixed_book'):
                    raise RuntimeError('fixture')
            row, = rows(path)
            self.assertEqual(row['status'], 'failed')
            self.assertEqual(row['fields'], {'error': 'RuntimeError'})
            self.assertGreaterEqual(row['seconds'], 0)

    def test_cancelled_stage_is_marked_separately(self):
        with TemporaryDirectory() as folder:
            trace = startup_trace.Trace('host', path=Path(folder) / 'host.jsonl', sid='startup-e')
            with self.assertRaises(asyncio.CancelledError):
                with trace.timed('fixed_book.resident', parent='fixed_book'):
                    raise asyncio.CancelledError
            row, = rows(Path(folder) / 'host.jsonl')
            self.assertEqual(row['status'], 'cancelled')

    def test_current_reuses_one_recorder_from_environment(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ, {
                'STARTUP_ID': 'startup-f', 'STARTUP_SERVICE': 'worker',
                'STARTUP_TRACE_DIR': folder}):
            startup_trace.reset()
            trace = startup_trace.current()
            trace.record('worker.entry', parent='worker', seconds=0)
            self.assertIs(startup_trace.current(), trace)
            self.assertEqual(trace.startup_id, 'startup-f')
            self.assertEqual(trace.service, 'worker')
            written, = list(Path(folder).glob('worker-*.jsonl'))
            self.assertEqual(rows(written)[0]['stage'], 'worker.entry')

    def test_write_failure_is_swallowed_so_startup_never_depends_on_telemetry(self):
        with TemporaryDirectory() as folder:
            target = Path(folder) / 'not-a-directory'
            target.write_text('x', encoding='utf-8')
            trace = startup_trace.Trace('host', path=target / 'host.jsonl', sid='startup-h')
            with self.assertLogs('knowledge.startup_trace', level='WARNING'):
                row = trace.record('fixed_book.entry', parent='fixed_book', seconds=0)
            self.assertEqual(row['stage'], 'fixed_book.entry')

    def test_trace_is_silent_on_disk_when_no_directory_is_configured(self):
        with patch.dict(os.environ, {'STARTUP_ID': 'startup-g'}, clear=False):
            os.environ.pop('STARTUP_TRACE_DIR', None)
            startup_trace.reset()
            trace = startup_trace.current()
            self.assertIsNone(trace.path)
            trace.record('host.entry', parent='host', seconds=0)


if __name__ == '__main__':
    unittest.main()
