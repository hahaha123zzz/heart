"""适配 DeepTutor 有界客户端池；同步传输按调用借用，不共享回合状态。"""
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import atexit
import os
import threading

_pool = OrderedDict()
_lock = threading.RLock()
_borrowed = ContextVar('borrowed_transport', default=None)
_limit = 8
_stats = {'created': 0, 'hits': 0, 'closed': 0}


def _key(api_key, base_url):
    # 凭据仅在内存；代理与 TLS 环境变化必须建立新传输。
    return (api_key, base_url, tuple((key, os.environ.get(key)) for key in
        ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy',
         'all_proxy','no_proxy','SSL_CERT_FILE','SSL_CERT_DIR','OPENAI_ORG_ID','OPENAI_PROJECT_ID')))


def _close(entry):
    entry['client'].close()
    _stats['closed'] += 1


@contextmanager
def borrow(api_key, base_url):
    key = _key(api_key, base_url)
    with _lock:
        entry = _pool.get(key)
        if entry is None:
            from openai import OpenAI
            entry = {'client': OpenAI(api_key=api_key, base_url=base_url, max_retries=0),
                     'active': 0, 'retired': False}
            _pool[key] = entry
            _stats['created'] += 1
        else:
            _stats['hits'] += 1
        entry['active'] += 1
        _pool.move_to_end(key)
        while len(_pool) > _limit:
            _, old = _pool.popitem(last=False)
            old['retired'] = True
            if not old['active']:
                _close(old)
    token = _borrowed.set((key, entry['client']))
    try:
        yield entry['client']
    finally:
        _borrowed.reset(token)
        with _lock:
            entry['active'] -= 1
            if entry['retired'] and not entry['active']:
                _close(entry)


def current(api_key, base_url):
    value = _borrowed.get()
    return value[1] if value and value[0] == _key(api_key, base_url) else None


def pooled_call(method):
    @wraps(method)
    def run(self, *args, **kwargs):
        # 保留 mock/缺密钥及测试注入的原入口行为。
        if self._client is not None or self.mock or not self.api_key or current(self.api_key, self.base_url):
            return method(self, *args, **kwargs)
        with borrow(self.api_key, self.base_url):
            return method(self, *args, **kwargs)
    return run


def close_pool():
    with _lock:
        entries = list(_pool.values())
        _pool.clear()
        for entry in entries:
            entry['retired'] = True
            if not entry['active']:
                _close(entry)


def stats():
    with _lock:
        return {**_stats, 'retained': len(_pool), 'capacity': _limit}


atexit.register(close_pool)
