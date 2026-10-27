"""Q5只读快照到原生LearningStore的隔离候选；不接在线入口或修改旧库。"""
from copy import deepcopy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

EVENT = 'host.q5_snapshot_imported'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def read_snapshots(source: Path, *, student_id: str, course_id: str):
    if not student_id.strip() or not course_id.strip():
        raise ValueError('必须明确学生与课程')
    with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {'q5_learning_paths', 'q5_learning_modules', 'q5_learning_objectives',
                    'q5_learning_progress', 'q5_learning_bindings'}
        if not required <= tables:
            raise ValueError('快照缺少Q5表，不能视为空学习记录')
        paths = db.execute('SELECT * FROM q5_learning_paths WHERE student_id=? AND course_id=? ORDER BY path_id',
                           (student_id, course_id)).fetchall()
        output = []
        for path in paths:
            item = {'path': dict(path)}
            for key, table, order in (
                ('modules', 'q5_learning_modules', 'position, module_id'),
                ('objectives', 'q5_learning_objectives', 'module_id, position, objective_id'),
                ('progress', 'q5_learning_progress', 'objective_id'),
            ):
                item[key] = [dict(row) for row in db.execute(
                    f'SELECT * FROM {table} WHERE path_id=? ORDER BY {order}', (path['path_id'],))]
            item['bindings'] = [dict(row) for row in db.execute(
                'SELECT * FROM q5_learning_bindings WHERE student_id=? AND active_path_id=? ORDER BY session_id',
                (student_id, path['path_id']))]
            output.append(item)
        return output


def _json(value):
    return json.loads(value) if isinstance(value, str) else deepcopy(value)


def build_candidate(snapshot):
    from deeptutor.learning.models import KnowledgePoint, LearningModule, LearningProgress, LearningStage, TopicSource
    from deeptutor.learning.objective_relations import validate_objective_relations

    path = snapshot['path']
    if path['kind'] != 'mastery_goal':
        raise ValueError('教材导航仍由Q2拥有，不能迁成原生掌握路径')
    if not path['plan_confirmed'] or path['status'] != 'active':
        raise ValueError('仅转换已确认且活动的目标路径；草稿与离开状态保留待适配')
    native_id = 'q5-' + fingerprint([path['student_id'], path['course_id'], path['path_id']])[:32]
    modules, sources = [], {}
    known_modules = {row['module_id'] for row in snapshot['modules']}
    if len(known_modules) != len(snapshot['modules']):
        raise ValueError('模块身份重复')
    for row in snapshot['objectives']:
        if row['path_id'] != path['path_id'] or row['module_id'] not in known_modules:
            raise ValueError('目标不属于当前路径模块')
    for module in snapshot['modules']:
        if module['path_id'] != path['path_id']:
            raise ValueError('模块不属于当前路径')
        points = []
        for row in snapshot['objectives']:
            if row['module_id'] != module['module_id']:
                continue
            refs = _json(row['source_refs'])
            if not isinstance(refs, list) or not refs or any(not isinstance(ref, dict) for ref in refs):
                raise ValueError('学习目标缺少可追溯来源')
            ids = []
            for ref in refs:
                key = native_id + '-source-' + fingerprint(ref)[:20]
                ids.append(key)
                sources.setdefault(key, TopicSource(id=key, kind='file',
                    source_id=str(ref.get('document_id') or ''), label=str(ref.get('title') or row['name']),
                    position=len(sources), available=False,
                    metadata={'host_q5_source_ref': ref, 'requires_host_validation': True}))
            points.append(KnowledgePoint(id=row['objective_id'], name=row['name'],
                type=row['knowledge_type'], module_id=module['module_id'], topic_source_ids=ids,
                prerequisite_ids=_json(row['prerequisite_ids']),
                required_visual_tasks=_json(row['required_visual_tasks'])))
        if not points:
            raise ValueError('不能迁入空模块')
        modules.append(LearningModule(id=module['module_id'], name=module['name'],
            objective=module['objective'], order=module['position'],
            pass_threshold=module['pass_threshold'], knowledge_points=points))
    if not modules:
        raise ValueError('路径没有模块')
    validate_objective_relations(modules, sources.values())
    current = next((module for module in modules if module.id == path['current_module_id']), None)
    if current is None or path['current_objective_id'] not in {point.id for point in current.knowledge_points}:
        raise ValueError('原当前位置无法精确对应，禁止猜测或回到第一项')
    explained = {}
    point_ids = {point.id for module in modules for point in module.knowledge_points}
    for row in snapshot['progress']:
        if row['path_id'] != path['path_id'] or row['objective_id'] not in point_ids:
            raise ValueError('进度不属于当前目标')
        if row['explained']:
            explained[row['objective_id']] = {'summary': row['explanation_summary'], 'source': 'host_q5',
                                             'legacy_explained_at': row['explained_at']}
    for row in snapshot['bindings']:
        if row['student_id'] != path['student_id'] or row['active_path_id'] != path['path_id']:
            raise ValueError('会话绑定不属于当前学生路径')
    progress = LearningProgress(book_id=native_id, name=path['name'], modules=modules,
        current_module_id=current.id,
        current_kp_index=next(i for i, point in enumerate(current.knowledge_points) if point.id == path['current_objective_id']),
        current_stage=LearningStage.EXPLAIN, explained_objectives=explained,
        knowledge_types={point.id: point.type for module in modules for point in module.knowledge_points})
    return progress, list(sources.values())


def import_candidate(snapshot, store):
    """复用原生事务和事件作迁移收据；只应传入隔离候选store。"""
    from deeptutor.learning.models import TopicMetadata

    progress, sources = build_candidate(snapshot)
    digest = fingerprint(snapshot)
    outcome = 'imported'
    with store.transaction(progress.book_id, create=True) as tx:
        if tx.base_revision:
            receipts = [event for event in store.list_events(progress.book_id) if event.event_type == EVENT]
            if not receipts or receipts[-1].payload.get('snapshot_digest') != digest:
                raise ValueError('候选已存在或原快照已变化，禁止覆盖原生记录')
            outcome = 'already_imported'
        else:
            for name in ('name', 'modules', 'current_module_id', 'current_kp_index',
                         'current_stage', 'explained_objectives', 'knowledge_types'):
                setattr(tx.progress, name, deepcopy(getattr(progress, name)))
            tx.put_topic(TopicMetadata(path_id=progress.book_id, goal=snapshot['path']['goal'],
                                      status='archived'), sources)
            tx.emit(EVENT, {'schema': 'host-q5-migration/v1', 'snapshot_digest': digest,
                           'legacy_snapshot': snapshot, 'activated': False,
                           'unmapped': ['self_reported_understood', 'binding_modes_and_session_plans',
                                        'source_runtime_authorization', 'learner_profile', 'navigation_semantics',
                                        'legacy_command_receipts', 'host_formative_pending_questions']})
    return {'status': outcome, 'native_path_id': progress.book_id, 'snapshot_digest': digest,
            'modules': len(progress.modules), 'objectives': sum(len(m.knowledge_points) for m in progress.modules),
            'ready_for_cutover': False, 'activated': False}


def _candidate_session_state(snapshot, row, native_path_id):
    from deeptutor.capabilities.mastery.mode import MODES
    from models.session_study_plan import SessionStudyPlan

    path = snapshot['path']
    if row.get('mode') not in MODES or row.get('teaching_strategy') not in ('probe_first', 'teach_first'):
        raise ValueError('旧会话模式或教学顺序无效，禁止静默改成默认值')
    plan = _json(row.get('session_plan'))
    if plan is not None:
        plan = SessionStudyPlan.model_validate(plan)
        if ((plan.student_id, plan.course_id, plan.session_id) !=
                (path['student_id'], path['course_id'], row['session_id']) or
                plan.path_id not in (None, path['path_id'])):
            raise ValueError('本次安排不属于当前学生、课程、会话或路径')
        known = {item['objective_id'] for item in snapshot['objectives']}
        if any(item.objective_id and item.objective_id not in known for item in plan.items):
            raise ValueError('本次安排含当前路径之外的目标')
        # 完整旧安排已在LearningStore迁移收据中，公开会话偏好只保留恢复位置。
        plan = plan.model_dump(include={'plan_id', 'revision', 'path_revision', 'status', 'current_item_id'})
    return {'schema': 'host-q5-session-migration/v1', 'snapshot_digest': fingerprint(snapshot),
            'native_path_id': native_path_id, 'legacy_path_id': path['path_id'],
            'mode': row['mode'], 'teaching_strategy': row['teaching_strategy'],
            'legacy_session_plan': plan, 'session_plan_requires_revalidation': plan is not None,
            'self_reported_understood': [{'objective_id': item['objective_id'],
                'understood_at': item.get('understood_at')} for item in snapshot['progress'] if item.get('understood')],
            'assessed_mastery': False, 'activated': False}


async def _restore_candidate_session(session_id, state):
    from deeptutor.services.session import get_session_store

    store = get_session_store()
    session = await store.get_session(session_id)
    if session is None:
        raise ValueError('原生会话不存在，不能恢复模式')
    preferences = session.get('preferences') or {}
    receipt = preferences.get('heart_q5_session_migration')
    if receipt is not None:
        if receipt != state:
            raise ValueError('原生会话迁移收据与快照冲突')
        return 'already_restored'
    if await store.list_active_turns(session_id):
        raise ValueError('原生会话仍有活动回合，停止迁移会话状态')
    for key, expected in (('mastery_path_id', state['native_path_id']), ('mastery_session_mode', state['mode'])):
        if preferences.get(key) not in (None, '', expected):
            raise ValueError('原生会话已有不同路径或模式，禁止覆盖')
    # 同用原生偏好更新接口；不使用吞掉错误的best-effort模式助手。
    if not await store.update_session_preferences(session_id, {
            'mastery_path_id': state['native_path_id'], 'mastery_session_mode': state['mode'],
            'heart_q5_session_migration': state}):
        raise ValueError('原生会话状态恢复失败')
    saved = await store.get_session(session_id)
    if not saved or (saved.get('preferences') or {}).get('heart_q5_session_migration') != state:
        raise ValueError('原生会话状态恢复复核失败')
    return 'restored'


async def bind_candidate_sessions(snapshot, bridge):
    """在隔离原生home内复用真实用户/工作区映射；不激活候选或覆盖其他路径。"""
    from deeptutor.learning.storage import LearningStore
    from deeptutor.learning.service import LearningService
    from deeptutor.services.workspace import get_content_workspace_service
    from deeptutor.services.workspace.context import workspace_context
    from .session_bridge import SessionBindingRequest

    progress, _ = build_candidate(snapshot)
    path = snapshot['path']
    if not snapshot['bindings']:
        raise ValueError('没有可核验的活动会话绑定，不新造宿主会话')
    states = [_candidate_session_state(snapshot, row, progress.book_id) for row in snapshot['bindings']]
    requests = [SessionBindingRequest(student_id=path['student_id'], course_id=path['course_id'],
        course_title=path['name'][:60] or '学习迁移候选', session_id=row['session_id'])
        for row in snapshot['bindings']]
    bindings = []
    restored = []
    for request, state in zip(requests, states):
        mapped = await bridge.bind_scope(request)
        with bridge.user_scope(mapped['user_id']), workspace_context(mapped['workspace_id']):
            store = LearningStore()
            workspace = get_content_workspace_service().binding_by_id(mapped['workspace_id'])
            if not store.db_path.resolve().is_relative_to(workspace.root.resolve()):
                raise ValueError('学习库不属于当前原生工作区，停止绑定')
            current = store.path_id_for_session(mapped['native_session_id'])
            if current and current != progress.book_id:
                raise ValueError('原生会话已绑定其他路径，迁移不能静默切换')
            migration = import_candidate(snapshot, store)
            store.bind_session(progress.book_id, mapped['native_session_id'], owns_path=False)
            if store.path_id_for_session(mapped['native_session_id']) != progress.book_id:
                raise ValueError('原生会话路径绑定复核失败')
            restored.append(await _restore_candidate_session(mapped['native_session_id'], state))
            migration['native_service_loaded'] = LearningService(store).get_or_create(progress.book_id).book_id == progress.book_id
            migration['mastery_evidence_count'] = store.count_learning_evidence(progress.book_id)
            migration['workspace_store_verified'] = True
        bindings.append(mapped)
    migration['session_state_statuses'] = restored
    return {'migration': migration, 'bindings': bindings, 'activated': False, 'ready_for_cutover': False}
