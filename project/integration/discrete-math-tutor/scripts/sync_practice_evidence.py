"""把厂家练习结果同步成宿主 evidence（只写证据，不改成绩）。

用法：python scripts/sync_practice_evidence.py
幂等：按 (username, entry_id, attempt_count) 记录已同步键。
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database.database import session_scope  # noqa: E402
from database.models import EvidenceRow  # noqa: E402

HOME = Path(r"E:\heart-runtime\deeptutor")
STATE = ROOT / ".runtime" / "practice-evidence-sync.json"


def user_ids() -> dict[str, str]:
    data = json.loads((HOME / "data" / "system" / "auth" / "users.json")
                      .read_text(encoding="utf-8"))
    return {name: str(record.get("id") or "") for name, record in data.items()}


def load_state() -> set[str]:
    if not STATE.is_file():
        return set()
    return set(json.loads(STATE.read_text(encoding="utf-8")).get("synced") or [])


def save_state(synced: set[str]) -> None:
    STATE.write_text(json.dumps({"synced": sorted(synced)}, ensure_ascii=False),
                     encoding="utf-8")


def main() -> None:
    ids = user_ids()
    synced = load_state()
    added = 0
    for index in range(1, 11):
        username = f"student{index:02d}"
        user_id = ids.get(username)
        if not user_id:
            print(f"skip {username}: 无厂家用户")
            continue
        db = HOME / "data" / "users" / user_id / "user" / "chat_history.db"
        if not db.is_file():
            print(f"skip {username}: 无会话库")
            continue
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                select ev.request_id, ev.entry_id, ev.rating, ev.outcome_json,
                       c.name as kc
                from practice_review_events ev
                join notebook_entry_categories ec on ec.entry_id = ev.entry_id
                join notebook_categories c on c.id = ec.category_id
                where c.name like 'kc-%'
                """).fetchall()
        for row in rows:
            key = f"{username}:{row['request_id']}"
            if key in synced:
                continue
            outcome = json.loads(row["outcome_json"] or "{}")
            correct = bool(outcome.get("correct"))
            payload = {"entry_id": row["entry_id"], "request_id": row["request_id"],
                       "rating": row["rating"], "correct": correct}
            with session_scope() as session:
                session.add(EvidenceRow(
                    student_id=username, knowledge_point=row["kc"],
                    evidence_type="practice",
                    content=json.dumps(payload, ensure_ascii=False),
                    confidence=0.9 if correct else 0.2))
            synced.add(key)
            added += 1
    save_state(synced)
    print(f"evidence_added={added} synced_keys={len(synced)}")


if __name__ == "__main__":
    main()
