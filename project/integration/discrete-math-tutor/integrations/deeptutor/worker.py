"""在独立进程内启动仓库中的完整上游后端。"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys

HOST_ROOT = Path(__file__).resolve().parents[2]
VENDOR_ROOT = HOST_ROOT.parents[1] / "vendor" / "DeepTutor"
DEFAULT_HOME = HOST_ROOT / ".runtime" / "deeptutor"


def prepare(home: Path, port: int) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("端口必须在 1 到 65535 之间")
    if not (VENDOR_ROOT / "UPSTREAM_SNAPSHOT.json").is_file():
        raise ValueError("尚未迁入 DeepTutor 固定源码")
    home = home.resolve()
    if home.is_relative_to(VENDOR_ROOT.resolve()):
        raise ValueError("运行数据必须位于源码副本之外")
    home.mkdir(parents=True, exist_ok=True)
    os.environ["DEEPTUTOR_HOME"] = str(home)
    os.environ["BACKEND_PORT"] = str(port)
    os.environ.setdefault("DEEPTUTOR_VERSION_CHECK_ENABLED", "false")
    os.environ.setdefault("DEEPTUTOR_SANDBOX_ALLOW_SUBPROCESS", "false")
    sys.path.insert(0, str(VENDOR_ROOT))
    os.chdir(home)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18001)
    parser.add_argument("--home", type=Path, default=DEFAULT_HOME)
    args = parser.parse_args()
    args.home = args.home.resolve()
    from dotenv import load_dotenv
    load_dotenv(HOST_ROOT / ".env", override=False)
    prepare(args.home, args.port)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    import deeptutor
    if not Path(deeptutor.__file__).resolve().is_relative_to(VENDOR_ROOT.resolve()):
        raise RuntimeError("加载到仓库外的 DeepTutor，停止启动")
    import uvicorn
    from deeptutor.runtime.mode import RunMode, set_mode
    set_mode(RunMode.SERVER)
    from deeptutor.api.main import app
    # worker 按文件路径启动；宿主目录只用于加载适配层，上游仍来自固定副本。
    sys.path.append(str(HOST_ROOT))
    from integrations.deeptutor.boundary import HostBridgeBoundary
    from integrations.deeptutor.session_bridge import install_session_bridge
    from integrations.deeptutor.turn_bridge import install_turn_bridge
    from integrations.deeptutor.generation_bridge import install_generation_bridge
    from integrations.deeptutor.agentic_bridge import install_agentic_bridge
    from integrations.deeptutor.knowledge_bridge import install_knowledge_bridge
    sessions = install_session_bridge(app, args.home)
    install_turn_bridge(app, sessions)
    install_generation_bridge(app)
    install_agentic_bridge(app)
    install_knowledge_bridge(app, args.home.resolve())
    app.add_middleware(HostBridgeBoundary)
    uvicorn.run(app, host="127.0.0.1", port=args.port,
                proxy_headers=False, access_log=False)


if __name__ == "__main__":
    main()
