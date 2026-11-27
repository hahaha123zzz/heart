"""单进程后端：宿主与原生运行时共用一个 ASGI 应用、一个端口。

宿主优先：宿主自己定义的路由（教材、练习、图表、鉴权、`/internal/*`）先匹配；
没匹配到的 `/api/*` 与 `/ws` 交给 DeepTutor 原生应用。`/api/chat` 保持宿主退役响应。
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

WORKER_RETIRED = ('/api/chat', '/api/chat/stream')
# 浏览器今天走 worker 的表面：宿主即使定义了同名路由也让给原生运行时。
WORKER_FIRST = ('/api/auth', '/api/sessions', '/api/models', '/api/settings', '/api/agents',
                '/api/personas', '/api/knowledge-bases', '/api/notebooks', '/api/memories',
                '/api/skills', '/api/tools', '/api/mcp', '/api/history', '/api/attachments',
                '/api/upload', '/api/users', '/api/workspaces', '/api/books', '/api/files',
                '/api/version', '/api/health', '/ws')


def single_backend_enabled() -> bool:
    return os.getenv('HEART_SINGLE_BACKEND', '0').strip() == '1'


def _matches(app, scope) -> bool:
    from starlette.routing import Match

    for route in app.router.routes:
        try:
            match, _ = route.matches(scope)
        except Exception:  # noqa: BLE001 - 单条路由不匹配即跳过
            continue
        if match is Match.FULL:
            return True
    return False


class SingleBackend:
    """把宿主应用和原生运行时装进同一个进程，共用 uvicorn 生命周期。"""

    def __init__(self, host, *, home: Path, port: int):
        self.host = host
        self.home = home
        self.port = port
        self.worker = None

    def _target(self, scope):
        if self.worker is None:
            return self.host
        path = scope.get('path') or ''
        if path in WORKER_RETIRED:
            return self.host
        if scope['type'] == 'websocket':
            return self.worker if not _matches(self.host, scope) else self.host
        if any(path == prefix or path.startswith(prefix + '/') for prefix in WORKER_FIRST):
            return self.worker
        if _matches(self.host, scope):
            return self.host
        return self.worker

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            await self._lifespan(receive, send)
            return
        await self._target(scope)(scope, receive, send)

    async def _lifespan(self, receive, send):
        message = await receive()
        while message['type'] != 'lifespan.startup':
            message = await receive()
        try:
            async with self.host.router.lifespan_context(self.host):
                self.worker = await self._build_worker()
                async with self.worker.router.lifespan_context(self.worker):
                    self.host.state.native_runtime = {
                        'enabled': True, 'managed': True, 'ready': True, 'in_process': True}
                    await send({'type': 'lifespan.startup.complete'})
                    message = await receive()
                    while message['type'] != 'lifespan.shutdown':
                        message = await receive()
        except BaseException as exc:  # noqa: BLE001 - 启动失败要回给 uvicorn
            await send({'type': 'lifespan.startup.failed', 'message': repr(exc)})
            return
        await send({'type': 'lifespan.shutdown.complete'})

    async def _build_worker(self):
        from integrations.deeptutor import worker as worker_module
        from integrations.deeptutor import client as client_module

        app = await asyncio.to_thread(worker_module.build_app, self.home, self.port, chdir=False)
        client_module.install_inprocess(self.host)
        return app


def install(host):
    if not single_backend_enabled():
        return host
    root = Path(__file__).resolve().parents[2]
    home = Path(os.getenv('DEEPTUTOR_HOME', str(root / '.runtime/deeptutor'))).resolve()
    home.mkdir(parents=True, exist_ok=True)
    port = int(os.getenv('BACKEND_PORT') or os.getenv('HEART_HOST_PORT') or 8000)
    return SingleBackend(host, home=home, port=port)
