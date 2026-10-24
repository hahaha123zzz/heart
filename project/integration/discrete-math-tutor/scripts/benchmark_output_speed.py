"""隔离服务同配置交替成对验收；探索文字不算有效正文首字。"""
import argparse
import json
from pathlib import Path
import statistics
import time
import uuid
import httpx


def turn(url, payload, output, *, expected_status="answered"):
    started = time.monotonic()
    row = {'request': payload, 'events': [], 'first_progress': None,
           'first_answer_delta': None, 'answer_ready': None, 'result': None}
    try:
        with httpx.Client(trust_env=False, timeout=240) as client:
            with client.stream('POST', url + '/api/chat/stream', json=payload) as response:
                response.raise_for_status()
                event = ''
                for line in response.iter_lines():
                    if line.startswith('event:'):
                        event = line[6:].strip()
                    elif line.startswith('data:'):
                        data = json.loads(line[5:])
                        elapsed = time.monotonic() - started
                        row['events'].append({'event': event, 'seconds': elapsed, 'data': data})
                        if event == 'progress' and row['first_progress'] is None:
                            row['first_progress'] = elapsed
                        if event == 'answer_delta' and data.get('text') and row['first_answer_delta'] is None:
                            row['first_answer_delta'] = elapsed
                        if event == 'answer':
                            row['answer_ready'] = elapsed
                        if event == 'done':
                            row['result'] = data
        result = row['result'] or {}
        row['expected_status']=expected_status
        row['passed'] = result.get('answer_status') == expected_status
        # 被拒绝的草稿不能作为成功回答首字；另保留原始事件时间。
        row['effective_first_answer'] = row['first_answer_delta'] if row['passed'] and expected_status=='answered' else None
    except Exception as exc:
        row.update(passed=False, error_type=type(exc).__name__, error=str(exc))
    finally:
        row['seconds'] = time.monotonic() - started
        output.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding='utf8')
    return row


def summary(rows):
    output = {}
    for case in sorted({r['case'] for r in rows}):
        output[case] = {}
        for version in ('before', 'after'):
            group = [r for r in rows if r['case'] == case and r['version'] == version]
            good = [r for r in group if r['passed']]
            times = [r['seconds'] for r in good]
            first = [r['effective_first_answer'] for r in good if r['effective_first_answer'] is not None]
            output[case][version] = {'attempts': len(group), 'successes': len(good),
                'failure_rate': 1-len(good)/len(group) if group else None,
                'complete_median': statistics.median(times) if times else None,
                'complete_max': max(times) if times else None,
                'first_median': statistics.median(first) if first else None}
        before, after = output[case]['before'], output[case]['after']
        for key in ('complete_median', 'first_median'):
            output[case][key+'_improvement'] = (1-after[key]/before[key]
                if before[key] and after[key] else None)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', required=True)
    parser.add_argument('--after', required=True)
    parser.add_argument('--cases', required=True, type=Path,
                        help='JSON 数组，每项 id、message，可附 ChatRequest 的可信入口字段')
    parser.add_argument('--pairs', type=int, default=5)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.pairs < 1:
        parser.error('pairs 必须大于0')
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for pair in range(args.pairs):
        for case in json.loads(args.cases.read_text('utf8')):
            for version in (('before', 'after') if pair % 2 == 0 else ('after', 'before')):
                payload = {k:v for k,v in case.items() if k not in ('id','expected_status')}
                payload.update(student_id='speed-'+uuid.uuid4().hex[:16],
                               session_id='speed-benchmark', request_id=uuid.uuid4().hex)
                row = turn(getattr(args, version), payload,
                           args.output/f'{pair}-{case["id"]}-{version}.json',
                           expected_status=case.get('expected_status','answered'))
                row.update(case=case['id'], version=version, pair=pair)
                rows.append(row)
                (args.output/'summary.json').write_text(json.dumps(summary(rows), ensure_ascii=False, indent=2), encoding='utf8')
                print(json.dumps({k: row[k] for k in ('case','version','pair','passed','seconds') }), flush=True)


if __name__ == '__main__':
    main()
