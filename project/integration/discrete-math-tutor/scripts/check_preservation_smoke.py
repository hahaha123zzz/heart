"""对已启动的 8000 服务做真实 SSE 冒烟；只读事件，不启动服务。"""
import argparse
import json
import time
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--student-id", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--message", required=True)
    args = parser.parse_args()

    payload = {
        "student_id": args.student_id,
        "session_id": args.session_id,
        "message": args.message,
        "account_type": "test",
        "request_id": "smoke-" + str(int(time.time())),
    }
    request = urllib.request.Request(
        args.base_url.rstrip("/") + "/api/chat/stream",
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    started = time.perf_counter()
    event = data = None
    last_stage = None
    answer_status = None
    done = False
    with opener.open(request, timeout=300) as response:
        for raw in response:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
            elif not line:
                if not event:
                    continue
                elapsed = round(time.perf_counter() - started, 2)
                try:
                    body = json.loads(data or "{}")
                except ValueError:
                    body = {}
                if event == "progress" and body.get("stage") and body["stage"] != last_stage:
                    last_stage = body["stage"]
                    print(f"{elapsed:7.2f}s stage={last_stage}")
                elif event in ("answer", "done", "error"):
                    answer_status = body.get("answer_status") or answer_status
                    print(f"{elapsed:7.2f}s {event} status={answer_status}")
                    done = event == "done"
                    if event in ("done", "error"):
                        break
                event = data = None
    return 0 if done and answer_status == "answered" else 1


if __name__ == "__main__":
    raise SystemExit(main())
