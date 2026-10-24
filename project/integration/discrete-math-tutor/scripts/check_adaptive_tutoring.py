"""Real-HTTP acceptance for the DeepTutor teaching adapter (uses model credits).

Run against an isolated database. Evidence contains synthetic student dialogue,
never API credentials. Split phases allow an actual server restart in between.
"""
import argparse
import json
from pathlib import Path
import time
import uuid
import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:8001")
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--phase", choices=("prepare", "resume"), required=True)
parser.add_argument("--student", default="adaptive-live-20261024")
parser.add_argument("--session", default="adaptive-live-1")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
client = httpx.Client(base_url=args.base_url, timeout=360, trust_env=False)
summary_path = args.output / "summary.json"
summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {
    "student": args.student, "session": args.session, "cases": []}


def save(name, value):
    (args.output / (name + ".json")).write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def turn(name, message, request_id=None):
    payload = {"student_id": args.student, "session_id": args.session,
               "request_id": request_id or uuid.uuid4().hex, "message": message,
               "reader_location": {"chapter_id": 2, "section_id": 1}}
    print("START " + name, flush=True)
    started = time.monotonic()
    response = client.post("/api/chat", json=payload)
    response.raise_for_status()
    data = response.json()
    save(name, {"request": payload, "response": data})
    teaching = data.get("teaching") or {}
    case = {"name": name, "seconds": round(time.monotonic() - started, 2),
            "status": data.get("answer_status"), "task_id": data.get("task_id"),
            "teaching": teaching, "loop": data.get("loop_summary"),
            "retrieval_count": len(data.get("retrieval_calls") or []),
            "references": len(data.get("pdf_references") or []),
            "reply": data.get("reply")}
    summary["cases"].append(case)
    save("summary", summary)
    print(json.dumps(case, ensure_ascii=False), flush=True)
    assert data.get("answer_status") == "answered", "Not published: " + str(data.get("reply"))
    assert teaching.get("schema") == "deeptutor-teaching-v2", "Engine not active"
    assert teaching.get("formal_mastery") is False, "Formative feedback granted formal mastery"
    if data.get("publication_mode") != "saved_formative_question":
        assert data.get("pdf_references"), "No published evidence"
    for ref in data.get("pdf_references") or []:
        state = client.post("/api/course/citation-state", json={"reference": ref})
        state.raise_for_status()
        assert state.json().get("stale") is False
    return data, payload


if args.phase == "prepare":
    client.post("/api/accounts/test", json={"student_id": args.student}).raise_for_status()
    first, payload = turn("concept",
        "请解释自变量和因变量的区别，先讲一个简单例子，再给我一个很小的理解检查。", "concept-1")
    pending = first["teaching"]["pending_check"]
    assert pending
    replay = client.post("/api/chat", json=payload)
    replay.raise_for_status()
    assert replay.json() == first, "Idempotent request changed state"
    second, _ = turn("difficulty", "我没听懂，请换一种更简单的讲法。先不出新题，原来的小检查留着。")
    assert second["teaching"]["last_strategy"] != first["teaching"]["last_strategy"]
    assert second["teaching"]["pending_check"] == pending, "Difficulty erased or replaced original question"
    assert not second.get("retrieval_calls"), "Same-topic explanation unnecessarily retrieved"
    third, _ = turn("side-question", "先插问一下，什么是控制变量？原来的小检查我还没作答。")
    assert third["teaching"]["pending_check"] == pending, "Side question erased original question"
    assert third["teaching"]["assessment"] is None, "Side question was graded"
    print("PREPARE PASSED; restart server before --phase resume.", flush=True)
else:
    prepared = json.loads((args.output / "concept.json").read_text(encoding="utf-8"))["response"]
    pending = prepared["teaching"]["pending_check"]
    history = client.get(f"/api/students/{args.student}/conversation",
                         params={"session_id": args.session})
    history.raise_for_status()
    save("refreshed-history", history.json())
    assert pending["prompt"] in json.dumps(history.json(), ensure_ascii=False)
    resumed, _ = turn("resume-question", "回到刚才的小检查，请原样重现题目，不要给答案。")
    assert resumed["teaching"]["pending_check"] == pending, "Restart changed saved question"
    assert resumed["reply"].rstrip().endswith(pending["prompt"]), "Original question not displayed"
    # Synthetic response for the saved room-temperature / completion-time case.
    assert "室温" in pending["prompt"] and "时间" in pending["prompt"], "Update synthetic answer for this case"
    feedback, _ = turn("answer-feedback",
        "室温是自变量，因为它是研究者设定的条件；作答时间是因变量，因为它是被试的反应指标。")
    observed = feedback["teaching"]["assessment"] or {}
    assert observed.get("question_id") == pending["question_id"], "Graded a different question"
    assert observed.get("verdict") == "correct", "Equivalent answer not recognized"
    assert feedback["teaching"]["stage"] == "practiced_with_help"
    plain, _ = turn("explain-only", "先讲不考，不要问我，也不要出题。继续简单解释这两个变量。")
    assert plain["teaching"]["allow_check"] is False
    assert plain["teaching"]["pending_check"] is None
    assert "？" not in plain["reply"] and "?" not in plain["reply"]
    print("RESUME PASSED: restart recovery, actual answer feedback, explain-only preference.", flush=True)
