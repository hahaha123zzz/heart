"""隔离原生SQLite/HTTP + 真实Q2来源和模型作答；教师批准为受控输入。"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env', override=False)
from llm.client import LLMClient


async def check(source_file, output):
    # 在隔离夹具替换环境前构造真实模型客户端，不输出配置或凭据。
    model = LLMClient(mock=False)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from agents.adaptive_tutoring import verified_sources
    from database.database import session_scope
    from database.learning_tasks import LearningTaskRepository
    from database.models import LearningTaskRow
    from database.repository import Repository
    from integrations.deeptutor.native_bridge import install_native_bridge, NativeTurnBridge
    from integrations.deeptutor.native_contract import NativeTurnStart, NativeTurnKey
    from tests.test_native_assessment import NativeAssessmentTests

    fixture = NativeAssessmentTests(methodName='test_original_tools_present_freeze_grade_and_restore_exactly_once')
    report = {'passed': False, 'teacher_review': 'controlled_input', 'browser_checked': False,
              'formal_service_changed': False, 'source_fixture': False}
    await fixture.asyncSetUp()
    try:
        fixture.source_check.stop()
        fixture.host.documents.stop()
        fixture.authority_patch.stop()
        source = json.loads(source_file.read_text(encoding='utf-8'))['response']['sources'][0]
        sources = verified_sources([source])
        assert len(sources) == 1, '当前Q2原文/版本核验失败'
        versions = {source['document_id']: source['version']}
        row, _, _ = LearningTaskRepository().claim(student_id='s', session_id='sess', request_id='ta2-live',
            payload={'message': 'TA2隔离测评'}, point='变量', epoch=0, memory_repo=Repository())
        with session_scope() as db:
            db.get(LearningTaskRow, row['id']).context = {'document_versions': versions}
        request = NativeTurnStart(**(fixture.host.payload | {'request_id': 'ta2-live', 'task_id': row['id'],
            'task_revision': row['revision'], 'material_versions': versions}),
            content='解释自变量', course_title='教材测评隔离')
        await fixture.bridge.start(request)
        await fixture.finished(request)
        root = request.model_dump(include=set(NativeTurnKey.model_fields))
        key = root | {'path_id': 'tool-path', 'question_id': 'ta2-live-question'}
        question = fixture.pending(question_id='ta2-live-question')
        headers = {'X-Heart-Bridge-Token': 't'*32}
        app = FastAPI()
        with patch.dict(os.environ, DEEPTUTOR_NATIVE_ENABLED='1', DEEPTUTOR_LLM_ENABLED='0'):
            install_native_bridge(app, fixture.sessions)
            with TestClient(app) as client:
                def post(endpoint, data):
                    response = client.post('/internal/heart/native/assessment/' + endpoint,
                        json=data, headers=headers)
                    assert response.status_code == 200, (response.status_code, response.text)
                    return response.json()
                posed = post('register', root | {'path_id': 'tool-path',
                    'question': question.model_dump(mode='json'), 'reviewer_id': 'controlled-review-for-isolation',
                    'key_version': 'ta2-live-v1', 'sources': sources,
                    'evidence_decision': {'status': 'sufficient', 'source_ids': [source['source_id']],
                                          'reason': '当前Q2原文和版本已核验'}})
                post('action', key | {'command_id': 'present', 'action': 'present'})
                for i, message in enumerate(('我懂了', '请解释这个变量')):
                    result = post('action', key | {'command_id': 'interject'+str(i), 'action': 'message', 'text': message})
                    assert result['message_action'] == 'interjection'
                    assert result['interaction_id'] == key['question_id']
                # 只提供公开题干和选项；不向独立作答者提供原文提示或私有答案键。
                public = posed['question']
                model_input = [{'role': 'system', 'content': '你是一名参加测验的学生。根据教材独立作答，只输出选项字母。'},
                    {'role': 'user', 'content': json.dumps(public, ensure_ascii=False)}]
                answer = await asyncio.to_thread(model.chat, model_input, max_tokens=100, timeout=60)
                post('action', key | {'command_id': 'answer', 'action': 'message', 'text': answer, 'confidence': .8})
                graded = post('action', key | {'command_id': 'grade', 'action': 'grade'})
                replay = post('action', key | {'command_id': 'grade', 'action': 'grade'})
                assert replay == graded
                assert graded['status'] == 'graded' and graded['assessment']['is_correct'] is True
                assert graded['evidence_summary']['independent'] == 1
                report.update(question=public, raw_model_answer=answer, graded=graded,
                    q2_source_id=source['source_id'], source_version=source['version'],
                    duplicate_grade_same=True, interjections_preserved=True)
            # 新建桥接与HTTP客户端，从原生持久库读取；不是复用前端本地状态。
            restored_app = FastAPI()
            install_native_bridge(restored_app, fixture.sessions)
            with TestClient(restored_app) as restored_client:
                result = restored_client.post('/internal/heart/native/assessment/status', json=key, headers=headers)
                assert result.status_code == 200 and result.json() == graded
            with NativeTurnBridge(fixture.sessions).learning_service(request) as service:
                progress = service.store.load('tool-path')
                assert len(progress.learning_evidence) == len(progress.quiz_attempts) == 1
                report['attempts'] = len(progress.quiz_attempts)
                report['evidence'] = len(progress.learning_evidence)
                report['restored_from_sqlite'] = True
                report['mastery'] = progress.mastery_levels
        report['passed'] = True
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        await fixture.asyncTearDown()
    print(json.dumps({'passed': report['passed'], 'report': str(output)}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-json', type=Path, required=True, help='真实宿主回答记录，含response.sources')
    parser.add_argument('--output', type=Path, default=ROOT / '.runtime/ta2' / ('live-'+uuid.uuid4().hex[:8]+'.json'))
    args = parser.parse_args()
    asyncio.run(check(args.source_json, args.output))
