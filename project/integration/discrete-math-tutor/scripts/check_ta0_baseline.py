"""TA0只读身份盘点；--live用独立SQLite记录宿主基线，不启用原生或正式评分。"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
sys.path.insert(0, str(ROOT))
CORE = ('main.py', 'agents/task_service.py', 'agents/agent_loop_service.py', 'agents/adaptive_tutoring.py',
        'agents/q5_runtime.py', 'agents/q5_learning.py', 'agents/session_study_service.py',
        'database/learning_tasks.py', 'database/memory_management.py', 'database/q5_learning.py',
        'integrations/deeptutor/native_contract.py', 'integrations/deeptutor/native_bridge.py',
        'integrations/deeptutor/learning_migration.py', 'integrations/deeptutor/learning_tool_adapter.py',
        'integrations/deeptutor/learning_binding_adapter.py', 'integrations/deeptutor/learning_write_guard.py',
        'integrations/deeptutor/native_authorization.py', 'integrations/deeptutor/learning_sources.py',
        'integrations/deeptutor/client.py', 'agents/learning_feedback.py', 'agents/learning_cards.py',
        'llm/answer_events.py', 'frontend/learning-cards.js', 'frontend/index.html', 'scripts/check_ta0_baseline.py')
FLAGS = ('LOCAL_AGENT_LOOP_ENABLED', 'Q5_LEARNING_ENABLED', 'ADAPTIVE_TUTORING_ENABLED',
         'SELECTED_TEXT_AGENT_LOOP_ENABLED', 'DEEPTUTOR_NATIVE_ENABLED', 'LLM_MOCK',
         'Q3_RETRIEVAL_MODE', 'FIXED_BOOK_RETRIEVAL_ENABLED', 'DEEPTUTOR_LLM_ENABLED', 'DEEPTUTOR_AGENTIC_ENABLED')


def git(*args):
    return subprocess.check_output(['git', '-C', str(REPO), *args], text=True).strip()


def audit(remote_main):
    listeners = {}
    for port in (8000, 18001):
        with socket.socket() as sock:
            sock.settimeout(.3)
            listeners[str(port)] = sock.connect_ex(('127.0.0.1', port)) == 0
    versions = {}
    for name in ('fastapi', 'SQLAlchemy', 'openai', 'httpx', 'pydantic-settings', 'lightrag-hku'):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    spec = importlib.util.find_spec('deeptutor')
    return {'schema': 'ta0-baseline/v1', 'observed_at': datetime.now(timezone.utc).isoformat(),
        'head': git('rev-parse', 'HEAD'), 'local_main': git('rev-parse', 'main'),
        'remote_main_verified_by_caller': remote_main, 'cached_origin_main': git('rev-parse', 'origin/main'),
        'branch': git('branch', '--show-current'), 'listeners': listeners,
        'running_code_sha': None, 'deployment_verified': False,
        'python': sys.version.split()[0], 'packages': versions,
        'native_import': spec.origin if spec else None,
        'flags': {key: os.getenv(key, '0' if key != 'Q3_RETRIEVAL_MODE' else 'local') for key in FLAGS},
        'source_hashes': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in CORE},
        'cases': [], 'baseline_complete': False}


def snapshot(student):
    from sqlalchemy import func, select
    from database.database import session_scope
    from database.models import ConversationRow, ExerciseSubmissionRow, LearningTaskRow
    from database.q5_learning import Q5PathRow, Q5BindingRow
    with session_scope() as db:
        counts = {name: db.scalar(select(func.count()).select_from(model).where(model.student_id == student))
                  for name, model in (('paths', Q5PathRow), ('bindings', Q5BindingRow),
                                      ('tasks', LearningTaskRow), ('conversations', ConversationRow),
                                      ('exercise_submissions', ExerciseSubmissionRow))}
        counts['positions'] = [{'path_digest': hashlib.sha256(row.path_id.encode()).hexdigest(),
            'objective_digest': hashlib.sha256(row.current_objective_id.encode()).hexdigest(),
            'revision': row.revision} for row in db.scalars(select(Q5PathRow).where(Q5PathRow.student_id == student))]
        return counts


async def live(report, output):
    import httpx
    from main import app, orchestrator, _run_turn, _validate_pdf_request, health
    from models.chat_request import ChatRequest
    from knowledge.pdf_reader import document_for_chapter
    from practice_api import catalog

    counts, lock = Counter(), threading.Lock()
    sync_send, async_send = httpx.Client.send, httpx.AsyncClient.send
    def count(request):
        path = request.url.path.rstrip('/')
        name = 'model' if path.endswith(('/chat/completions', '/responses', '/messages')) else 'embedding' if path.endswith('/embeddings') else None
        if name:
            with lock:
                counts[name] += 1
    def send(client, request, *args, **kwargs):
        count(request)
        return sync_send(client, request, *args, **kwargs)
    async def asend(client, request, *args, **kwargs):
        count(request)
        return await async_send(client, request, *args, **kwargs)

    def turn(case_id, message, **extra):
        session = 'ask' if case_id.startswith('ask') else case_id
        student = 'ta0-' + output.name[-12:] + '-' + session
        orchestrator.memory.accounts.create_test_account(student, ttl_hours=24)
        request = ChatRequest(student_id=student, session_id=session, request_id=case_id + '-' + uuid.uuid4().hex[:10],
                              message=message, **extra)
        before = snapshot(student)
        calls, events = dict(counts), []
        started = time.monotonic()
        def emit(event, data):
            events.append({'event': event, 'ms': round((time.monotonic()-started)*1000, 3),
                'authoritative': bool(data.get('authoritative')), 'round_id': data.get('round_id')})
        row = {'id': case_id, 'before': before}
        result = {}
        try:
            _validate_pdf_request(request)
            result = _run_turn(request, answer_event=emit)
            row.update(status=result.get('answer_status'), loop_summary=result.get('loop_summary'),
                       formal_mastery=(result.get('teaching') or {}).get('formal_mastery'))
        except Exception as exc:
            row.update(status='error', error_type=type(exc).__name__, http_status=getattr(exc, 'status_code', None))
        row.update(complete_ms=round((time.monotonic()-started)*1000, 3),
            first_draft_ms=next((event['ms'] for event in events if event['event']=='answer_delta'), None),
            first_authoritative_ms=next((event['ms'] for event in events if event['authoritative']), None),
            model_http_attempts=counts['model']-calls.get('model', 0),
            embedding_http_attempts=counts['embedding']-calls.get('embedding', 0), after=snapshot(student))
        report['cases'].append(row)
        (output / (case_id + '.json')).write_text(json.dumps({'request': request.model_dump(), 'result': result, 'events': events}, ensure_ascii=False, indent=2), encoding='utf-8')
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({key: row[key] for key in ('id', 'status', 'complete_ms', 'model_http_attempts')}, ensure_ascii=False), flush=True)
        return result

    async with app.router.lifespan_context(app):
        report['isolated_health'] = health()
        from knowledge.course_release import validate
        release = validate(refresh=False)
        report['textbook_release'] = {key: release[key] for key in ('release_id', 'status', 'ready')}
        if report['isolated_health']['mock_mode']:
            raise ValueError('真实基线不能使用mock模型')
        with patch.object(httpx.Client, 'send', new=send), patch.object(httpx.AsyncClient, 'send', new=asend):
            await asyncio.to_thread(turn, 'chat', '直接解释教材中自变量的含义，不要出题。', reader_location={'chapter_id': 2, 'section_id': 2})
            await asyncio.to_thread(turn, 'learning', '按章导学第一章')
            record = document_for_chapter(2)
            section = next(item for item in record['sections'] if item['id'] == 2)
            await asyncio.to_thread(turn, 'selection', '直接解释我选中的教材内容，不要出题。', selection={
                'document_id': record['document_id'], 'version': record['version'], 'kind': 'text',
                'rects': [{'page': section['page'], 'x1': .08, 'y1': .15, 'x2': .92, 'y2': .45}]})
            book = catalog()
            if book['questions']:
                raise ValueError('当前固定样例预期心理学教材没有独立练习题，请先更新样例身份')
            await asyncio.to_thread(turn, 'practice_unavailable', '请解释这道题。', exercise_target={
                'question_id': 'ta0-no-exercise', 'part_id': '1', 'version': book['version']})
            paused = await asyncio.to_thread(turn, 'ask', '请先调用ask_user询问我想先学习自变量还是因变量，等我回答后再讲解。')
            if paused.get('loop_paused') and paused.get('task_id'):
                await asyncio.to_thread(turn, 'ask_resume', '自变量', task_id=paused['task_id'], task_revision=paused['task_revision'])
            report['baseline_complete'] = len(report['cases']) >= 5


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--remote-main', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.remote_main):
        parser.error('remote-main必须是只读核实的完整SHA')
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env', override=False)
    output = ROOT / '.runtime' / 'ta0' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
    output.mkdir(parents=True)
    if args.live:
        os.environ.update(DATABASE_URL='sqlite:///' + str(output / 'host.sqlite3'),
            COURSE_DATABASE_URL='sqlite:///' + str(output / 'course.sqlite3'),
            DEEPTUTOR_NATIVE_ENABLED='0', MEMORY_WORKER_ENABLED='0', CLEANUP_EXPIRED_ON_STARTUP='0',
            DEEPTUTOR_TURN_SYNC='0', DEEPTUTOR_SESSION_SYNC='0', VISUALIZATION_ON_DEMAND='0')
    report = audit(args.remote_main)
    try:
        if args.live:
            asyncio.run(live(report, output))
    finally:
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'report': str(output / 'report.json'), 'baseline_complete': report['baseline_complete']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
