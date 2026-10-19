"""Q2 目录导航复验；--live 使用真实模型和独立 SQLite，默认只核验原文。"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    home = ROOT / '.runtime' / 'course-navigation' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(3))
    home.mkdir(parents=True)
    os.environ.update(TUTOR_COURSE='experimental-psychology-3', LLM_MOCK='0',
        DATABASE_URL='sqlite:///' + str(home / 'host.sqlite3'),
        COURSE_DATABASE_URL='sqlite:///' + str(home / 'course.sqlite3'),
        MEMORY_WORKER_ENABLED='0', VISUALIZATION_ON_DEMAND='0', RAG_RERANK_DEVICE='cpu', RAG_EMBED_DEVICE='cpu')
    from knowledge.course_navigation import resolve, read_target
    from knowledge.course_config import PSYCHOLOGY_DIR
    index = PSYCHOLOGY_DIR / 'rag_index.sqlite3'
    before = hashlib.sha256(index.read_bytes()).hexdigest()
    target = resolve('我想要学习教材第一章的内容')
    source = read_target(target)[0]
    rows = [{'offline': True, 'target': target, 'source_characters': len(source.text),
             'passed': bool(source.source_spans and len(source.text) > 100)}]
    report = {'live': args.live, 'rows': rows, 'index_before': before}
    report_path = home / 'report.json'
    try:
        if args.live:
            from agents.task_service import TaskService
            from models.chat_request import ChatRequest
            from orchestrator import TutorOrchestrator
            tutor = TutorOrchestrator()
            service = TaskService(tutor)
            def execute(request, context, resolved, intercept, guard, progress):
                return tutor.handle_turn(request.student_id, request.message, request.learning_goal,
                    request.account_type, task_context=context, routing_interceptor=intercept, task_guard=guard)
            previous = None
            for i, message in enumerate(('我想要学习教材第一章的内容', '继续下一个知识点', '没听懂，请换个说法')):
                started = time.monotonic()
                result = service.run(ChatRequest(student_id='q2-nav', session_id='navigation', request_id=f'turn-{i}',
                    message=message, account_type='test', reader_location={'chapter_id': 2, 'section_id': 1}), execute)
                navigation = result.get('course_navigation') or {}
                passed = (result.get('answer_status') == 'answered' and bool(result.get('pdf_references'))
                    and result.get('quality', {}).get('passed') is True and not result.get('quality', {}).get('issues')
                    and bool(navigation.get('explained')) and not navigation.get('covered')
                    and navigation.get('chapter_id') == 1)
                if previous:
                    passed = passed and ((navigation.get('id') != previous.get('id')) if i == 1 else
                                         (navigation.get('id') == previous.get('id')))
                rows.append({'message': message, 'elapsed_seconds': round(time.monotonic() - started, 3),
                             'passed': passed, 'result': result})
                report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                print(json.dumps({'turn': i, 'passed': passed, 'status': result.get('answer_status')}, ensure_ascii=True), flush=True)
                previous = navigation
    except Exception as exc:
        report['error'] = type(exc).__name__
        raise
    finally:
        report['index_after'] = hashlib.sha256(index.read_bytes()).hexdigest()
        report['passed'] = all(row['passed'] for row in rows) and report['index_after'] == before and not report.get('error')
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(report_path, flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
