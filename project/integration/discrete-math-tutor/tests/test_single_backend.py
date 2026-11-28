"""单进程后端：宿主优先，浏览器用的原生面（/ws、/api/auth 等）留给 worker。"""
from pathlib import Path

from fastapi import FastAPI

from integrations.deeptutor.single_backend import SingleBackend

WORKER_FIRST = ('/api/auth', '/api/sessions', '/api/models', '/api/settings', '/api/agents',
                '/api/personas', '/api/knowledge-bases', '/api/notebooks', '/api/memories',
                '/api/skills', '/api/tools', '/api/mcp', '/api/history', '/api/attachments',
                '/api/upload', '/api/users', '/api/workspaces', '/api/books', '/api/files',
                '/api/version', '/api/health', '/ws')


def test_single_backend_dispatch_prefers_host_but_keeps_worker_surfaces():
    host = FastAPI()

    @host.get('/health')
    def health():
        return {}

    @host.get('/api/practice/chapters/{chapter_id}')
    def practice(chapter_id: int):
        return {}

    @host.get('/api/figures/{figure_id}/image')
    def figure(figure_id: str):
        return {}

    worker = FastAPI()

    @worker.get('/api/sessions')
    def sessions():
        return {}

    @worker.get('/api/auth/login')
    def login():
        return {}

    app = SingleBackend(host, home=Path('.'), port=1)
    app.worker = worker

    assert app._target({'type': 'http', 'method': 'GET', 'path': '/health'}) is host
    assert app._target({'type': 'http', 'method': 'GET', 'path': '/api/practice/chapters/3'}) is host
    assert app._target({'type': 'http', 'method': 'GET', 'path': '/api/figures/a/image'}) is host
    assert app._target({'type': 'http', 'method': 'GET', 'path': '/api/sessions'}) is worker
    assert app._target({'type': 'http', 'method': 'GET', 'path': '/api/auth/login'}) is worker
    assert app._target({'type': 'http', 'method': 'GET', 'path': '/api/chat'}) is host
    assert app._target({'type': 'websocket', 'path': '/ws'}) is worker
    assert app._target({'type': 'http', 'method': 'GET', 'path': '/api/unknown'}) is worker


def test_single_backend_falls_back_to_host_before_worker_is_built():
    host = FastAPI()
    app = SingleBackend(host, home=Path('.'), port=1)
    assert app._target({'type': 'http', 'method': 'GET', 'path': '/api/sessions'}) is host


def test_single_backend_warms_lightrag_and_rerank_before_ready(monkeypatch):
    import asyncio

    calls = []

    class Backend:
        async def search(self, *args, **kwargs):
            calls.append(('search', kwargs.get('course_id')))

    class Fixed:
        backend = Backend()

    monkeypatch.setattr('knowledge.fixed_book.active', lambda: Fixed())
    monkeypatch.setattr(
        'knowledge.local_rag.rerank.warm_rerank_api', lambda: calls.append(('rerank', None)))

    app = SingleBackend(FastAPI(), home=Path('.'), port=1)
    asyncio.run(app._warm_course_retrieval())

    assert calls[0] == ('search', 'experimental-psychology-3')
    assert calls[1] == ('rerank', None)


def test_single_backend_warmup_failures_do_not_block_startup(monkeypatch):
    import asyncio

    class Backend:
        async def search(self, *args, **kwargs):
            raise OSError('retrieval down')

    class Fixed:
        backend = Backend()

    def fail():
        raise OSError('api down')

    monkeypatch.setattr('knowledge.fixed_book.active', lambda: Fixed())
    monkeypatch.setattr('knowledge.local_rag.rerank.warm_rerank_api', fail)

    app = SingleBackend(FastAPI(), home=Path('.'), port=1)
    asyncio.run(app._warm_course_retrieval())
