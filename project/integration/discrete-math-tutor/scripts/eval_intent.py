"""独立意图评测：默认离线，不导入 Orchestrator 或初始化业务数据库。

mock 只检查现有离线夹具，replay 检查录制预测，real 显式使用配置模型。
legacy 保留旧路由基线；task 使用冻结的已校验上下文快照，不读取业务数据库。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FLOW_LABELS = ("continue", "switch_topic", "new_goal", "off_task", "clarify_task")
LEGACY_FIELDS = ("intent", "student_move", "needs_context", "topic")
TASK_FIELDS = ("learning_intents", "target_refs", "answer_constraints", "missing_slots")


def limit_model_calls(client, limit, timeout=30):
    """限制网关尝试次数，关闭SDK隐式重试；配置失败也占一次尝试。"""
    from llm.client import LLMError
    budget={'attempts':0,'limit':limit}
    original_call, original_factory=client._one_call, client._client_lazy
    client._client_lazy=lambda: original_factory().with_options(max_retries=0)
    def bounded_call(*args,**kwargs):
        if budget['attempts']>=limit: raise LLMError('本次评测调用预算已用完')
        budget['attempts']+=1
        kwargs.setdefault('timeout',timeout)
        return original_call(*args,**kwargs)
    client._one_call=bounded_call
    return budget


def task_context(case):
    from models.task_context import TaskContext
    inputs = case["input"]
    extra = inputs.get("context", {})
    if set(extra) - {"objects", "preferences"}:
        raise ValueError("评测上下文只允许objects和preferences")
    context = TaskContext(student_id="intent-evaluation", message=inputs["message"],
        knowledge_point=inputs["knowledge_point"], history=inputs["history"],
        known_points=inputs["known_points"], **extra)
    if len({obj.id for obj in context.objects}) != len(context.objects):
        raise ValueError("评测对象ID重复")
    return context


def load_cases(path):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [row["id"] for row in rows]
    if not rows or len(set(ids)) != len(ids):
        raise ValueError("样例必须非空且ID唯一")
    for row in rows:
        if row.get("split") not in ("optimization", "development", "holdout"):
            raise ValueError("样例必须声明数据划分")
        if row["expected"]["intent"] not in FLOW_LABELS:
            raise ValueError("样例包含未知流程标签")
        from models.task_understanding import TaskUnderstanding
        TaskUnderstanding(intent=row["expected"]["intent"],
            **{key:value for key,value in row.get("desired_task",{}).items() if key in TASK_FIELDS})
    # 同模板或同会话不得跨优化/开发/盲测集合。
    for field in ("conversation_id", "template_family"):
        groups = {}
        for row in rows:
            groups.setdefault(row[field], set()).add(row["split"])
        if any(len(splits) > 1 for splits in groups.values()):
            raise ValueError("会话或模板跨集合泄漏")
    return rows


def percentile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * p) - 1)]


def score(cases, predictions, *, router_mode="legacy"):
    if set(predictions) != {row["id"] for row in cases}:
        raise ValueError("预测ID必须与所选样例完全匹配")
    matches, denominators = Counter(), Counter()
    confusion = Counter()
    clarification, task_counts = Counter(), Counter()
    statuses = Counter()
    failures, timings = [], []
    unsupported = Counter()
    for case in cases:
        record = predictions[case["id"]]
        pred = record["prediction"]
        expected = case["expected"]
        if router_mode == "task":
            from models.task_understanding import TaskUnderstanding
            allowed = {obj.id for obj in task_context(case).objects}
            try:
                if not set(TASK_FIELDS).issubset(pred):
                    raise ValueError("录制任务字段缺失")
                checked = TaskUnderstanding.model_validate(pred)
                if not set(checked.target_refs).issubset(allowed) or checked.rewrite_sources or checked.rewritten_query != case['input']['message']:
                    raise ValueError("录制对象或问题改写不合法")
            except (ValueError, TypeError):
                pred = {"status":"parse_error","intent":"clarify_task"}
        status = pred.get("status", "legacy_unspecified")
        statuses[status] += 1
        executable = status in ("ok", "legacy_unspecified")
        # 失败不能因为兼容 intent=clarify_task 就得到“正确澄清”的分数。
        flow = pred.get("intent") if executable else "__failure__"
        confusion[(expected["intent"], flow)] += 1
        wrong = []
        for field in LEGACY_FIELDS:
            if field not in expected:
                continue
            denominators[field] += 1
            if executable and pred.get(field) == expected[field]:
                matches[field] += 1
            else:
                wrong.append(field)
        need = expected["intent"] == "clarify_task"
        asks = executable and pred.get("intent") == "clarify_task"
        clarification["required" if need else "clear"] += 1
        clarification["true_positive" if need and asks else "false_positive" if asks else "not_asked"] += 1
        for field in case.get("desired_task", {}):
            desired = case["desired_task"][field]
            if router_mode != "task" or field not in TASK_FIELDS:
                unsupported[field] += 1
                continue
            if field == "target_refs":
                allowed = {obj.id for obj in task_context(case).objects}
                if not set(desired).issubset(allowed):
                    unsupported["target_refs:unresolved_fixture"] += 1
                    continue
            denominators[field] += 1
            actual = pred.get(field)
            # 多意图顺序有教学含义；对象/约束/槽位按集合评分，但重复项不能算正确。
            equal = actual == desired if field == "learning_intents" else (
                isinstance(actual,list) and len(actual)==len(set(actual)) and set(actual)==set(desired))
            if executable and equal:
                matches[field] += 1
            else:
                wrong.append(field)
            if field == 'learning_intents' and len(desired)>1:
                task_counts['multi_total'] += 1
                task_counts['multi_correct'] += int(executable and equal)
        latency = record.get("latency_ms")
        if isinstance(latency, (int, float)) and math.isfinite(latency) and latency >= 0:
            timings.append(latency)
        if wrong:
            failures.append({"id": case["id"], "wrong_fields": wrong, "status": status})
    per_label = {}
    for label in FLOW_LABELS:
        tp = confusion[(label, label)]
        fp = sum(n for (gold, guess), n in confusion.items() if guess == label and gold != label)
        fn = sum(n for (gold, guess), n in confusion.items() if gold == label and guess != label)
        support = sum(n for (gold, _), n in confusion.items() if gold == label)
        per_label[label] = {"f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None, "support": support}
    supported = [v["f1"] for v in per_label.values() if v["support"]]
    return {
        "count": len(cases),
        "review_status_counts": dict(Counter(row.get("review_status", "unreviewed") for row in cases)),
        "field_scores": {key: {"correct": matches[key], "total": n, "accuracy": matches[key] / n} for key, n in denominators.items()},
        "flow_macro_f1_supported_classes": sum(supported) / len(supported) if supported else None,
        "flow_class_scores": per_label,
        "necessary_clarification_recall": {"numerator": clarification["true_positive"], "denominator": clarification["required"], "value": clarification["true_positive"] / clarification["required"] if clarification["required"] else None},
        "unnecessary_clarification_rate": {"numerator": clarification["false_positive"], "denominator": clarification["clear"], "value": clarification["false_positive"] / clarification["clear"] if clarification["clear"] else None},
        "status_counts": dict(statuses),
        "latency_ms": {"p50": percentile(timings, .5), "p95": percentile(timings, .95)},
        "unsupported_task_fields": dict(unsupported),
        "multi_intent_order": {"correct":task_counts['multi_correct'], "total":task_counts['multi_total'],
            "accuracy":task_counts['multi_correct']/task_counts['multi_total'] if task_counts['multi_total'] else None},
        "failures": failures,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "tests/data/intent/seed20.jsonl")
    parser.add_argument("--mode", choices=("mock", "replay", "real"), default="mock")
    parser.add_argument("--router", choices=("legacy", "task"), default="legacy")
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--split", choices=("optimization", "development", "holdout"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-api-calls", type=int, help="real模式的实际网络调用上限，含重试")
    parser.add_argument("--api-timeout", type=float, default=30, help="每次调用超时秒数")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("limit必须为正数")
    if args.max_api_calls is not None and (args.max_api_calls < 1 or args.mode != 'real'):
        parser.error("max-api-calls只用于real模式且必须为正数")
    if not math.isfinite(args.api_timeout) or not 0 < args.api_timeout <= 120:
        parser.error('api-timeout必须是0到120之间的有限正数')
    if args.mode == "replay" and args.predictions is None:
        parser.error("replay必须提供predictions")
    if args.mode != "replay" and args.predictions is not None:
        parser.error("predictions仅适用于replay")
    cases = load_cases(args.data)
    if args.split:
        cases = [row for row in cases if row["split"] == args.split]
    if args.limit:
        cases = cases[:args.limit]
    if not cases:
        parser.error("没有匹配样例")
    if args.router == "task":
        for case in cases:
            task_context(case)  # 在模型调用之前验证全部上下文。
    budget={'attempts':0}
    api_limit=args.max_api_calls if args.max_api_calls is not None else len(cases)*2
    if args.mode == "replay":
        saved = json.loads(args.predictions.read_text(encoding="utf-8"))
        if saved.get("router_mode", "legacy") != args.router:
            raise ValueError("录制预测与评测路由模式不一致")
        data_hash = hashlib.sha256(args.data.read_bytes()).hexdigest()
        if saved.get("data_sha256") and saved["data_sha256"] != data_hash:
            raise ValueError("录制预测与样例文件哈希不一致")
        records = saved["predictions"]
        if len({r["id"] for r in records}) != len(records):
            raise ValueError("录制预测包含重复ID")
        wanted = {c["id"] for c in cases}
        predictions = {r["id"]: r for r in records if r["id"] in wanted}
        source_mode = saved.get("source_mode", saved.get("mode", "unspecified_replay"))
    else:
        from agents.conversation_router import ConversationRouter
        from llm.client import LLMClient
        client = LLMClient(mock=args.mode == "mock")
        if args.mode == 'real':
            budget=limit_model_calls(client,api_limit,args.api_timeout)
        router = ConversationRouter(client)
        predictions = {}
        for case in cases:
            inputs = case["input"]
            start = time.perf_counter()
            result = router.route(inputs["message"], inputs["knowledge_point"], inputs["history"], inputs["known_points"],
                **({"context":task_context(case)} if args.router=="task" else {}))
            predictions[case["id"]] = {"id": case["id"], "prediction": result.model_dump(), "latency_ms": (time.perf_counter() - start) * 1000}
            print(json.dumps({'case':case['id'],'status':result.status,'latency_ms':round(predictions[case['id']]['latency_ms'],1)},ensure_ascii=False),flush=True)
        source_mode = args.mode
    router_hash = saved.get("router_sha256") if args.mode == "replay" else hashlib.sha256((ROOT / "agents/conversation_router.py").read_bytes()).hexdigest()
    report = {
        "schema_version": 2, "mode": args.mode, "source_mode": source_mode, "router_mode":args.router,
        "semantic_model_evaluation": source_mode == "real",
        "data_sha256": hashlib.sha256(args.data.read_bytes()).hexdigest(),
        "router_sha256": router_hash,
        "evaluator_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "task_schema_sha256":hashlib.sha256((ROOT/'models/task_understanding.py').read_bytes()).hexdigest(),
        "model":saved.get('model') if args.mode=='replay' else 'deterministic_mock' if args.mode=='mock' else client.model,
        "api_call_attempts":saved.get('api_call_attempts') if args.mode=='replay' else budget['attempts'],
        "api_call_limit":saved.get('api_call_limit') if args.mode=='replay' else api_limit if args.mode=='real' else None,
        "api_timeout":saved.get('api_timeout') if args.mode=='replay' else args.api_timeout if args.mode=='real' else None,
        "note": "样例未独立人工审核；mock不是模型语义准确率。task仅评冻结上下文中的识别结果，不评澄清恢复或实际回答泄露。",
        "metrics": score(cases, predictions,router_mode=args.router),
        "predictions": list(predictions.values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"mode": args.mode, "cases": len(cases), "output": str(args.output), "semantic_model_evaluation": report["semantic_model_evaluation"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
