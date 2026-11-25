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
    return row


async def run_turn(ws, record, question: str, session_id=None, label='first'):
    sent = time.perf_counter()
    payload = {'type': 'start_turn', 'protocol_version': '2.0',
               'client_submission_id': label + '-1', 'content': question}
    if session_id:
        payload['session_id'] = session_id
    await ws.send(json.dumps(payload, ensure_ascii=False))
    found = {'session_id': session_id, 'events': 0, 'chars': 0}
    seen = set()
    while True:
        message = json.loads(await asyncio.wait_for(ws.recv(), timeout=300))
        seconds = time.perf_counter() - sent
        row = marks(message)
        found['events'] += 1
        found['chars'] += row.get('chars', 0)
        kind = row['kind']
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
            raise SystemExit('回合失败：%s %s' % (message.get('error_code'), message.get('message')))
        if kind == 'done':
            break
    found['seconds'] = time.perf_counter() - sent
    return found


async def run(args):
    os.environ['STARTUP_SERVICE'] = 'sample'
    os.environ['STARTUP_TRACE_DIR'] = str(args.trace_dir)
    if args.startup_id:
        os.environ['STARTUP_ID'] = args.startup_id
    from knowledge.startup_trace import current
    trace = current()
    began = time.perf_counter()
    trace.record('sample.begin', parent='sample', seconds=0, base=args.base,
                 question_class='fixed_sample_textbook')
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
            first = await run_turn(ws, trace.record, args.question, label='first')
            trace.record('sample.turn', parent='sample', seconds=first['seconds'], turn='first',
                         events=first['events'], chars=first['chars'])
            second = await run_turn(ws, trace.record, args.question, first['session_id'], label='second')
            trace.record('sample.turn', parent='sample', seconds=second['seconds'], turn='second',
                         events=second['events'], chars=second['chars'])
        trace.record('sample.done', parent='sample', seconds=time.perf_counter() - began,
                     first_seconds=first['seconds'], second_seconds=second['seconds'])
        print(json.dumps({'startup_id': trace.startup_id, 'first': first['seconds'],
                          'second': second['seconds'], 'first_events': first['events'],
                          'first_chars': first['chars']}, ensure_ascii=False))
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
    asyncio.run(run(parser.parse_args()))


if __name__ == '__main__':
    main()
