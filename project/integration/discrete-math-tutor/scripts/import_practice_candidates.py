"""鎶婂闃呴€氳繃鐨勫績鐞嗗涔犻瀵煎叆姣忎釜瀛︾敓鐨勫巶瀹剁粌涔犲簱銆?
鐢ㄦ硶锛?  python scripts/import_practice_candidates.py --mark-approved   # 瀹￠槄鍚庣‘璁?  python scripts/import_practice_candidates.py                  # 閫愯处鍙峰鍏?鍙鍏?status=approved 鐨勯鐩紱绛旀涓庡紩鐢ㄦ潵鑷?practice_candidates.json銆?"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
COURSE = ROOT / "knowledge" / "courses" / "experimental-psychology-3"
CANDIDATES = ROOT / "knowledge" / "psychology_practice.json"
CREDS = ROOT / ".runtime" / "vendor-accounts.txt"
BASE = "http://127.0.0.1:3000"


def mark_approved() -> None:
    import json

    data = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    for item in data["questions"]:
        item["status"] = "approved"
    CANDIDATES.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"approved={len(data['questions'])}")


def password(username: str) -> str:
    lines = [l for l in CREDS.read_text(encoding="utf-8").splitlines()
             if l.startswith(f"{username}\t")]
    return lines[-1].split("\t", 1)[1]


def csv_bytes(questions: list[dict]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["question", "question_type", "A", "B", "C", "D",
                     "correct_answer", "explanation", "tags", "user_answer"])
    for item in questions:
        options = item.get("options") or {}
        is_choice = item["type"] == "single_choice"
        writer.writerow([
            item["question"],
            "single_choice" if is_choice else "true_false",
            options.get("A", "") if is_choice else "",
            options.get("B", "") if is_choice else "",
            options.get("C", "") if is_choice else "",
            options.get("D", "") if is_choice else "",
            item["answer"], item.get("explanation", ""),
            item["kc_id"], "",
        ])
    return buffer.getvalue().encode("utf-8-sig")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mark-approved", action="store_true")
    parser.add_argument("--base", default=BASE)
    args = parser.parse_args()
    if args.mark_approved:
        mark_approved()
        return
    import json

    questions = [q for q in json.loads(CANDIDATES.read_text(encoding="utf-8"))["questions"]
                 if q.get("status") == "approved"]
    if not questions:
        raise SystemExit("娌℃湁 approved 鐨勯鐩紱鍏堜汉宸ュ闃呭啀 --mark-approved")
    payload = csv_bytes(questions)
    for index in range(1, 11):
        username = f"student{index:02d}"
        session = requests.Session()
        session.post(f"{args.base}/api/auth/login",
                     json={"username": username, "password": password(username)},
                     timeout=30).raise_for_status()
        preview = session.post(
            f"{args.base}/api/question-notebook/practice/import/preview",
            files={"file": ("practice.csv", payload, "text/csv")},
            data={"target": "bank", "course_id": ""}, timeout=300)
        preview.raise_for_status()
        body = preview.json()
        token = body.get("token")
        if not token:
            print(f"{username}: 棰勮澶辫触 errors={body.get('errors')}")
            continue
        commit = session.post(f"{args.base}/api/question-notebook/practice/import/commit",
                              json={"token": token}, timeout=300)
        commit.raise_for_status()
        print(f"{username}: valid={body.get('valid')} commit={commit.json()}")


if __name__ == "__main__":
    main()

