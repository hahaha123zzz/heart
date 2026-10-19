"""Q1.1 连续对话质量样本运行器。

默认只做结构自检，不调用模型。``--live`` 在当前项目的本地
``TutorOrchestrator`` 链路上运行样本，使用隔离数据库；不会把请求转交给
独立 DeepTutor 应用。需要用户在本机 .env 中配置真实模型。

样本来源：tests/data/deeptutor-conversation-quality.json。
9 类心理学黄金问题仍由 tests/data/deeptutor-golden.json 保存；本脚本的
``--include-golden`` 只运行其中可由普通聊天入口执行的文本案例，选区和
视觉案例留给 Q2。
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CASES_PATH = ROOT / "tests/data/deeptutor-conversation-quality.json"
GOLDEN_PATH = ROOT / "tests/data/deeptutor-golden.json"
DEFERRED = {
    "clarify_and_continue": "Q3（需要 ask_user 任务恢复）",
    "correct_and_forget": "Q5（偏好撤销与删除语义）",
}
TEXT_GOLDEN_KINDS = {"answer", "hint", "refusal"}


def load_cases(path: Path = CASES_PATH):
    return json.loads(path.read_text(encoding="utf-8"))


def load_golden_text_cases(path: Path = GOLDEN_PATH):
    cases = json.loads(path.read_text(encoding="utf-8"))
    normalized = []
    for case in cases:
        if case.get("kind") not in TEXT_GOLDEN_KINDS:
            continue
        row = dict(case)
        row["turns"] = [case["message"]]
        row["checks"] = case.get("checks") or ["回答通过教材证据与质量核验"]
        normalized.append(row)
    return normalized


def _directive_for_second_turn(case):
    from agents.followup_context import followup_directive

    turns = case.get("turns") or []
    if not turns:
        return ""
    index = 1 if len(turns) > 1 else 0
    history = [{"role": "user", "content": turns[0]},
               {"role": "assistant", "content": "上一轮助教解释的占位内容。"}] if index else [
        {"role": "assistant", "content": "上一轮助教解释的占位内容。"}]
    return followup_directive(turns[index], history)


def self_test():
    """Validate samples and the deterministic follow-up contracts offline."""

    cases = load_cases()
    checks = {}
    errors = []
    expected = {
        "simplify_without_switching": "上一轮助教解释",
        "comparison_followup": "明确缩小范围",
        "accuracy_is_not_hint": "准确性要求",
        "explicit_hint_then_explain": "明确改变",
    }
    for case in cases:
        case_id = case.get("id")
        if not case_id or not case.get("turns") or not case.get("checks"):
            errors.append(f"{case_id or '<missing>'}: turns/checks 不能为空")
            continue
        if case_id in DEFERRED:
            checks[case_id] = {"deferred": DEFERRED[case_id]}
            continue
        directive = _directive_for_second_turn(case)
        marker = expected.get(case_id)
        passed = bool(directive) if marker is None else marker in directive
        checks[case_id] = {"followup_directive": bool(directive), "passed": passed}
        if not passed:
            errors.append(f"{case_id}: 未命中连续追问契约 {marker or '非空'}")

    # Budget behavior must produce a summary instead of silently dropping turns.
    from agents.conversation_context import build_history

    rows = []
    for index in range(8):
        rows += [{"role": "user", "content": "第%d轮问题" % index},
                 {"role": "assistant", "content": "第%d轮回答" % index}]
    packed = build_history(rows, budget_tokens=8)
    if not packed.summary or not packed.history:
        errors.append("历史预算没有产生摘要或保留最近回合")
    checks["budget_history"] = {"summary": bool(packed.summary),
                                "kept": len(packed.history),
                                "dropped": packed.dropped_messages}
    return {
        "passed": not errors,
        "cases": len(cases),
        "deferred": sorted(DEFERRED),
        "checks": checks,
        "errors": errors,
    }


def order_cases(cases):
    """Place a ``follows`` case immediately after the case it depends on."""

    ordered = []
    by_id = {case["id"]: case for case in cases}
    emitted = set()
    for case in cases:
        if case["id"] in emitted:
            continue
        if case.get("follows") in by_id:
            continue
        ordered.append(case)
        emitted.add(case["id"])
        for dependent in cases:
            if dependent.get("follows") == case["id"] and dependent["id"] not in emitted:
                ordered.append(dependent)
                emitted.add(dependent["id"])
    for case in cases:
        if case["id"] not in emitted:
            ordered.append(case)
            emitted.add(case["id"])
    return ordered


def case_student_id(case, base, by_id):
    """Give independent samples separate histories; keep ``follows`` connected."""

    parent = case.get("follows")
    if parent in by_id:
        return case_student_id(by_id[parent], base, by_id)
    return f"{base}-{case['id']}"


def _live_checks(case, results, history_before_turns):
    kind = case.get("kind")
    if kind == "refusal":
        return {
            "refused": all(result.get("answer_status") == "evidence_rejected" for result in results),
            "no_published_answer": all(not result.get("pdf_references")
                                       and not result.get("step_advanced") for result in results),
        }
    checks = {"answered": all(result.get("answer_status") == "answered" for result in results)}
    checks["quality_passed"] = all((result.get("quality") or {}).get("passed") is True
                                   and not (result.get("quality") or {}).get("issues")
                                   for result in results)
    checks["has_citation"] = all(bool(result.get("pdf_references")) or "[1]" in result.get("reply", "")
                                 for result in results)
    if kind == "hint":
        checks["hint_scope"] = all(bool((result.get("task_execution") or {}).get("hint_only"))
                                   for result in results)
    turns = case.get("turns") or []
    if len(results) >= 2 and len(turns) >= 2:
        from agents.followup_context import followup_directive
        directive = followup_directive(turns[1], history_before_turns[1])
        checks["followup_targeted"] = bool(directive)
        execution = results[1].get("task_execution") or {}
        if case["id"] == "simplify_without_switching":
            checks["kept_explain"] = "explain" in execution.get("learning_intents", []) and not execution.get("hint_only", False)
        if case["id"] == "accuracy_is_not_hint":
            checks["not_hint_only"] = not execution.get("hint_only", False)
        if case["id"] == "explicit_hint_then_explain":
            first = results[0].get("task_execution") or {}
            checks["first_hint_only"] = bool(first.get("hint_only"))
            checks["second_full"] = not bool(execution.get("hint_only"))
    elif results and (case.get("follows") or case["id"] == "followup"):
        from agents.followup_context import followup_directive
        checks["followup_targeted"] = bool(followup_directive(turns[0], history_before_turns[0]))
    if case["id"] == "accuracy_is_not_hint":
        checks["not_hint_only"] = not bool((results[0].get("task_execution") or {}).get("hint_only"))
    return checks


def live_run(cases, *, output: Path):
    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
    home = output / run
    home.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        TUTOR_COURSE="experimental-psychology-3",
        LLM_MOCK="0",
        DATABASE_URL="sqlite:///" + str(home / "host.sqlite3"),
        COURSE_DATABASE_URL="sqlite:///" + str(home / "course.sqlite3"),
        MEMORY_WORKER_ENABLED="0",
        VISUALIZATION_ON_DEMAND="0",
        RAG_RERANK_DEVICE="cpu",
        RAG_EMBED_DEVICE="cpu",
    )
    from orchestrator import TutorOrchestrator

    tutor = TutorOrchestrator()
    base_student_id = "q1-" + run
    by_id = {case["id"]: case for case in cases}
    case_records = {}
    rows = []
    for case in order_cases(cases):
        if case["id"] in DEFERRED:
            rows.append({"id": case["id"], "status": "deferred", "reason": DEFERRED[case["id"]]})
            continue
        student_id = case_student_id(case, base_student_id, by_id)
        parent = case.get("follows")
        conversation_history = list(case_records.get(parent, {}).get("history", []))
        turns = case["turns"]
        results = []
        history_before_turns = []
        started = time.monotonic()
        for turn in turns:
            history_before_turns.append(list(conversation_history))
            result = tutor.handle_turn(student_id, turn, learning_goal="实验心理学", account_type="test")
            results.append(result)
            conversation_history += [{"role": "user", "content": turn},
                                     {"role": "assistant", "content": result.get("reply", "")}]
        case_records[case["id"]] = {"student_id": student_id,
                                    "history": list(conversation_history)}
        checks = _live_checks(case, results, history_before_turns)
        rows.append({
            "id": case["id"],
            "student_id": student_id,
            "checks": checks,
            "passed": all(checks.values()),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "turns": [{
                "reply": result.get("reply", ""),
                "answer_status": result.get("answer_status"),
                "routing": result.get("routing"),
                "task_execution": result.get("task_execution"),
                "quality": result.get("quality"),
                "textbook_sources": result.get("textbook_sources", []),
                "pdf_references": result.get("pdf_references", []),
            } for result in results],
        })
    report = {"run": run, "cases": rows, "passed": all(
        row.get("passed") for row in rows if row.get("status") != "deferred")}
    (home / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report, home / "report.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="调用本机真实模型运行本地链路")
    parser.add_argument("--case", action="append", help="只运行指定样本 ID")
    parser.add_argument("--include-golden", action="store_true", help="加入 9 类黄金集中的文本案例")
    parser.add_argument("--output", type=Path, default=ROOT / ".runtime/conversation-quality")
    args = parser.parse_args()

    if not args.live:
        report = self_test()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(0 if report["passed"] else 1)

    cases = load_cases()
    if args.include_golden:
        cases += load_golden_text_cases()
    if args.case:
        requested = set(args.case)
        known = {case["id"] for case in cases}
        if not requested <= known:
            parser.error("未知样本 ID：" + ", ".join(sorted(requested - known)))
        cases = [case for case in cases if case["id"] in requested]
    args.output.mkdir(parents=True, exist_ok=True)
    report, path = live_run(cases, output=args.output)
    print(json.dumps({"passed": report["passed"], "report": str(path),
                      "cases": len(report["cases"])}, ensure_ascii=False))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
