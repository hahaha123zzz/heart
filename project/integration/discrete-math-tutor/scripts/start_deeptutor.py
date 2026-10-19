"""启动独立 DeepTutor 后端；默认使用本项目专属 Python 环境。"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    default_python = ROOT / ".venv-deeptutor" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    parser.add_argument("--python", type=Path, default=Path(os.getenv("DEEPTUTOR_PYTHON", str(default_python))))
    parser.add_argument("--port", type=int, default=18001)
    parser.add_argument("--home", type=Path, default=ROOT / ".runtime/deeptutor")
    args = parser.parse_args()
    if not args.python.is_file():
        parser.error("找不到独立环境；先运行 scripts/setup_deeptutor.py，或用 --python 指定已安装依赖的解释器")
    if not 1 <= args.port <= 65535:
        parser.error("端口必须在 1 到 65535 之间")
    worker = ROOT / "integrations/deeptutor/worker.py"
    command = [str(args.python.resolve()), "-X", "utf8", str(worker),
               "--port", str(args.port), "--home", str(args.home.resolve())]
    raise SystemExit(subprocess.call(command, cwd=ROOT))


if __name__ == "__main__":
    main()
