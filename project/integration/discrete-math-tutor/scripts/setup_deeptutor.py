"""安装完整上游后端到项目独立虚拟环境，不改动现有教学环境。"""
import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT.parents[1] / "vendor/DeepTutor"
LOCK_NAME = f"requirements-deeptutor-{sys.platform}-py{sys.version_info[0]}{sys.version_info[1]}.lock.txt"


def main():
    if not (VENDOR / "UPSTREAM_SNAPSHOT.json").is_file():
        raise SystemExit("请先执行 project/scripts/vendor_deeptutor.py")
    env = ROOT / ".venv-deeptutor"
    python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(env)
    lock = ROOT / LOCK_NAME
    requirements = ["-r", str(lock)] if lock.is_file() else ["-e", str(VENDOR)]
    subprocess.run([str(python), "-m", "pip", "install", *requirements], check=True, cwd=ROOT)


if __name__ == "__main__":
    main()
