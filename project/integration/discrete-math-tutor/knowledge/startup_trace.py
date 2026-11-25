"""启动分段计时：同 startup_id 写 JSONL，只记阶段、耗时与已有计数。

不记录教材原文、个人数据或密钥。进程内用单调时钟算耗时，事件时间按本机时区。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import threading
import time

LOG = logging.getLogger(__name__)
_recorder = None


def startup_id():
    return os.getenv('STARTUP_ID') or 'pid-%d' % os.getpid()


class Trace:
    def __init__(self, service='host', *, path=None, sid=None):
        self.service = service
        self.startup_id = sid or startup_id()
        self.path = Path(path) if path else None
        self.seq = 0
        self.lock = threading.Lock()

    def record(self, stage, *, parent=None, seconds=0.0, status='ok', **fields):
        with self.lock:
            self.seq += 1
            row = {'startup_id': self.startup_id, 'service': self.service,
                   'pid': os.getpid(), 'seq': self.seq, 'stage': stage,
                   'parent': parent, 'seconds': round(float(seconds), 4),
                   'status': status,
                   'at': datetime.now().astimezone().isoformat(timespec='milliseconds'),
                   'fields': fields}
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
            LOG.info('startup_trace %s', json.dumps(row, ensure_ascii=False, sort_keys=True))
            return row

    @contextmanager
    def timed(self, stage, *, parent=None, **fields):
        """yield 一个 detail 字典；退出前把其内容并入已有计数。"""
        started = time.perf_counter()
        detail = {}
        status = 'ok'
        try:
            yield detail
        except asyncio.CancelledError:
            status = 'cancelled'
            detail.setdefault('error', 'CancelledError')
            raise
        except BaseException as exc:
            status = 'failed'
            detail.setdefault('error', type(exc).__name__)
            raise
        finally:
            self.record(stage, parent=parent, seconds=time.perf_counter() - started,
                        status=status, **fields, **detail)


def current():
    global _recorder
    if _recorder is None:
        service = os.getenv('STARTUP_SERVICE') or 'host'
        directory = os.getenv('STARTUP_TRACE_DIR')
        path = Path(directory) / ('%s-%d.jsonl' % (service, os.getpid())) if directory else None
        _recorder = Trace(service, path=path)
    return _recorder


def reset():
    global _recorder
    _recorder = None
