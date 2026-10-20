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
                if request.selection:
                    from agents.pdf_selection_tutor import explain_selection
                    return explain_selection(tutor, request.student_id, request.message, request.selection,
                        request.account_type, progress, session_id=request.session_id,
                        request_id=request.request_id, reader_location=request.reader_location,
                        task_context=context, resolved_selection=resolved,
                        routing_interceptor=intercept, task_guard=guard)
                return tutor.handle_turn(request.student_id, request.message, request.learning_goal,
                    request.account_type, task_context=context, routing_interceptor=intercept, task_guard=guard)

            def check(result, *, chapter, previous=None, same=False, require_images=False):
                navigation = result.get('course_navigation') or {}
                quality = result.get('quality') or result.get('quality_check') or {}
                passed = (result.get('answer_status') == 'answered'
                    and bool(result.get('pdf_references') or result.get('selection_ref'))
                    and quality.get('passed') is True and not quality.get('issues')
                    and navigation.get('status') == 'ready' and bool(navigation.get('explained'))
                    and not navigation.get('covered') and navigation.get('chapter_id') == chapter)
                if require_images:
                    passed = passed and bool(result.get('image_refs'))
                if previous is not None:
                    passed = passed and ((navigation.get('id') == previous.get('id')) if same
                                         else (navigation.get('id') != previous.get('id')))
                return passed

            def run_scenario(name, messages, *, chapter, selection=None, same_last=False,
                             require_images=False, same_turns=()):
                previous = None
                for index, message in enumerate(messages):
                    started = time.monotonic()
                    payload = {'student_id': 'q2-nav-' + name, 'session_id': 'navigation-' + name,
                        'request_id': f'{name}-{index}', 'message': message, 'account_type': 'test',
                        'reader_location': {'chapter_id': 2, 'section_id': 1}}
                    if selection is not None and index == 0:
                        payload['selection'] = selection
                    try:
                        result = service.run(ChatRequest(**payload), execute)
                        navigation = result.get('course_navigation') or {}
                        passed = check(result, chapter=chapter, previous=previous,
                            same=index in same_turns or (same_last and index == len(messages) - 1),
                            require_images=require_images)
                        rows.append({'scenario': name, 'message': message,
                            'elapsed_seconds': round(time.monotonic() - started, 3),
                            'passed': passed, 'result': result})
                        previous = navigation
                    except Exception as exc:
                        rows.append({'scenario': name, 'message': message,
                            'elapsed_seconds': round(time.monotonic() - started, 3),
                            'passed': False, 'error': type(exc).__name__})
                        break
                    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                    print(json.dumps({'scenario': name, 'turn': index, 'passed': passed,
                        'status': result.get('answer_status')}, ensure_ascii=True), flush=True)

            run_scenario('explicit', ('学习第一章', '解释', '没听懂', '换说法',
                '我懂了，下一部分', '下一知识点'), chapter=1, same_turns=(1, 2, 3))

            run_scenario('within-point', ('学习第一章', '下一步推导', '继续这个例子'),
                chapter=1, same_turns=(1, 2))

            run_scenario('ordinary', ('请解释教材里的自变量，不要出题。',
                '我懂了，下一部分', '继续'), chapter=2)

            from knowledge.pdf_reader import PDFSelection, document_for_chapter
            record = document_for_chapter(2)
            section = next(item for item in record['sections'] if item['id'] == 2)
            rect = section['rect'] | {'x1': .14, 'x2': .84,
                'y2': min(.95, section['rect']['y2'] + .12)}
            selection = PDFSelection(document_id=record['document_id'], version=record['version'],
                kind='text', rects=[rect])
            run_scenario('selection', ('请解释我选中的自变量含义，并引用本次选区。不要出题。',
                '我懂了，下一部分'), chapter=2, selection=selection)

            run_scenario('visual', ('请解释教材图1-1说明了什么。',), chapter=1,
                require_images=True)
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
