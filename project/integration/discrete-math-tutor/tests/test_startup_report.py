"""分段报告：多样本中位数/范围、控制与探测对照、重复目录遍历。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from deploy.startup_report import duplicates, load, render, summaries


def write(directory, sid, rows):
    path = Path(directory) / sid / (sid + '.jsonl')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(json.dumps(row, ensure_ascii=False) for row in rows) + '\n', encoding='utf-8')


def row(sid, service, stage, seconds, parent=None, status='ok', **fields):
    return {'startup_id': sid, 'service': service, 'pid': 1, 'seq': 1, 'stage': stage,
            'parent': parent, 'seconds': seconds, 'status': status,
            'at': '2026-11-25T10:00:00+08:00', 'fields': fields}


class StartupReportTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        common = [
            row('s1', 'control', 'control.begin', 0, cache_state='process-cold'),
            row('s1', 'control', 'control.done', 100),
            row('s1', 'control', 'control.ready', 40, target='host'),
            row('s1', 'probe', 'probe.first_ok', 38, target='host'),
            row('s1', 'host', 'host.health.first_ok', 95),
            row('s1', 'host', 'fixed_book.start.complete', 90),
            row('s1', 'host', 'lightrag.manifest.host_textbook', 8, parent='lightrag.manifest', files=409),
            row('s1', 'host', 'fixed_book.hashes', 7, parent='fixed_book', files=409),
            row('s1', 'sample', 'sample.turn', 30, turn='first'),
            row('s1', 'sample', 'sample.turn', 20, turn='second'),
        ]
        write(self.folder.name, 's1', common)
        write(self.folder.name, 's2', [
            row('s2', 'control', 'control.begin', 0, cache_state='os-warm'),
            row('s2', 'control', 'control.done', 120),
            row('s2', 'host', 'fixed_book.start.complete', 110),
            row('s2', 'host', 'lightrag.manifest.host_textbook', 10, files=409),
            row('s2', 'host', 'fixed_book.hashes', 9, files=409),
        ])

    def test_summaries_report_median_range_and_share(self):
        rows = load(self.folder.name)
        summary, baseline = summaries(rows)
        self.assertEqual(baseline, 100)
        by_stage = {row['stage']: row for row in summary}
        self.assertEqual(by_stage['fixed_book.hashes']['median'], 8)
        self.assertEqual(by_stage['fixed_book.hashes']['minimum'], 7)
        self.assertEqual(by_stage['fixed_book.hashes']['maximum'], 9)
        self.assertAlmostEqual(by_stage['fixed_book.hashes']['share'], 0.08)
        self.assertEqual(by_stage['fixed_book.hashes']['calls'], 2)

    def test_duplicates_use_the_two_same_root_inventories(self):
        found = duplicates(load(self.folder.name))
        self.assertEqual([row['startup_id'] for row in found], ['s1', 's2'])
        self.assertEqual(found[0]['mergeable'], 7)
        self.assertEqual(found[0]['verify_files'], 409)

    def test_render_lists_timeline_and_ranges(self):
        report = render(load(self.folder.name))
        self.assertIn('样本数：2', report)
        self.assertIn('7.00', report)
        self.assertIn('7.00–9.00', report)
        self.assertIn('| s1 | process-cold |', report)
        self.assertIn('30.00', report)  # 第一问

    def test_single_sample_prints_measured_value(self):
        rows = [row for row in load(self.folder.name) if row['startup_id'] == 's1']
        report = render(rows)
        self.assertIn('实测耗时', report)
        self.assertIn('| host | fixed_book.hashes | 1 | 7.00 | 7.8% |', report)


if __name__ == '__main__':
    unittest.main()
