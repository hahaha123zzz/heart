"""控制脚本分段记录与并行探测：发行校验/进程创建/就绪与辅助采集分开。"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest

from deploy.manage_student_local import PROBES, launch, probe, recorder


class _Ok(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
    def log_message(self, *args):
        pass


def rows(directory):
    return [json.loads(line) for path in Path(directory).glob('*.jsonl')
            for line in path.read_text(encoding='utf-8').splitlines()]


class ControlTraceTests(unittest.TestCase):
    def test_recorder_uses_the_same_identity_and_sequence_shape(self):
        with TemporaryDirectory() as folder:
            record = recorder(Path(folder), 'control-a', 'control')
            record('control.begin', parent='control', seconds=0, label='cold')
            record('control.ready', parent='control.service', seconds=12.5, target='host', attempts=13)
            first, second = rows(folder)
            self.assertEqual(first['startup_id'], 'control-a')
            self.assertEqual(first['service'], 'control')
            self.assertEqual(second['fields'], {'target': 'host', 'attempts': 13})
            self.assertEqual(second['status'], 'ok')
            self.assertIn('at', second)

    def test_worker_is_ready_before_other_services_start(self):
        events = []
        launch(['worker', 'host', 'web'],
               lambda service: events.append(('spawn', service)),
               lambda service: events.append(('ready', service)))
        self.assertLess(events.index(('ready', 'worker')), events.index(('spawn', 'host')))
        self.assertLess(events.index(('ready', 'worker')), events.index(('spawn', 'web')))
        self.assertEqual([name for kind, name in events if kind == 'spawn'], ['worker', 'host', 'web'])
        self.assertEqual([name for kind, name in events if kind == 'ready'], ['worker', 'host', 'web'])

    def test_host_first_order_reproduces_the_old_control_sequence(self):
        events = []
        launch(['worker', 'host', 'web'],
               lambda service: events.append(('spawn', service)),
               lambda service: events.append(('ready', service)), host_first=True)
        self.assertEqual([name for kind, name in events if kind == 'spawn'], ['host', 'worker', 'web'])
        self.assertEqual([name for kind, name in events if kind == 'ready'], ['host', 'worker', 'web'])
        self.assertLess(events.index(('spawn', 'host')), events.index(('ready', 'worker')))

    def test_running_worker_does_not_delay_host_or_web(self):
        events = []
        launch(['host', 'web'],
               lambda service: events.append(('spawn', service)),
               lambda service: events.append(('ready', service)))
        self.assertEqual(events, [('spawn', 'host'), ('spawn', 'web'),
                                  ('ready', 'host'), ('ready', 'web')])

    def test_probe_records_first_availability_for_each_port(self):
        server = HTTPServer(('127.0.0.1', 0), _Ok)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]
        try:
            with TemporaryDirectory() as folder:
                record = recorder(Path(folder), 'control-b', 'probe')
                keeper = probe(record, {'host': port, 'worker': port, 'web': port}, time.perf_counter())
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    found = [row for row in rows(folder) if row['stage'] == 'probe.first_ok']
                    if len(found) == len(PROBES):
                        break
                    time.sleep(.05)
                keeper.set()
                found = {row['fields']['target']: row for row in rows(folder)
                         if row['stage'] == 'probe.first_ok'}
                self.assertEqual(set(found), {'host', 'worker', 'web'})
                self.assertTrue(all(row['service'] == 'probe' for row in found.values()))
                self.assertTrue(all(row['seconds'] >= 0 for row in found.values()))
        finally:
            server.shutdown()


if __name__ == '__main__':
    unittest.main()
