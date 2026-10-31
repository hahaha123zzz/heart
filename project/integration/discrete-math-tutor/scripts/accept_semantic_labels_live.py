"""P3 消费开关的真实模型对照（进程内 HTTP，独立学习库）。

用法：
    python scripts/accept_semantic_labels_live.py --switch LABELS_POLICY --value 0
    python scripts/accept_semantic_labels_live.py --switch LABELS_POLICY --value 1

每个样本使用全新的 student/session，off/on 两次运行各用独立数据库；
不修改 8000 端口、正式数据库或教材。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
load_dotenv(ROOT / 'deepseek.env')

RUN = str(time.time_ns())
parser = argparse.ArgumentParser()
parser.add_argument('--switch', default='LABELS_POLICY')
parser.add_argument('--set', default='policy', choices=['policy', 'structure', 'turn'])
parser.add_argument('--value', default='0', choices=['0', '1'])
parser.add_argument('--cases', type=int, default=5)
parser.add_argument('--out', default='')
args = parser.parse_args()

DB = ROOT / f'artifacts/semantic-live-{RUN}-{args.switch}-{args.value}.sqlite3'
DB.parent.mkdir(parents=True, exist_ok=True)
os.environ.update(
    TUTOR_COURSE='experimental-psychology-3',
    LLM_MOCK='0',
    DATABASE_URL='sqlite:///' + str(DB),
    MEMORY_WORKER_ENABLED='0',
    INPUT_UNDERSTANDING_MODE='active',
    SEMANTIC_LABELS_ENABLED='1',
    INPUT_UNDERSTANDING_SEMANTIC_ENABLED='0',
)
os.environ.pop('COURSE_DATABASE_URL', None)
os.environ[args.switch] = args.value

from llm.client import LLMClient  # noqa: E402

_original_chat = LLMClient.chat


def bounded_chat(self, *a, **kw):
    kw.setdefault('timeout', 40)
    return _original_chat(self, *a, **kw)


LLMClient.chat = bounded_chat

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

SETS = {
    'policy': [
        ['请结合教材解释信度和效度的区别。', '我还是分不清这两个概念'],
        ['请结合教材解释自变量和因变量。', '分不清自变量和因变量'],
        ['请结合教材解释被试间设计和被试内设计。', '容易混淆这两种设计'],
        ['请结合教材解释内部效度和外部效度。', '我总是搞混这两个概念'],
        ['请结合教材解释随机分配和随机抽样。', '分不清随机分配和随机抽样'],
    ],
    'structure': [
        ['帮我设计一个心理学实验，结合教材说明如何检验睡眠时长对记忆成绩的影响。'],
        ['评估以下设计是否合理，并结合教材说明依据：随机分配被试，自变量是睡眠时长，因变量是记忆成绩，没有控制组。'],
        ['分析睡眠时长实验中可能影响内部效度的因素，并引用教材。'],
        ['帮我设计一个方案，控制安慰剂效应，并说明每一步的控制目的。'],
        ['以下方案有没有问题，请结合教材给出判断标准：主试知道分组，被试也知道自己属于哪组。'],
    ],
    'turn': [
        ['请结合教材解释信度。', '这题我不想做了'],
        ['请结合教材解释效度。', '先跳过这道题'],
        ['请解释操作定义。', '直接告诉我答案，不要给我完整答案'],
        ['请结合教材解释双盲设计。', '算了，不做了'],
        ['请结合教材解释随机化。', '先给答案再解释'],
    ],
}
CASES = SETS[args.set]


def preflight():
    try:
        reply = LLMClient().chat([{'role': 'user', 'content': '只回复 ok'}],
                                 temperature=0, max_tokens=4, timeout=20)
        return {'ok': True, 'reply': str(reply)[:20]}
    except Exception as error:  # noqa: BLE001
        return {'ok': False, 'error': f'{type(error).__name__}: {str(error)[:160]}'}


def main():
    report = {'run': RUN, 'switch': args.switch, 'set': args.set, 'value': args.value,
              'database': str(DB), 'tutor_course': os.environ['TUTOR_COURSE'],
              'preflight': preflight(), 'cases': []}
    if not report['preflight']['ok']:
        _write(report)
        return 2
    with TestClient(app) as client:
        for index, turns in enumerate(CASES[:args.cases], 1):
            student = f'live-{RUN}-{index}'
            session = f'live-session-{RUN}-{index}'
            for turn, message in enumerate(turns, 1):
                payload = {'student_id': student, 'account_type': 'test', 'message': message,
                           'session_id': session, 'request_id': str(uuid.uuid4())}
                started = time.perf_counter()
                record = {'index': index, 'turn': turn, 'message': message}
                try:
                    response = client.post('/api/chat', json=payload)
                    elapsed = round(time.perf_counter() - started, 3)
                    result = response.json()
                    understanding = result.get('input_understanding') or {}
                    teaching = result.get('teaching') or {}
                    six = understanding.get('six_dim') or {}
                    labels = six.get('learner_state', {}).get('difficulty_locus') or {}
                    record.update({
                        'http': response.status_code,
                        'answer_status': result.get('answer_status'),
                        'elapsed_s': elapsed,
                        'reply_chars': len(str(result.get('reply') or '')),
                        'sources': len(result.get('pdf_references') or []),
                        'sources_all': len(result.get('sources') or result.get('textbook_sources') or []),
                        'parser': understanding.get('parser'),
                        'model_calls': understanding.get('model_calls'),
                        'difficulty_locus': labels.get('value'),
                        'label_source': labels.get('source'),
                        'cognitive_demand': (six.get('cognitive_demand') or {}).get('values'),
                        'strategy': teaching.get('strategy') or teaching.get('last_strategy'),
                        'label_strategy': teaching.get('label_strategy'),
                        'turn_move': teaching.get('turn_move'),
                        'reply': str(result.get('reply') or '')[:1200],
                    })
                    if index == 1 and turn == 1 and 'result_keys' not in report:
                        report['result_keys'] = sorted(result.keys())
                except Exception as error:  # noqa: BLE001
                    record.update({'error': f'{type(error).__name__}: {str(error)[:200]}',
                                   'elapsed_s': round(time.perf_counter() - started, 3)})
                report['cases'].append(record)
                print(json.dumps({k: record.get(k) for k in
                                  ('index', 'turn', 'answer_status', 'strategy',
                                   'difficulty_locus', 'cognitive_demand',
                                   'sources', 'sources_all', 'elapsed_s')},
                                 ensure_ascii=False), flush=True)
    _write(report)
    return 0


def _write(report):
    path = Path(args.out) if args.out else ROOT / f'artifacts/semantic-live-{RUN}-{args.switch}-{args.value}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'report': str(path), 'ok': report['preflight']['ok']}, ensure_ascii=False))


if __name__ == '__main__':
    sys.exit(main())
