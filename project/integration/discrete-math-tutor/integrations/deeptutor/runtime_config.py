"""原生执行开关与宿主拥有的独立 worker 生命周期。"""
import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import secrets
import subprocess
import time
from urllib.parse import urlsplit


def native_enabled():
    return os.getenv("DEEPTUTOR_NATIVE_ENABLED", "1").strip() == "1"


@asynccontextmanager
async def native_lifespan(app):
    process = None
    log = None
    app.state.native_runtime = {"enabled": native_enabled(), "managed": False, "ready": False}
    try:
        if native_enabled():
            from .client import DeepTutorBackend
            backend = DeepTutorBackend()
            if os.getenv("DEEPTUTOR_AUTOSTART", "1") == "1":
                root = Path(__file__).resolve().parents[2]
                python = Path(os.getenv("DEEPTUTOR_PYTHON", str(root / ".venv-deeptutor" /
                              ("Scripts/python.exe" if os.name == "nt" else "bin/python"))))
                if not python.is_file():
                    raise RuntimeError("原生环境不存在，请运行 scripts/setup_deeptutor.py")
                if not backend.status()["connected"]:
                    if not os.getenv("DEEPTUTOR_BRIDGE_TOKEN"):
                        os.environ["DEEPTUTOR_BRIDGE_TOKEN"] = secrets.token_hex(32)
                    if len(os.environ["DEEPTUTOR_BRIDGE_TOKEN"]) < 32:
                        raise RuntimeError("DEEPTUTOR_BRIDGE_TOKEN 至少需要 32 个字符")
                    home = Path(os.getenv("DEEPTUTOR_HOME", str(root / ".runtime/deeptutor"))).resolve()
                    home.mkdir(parents=True, exist_ok=True)
                    log = (home / "worker.log").open("ab")
                    process = subprocess.Popen([str(python), "-X", "utf8", "-B",
                        str(root / "integrations/deeptutor/worker.py"), "--port",
                        str(urlsplit(backend.base_url).port), "--home", str(home)], cwd=root,
                        env=dict(os.environ), stdout=log, stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                    app.state.native_runtime["managed"] = True
            deadline = time.monotonic() + 60
            while True:
                status = await asyncio.to_thread(backend.status)
                if status["backend_ready"]:
                    app.state.native_runtime["ready"] = True
                    break
                if process is not None and process.poll() is not None:
                    raise RuntimeError("原生 worker 启动失败，请检查 worker.log")
                if time.monotonic() >= deadline:
                    raise RuntimeError("原生 worker 在 60 秒内未就绪")
                await asyncio.sleep(.25)
        yield
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait)
        if log is not None:
            log.close()


@asynccontextmanager
async def application_lifespan(app):
    from memory.background_worker import memory_lifespan
    async with native_lifespan(app), memory_lifespan(app):
        yield
