"""Q3 循环可复现检查。

默认 ``stub`` 只验证暂停/接续和工具配对，不调用教材检索或真实模型。
``local`` 通过 Q2 的本地检索接口做一次受控联调；它仍不是页面或真实模型验收。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.agent_loop_service import run_agent_loop_turn
from agents.q3_navigation import StubLearningNavigator
from llm.client import ChatToolCall, ChatToolResult
from models.chat_request import ChatRequest
from models.task_context import TaskContext


class ScriptedLLM:
    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.calls = []

    def chat_with_tools(self, messages, tools, **kwargs):
        self.calls.append({"messages": messages, "tools": tools, **kwargs})
        if not self.rounds:
            raise RuntimeError("script exhausted")
        item = self.rounds.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeMemory:
    def read_version(self, student_id, point):
        return "token", 0

    def append_exchange(self, *args, **kwargs):
        return 1


def tool_round(*calls):
    return ChatToolResult(text="", finish_reason="tool_calls", tool_calls=[
        ChatToolCall(id=f"call_{i}", name=name, arguments=args,
                     raw_arguments=json.dumps(args, ensure_ascii=False))
        for i, (name, args) in enumerate(calls)])


def final_round(text):
    return ChatToolResult(text=text, finish_reason="stop")


def run_stub():
    llm = ScriptedLLM([
        tool_round(("ask_user", {"questions": [{"id": "q1", "prompt": "你指哪种设计？",
            "options": [{"label": "被试间设计"}, {"label": "被试内设计"}]}]})),
        final_round("按被试内设计解释。[1]"),
    ])
    orchestrator = SimpleNamespace(llm=llm, memory=FakeMemory(), quality_checker=None)
    context = TaskContext(student_id="s", message="请比较这两种设计。",
                          knowledge_point="实验设计")
    request = ChatRequest(student_id="s", session_id="legacy", request_id="stub-1",
                          message=context.message)
    first = run_agent_loop_turn(
        orchestrator=orchestrator, request=request, context=context,
        navigator=StubLearningNavigator(), publish_gate=lambda text, state: (True, ""),
        llm=llm)
    if not first.get("loop_paused"):
        return {"passed": False, "stage": "pause", "result": first}
    request2 = ChatRequest(student_id="s", session_id="legacy", request_id="stub-2",
                           message="被试内设计", selected_option=None)
    context2 = TaskContext(student_id="s", message=request2.message,
                           knowledge_point="实验设计",
                           history=[{"role": "user", "content": "请比较这两种设计。"},
                                    {"role": "assistant", "content": "你指哪种设计？"}])
    second = run_agent_loop_turn(
        orchestrator=orchestrator, request=request2, context=context2,
        previous={"context": {"loop_state": first["loop_state"]},
                  "_resume_answer": "被试内设计"},
        navigator=StubLearningNavigator(), publish_gate=lambda text, state: (True, ""),
        llm=llm)
    passed = (second.get("answer_status") == "answered"
              and "被试内" in second.get("reply", ""))
    return {"passed": passed, "stage": "resume", "first": first, "second": second}


def run_local():
    os.environ["Q3_RETRIEVAL_MODE"] = "local"
    from knowledge.local_rag.course_retrieval import retrieve  # noqa: F401  availability probe
    llm = ScriptedLLM([
        tool_round(("retrieve_course", {"query": "自变量的定义", "limit": 2})),
        final_round("自变量是研究者操纵并会影响被试反应的变量。[1]"),
    ])
    orchestrator = SimpleNamespace(llm=llm, memory=FakeMemory(), quality_checker=None)
    context = TaskContext(student_id="s", message="请解释自变量。", knowledge_point="自变量")
    request = ChatRequest(student_id="s", session_id="legacy", request_id="local-1",
                          message=context.message)
    result = run_agent_loop_turn(
        orchestrator=orchestrator, request=request, context=context,
        publish_gate=lambda text, state: (True, ""), llm=llm)
    sources = result.get("sources") or []
    return {"passed": result.get("answer_status") == "answered" and bool(sources),
            "stage": "local_q2_interface", "answer_status": result.get("answer_status"),
            "sources": len(sources), "stub": any(item.get("stub") for item in sources),
            "reply": result.get("reply"), "loop_summary": result.get("loop_summary")}


def run_live():
    """Real model + Q2 local retrieval, still not a page acceptance test."""
    import os
    from datetime import datetime, timezone
    import secrets

    root = ROOT
    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
    home = root / ".runtime/q3-live" / run
    home.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        TUTOR_COURSE="experimental-psychology-3", LLM_MOCK="0",
        DATABASE_URL="sqlite:///" + str(home / "host.sqlite3"),
        COURSE_DATABASE_URL="sqlite:///" + str(home / "course.sqlite3"),
        Q3_RETRIEVAL_MODE="local", MEMORY_WORKER_ENABLED="0",
        VISUALIZATION_ON_DEMAND="0", RAG_RERANK_DEVICE="cpu", RAG_EMBED_DEVICE="cpu",
    )
    from database.database import init_db
    from dotenv import load_dotenv
    from orchestrator import TutorOrchestrator
    from models.task_context import TaskContext
    from models.chat_request import ChatRequest

    # The worktree intentionally has no .env; read the user's local key without copying it.
    load_dotenv(Path("E:/项目/heart/project/integration/discrete-math-tutor/.env"))
    init_db()
    orchestrator = TutorOrchestrator()
    student_id = "q3-" + run
    orchestrator.memory.ensure_student(student_id, account_type="test")
    message = "请解释教材里的自变量，并引用教材依据。"
    context = TaskContext(student_id=student_id, message=message, knowledge_point="自变量")
    request = ChatRequest(student_id=student_id, session_id="q3-session",
                          request_id=run, message=message, account_type="test")
    result = run_agent_loop_turn(
        orchestrator=orchestrator, request=request, context=context, llm=orchestrator.llm)
    return {"passed": result.get("answer_status") == "answered",
            "stage": "live_model_q2", "run": run,
            "answer_status": result.get("answer_status"),
            "reply": result.get("reply"),
            "sources": len(result.get("sources") or []),
            "loop_summary": result.get("loop_summary"),
            "loop_error": result.get("loop_error"),
            "loop_events": result.get("loop_events"),
            "quality": result.get("quality")}


def run_live_navigation():
    """Real model through TaskService: chapter start then next knowledge point."""
    from datetime import datetime, timezone
    import secrets

    root = ROOT
    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
    home = root / ".runtime/q3-live" / run
    home.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        TUTOR_COURSE="experimental-psychology-3", LLM_MOCK="0",
        DATABASE_URL="sqlite:///" + str(home / "host.sqlite3"),
        COURSE_DATABASE_URL="sqlite:///" + str(home / "course.sqlite3"),
        Q3_RETRIEVAL_MODE="local", LOCAL_AGENT_LOOP_ENABLED="1",
        MEMORY_WORKER_ENABLED="0", VISUALIZATION_ON_DEMAND="0",
        RAG_RERANK_DEVICE="cpu", RAG_EMBED_DEVICE="cpu",
    )
    from database.database import init_db
    from dotenv import load_dotenv
    from orchestrator import TutorOrchestrator
    from agents.agent_loop_service import run_agent_loop_turn
    from agents.task_service import TaskService
    from models.chat_request import ChatRequest

    load_dotenv(Path("E:/项目/heart/project/integration/discrete-math-tutor/.env"))
    init_db()
    orchestrator = TutorOrchestrator()
    student_id = "q3-nav-" + run
    orchestrator.memory.ensure_student(student_id, account_type="test")
    service = TaskService(orchestrator)

    def execute(request, context, resolved, intercept, guard, progress,
                previous=None, **kwargs):
        return run_agent_loop_turn(
            orchestrator=orchestrator, request=request, context=context,
            resolved=resolved, intercept=intercept, guard=guard,
            progress=progress, previous=previous,
        )

    turns = []
    for index, message in enumerate(("我想要学习教材第一章的内容", "继续下一个知识点")):
        request = ChatRequest(
            student_id=student_id, session_id="q3-nav-session",
            request_id=f"{run}-{index}", message=message, account_type="test",
        )
        started = time.monotonic()
        result = service.run(request, execute)
        elapsed = round(time.monotonic() - started, 3)
        sources = result.get("sources") or []
        citation_indexes = sorted({int(value) for value in re.findall(r"\[(\d+)\]", result.get("reply") or "")})
        source_indexes = sorted({int(source.get("index")) for source in sources
                                 if source.get("index") is not None})
        turns.append({
            "message": message,
            "answer_status": result.get("answer_status"),
            "reply": result.get("reply"),
            "knowledge_point": result.get("knowledge_point"),
            "navigation_id": (result.get("course_navigation") or {}).get("id"),
            "navigation": result.get("course_navigation"),
            "sources": len(sources),
            "source_indexes": source_indexes,
            "citation_indexes": citation_indexes,
            "citations_consistent": bool(citation_indexes) and set(citation_indexes) <= set(source_indexes),
            "elapsed_seconds": elapsed,
            "loop_error": result.get("loop_error"),
        })
    passed = (all(turn["answer_status"] == "answered" for turn in turns)
              and all(turn["citations_consistent"] for turn in turns))
    navigation_advanced = (turns[0]["navigation_id"] is not None
                           and turns[1]["navigation_id"] is not None
                           and turns[1]["navigation_id"] != turns[0]["navigation_id"])
    return {"passed": passed, "stage": "live_navigation", "run": run,
            "navigation_advanced": navigation_advanced, "turns": turns}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("stub", "local", "live", "live_navigation"),
                        default="stub")
    args = parser.parse_args()
    report = {"stub": run_stub, "local": run_local, "live": run_live,
              "live_navigation": run_live_navigation}[args.mode]()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
