"""发布当前实验心理学教材到独立后端的原生 Markdown 知识库。"""
import argparse
import os
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from integrations.deeptutor.published_course import publish

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=ROOT / ".runtime" / "deeptutor")
    args = parser.parse_args()
    os.environ["DEEPTUTOR_HOME"] = str(args.home.resolve())
    print(json.dumps(publish(args.home), ensure_ascii=False))
