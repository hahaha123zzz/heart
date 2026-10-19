"""独立后端仅允许宿主凭据访问数据接口，包括 WebSocket。"""
import hmac
import os

from starlette.responses import JSONResponse


class HostBridgeBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            public = scope.get("path") in {"/health", "/health/live", "/health/ready", "/api/capabilities/registered"}
            expected = os.getenv("DEEPTUTOR_BRIDGE_TOKEN", "")
            provided = dict(scope.get("headers", [])).get(b"x-heart-bridge-token", b"")
            allowed = len(expected) >= 32 and hmac.compare_digest(provided, expected.encode())
            if not public and not allowed:
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    await JSONResponse({"detail": "仅允许宿主服务访问"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)
