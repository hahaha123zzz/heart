"""建立 GPU 运行库覆盖环境，复用现有应用依赖。"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    base = ROOT / ".venv"
    target = ROOT / ".venv-gpu"
    if not (base / "Scripts/python.exe").exists():
        raise SystemExit("先建立 .venv 并安装 requirements.txt")
    subprocess.run([sys.executable, "-m", "venv", str(target)], check=True)
    site = target / "Lib/site-packages"
    (site / "project_cpu_dependencies.pth").write_text(str(base / "Lib/site-packages") + "\n", encoding="utf-8")
    subprocess.run([str(target / "Scripts/python.exe"), "-m", "pip", "install", "-r", str(ROOT / "requirements-gpu-runtime.txt")], check=True)
    print("GPU 环境已创建；运行 scripts.benchmark_rag_device 验证实际 CUDA 推理后再启用。")
