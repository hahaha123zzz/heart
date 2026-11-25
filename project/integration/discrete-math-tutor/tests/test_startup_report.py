"""分段报告：自身耗时、总量排除、对账、就绪到首问差值、重复目录遍历。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from deploy.startup_report import duplicates, load, reconciliation, render, summaries, timeline


def write(directory, sid, rows):
    path = Path(directory) / sid / (sid + '.jsonl')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(json.dumps(row, ensure_ascii=False) for row in rows) + '\n', encoding='utf-8')


def row(sid, service, stage, seconds, parent=None, status='ok', at='2026-11-25T10:00:00+08:00', **fields):
    return {'startup_id': sid, 'service': service, 'pid': 1, 'seq': 1, 'stage': stage,
            'parent': parent, 'seconds': seconds, 'status': status, 'at': at, 'fields': fields}


class StartupReportTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        write(self.folder.name, 's1', [
            row('s1', 'control', 'control.begin', 0, cache_state='process-cold'),
            row('s1', 'control', 'control.done', 100),
            row('s1', 'control', 'control.ready', 5, target='host', elapsed_since_origin=40),
            row('s1', 'probe', 'probe.first_ok', 38, target='host'),
            row('s1', 'host', 'host.health.first_ok', 95, at='2026-11-25T10:00:00+08:00'),
            row('s1', 'host', 'fixed_book.start.complete', 90),
            row('s1', 'host', 'fixed_book.ready_flag', 80),
            row('s1', 'host', 'lightrag.manifest', 10, parent='fixed_book'),
            row('s1', 'host', 'lightrag.manifest.host_textbook', 8, parent='lightrag.manifest', files=409),
            row('s1', 'host', 'fixed_book.hashes', 7, parent='fixed_book', files=409),
            row('s1', 'sample', 'sample.turn', 30, turn='first', at='2026-11-25T10:00:30+08:00'),
            row('s1', 'sample', 'sample.turn', 20, turn='second', at='2026-11-25T10:00:50+08:00'),
        ])
        write(self.folder.name, 's2', [
            row('s2', 'control', 'control.begin', 0, cache_state='os-warm'),
            row('s2', 'control', 'control.done', 120),
            row('s2', 'host', 'fixed_book.start.complete', 110),
            row('s2', 'host', 'lightrag.manifest', 12, parent='fixed_book'),
            row('s2', 'host', 'lightrag.manifest.host_textbook', 10, parent='lightrag.manifest', files=409),
            row('s2', 'host', 'fixed_book.hashes', 9, parent='fixed_book', files=409),
        ])

    def test_summaries_use_per_startup_self_time_and_median(self):
        summary, baseline = summaries(load(self.folder.name))
        self.assertEqual(baseline, 100)
        by_stage = {row['stage']: row for row in summary}
        self.assertEqual(by_stage['fixed_book.hashes']['median'], 8)
        self.assertEqual(by_stage['fixed_book.hashes']['minimum'], 7)
        self.assertEqual(by_stage['fixed_book.hashes']['maximum'], 9)
        self.assertAlmostEqual(by_stage['fixed_book.hashes']['share'], 0.08)
        self.assertEqual(by_stage['fixed_book.hashes']['calls'], 2)
        self.assertEqual(by_stage['fixed_book.hashes']['startups'], 2)
        self.assertEqual(by_stage['lightrag.manifest']['median'], 2)  # 10/12 − 子阶段 8/10

    def test_totals_and_milestones_are_not_ranked_as_stages(self):
        summary, _ = summaries(load(self.folder.name))
        stages = {row['stage'] for row in summary}
        for marker in ('fixed_book.start.complete', 'fixed_book.ready_flag', 'control.done',
                       'host.health.first_ok', 'sample.turn'):
            self.assertNotIn(marker, stages)
        self.assertEqual(summary[0]['stage'], 'lightrag.manifest.host_textbook')

    def test_failed_startup_stages_do_not_shift_the_stage_table(self):
        rows = load(self.folder.name)
        rows += [row('s3', 'control', 'control.begin', 0, status='failed'),
                 row('s3', 'host', 'fixed_book.hashes', 99, status='ok', files=409),
                 row('s3', 'host', 'fixed_book.start.failed', 5, status='failed')]
        summary, baseline = summaries(rows)
        hashes = next(row for row in summary if row['stage'] == 'fixed_book.hashes')
        self.assertEqual(hashes['maximum'], 9)
        self.assertEqual(baseline, 100)

    def test_reconciliation_compares_top_level_stages_with_total(self):
        found = {row['startup_id']: row for row in reconciliation(load(self.folder.name))}
        self.assertEqual(found['s1']['total'], 90)
        self.assertEqual(found['s1']['stages'], 17)
        self.assertEqual(found['s1']['residual'], 73)

    def test_timeline_reports_readiness_to_first_answer_gap(self):
        found = {row['startup_id']: row for row in timeline(load(self.folder.name))}
        self.assertEqual(found['s1']['ready_gap'], 30)
        self.assertEqual(found['s1']['ready']['host'], 40)
        self.assertEqual(found['s1']['probed']['host'], 38)
        self.assertEqual(found['s1']['first_answer'], 30)

    def test_duplicates_only_merge_when_file_scope_matches(self):
        found = duplicates(load(self.folder.name))
        self.assertEqual([row['startup_id'] for row in found], ['s1', 's2'])
        self.assertEqual(found[0]['mergeable'], 7)
        self.assertEqual(found[0]['verify_files'], 409)
        rows = load(self.folder.name)
        rows = [dict(row, fields=dict(row['fields'], files=1)) if row['stage'] == 'fixed_book.hashes'
                and row['startup_id'] == 's1' else row for row in rows]
        found = duplicates(rows)
        self.assertIsNone(next(row for row in found if row['startup_id'] == 's1')['mergeable'])

    def test_render_lists_timeline_ranges_gap_and_reconciliation(self):
        report = render(load(self.folder.name))
        self.assertIn('样本数：2（成功就绪 2）', report)
        self.assertIn('就绪→首问', report)
        self.assertIn('7.00–9.00', report)
        self.assertIn('| s1 | process-cold |', report)
        self.assertIn('| s1 | 90.00 | 17.00 | 73.00 |', report)

    def test_single_sample_prints_measured_value(self):
        rows = [row for row in load(self.folder.name) if row['startup_id'] == 's1']
        report = render(rows)
        self.assertIn('实测自身耗时', report)
        self.assertIn('| host | fixed_book.hashes | fixed_book | 1 | 7.00 | 7.8% |', report)

    def test_load_skips_partial_jsonl_lines(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 's1' / 'host.jsonl'
            path.parent.mkdir(parents=True)
            path.write_text('{"stage": "ok"}\n{"broken":\n', encoding='utf-8')
            self.assertEqual(load(folder), [{'stage': 'ok'}])


if __name__ == '__main__':
    unittest.main()
