"""隔离服务的真实 HTTP/SSE 验收；不替换模型，不启动服务，不读取密钥。"""
import argparse
import json
from pathlib import Path
import sqlite3
import time
import urllib.request
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True, help='已经启动的隔离服务地址')
    parser.add_argument('--database', required=True, type=Path, help='该隔离服务的课程 SQLite；只读查询')
    parser.add_argument('--report-dir', required=True, type=Path)
    args = parser.parse_args()
    args.report_dir.mkdir(parents=True, exist_ok=True)
    run = uuid4().hex[:12]
    student = 'input-check-' + run
    records = []
    report = args.report_dir / (run + '.json')

    def snapshot(session):
        with sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute('SELECT id,revision,status,context,result FROM learning_tasks '
                'WHERE student_id=? AND session_id=? ORDER BY created_at DESC LIMIT 3', (student, session))
            return [dict(row, context=json.loads(row['context']), result=json.loads(row['result'])) for row in rows]

    def ask(name, message, session='general', previous=None, option=None, reader=None):
        session = run + '-' + session
        payload = dict(student_id=student, session_id=session, account_type='test',
                       request_id=uuid4().hex, message=message)
        if previous:
            payload.update(task_id=previous['task_id'], task_revision=previous['task_revision'])
        if option:
            payload['selected_option'] = option
        if reader:
            payload['reader_location'] = reader
        row = dict(name=name, payload=payload, before=snapshot(session))
        records.append(row)
        started = time.perf_counter()
        try:
            request = urllib.request.Request(args.base_url.rstrip('/') + '/api/chat/stream',
                data=json.dumps(payload).encode('utf8'), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=180) as response:
                row['sse'] = response.read().decode('utf8')
            packet = next(p for p in row['sse'].replace('\r\n', '\n').split('\n\n') if 'event: done' in p)
            row['result'] = json.loads(next(line[6:] for line in packet.splitlines() if line.startswith('data: ')))
        except Exception as exc:
            row['error'] = type(exc).__name__ + ': ' + str(exc)
            raise
        finally:
            row.update(seconds=round(time.perf_counter() - started, 3), after=snapshot(session))
            report.write_text(json.dumps(dict(run=run, student=student, rows=records),
                                         ensure_ascii=False, indent=2), encoding='utf8')
        print(json.dumps(dict(name=name, status=row['result'].get('answer_status'), seconds=row['seconds']),
                         ensure_ascii=False), flush=True)
        return row['result']

    ask('definition', '什么是自变量？请用一个日常实验举例，先讲解，不要出题。', reader=dict(chapter_id=2, section_id=2))
    ask('reference_example', '刚才那个例子，再通俗解释一遍，不要换例子。')
    ask('negation', '不要告诉我完整答案，只给一个提示，不要出题。')
    ask('scoped_preferences', '以后详细一点，但这一题直接给答案：自变量和因变量有什么区别？')
    ask('guided_question', '请用一道含 A、B、C 三个选项的题考考我对自变量的理解，先不要公布答案。',
        session='quiz', reader=dict(chapter_id=2, section_id=2))
    ask('question_about_option', '为什么 B 不对？我是在问选项，不是提交答案。', session='quiz')
    ask('negated_answer', '我不选 B。', session='quiz')
    ask('composite_resume', '先解释“操作性定义”这个词，再回到原来的题，不要替我作答。',
        session='quiz', reader=dict(chapter_id=1, section_id=1))
    ask('return_question', '回到原来的题，我还没作答。', session='quiz')
    paused = ask('clarify', '先用问题卡问我想详细还是简短，再解释效度。', session='clarify')
    ask('clarify_resume', '第二个', session='clarify', previous=paused)
    ask('isolated_reference', '刚才那个例子，再讲一遍。', session='isolated')
    proposed = ask('plan', '帮我安排今天20分钟学习第二章自变量和因变量，我零基础，只讲解不测验。', session='plan')
    options = (proposed.get('clarification') or {}).get('options') or []
    selected = next((o.get('id') for o in options if o.get('id') == 'q5sp:confirm'), None)
    confirmed = ask('plan_confirm', '确认开始', session='plan', previous=proposed, option=selected)
    ask('plan_interjection', '先解释一下信度，不要推进当前活动。', session='plan')
    ask('plan_return', '回到刚才的学习安排，继续解释当前活动，不要切到下一步。', session='plan')

    by_name = {row['name']: row for row in records}

    def context(name):
        row = by_name[name]
        return next(t['context'] for t in row['after'] if t['id'] == row['result']['task_id'])

    def pending(name):
        return context(name)['tutoring']['progress']['pending_question']['question_id']

    for row in records:
        expected = 'awaiting_clarification' if row['name'] in ('clarify', 'plan') else 'answered'
        assert row['result']['answer_status'] == expected, (row['name'], row['result']['answer_status'])
        understood = context(row['name'])['input_understanding']
        assert understood['parser'] == 'rule' and understood['model_calls'] == 0, row['name']
    original = pending('guided_question')
    for name in ('question_about_option', 'negated_answer', 'composite_resume', 'return_question'):
        assert pending(name) == original, name
        assert context(name)['tutoring']['assessment'] is None, name
    assert by_name['composite_resume']['result']['input_resume_question_id'] == original
    restored = context('clarify_resume')['input_understanding']
    assert restored['reply_envelope']['raw_text'] == '第二个'
    assert restored['envelope']['raw_text'] == by_name['clarify']['payload']['message']
    assert by_name['clarify']['result']['task_id'] == by_name['clarify_resume']['result']['task_id']
    assert confirmed['q5_status']['session_plan']['status'] == 'active'
    current = confirmed['q5_status']['session_plan']['current_item_id']
    for name in ('plan_interjection', 'plan_return'):
        assert by_name[name]['result']['q5_status']['session_plan']['current_item_id'] == current
    assert by_name['scoped_preferences']['result']['style_suggestion']['origin'] == 'explicit_request'
    print('HTTP 状态、原题身份、零额外理解调用、澄清原话和计划位置检查通过。')
    print('此结果不替代回答语义人工复核、跨入口页面验收或性能基准。')
    print(report)


if __name__ == '__main__':
    main()
