"""真实原 API 黄金集；只使用合成学生、隔离数据库和本机配置的模型。"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def checks_for(case, result, calls, versions):
    generated = [call for call in calls if call['path'].endswith('/generate') and call['ok']]
    checks = {'real_gateway_used': bool(generated), 'no_client_text_leak': not any(call.get('client_text_leaked') for call in calls)}
    if case['kind'] == 'refusal':
        gate = result.get('evidence_check') or {}
        checks.update(refused=result.get('answer_status') == 'evidence_rejected',
            insufficient_evidence=gate.get('mode') == 'model' and gate.get('status') in {'partial', 'insufficient', 'conflicting'},
            no_published_answer=not result.get('pdf_references') and not result.get('step_advanced'))
        return checks
    refs = result.get('pdf_references') or []
    markers = {int(value) - 1 for value in re.findall(r'\[(\d+)\]', result.get('reply', ''))}
    indexes = {ref.get('source_index') for ref in refs}
    valid = bool(refs)
    for ref in refs:
        evidence = ref.get('evidence') or {}
        pointer = ref.get('selection_ref') or {}
        valid &= bool(evidence.get('evidence_id') and pointer.get('evidence_id') == evidence.get('evidence_id')
            and pointer.get('document_id') in versions and versions[pointer['document_id']] == pointer.get('version')
            and evidence.get('document_version') == pointer.get('version')
            and evidence.get('document_id') == pointer.get('document_id')
            and evidence.get('location_status') in {'exact', 'page', 'section'}
            and (evidence.get('quote') or (case['kind'] == 'vision' and evidence.get('media_kind') == 'image')))
    quality = result.get('quality') or result.get('quality_check') or {}
    gate = result.get('evidence_check') or {}
    checks.update(answered=result.get('answer_status') == 'answered',
        quality_passed=quality.get('passed') is True and not quality.get('issues'),
        evidence_gate=gate.get('status') == 'sufficient' and gate.get('mode') == 'model',
        citation_ids=bool(markers) and markers <= indexes and len(indexes) == len(refs),
        source_versions=bool(valid),
        session_sync=(result.get('deeptutor_session') or {}).get('status') == 'ready',
        turn_sync=(result.get('deeptutor_turn') or {}).get('status') == 'ready')
    if case['kind'] in {'answer', 'hint'}:
        checks['knowledge_gateway_used'] = any(call['path'].endswith('/knowledge/search') and call['ok'] for call in calls)
    if case['kind'] == 'hint':
        from agents.task_execution import TaskExecution
        execution = TaskExecution.model_validate(result.get('task_execution') or {})
        checks['hint_scope'] = execution.hint_only and (result.get('teaching_plan') or {}).get('action') == 'give_hint'
    if case['kind'] == 'vision':
        checks['images_sent'] = any(call.get('images', 0) > 0 and call['ok'] for call in generated)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', action='append', help='仅检查指定 ID；追问自动加入前置概念案例')
    parser.add_argument('--citation-index', type=Path, default=ROOT / '.runtime/deeptutor-generation-smoke/citation-index.sqlite3')
    args = parser.parse_args()
    if not args.citation_index.is_file(): parser.error('请先用原 scripts.build_citation_index 构建隔离精细引用索引')
    cases = json.loads((ROOT / 'tests/data/deeptutor-golden.json').read_text(encoding='utf-8'))
    if args.case:
        requested = set(args.case)
        if not requested <= {case['id'] for case in cases}: parser.error('未知案例 ID')
        requested.update(case['follows'] for case in cases if case['id'] in requested and case.get('follows'))
        cases = [case for case in cases if case['id'] in requested]
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(3)
    home = ROOT / '.runtime/deeptutor-golden' / run
    home.mkdir(parents=True)
    worker_python = Path(os.getenv('DEEPTUTOR_PYTHON', str(ROOT / '.venv-deeptutor' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python'))))
    if not worker_python.is_file(): parser.error('请先安装 DeepTutor 独立环境')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
    os.environ.update(TUTOR_COURSE='experimental-psychology-3', LLM_MOCK='0',
        DATABASE_URL='sqlite:///' + str(home / 'host.sqlite3'),
        DEEPTUTOR_BACKEND_URL=f'http://127.0.0.1:{port}', DEEPTUTOR_BRIDGE_TOKEN=secrets.token_hex(32),
        DEEPTUTOR_LLM_ENABLED='1', DEEPTUTOR_KNOWLEDGE_ENABLED='1',
        DEEPTUTOR_SESSION_SYNC='1', DEEPTUTOR_TURN_SYNC='1',
        CITATION_GROUNDING_MODE='active', CITATION_GROUNDING_INDEX=str(args.citation_index.resolve()),
        MEMORY_WORKER_ENABLED='0', VISUALIZATION_ON_DEMAND='0',
        RAG_RERANK_DEVICE='cpu', RAG_EMBED_DEVICE='cpu')
    os.environ.pop('COURSE_DATABASE_URL', None)
    subprocess.run([str(worker_python), '-B', str(ROOT / 'scripts/publish_deeptutor_course.py'), '--home', str(home)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    from integrations.deeptutor.client import DeepTutorBackend
    from scripts.check_deeptutor_sessions import wait_ready
    from llm.client import LLMClient, LLMError
    calls = []
    original_post, original_chat = DeepTutorBackend._post, LLMClient.chat

    def counted_post(self, path, payload):
        if path.endswith('/generate') and sum(call['path'].endswith('/generate') for call in calls) >= 180:
            raise LLMError('黄金集达到180次模型调用上限')
        messages = payload.get('messages', [])
        images = sum(part.get('type') == 'image_url' for message in messages if isinstance(message.get('content'), list) for part in message['content'])
        call = {'path': path, 'ok': False, 'images': images,
            'client_text_leaked': 'GOLDEN_FAKE_SELECTION_TEXT' in json.dumps(messages)}
        calls.append(call); started = time.monotonic()
        try:
            result = original_post(self, path, payload); call['ok'] = True
            return result
        finally:
            call['seconds'] = round(time.monotonic() - started, 2)
            print(json.dumps({'transport': path, 'ok': call['ok'], 'images': images, 'seconds': call['seconds']}), flush=True)

    def bounded_chat(self, *positional, **kwargs):
        if kwargs.get('timeout') is None: kwargs['timeout'] = 35
        return original_chat(self, *positional, **kwargs)

    DeepTutorBackend._post, LLMClient.chat = counted_post, bounded_chat
    # 裁图缓存也放隔离目录；不修改教材目录或真实学生数据。
    from knowledge import pdf_reader
    pdf_reader.CROPS = home / 'crops'
    from fastapi.testclient import TestClient
    from main import app
    from database.database import engine
    from knowledge.citation_index import CitationIndex
    from knowledge.grounding_text import normalized
    assert Path(engine.url.database).resolve().is_relative_to(home.resolve())
    records = pdf_reader.documents()
    versions = {record['document_id']: record['version'] for record in records}
    report = {'run': run, 'cases': [], 'passed': False, 'database_isolated': True, 'visualization_enabled': False}
    output = home / 'report.json'
    identities, payloads = {}, {}

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    with (home / 'worker.log').open('w', encoding='utf-8') as log:
        worker = subprocess.Popen([str(worker_python), '-B', str(ROOT / 'integrations/deeptutor/worker.py'), '--home', str(home), '--port', str(port)],
            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            wait_ready(DeepTutorBackend(), worker)
            with TestClient(app) as client:
                for case in cases:
                    identity = identities.get(case.get('follows')) or ('golden-' + secrets.token_hex(6), 'session-' + secrets.token_hex(6))
                    identities[case['id']] = identity
                    payload = {'student_id': identity[0], 'session_id': identity[1], 'account_type': 'test',
                        'request_id': secrets.token_hex(16), 'message': case['message']}
                    if case['kind'] == 'selection':
                        record = pdf_reader.document_for_chapter(2); section = record['sections'][1]
                        rect = section['rect'] | {'x1': .14, 'x2': .84, 'y2': min(.95, section['rect']['y2'] + .12)}
                        payload['selection'] = {'document_id': record['document_id'], 'version': record['version'],
                            'kind': 'text', 'rects': [rect], 'text': 'GOLDEN_FAKE_SELECTION_TEXT：这不是教材原文。'}
                    if case['kind'] == 'vision':
                        import fitz
                        record = pdf_reader.document_for_chapter(7)
                        with fitz.open(pdf_reader.pdf_path(record)) as pdf:
                            page = pdf[9]
                            rect = {'page': 10, 'x1': 84/page.rect.width, 'x2': 513/page.rect.width, 'y1': 104/page.rect.height, 'y2': 248/page.rect.height}
                        payload['selection'] = {'document_id': record['document_id'], 'version': record['version'], 'kind': 'area', 'rects': [rect]}
                    payloads[case['id']] = payload
                    start = time.monotonic(); offset = len(calls)
                    row = {'id': case['id'], 'name': case['name'], 'checks': {}, 'result': None}
                    report['cases'].append(row)
                    print(json.dumps({'case': case['id'], 'stage': 'start'}), flush=True)
                    try:
                        response = client.post('/api/chat', json=payload)
                        result = response.json(); row['result'] = result
                        row['checks'] = {'http_ok': response.status_code == 200, **checks_for(case, result, calls[offset:], versions)}
                        if payload.get('selection'):
                            pointer = result.get('selection_ref') or {}
                            row['checks']['selection_identity'] = all(pointer.get(key) == payload['selection'][key] for key in ('document_id', 'version'))
                        geometry = original_quotes = True
                        with closing(CitationIndex(args.citation_index)) as index:
                            for ref in result.get('pdf_references', []):
                                evidence = ref.get('evidence') or {}
                                selections = evidence.get('selections', [])
                                if evidence.get('quote'):
                                    document = index.document(evidence['document_id'], evidence['document_version'])
                                    original_quotes &= normalized(evidence['quote']) in normalized(document['text'])
                                if evidence.get('location_status') == 'exact': geometry &= bool(selections)
                                for selection in selections:
                                    pdf_reader.validate_selection(pdf_reader.PDFSelection(**{key: selection[key] for key in ('document_id', 'version', 'kind', 'rects')}))
                                if selections:
                                    rendered = '\n'.join(pdf_reader.evidence_text(selection['document_id'], selection['version'], selection['rects']) for selection in selections)
                                    geometry &= normalized(evidence['quote']) in normalized(rendered)
                        row['checks']['geometry_valid'] = geometry
                        row['checks']['quote_in_original'] = original_quotes
                    except Exception as error:
                        row['error'] = type(error).__name__; row['checks']['completed'] = False
                    row['seconds'] = round(time.monotonic() - start, 1)
                    row['calls'] = calls[offset:]; row['passed'] = all(row['checks'].values())
                    save(); print(json.dumps({'case': case['id'], 'passed': row['passed'], 'checks': row['checks']}, ensure_ascii=False), flush=True)
                first = next((row for row in report['cases'] if row['passed'] and row['result'].get('answer_status') == 'answered'), None)
                if first:
                    payload = payloads[first['id']]; result = first['result']
                    before = sum(call['path'].endswith('/generate') for call in calls)
                    replay = client.post('/api/chat', json=payload)
                    report['idempotency'] = replay.status_code == 200 and replay.json().get('conversation_id') == result['conversation_id'] and before == sum(call['path'].endswith('/generate') for call in calls)
                    query = {'student_id': payload['student_id'], 'session_id': payload['session_id'], 'task_revision': result['task_revision']}
                    events = client.get('/api/chat/tasks/' + result['task_id'] + '/events', params=query)
                    report['event_replay'] = events.status_code == 200 and 'event: sources' in events.text and 'event: done' in events.text
                    denied = client.get('/api/chat/tasks/' + result['task_id'] + '/events', params={**query, 'student_id': 'golden-unrelated'})
                    report['foreign_student_blocked'] = denied.status_code in {403, 404}
                report['transport_counts'] = dict(Counter(call['path'] for call in calls))
                report['passed'] = bool(first) and all(row['passed'] for row in report['cases']) and all(report.get(key) is True for key in ('idempotency', 'event_replay', 'foreign_student_blocked'))
        finally:
            worker.terminate()
            try: worker.wait(timeout=10)
            except subprocess.TimeoutExpired: worker.kill(); worker.wait(timeout=5)
            report['worker_stopped'] = worker.poll() is not None
            save()
    print(json.dumps({'passed': report['passed'], 'report': str(output), 'cases': len(report['cases']), 'transport_counts': report.get('transport_counts')}, ensure_ascii=False), flush=True)
    if not report['passed']: raise SystemExit(1)


if __name__ == '__main__': main()
