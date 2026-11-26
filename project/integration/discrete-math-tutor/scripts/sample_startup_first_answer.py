"""启动后第一问分段：复核账号登录、正常 /ws 发教材题、记录首个检索/正文/来源/done。

只记录事件类型、阶段、耗时与数量；不落教材原文或账号凭据。
"""
import argparse
import asyncio
import http.cookiejar
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def password_from(creds: Path, username: str) -> str:
    lines = [line for line in creds.read_text(encoding='utf-8').splitlines()
             if line.startswith(username + '\t')]
    if not lines:
        raise SystemExit('账号不存在：' + username)
    return lines[-1].split('\t', 1)[1]


def login(base: str, username: str, password: str) -> str:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    request = urllib.request.Request(base + '/api/auth/login',
        data=json.dumps({'username': username, 'password': password}).encode(),
        headers={'Content-Type': 'application/json'})
    with opener.open(request, timeout=30) as response:
        response.read()
    for cookie in jar:
        if cookie.name == 'dt_token':
            return 'dt_token=' + cookie.value
    raise SystemExit('登录未返回 dt_token')


def marks(message: dict) -> dict:
    """只保留可报告的字段，避免把正文或凭据写进分段记录。"""
    kind = message.get('type')
    stage = message.get('stage') or ''
    source = message.get('source') or ''
    row = {'kind': kind,
           'event_stage': stage if isinstance(stage, str) and len(stage) <= 80 else '',
           'event_source': source if isinstance(source, str) and len(source) <= 80 else ''}
    content = message.get('content')
    if isinstance(content, str):
        row['chars'] = len(content)
    metadata = message.get('metadata') if isinstance(message.get('metadata'), dict) else {}
    for key in ('name', 'tool'):
        value = metadata.get(key)
        if isinstance(value, str) and len(value) <= 80:
            row['tool'] = value
            break
    if isinstance(metadata.get('sources'), list):
        row['source_count'] = len(metadata['sources'])
    summary = metadata.get('cost_summary') or metadata.get('usage_summary')
    if isinstance(summary, dict):
        for key in ('prompt_tokens', 'completion_tokens'):
            value = summary.get(key)
            if isinstance(value, int):
                row[key] = value
    return row


async def await_acceptable(ws, session_id, record, *, label='first', since=None, timeout=60):
    """从 done 起询问活跃回合，直到服务报告没有活跃回合。"""
    if not session_id:
        return 0.0
    began = time.perf_counter() if since is None else since
    deadline = time.perf_counter() + timeout
    status = 'no_response'
    while time.perf_counter() < deadline:
        await ws.send(json.dumps({'type': 'check_active_turn', 'protocol_version': '2.0',
                                  'session_id': session_id}))
        try:
            message = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        except (asyncio.TimeoutError, TimeoutError):
            status = 'no_response'
            break
        if message.get('type') == 'protocol_error':
            status = 'protocol_error:' + str(message.get('error_code') or '')
            break
        if message.get('type') != 'active_turn_info':
            continue
        status = str(message.get('status') or 'none')
        if status in ('none', 'completed', 'failed', 'cancelled'):
            break
        await asyncio.sleep(.2)
    waited = time.perf_counter() - began
    record('sample.acceptable', parent='sample.turn', seconds=waited, turn=label, status=status)
    return waited


class TurnRejected(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


async def run_turn(ws, record, question: str, session_id=None, label='first', submission=None):
    sent = time.perf_counter()
    payload = {'type': 'start_turn', 'protocol_version': '2.0',
               'client_submission_id': submission or label + '-' + uuid4().hex[:12],
               'content': question}
    if session_id:
        payload['session_id'] = session_id
    await ws.send(json.dumps(payload, ensure_ascii=False))
    found = {'session_id': session_id, 'events': 0, 'chars': 0, 'tool_calls': 0, 'sources': 0}
    seen = set()
    while True:
        message = json.loads(await asyncio.wait_for(ws.recv(), timeout=300))
        seconds = time.perf_counter() - sent
        row = marks(message)
        found['events'] += 1
        found['chars'] += row.get('chars', 0)
        kind = row['kind']
        if kind == 'tool_call':
            found['tool_calls'] += 1
        if row.get('source_count'):
            found['sources'] = max(found['sources'], row['source_count'])
        for key in ('prompt_tokens', 'completion_tokens'):
            if key in row:
                found[key] = row[key]
        if kind == 'session' and not found['session_id']:
            metadata = message.get('metadata')
            found['session_id'] = message.get('session_id') or (
                metadata.get('session_id') if isinstance(metadata, dict) else None)
        for mark, condition in (
                ('first_event', True),
                ('first_text', kind == 'content' and row.get('chars', 0) > 0),
                ('first_tool_call', kind == 'tool_call'),
                ('first_sources', kind == 'sources'),
                ('done', kind == 'done')):
            key = label + '.' + mark
            if condition and key not in seen:
                seen.add(key)
                record('sample.' + mark, parent='sample.turn', seconds=seconds, turn=label, **row)
        if kind == 'protocol_error' or kind == 'error':
            record('sample.protocol_error', parent='sample.turn', seconds=seconds, turn=label,
                   kind=kind, error_code=str(message.get('error_code') or '')[:80])
            raise TurnRejected(str(message.get('error_code') or kind))
        if kind == 'done':
            found['done_at'] = time.perf_counter()
            record('sample.usage', parent='sample.turn', seconds=seconds, turn=label,
                   events=found['events'], chars=found['chars'], tool_calls=found['tool_calls'],
                   sources=found['sources'], prompt_tokens=found.get('prompt_tokens'),
                   completion_tokens=found.get('completion_tokens'))
            break
    found['seconds'] = time.perf_counter() - sent
    return found


async def run_second_turn(ws, record, question, session_id, submission, done_at, deadline=60):
    """上一回合 done 后协调租约可能仍在；用同一提交 ID 重试直到服务真正接收。"""
    attempts = 0
    while True:
        attempts += 1
        try:
            found = await run_turn(ws, record, question, session_id, label='second', submission=submission)
            record('sample.second_accepted', parent='sample.turn',
                   seconds=time.perf_counter() - done_at, turn='second', attempts=attempts)
            return found
        except TurnRejected as exc:
            waited = time.perf_counter() - done_at
            record('sample.second_retry', parent='sample.turn', seconds=waited, turn='second',
                   attempts=attempts, error_code=exc.code)
            if waited >= deadline:
                raise
            await asyncio.sleep(.25)


async def run(args):
    os.environ['STARTUP_SERVICE'] = 'sample'
    os.environ['STARTUP_TRACE_DIR'] = str(args.trace_dir)
    if args.startup_id:
        os.environ['STARTUP_ID'] = args.startup_id
    from knowledge.startup_trace import current
    trace = current()
    began = time.perf_counter()
    trace.record('sample.begin', parent='sample', seconds=0, base=args.base,
                 question_class=args.question_class)
    try:
        password = password_from(args.creds, args.username)
        cookie = login(args.base, args.username, password)
        trace.record('sample.login', parent='sample', seconds=time.perf_counter() - began)
        try:
            import websockets
        except ImportError:
            raise SystemExit('websockets 未安装，无法连接 /ws')
        headers = {'Cookie': cookie, 'Origin': args.base}
        try:
            connect = websockets.connect
            ws = await connect(args.ws, additional_headers=headers, open_timeout=30, max_size=8_000_000)
        except TypeError:
            ws = await websockets.connect(args.ws, extra_headers=headers, open_timeout=30, max_size=8_000_000)
        async with ws:
            trace.record('sample.connected', parent='sample', seconds=time.perf_counter() - began)
            run_id = uuid4().hex[:12]
            first = await run_turn(ws, trace.record, args.question, label='first',
                                   submission=run_id + '-first')
            accepted = await await_acceptable(ws, first['session_id'], trace.record, label='first',
                                              since=first.get('done_at'))
            trace.record('sample.turn', parent='sample', seconds=first['seconds'], turn='first',
                         events=first['events'], chars=first['chars'],
                         tool_calls=first['tool_calls'], sources=first['sources'],
                         prompt_tokens=first.get('prompt_tokens'),
                         completion_tokens=first.get('completion_tokens'),
                         done_to_acceptable=accepted)
            second = await run_second_turn(ws, trace.record, args.question, first['session_id'],
                                           run_id + '-second', first.get('done_at'))
            trace.record('sample.turn', parent='sample', seconds=second['seconds'], turn='second',
                         events=second['events'], chars=second['chars'],
                         tool_calls=second['tool_calls'], sources=second['sources'],
                         prompt_tokens=second.get('prompt_tokens'),
                         completion_tokens=second.get('completion_tokens'))
        trace.record('sample.done', parent='sample', seconds=time.perf_counter() - began,
                     first_seconds=first['seconds'], second_seconds=second['seconds'])
        print(json.dumps({'startup_id': trace.startup_id, 'first': first['seconds'],
                          'second': second['seconds'], 'first_events': first['events'],
                          'first_chars': first['chars'], 'first_tools': first['tool_calls'],
                          'first_sources': first['sources'],
                          'first_prompt_tokens': first.get('prompt_tokens'),
                          'first_completion_tokens': first.get('completion_tokens')},
                         ensure_ascii=False))
    except BaseException as exc:
        trace.record('sample.failed', parent='sample', seconds=time.perf_counter() - began,
                     status='cancelled' if type(exc).__name__ == 'CancelledError' else 'failed',
                     error=type(exc).__name__)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--ws', default='ws://127.0.0.1:8000/ws')
    parser.add_argument('--creds', type=Path, required=True)
    parser.add_argument('--trace-dir', type=Path, required=True)
    parser.add_argument('--startup-id', default=None)
    parser.add_argument('--username', default='heart-review-01')
    parser.add_argument('--question', default='自变量是什么')
    parser.add_argument('--question-class', default='fixed_sample_textbook')
    asyncio.run(run(parser.parse_args()))


if __name__ == '__main__':
    main()
