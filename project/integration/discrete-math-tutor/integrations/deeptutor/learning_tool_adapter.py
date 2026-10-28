"""原生mastery工具工厂的请求上下文适配，不替换全局LearningStore。"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .client import BackendUnavailable
from .native_contract import NativeTaskCheck

_scope = ContextVar('heart_native_learning_tools', default=None)
_managed_users = set()


@dataclass(frozen=True)
class LearningToolContext:
    check: NativeTaskCheck
    user_id: str
    workspace_id: str
    session_id: str
    submission_id: str


def current_learning_context():
    from deeptutor.multi_user.context import get_current_user_or_none
    from deeptutor.services.workspace.context import current_workspace_id

    current = _scope.get()
    user = get_current_user_or_none()
    if current is None:
        if user is not None and (user.id in _managed_users or user.username.startswith('heart_native_')):
            raise BackendUnavailable('宿主管理的原生工具缺少任务授权上下文')
        return None
    if user is None or user.id != current.user_id or current_workspace_id() != current.workspace_id:
        raise BackendUnavailable('原生学习工具的账户或工作区与宿主授权不匹配')
    return current


def install_learning_tool_factory(managed_users=()):
    from deeptutor.capabilities.mastery import tools

    _managed_users.update(managed_users)
    from .learning_binding_adapter import install_learning_binding_adapter
    install_learning_binding_adapter()
    install_learning_answer_adapter()
    original = tools._new_service
    if getattr(original, '_heart_scoped_factory', False):
        return
    if original.__module__ != tools.__name__:
        raise BackendUnavailable('原生学习工具工厂已被其他实现替换')
    from .worker import VENDOR_ROOT
    source = VENDOR_ROOT / 'deeptutor/capabilities/mastery/tools.py'
    pin = json.loads((VENDOR_ROOT / 'UPSTREAM_SNAPSHOT.json').read_text(encoding='utf-8'))
    if Path(tools.__file__).resolve() != source.resolve() or hashlib.sha256(source.read_bytes()).hexdigest() != pin['files']['deeptutor/capabilities/mastery/tools.py']:
        raise BackendUnavailable('原生学习工具与固定上游源码不一致')

    def new_service():
        from .assessment_store import HostAssessmentStore, HostAssessmentService

        current = current_learning_context()
        if current is None:
            return original()
        return HostAssessmentService(HostAssessmentStore(current.check))

    new_service._heart_scoped_factory = True
    tools._new_service = new_service


def install_learning_answer_adapter():
    """上游下一轮题卡提交也使用同一门禁；不替换全局LearningService。"""
    from deeptutor.services.session.turns.learning_adapter import LearningTurnAdapter
    original = LearningTurnAdapter._commit_mastery_card_answer
    if getattr(original, '_heart_scoped_answer', False):
        return
    from .worker import VENDOR_ROOT
    source = VENDOR_ROOT / 'deeptutor/services/session/turns/learning_adapter.py'
    pin = json.loads((VENDOR_ROOT / 'UPSTREAM_SNAPSHOT.json').read_text(encoding='utf-8'))
    if (Path(original.__code__.co_filename).resolve() != source.resolve()
            or hashlib.sha256(source.read_bytes()).hexdigest() != pin['files']['deeptutor/services/session/turns/learning_adapter.py']):
        raise BackendUnavailable('原生题卡提交与固定上游源码不一致')

    async def commit(self, *, path_id, session_id, turn_id, question_id, answer):
        current = current_learning_context()
        if current is None:
            return await original(self, path_id=path_id, session_id=session_id,
                                  turn_id=turn_id, question_id=question_id, answer=answer)
        if current.session_id != session_id:
            raise BackendUnavailable('题卡提交会话与宿主授权不匹配')
        import asyncio
        from .assessment_store import HostAssessmentStore, HostAssessmentService
        from .assessment_commands import AssessmentCommands
        def record():
            commands = AssessmentCommands(HostAssessmentService(HostAssessmentStore(current.check)))
            command_id = hashlib.sha256(json.dumps([session_id, turn_id, question_id]).encode()).hexdigest()
            return commands.run(path_id, question_id, command_id=command_id, action='message', text=answer)
        await asyncio.to_thread(record)

    commit._heart_scoped_answer = True
    LearningTurnAdapter._commit_mastery_card_answer = commit


@contextmanager
def learning_tool_scope(entry):
    install_learning_tool_factory((entry['user_id'],))

    check = NativeTaskCheck(**{key: entry[key] for key in NativeTaskCheck.model_fields
                             if key not in ('memory_epoch', 'material_versions')},
        memory_epoch=entry['memory_epoch'], material_versions=json.loads(entry['material_versions']))
    token = _scope.set(LearningToolContext(check, entry['user_id'], entry['workspace_id'],
                                         entry['native_session_id'], entry['submission_id']))
    try:
        yield
    finally:
        _scope.reset(token)
