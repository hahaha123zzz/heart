"""只读短句语义对照；--live 才调用模型，结果不进入生产任务或画像。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.input_understanding.service import understand
from agents.input_understanding.semantic import resolve
from agents.input_understanding.adapters import legacy_routing
from models.chat_request import ChatRequest
from models.task_context import TaskContext
from unittest.mock import patch


def compare_case(row, llm=None, *, compare_legacy=False):
    text = row['text']
    context = TaskContext.model_validate({'student_id':'semantic-shadow', 'session_id':'isolated',
        **row.get('context', {}), 'message':text, 'input_mode':'active'})
    snapshot = context.model_dump()
    request = ChatRequest.model_validate({**row.get('request', {}), 'student_id':context.student_id,
        'session_id':context.session_id, 'message':text})
    # 基线只能执行规则，不能从本机 .env 意外启用额外解析。
    with patch.dict('os.environ', {'INPUT_UNDERSTANDING_SEMANTIC_ENABLED':'0', 'SEMANTIC_LABELS_ENABLED':'1'}):
        turn = understand(context, request)
    baseline = turn.model_dump()
    started = time.perf_counter()
    if compare_legacy:
        if llm is None:
            raise ValueError('旧模型路由对照要求显式 --live')
        # 对照真实入口的按需升级，不能强迫简单输入多调用一次解析器。
        with patch.dict('os.environ', {'INPUT_UNDERSTANDING_SEMANTIC_ENABLED':'1', 'SEMANTIC_LABELS_ENABLED':'1'}):
            candidate = understand(context.model_copy(deep=True),request,llm=llm)
    else:
        candidate = resolve(turn.model_copy(deep=True), context.model_copy(deep=True), llm) if llm is not None else turn
    proposed = candidate.model_dump()
    baseline_context = context.model_copy(update={'input_understanding':turn})
    candidate_context = context.model_copy(update={'input_understanding':candidate})
    old_projection = legacy_routing(baseline_context)
    new_projection = legacy_routing(candidate_context)
    projections = [value.model_dump() if value is not None else None
                   for value in (old_projection,new_projection)]
    legacy = None
    legacy_calls = 0
    if compare_legacy:
        if llm is None:
            raise ValueError('旧模型路由对照要求显式 --live')
        from agents.conversation_router import ConversationRouter
        legacy_context = context.model_copy(deep=True, update={'input_mode':'off', 'input_understanding':None})
        def route_chat(messages):
            nonlocal legacy_calls
            legacy_calls += 1
            return llm.chat_json(messages,retries=0,timeout=15,max_tokens=1400)
        router_model = SimpleNamespace(chat_json=route_chat)
        legacy = ConversationRouter(router_model).route(text,legacy_context.knowledge_point,
            legacy_context.history,[],context=legacy_context).model_dump()
    fields = ('status','student_move','intent','learning_intents','target_refs','answer_constraints')
    differences = [key for key in fields if legacy is not None and projections[1] is not None
                   and legacy.get(key) != projections[1].get(key)]
    return {'case_id':row['case_id'], 'promoted':False, 'model_calls':candidate.model_calls,
            'legacy_model_calls':legacy_calls,
            'candidate_mode':'runtime_conditional' if compare_legacy else 'diagnostic' if llm else 'rules',
            'seconds':round(time.perf_counter()-started,3), 'parser':candidate.parser,
            'baseline_labels':baseline['annotations'], 'candidate_labels':proposed['annotations'],
            'task_changed':baseline['tasks'] != proposed['tasks'],
            'directives_changed':baseline['directives'] != proposed['directives'],
            'references_changed':baseline['references'] != proposed['references'],
            'legacy_projection':projections[0], 'candidate_projection':projections[1],
            'projection_changed':projections[0] != projections[1],
            'legacy_model_projection':legacy, 'legacy_differences':differences,
            'legacy_comparable':legacy is not None and projections[1] is not None,
            'context_unchanged':snapshot == context.model_dump(),
            'baseline_unchanged':baseline == turn.model_dump()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--legacy', action='store_true', help='另调用旧路由，比较同一输入快照；仅用于隔离评测')
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error('--limit 必须在 1–100 之间')
    if args.legacy and not args.live:
        parser.error('--legacy 要求 --live')
    llm = None
    if args.live:
        from dotenv import load_dotenv
        load_dotenv(ROOT / '.env')
        from llm.client import LLMClient
        llm = LLMClient()
    rows = [json.loads(line) for line in args.input.read_text(encoding='utf-8').splitlines() if line.strip()][:args.limit]
    args.out.parent.mkdir(parents=True,exist_ok=True)
    results = []
    for index,row in enumerate(rows,1):
        results.append(compare_case({'case_id':f'shadow-{index}', **row},llm,compare_legacy=args.legacy))
        # 每条完成即保存，长批次被打断仍保留已完成结果。
        args.out.write_text(json.dumps({'live':args.live,'promoted':False,'complete':False,
            'cases':results},ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'completed_cases':index,'parser':results[-1]['parser']},ensure_ascii=False),flush=True)
    comparable = [row for row in results if row['legacy_comparable']]
    different = sum(bool(row['legacy_differences']) for row in comparable)
    summary = {'comparable':len(comparable), 'different':different,
        'difference_rate':different / len(comparable) if comparable else None,
        'effective_difference_rate':different / len(results)
            if args.legacy and results and len(comparable)==len(results) else None,
        'unprojected':sum(row['candidate_projection'] is None for row in results),
        'critical_different':sum(bool(set(row['legacy_differences']) &
            {'student_move','intent','target_refs','answer_constraints'}) for row in comparable),
        'legacy_requested':args.legacy, 'eligible_for_removal':False}
    args.out.write_text(json.dumps({'live':args.live,'promoted':False,'complete':True,'summary':summary,'cases':results},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'cases':len(results),'model_calls':sum(r['model_calls']+r['legacy_model_calls'] for r in results),
                      'baseline_unchanged':all(r['baseline_unchanged'] for r in results)},ensure_ascii=False))


if __name__ == '__main__':
    main()
