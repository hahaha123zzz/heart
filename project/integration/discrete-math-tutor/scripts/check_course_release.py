"""Report the local textbook release identity, index and asset gaps.

Read-only: no publication, re-indexing or file rewriting. The current staging
manifest is expected to report ``ready=false`` until visual review and release
state are completed.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge.course_release import validate  # noqa: E402


def main() -> int:
    state = validate()
    summary = {key: state[key] for key in
               ("course_id", "title", "status", "ready", "release_id",
                "index_sha256", "gaps")} | {"visuals": state["visuals"],
                                             "chapters": state["chapters"]}
    output = ROOT / ".runtime" / "course-release"
    output.mkdir(parents=True, exist_ok=True)
    path = output / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("course_id", "title", "status", "ready", "release_id",
                       "index_sha256", "gaps", "visuals")}, ensure_ascii=False, indent=2))
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
