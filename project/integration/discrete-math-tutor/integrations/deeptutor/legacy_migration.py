"""旧学习数据的一次性快照与原生导入；不推算掌握度、不改旧业务表。"""
import hashlib
import datetime as dt
import json
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from .native_contract import NativeScopeRequest


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def snapshot(student_id):
    from database.database import session_scope
    from database.models import (Student, ConversationRow, LearnerProfileRow, MemoryChangeRow,
        KnowledgeStateRow, MisconceptionRow, QuizAttemptRow, ExerciseSubmissionRow, LearningTaskRow, PDFCitationRow)
    from database.preference_provenance import confirmed_preferences
    def dump(row):
        return {column.name: getattr(row, column.name) for column in row.__table__.columns}
    with session_scope() as db:
        actor = db.get(Student, student_id)
        if actor is None:
            raise HTTPException(404, '学生账户不存在')
        account_created_at = actor.created_at.isoformat()
        archive = {model.__tablename__: [dump(row) for row in db.scalars(select(model).where(
            model.student_id == student_id).order_by(*model.__table__.primary_key.columns))]
            for model in (ConversationRow, LearnerProfileRow, MemoryChangeRow, KnowledgeStateRow,
                          MisconceptionRow, QuizAttemptRow, ExerciseSubmissionRow)}
        public_reference_fields = {'learning_cards', 'learning_response', 'pdf_references', 'image_refs',
                                   'textbook_sources', 'section_title', 'native_result', 'session_study_plan',
                                   'guided_visualization'}
        archive['conversation_references'] = [{'conversation_id': row.conversation_id,
            'reference': {key: value for key, value in (row.reference or {}).items()
                          if key in public_reference_fields}}
            for row in db.scalars(select(PDFCitationRow).join(ConversationRow,
                PDFCitationRow.conversation_id == ConversationRow.id).where(
                ConversationRow.student_id == student_id).order_by(PDFCitationRow.conversation_id))]
        profile = db.get(LearnerProfileRow, student_id)
        confirmed = confirmed_preferences(db, student_id, profile.preferences or {}) if profile else {}
        native_sessions = {row.session_id for row in db.scalars(select(LearningTaskRow).where(
            LearningTaskRow.student_id == student_id)) if (row.result or {}).get('native_result') is not None}
    # 快照内保留原始时间；序列化结果固定，预览与实施之间的数据变化必须重新预览。
    archive = json.loads(json.dumps(archive, ensure_ascii=False, default=lambda value: value.isoformat()))
    conversations = {}
    for row in archive['conversations']:
        if row['session_id'] and row['session_id'] not in native_sessions and row['role'] in ('user', 'assistant'):
            conversations.setdefault(row['session_id'], []).append(row)
    labels = {
        'answer_length': ('回答简短', '回答长度适中', '回答详细'),
        'example_density': ('少举例', '适量举例', '多举例'),
        'learning_pace': ('放慢学习节奏', '正常学习节奏', '紧凑学习节奏'),
        'explanation_order': ('先给结论再解释', '按问题选择讲解顺序', '先给情境再归纳概念'),
        'question_frequency': ('少提问', '必要时检查理解', '适当增加理解检查'),
        'teaching_sequence': ('先练后讲', '按问题安排讲练顺序', '先讲后练'),
    }
    preferences = [{'key': key, 'value': value, 'text': labels[key][(0., .5, 1.).index(value)]}
                   for key, value in sorted(confirmed.items()) if key in labels and value in (0., .5, 1.)]
    return {'schema': 1, 'student_id': student_id, 'account_created_at': account_created_at, 'archive': archive,
            'conversations': conversations, 'preferences': preferences}


class MigrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: str = Field(min_length=1, max_length=64)
    session_id: str = Field(default="legacy", min_length=1, max_length=64)
    action: str = Field(default='preview', pattern='^(preview|apply|archive)$')
    fingerprint: str = Field(default='', max_length=64, pattern='^[a-f0-9]*$')


class NativeMigrationRequest(NativeScopeRequest):
    snapshot: dict
    fingerprint: str = Field(pattern='^[a-f0-9]{64}$')


def handle(request: MigrationRequest):
    from database.task_locks import student_turn_lock
    from database.database import session_scope
    from database.models import LearningTaskRow
    from database.learning_tasks import ACTIVE
    from knowledge.course_config import COURSE_ID, COURSE_TITLE
    from .client import DeepTutorBackend
    from .runtime_config import native_enabled
    if not native_enabled():
        raise HTTPException(503, '原生数据迁移未启用')
    with session_scope() as db:
        from database.models import Student
        actor = db.get(Student, request.student_id)
        if actor is None:
            raise HTTPException(404, '学生账户不存在')
        account_created_at = actor.created_at.isoformat()
    root = Path(__file__).resolve().parents[2] / '.runtime/native-migration' / digest([request.student_id, COURSE_ID, account_created_at])
    with student_turn_lock(request.student_id):
        if request.action == 'archive':
            path = root / (request.fingerprint + '.json')
            if len(request.fingerprint) != 64 or not path.is_file():
                raise HTTPException(404, '旧数据快照不存在')
            saved = json.loads(path.read_text(encoding='utf8'))
            if saved['student_id'] != request.student_id:
                raise HTTPException(404, '旧数据快照不存在')
            return {'fingerprint': request.fingerprint, 'readonly': True, 'archive': saved['archive']}
        data = snapshot(request.student_id)
        fingerprint = digest(data)
        root.mkdir(parents=True, exist_ok=True)
        path = root / (fingerprint + '.json')
        if not path.exists():
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True), encoding='utf8')
            temp.replace(path)
        preview = {'fingerprint': fingerprint, 'sessions': len(data['conversations']),
            'messages': sum(map(len, data['conversations'].values())), 'preferences': data['preferences'],
            'archive_counts': {name: len(rows) for name, rows in data['archive'].items()},
            'mastery_converted': False}
        if request.action == 'preview':
            return preview
        if request.fingerprint != fingerprint:
            raise HTTPException(409, '旧数据已变化，请重新预览')
        with session_scope() as db:
            if db.scalar(select(LearningTaskRow.id).where(LearningTaskRow.student_id == request.student_id,
                                                         LearningTaskRow.status.in_(ACTIVE)).limit(1)):
                raise HTTPException(409, '请先结束当前任务，再迁移旧数据')
        result = DeepTutorBackend(timeout=180)._post('/internal/heart/native/migrate', {
            'student_id': request.student_id, 'session_id': request.session_id,
            'course_id': COURSE_ID, 'course_title': COURSE_TITLE,
            'snapshot': data, 'fingerprint': fingerprint})
        return {**preview, **result}


async def apply_native(bridge, request: NativeMigrationRequest):
    from deeptutor.multi_user.context import get_current_user
    from deeptutor.services.memory import get_memory_store
    from deeptutor.services.session import get_sqlite_session_store
    from deeptutor.services.workspace.context import workspace_context
    from deeptutor.services.file_io import atomic_write_text
    # 只接受经宿主身份绑定的完整快照，不接收目标物理路径或用户指定原生ID。
    if request.snapshot.get('student_id') != request.student_id or digest(request.snapshot) != request.fingerprint:
        raise HTTPException(422, '迁移快照身份或校验值不一致')
    mapped = await bridge.bind_scope(request)
    async with bridge.sessions.lock:
        with bridge.user_scope(mapped['user_id']), workspace_context(mapped['workspace_id']):
            folder = get_current_user().scope.root / 'heart-migration' / digest([request.course_id, request.snapshot['account_created_at']])
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / 'ledger.json'
            ledger = json.loads(path.read_text(encoding='utf8')) if path.exists() else {
                'fingerprint': request.fingerprint, 'preferences': {}, 'sessions': {},
                'before_preferences': get_memory_store().read_raw('L3', 'preferences')}
            def save():
                atomic_write_text(path, json.dumps(ledger, ensure_ascii=False, sort_keys=True))
            save()
            memory = get_memory_store()
            for item in request.snapshot['preferences']:
                if item['key'] in ledger['preferences']:
                    continue
                # 原生写入自带重复文本去重，崩溃后重跑不重复造条目。
                report = await memory.write_preference(op='add', text=item['text'], trace_id='chat')
                if not report.accepted:
                    raise HTTPException(409, '原生偏好导入未被接受')
                ledger['preferences'][item['key']] = {'source_value': item['value'],
                    'entry_id': report.results[0].entry_id, 'source': 'explicit_user'}
                save()
            store = get_sqlite_session_store()
            for host_session, rows in request.snapshot['conversations'].items():
                if host_session in ledger['sessions']:
                    continue
                from .native_bridge import digest as native_digest
                identity = native_digest([mapped['user_id'], request.course_id, host_session])
                standard = 'heart_native_' + identity
                if await store.get_messages(standard):
                    ledger['sessions'][host_session] = {'archived_only': True, 'reason': 'native_session_in_use'}
                    save()
                    continue
                native_id = 'imported_heart_' + identity
                messages = [{'role': row['role'], 'content': row['content'],
                    'created_at': dt.datetime.fromisoformat(row['created_at']).replace(tzinfo=dt.timezone.utc).timestamp(),
                    'metadata': {'heart_legacy_id': row['id'], 'heart_legacy_snapshot': request.fingerprint}}
                    for row in rows]
                if not messages:
                    continue
                await store.import_session(native_id, '旧对话 · ' + host_session[:60],
                    messages[0]['created_at'], messages[-1]['created_at'],
                    {'course_id': mapped['native_course_id'], 'workspace_id': mapped['workspace_id'], 'heart_native': True,
                     'import': {'source': 'heart_legacy', 'external_id': host_session}}, messages)
                imported = await store.get_messages(native_id)
                ledger['sessions'][host_session] = {'session_id': native_id,
                    'message_ids': {str(message['metadata']['heart_legacy_id']): message['id']
                                    for message in imported if message.get('metadata', {}).get('heart_legacy_id')}}
                save()
            ledger['complete'] = True
            save()
            return {'completed': True, 'mapping': ledger['sessions'],
                    'preference_entries': ledger['preferences'], 'mastery_converted': False}


def install(router, bridge):
    @router.post('/migrate')
    async def migrate(request: NativeMigrationRequest):
        return await apply_native(bridge, request)
