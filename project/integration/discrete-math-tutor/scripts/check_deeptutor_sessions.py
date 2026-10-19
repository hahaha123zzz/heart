"""用独立环境启动临时后端，验证真实课程/会话映射并关闭进程。"""
from __future__ import annotations

import json
import argparse
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from integrations.deeptutor.client import DeepTutorBackend


def wait_ready(backend, process):
    deadline = time.monotonic() + 45
    while not backend.status()["backend_ready"]:
        if process.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError("独立后端未就绪，请检查临时运行目录 server.log")
        time.sleep(.2)


def check_turns(backend):
    from integrations.deeptutor.turn_contract import SourcePointer, TurnProjection
    from knowledge.pdf_reader import documents
    from knowledge.course_config import COURSE_ID, COURSE_TITLE
    record = documents()[0]
    projection = TurnProjection(student_id="session-smoke-student-a", session_id="tab-a",
        course_id=COURSE_ID, course_title=COURSE_TITLE, task_id="smoke-" + secrets.token_hex(8),
        task_revision=3, outcome="completed", result_digest="a" * 64,
        sources=[SourcePointer(kind="section", document_id=record["document_id"], version=record["version"], chapter_id=record["chapter_id"])])
    payload = projection.model_dump()
    first = backend.publish_turn(payload)
    assert first == backend.publish_turn(payload)
    cursor = projection.model_dump(include={"student_id", "session_id", "course_id", "course_title", "task_id", "task_revision"})
    events = backend.turn_events({**cursor, "after_seq": 0})
    assert [event["seq"] for event in events["events"]] == [1, 2]
    assert all(not event["content"] for event in events["events"])
    assert events["events"][0]["metadata"]["sources"] == payload["sources"]
    assert [event["seq"] for event in backend.turn_events({**cursor, "after_seq": 1})["events"]] == [2]
    assert backend.turn_events({**cursor, "after_seq": 2})["events"] == []
    return cursor, first


def check_generation(backend):
    from knowledge.course_config import COURSE_ID
    from knowledge.hybrid_retrieval import _as_chunk
    from knowledge.course_config import PSYCHOLOGY_DIR
    from knowledge.grounded_citations import choose_evidence, settings
    from knowledge.textbook import format_excerpts
    from agents.response_generator import ResponseGenerator
    from agents.teaching_planner import TeachingPlan
    from agents.quality_checker import QualityChecker
    from models.student_state import StudentState
    from llm.client import LLMClient
    import sqlite3

    os.environ["DEEPTUTOR_BACKEND_URL"] = backend.base_url
    os.environ["DEEPTUTOR_LLM_ENABLED"] = "1"
    llm = LLMClient(mock=False)
    backend.timeout = 30
    result = backend._post("/internal/heart/knowledge/search", {"terms": ["随机分配"], "limit": 6})
    assert result["course_id"] == COURSE_ID and result["chunk_ids"]
    connection = sqlite3.connect((PSYCHOLOGY_DIR / "rag_index.sqlite3").resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        sources = [_as_chunk(connection.execute("SELECT * FROM chunks WHERE id=?", (key,)).fetchone()) for key in result["chunk_ids"]]
    finally:
        connection.close()
    question = "随机分配如何帮助控制无关变量？请只给我一个提示。"
    local_index = ROOT / ".runtime/deeptutor-generation-smoke/citation-index.sqlite3"
    if settings() is None and local_index.is_file():
        os.environ["CITATION_GROUNDING_MODE"] = "active"
        os.environ["CITATION_GROUNDING_INDEX"] = str(local_index)
    citation_index = settings()
    assert citation_index is not None, "请先构建隔离精细引用索引，或配置 CITATION_GROUNDING_INDEX"
    bundle = choose_evidence(llm, question, sources, citation_index)
    excerpts = format_excerpts(bundle.sources)
    plan = TeachingPlan(goal="理解随机分配的作用", strategy="progressive_hinting", action="give_hint", difficulty="easy")
    state = StudentState(student_id="isolated-generation-smoke", current_concept="随机分配")
    feedback = None
    checks = []
    for _ in range(2):
        answer = ResponseGenerator(llm).generate(state, plan, question, [], textbook_excerpts=excerpts, feedback=feedback)
        quality = QualityChecker(llm).check(answer, state, plan, question, textbook_excerpts=excerpts,
            context={"grounded_evidence": bundle.evidence})
        checks.append(quality.model_dump())
        if quality.passed and not quality.issues:
            references = bundle.references(answer)
            assert references
            return {"model_execution_verified": True, "knowledge_search_verified": True,
                "citation_grounding_verified": True, "hint_quality_verified": True,
                "answer": answer, "quality_checks": checks, "evidence_ids": [item["evidence_id"] for item in bundle.evidence]}
        feedback = "；".join(quality.issues)
    raise AssertionError("真实模型讲解未通过原质检，详见服务器或验收日志")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turns", action="store_true", help="同时检查回合事件与重启恢复")
    parser.add_argument("--generation", action="store_true", help="使用本机配置调用真实模型并验证教材讲解/引用，不写学习数据库")
    args = parser.parse_args()
    home = ROOT / ".runtime" / ("deeptutor-generation-smoke" if args.generation else "deeptutor-session-smoke")
    home.mkdir(parents=True, exist_ok=True)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = dict(os.environ, DEEPTUTOR_BRIDGE_TOKEN=secrets.token_hex(32))
    os.environ["DEEPTUTOR_BRIDGE_TOKEN"] = environment["DEEPTUTOR_BRIDGE_TOKEN"]
    backend = DeepTutorBackend(f"http://127.0.0.1:{port}", timeout=5)
    with (home / "server.log").open("w", encoding="utf-8") as log:
        def start():
            return subprocess.Popen([sys.executable, "-B", str(ROOT / "integrations/deeptutor/worker.py"),
                "--home", str(home), "--port", str(port)], cwd=ROOT, env=environment,
                stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        process = start()
        try:
            wait_ready(backend, process)
            first = backend.bind_session("session-smoke-student-a", "tab-a")
            assert first == backend.bind_session("session-smoke-student-a", "tab-a")
            second = backend.bind_session("session-smoke-student-a", "tab-b")
            other = backend.bind_session("session-smoke-student-b", "tab-a")
            assert first["user_id"] == second["user_id"]
            assert first["course_id"] == second["course_id"]
            assert first["session_id"] != second["session_id"]
            assert first["user_id"] != other["user_id"]
            assert first["course_id"] != other["course_id"]
            try:
                backend.opener.open(Request(backend.base_url + "/api/sessions"), timeout=5)
            except HTTPError as error:
                assert error.code == 401
            else:
                raise AssertionError("数据接口没有阻止匿名访问")
            result = {"backend_ready": True, "idempotency": True, "student_isolation": True,
                      "session_isolation": True, "anonymous_access_blocked": True,
                      "binding": first, "model_execution_verified": False}
            if args.turns:
                cursor, receipt = check_turns(backend)
                process.terminate()
                process.wait(timeout=10)
                process = start()
                wait_ready(backend, process)
                events = backend.turn_events({**cursor, "after_seq": 1})
                assert events["turn_id"] == receipt["turn_id"]
                assert [event["seq"] for event in events["events"]] == [2]
                result.update(turn_events_verified=True, restart_recovery=True, source_versions_verified=True)
            if args.generation:
                result.update(check_generation(backend))
            name = "phase-b-generation-smoke.json" if args.generation else "phase-b2-smoke.json" if args.turns else "phase-b1-smoke.json"
            artifact = ROOT / "artifacts/deeptutor" / name
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(result, ensure_ascii=True))
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
