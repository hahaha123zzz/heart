"""Real-model, real-PDF acceptance for the shared selection teaching loop."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import uuid

import fitz
import httpx

from knowledge.pdf_reader import document_for_chapter, pdf_path

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:8001")
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--phase", choices=("start", "finish", "switch"), required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
client = httpx.Client(base_url=args.base_url, timeout=300, trust_env=False)
state_path = args.output / "state.json"
state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {
    "student": "selection-qa-" + uuid.uuid4().hex[:12],
    "session": "selection-" + uuid.uuid4().hex[:12], "cases": []}


def save(name, value):
    (args.output / (name + ".json")).write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def selected_text(marker):
    record = document_for_chapter(2)
    with fitz.open(pdf_path(record)) as pdf:
        for number, page in enumerate(pdf, 1):
            block = next((b for b in page.get_text("blocks", sort=True) if marker in b[4]), None)
            if block is None:
                continue
            # Read the definition and the following lines, not a partial keyword.
            rect = {"page": number, "x1": 89/page.rect.width, "x2": 501/page.rect.width,
                    "y1": (block[1]-1)/page.rect.height, "y2": min(page.rect.height, block[3]+35)/page.rect.height}
            return {"document_id": record["document_id"], "version": record["version"],
                    "kind": "text", "rects": [rect], "text": "FORGED CLIENT PREVIEW - DO NOT TRUST"}
    raise AssertionError("Acceptance definition not found")


def turn(name, message, selection=None, stream=False):
    payload = {"student_id": state["student"], "session_id": state["session"],
               "request_id": uuid.uuid4().hex, "message": message}
    if selection:
        payload["selection"] = selection
    print("START " + name, flush=True)
    started = time.monotonic()
    if stream:
        events = []
        event = ""
        with client.stream("POST", "/api/chat/stream", json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    events.append({"event": event, "data": json.loads(line[5:].strip())})
        data = next((item["data"] for item in reversed(events) if item["event"] == "done"), None)
        save(name + "-events", events)
        assert data, "No final SSE result"
    else:
        response = client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
    save(name, {"request": payload, "response": data})
    teaching = data.get("teaching") or {}
    case = {"name": name, "seconds": round(time.monotonic()-started, 2),
            "status": data.get("answer_status"), "entrypoint": data.get("entrypoint"),
            "task_id": data.get("task_id"), "target": (data.get("loop_summary") or {}).get("target"),
            "teaching": teaching, "loop_summary": data.get("loop_summary"),
            "references": len(data.get("pdf_references") or []), "reply": data.get("reply")}
    state["cases"].append(case)
    save("state", state)
    print(json.dumps(case, ensure_ascii=False), flush=True)
    assert data.get("answer_status") == "answered", data.get("reply")
    assert data.get("entrypoint") == "pdf_text_selection", "Selection did not use shared loop"
    assert teaching.get("schema") == "deeptutor-teaching-v2"
    assert teaching.get("formal_mastery") is False
    assert not data.get("step_advanced")
    assert data.get("learning_interjection") is True
    assert "FORGED" not in json.dumps(data, ensure_ascii=False), "Client preview became evidence"
    if data.get("publication_mode") != "saved_formative_question":
        assert data.get("pdf_references"), "No published PDF citations"
    for ref in data.get("pdf_references") or []:
        checked = client.post("/api/course/citation-state", json={"reference": ref})
        checked.raise_for_status()
        assert checked.json().get("stale") is False
    return data, payload


if args.phase == "start":
    client.post("/api/accounts/test", json={"student_id": state["student"]}).raise_for_status()
    selection = selected_text("研究者所操纵")
    state["selection"] = selection
    save("state", state)
    first, payload = turn("selection-explanation",
        "请解释选区里自变量的意思，先举一个研究者改变室温的教学示例。"
        "然后用这道小检查结尾：研究者把室温设为18℃和26℃，这里主动改变的条件是什么？"
        "不要给出小检查的答案。", selection, stream=True)
    pending = first["teaching"]["pending_check"]
    assert pending and "室温" in pending["prompt"], "No saved formative question"
    replay = client.post("/api/chat", json=payload); replay.raise_for_status()
    assert replay.json()["reply"] == first["reply"]
    assert replay.json()["teaching"] == first["teaching"], "Replay changed question state"
    second, _ = turn("repeat-selection-followup",
        "我没听懂，请换一种更简单的讲法，保留原来的小检查，不出新题。", selection)
    assert second["teaching"]["pending_check"] == pending
    assert second["teaching"]["last_strategy"] != first["teaching"]["last_strategy"]
    assert second["loop_summary"]["target"] == first["loop_summary"]["target"]
    print("START PHASE PASSED. Restart isolated server, then run --phase finish.", flush=True)
elif args.phase == 'finish':
    original = json.loads((args.output / "selection-explanation.json").read_text(encoding="utf-8"))["response"]
    pending = original["teaching"]["pending_check"]
    history = client.get(f"/api/students/{state['student']}/conversation",
                         params={"session_id": state["session"]})
    history.raise_for_status(); save("history-after-restart", history.json())
    assert pending["prompt"] in json.dumps(history.json(), ensure_ascii=False)
    restored, _ = turn("restore-without-selection", "回到刚才的小检查，请原样重现，不要给答案。")
    assert restored["teaching"]["pending_check"] == pending
    assert restored["publication_mode"] == "saved_formative_question"
    assert restored["loop_summary"]["rounds"] == 0
    feedback, _ = turn("answer-without-selection", "室温，是研究者主动设置和改变的条件。")
    assessment = feedback["teaching"]["assessment"] or {}
    assert assessment.get("question_id") == pending["question_id"]
    assert assessment.get("verdict") == "correct"
    assert feedback["teaching"]["stage"] == "practiced_with_help"
if args.phase in ('finish', 'switch'):
    if args.phase == 'switch':
        turn('before-switch', '请简单解释当前选区，不要问我，不要出题。', state['selection'])
    original = json.loads((args.output / "selection-explanation.json").read_text(encoding="utf-8"))["response"]
    moved, _ = turn("new-selection",
        "请简单解释这个新选区，不要问我，不要出题。", selected_text("操作性自变量是指"))
    assert moved["loop_summary"]["target"] != original["loop_summary"]["target"]
    assert moved["teaching"]["assessment"] is None
    assert moved["teaching"]["pending_check"] is None
    assert moved["teaching"]["allow_check"] is False
    assert not any(phrase in moved['reply'] for phrase in ('没有附带新的选区', '未附带新选区', '没有收到选区', '没有出现新段落'))
    print("FINISH PASSED: same-PDF followup, restart, exact old question, answer feedback, selection change.", flush=True)
