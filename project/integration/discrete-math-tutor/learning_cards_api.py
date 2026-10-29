"""现有已发布展示卡片的状态；不持有题目、评分或学习路径写入权。"""
from copy import deepcopy
import os
from typing import Literal
from typing import Annotated
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from database.database import session_scope
from database.models import ConversationRow, PDFCitationRow
from database.repository import Repository

router = APIRouter(prefix='/api/learning/cards', tags=['learning-cards'])


class CardViewKey(BaseModel):
    model_config = ConfigDict(extra='forbid')
    student_id: str = Field(min_length=1, max_length=64)
    session_id: str = Field(min_length=1, max_length=64)
    conversation_id: int = Field(ge=1, strict=True)


class CardExpansion(CardViewKey):
    card_id: str = Field(min_length=1, max_length=100)
    command_id: str = Field(min_length=1, max_length=100)
    base_revision: int = Field(ge=0, strict=True)
    expanded: list[Annotated[int, Field(ge=0, le=6, strict=True)]] = Field(max_length=7)


class NativeCardAction(CardViewKey):
    card_id: str = Field(min_length=1, max_length=100)
    command_id: str = Field(min_length=1, max_length=100)
    base_revision: int = Field(ge=0, strict=True)
    action: Literal['set_expanded', 'submit_answer', 'grade', 'request_hint', 'view_explanation', 'defer', 'skip', 'return_path']
    text: str = Field(default='', max_length=4000)
    expanded: list[Annotated[int, Field(ge=0, le=6, strict=True)]] = Field(default_factory=list, max_length=7)


def _owned(db, request):
    owner = db.get(ConversationRow, request.conversation_id)
    row = db.get(PDFCitationRow, request.conversation_id)
    if (owner is None or row is None or owner.role != 'assistant' or owner.student_id != request.student_id
            or owner.session_id != request.session_id):
        raise HTTPException(404, '卡片不存在')
    reference = deepcopy(row.reference)
    cards = reference.get('learning_cards', [])
    epoch = Repository().memory_epoch(request.student_id, reference.get('section_title', ''))
    if any(card.get('memory_epoch') != epoch for card in cards):
        raise HTTPException(410, '学习记忆已变化，请重新提问')
    if reference.get('_native_assessment', {}).get('memory_epoch', epoch) != epoch:
        raise HTTPException(410, '测评记忆已变化')
    from knowledge.pdf_reader import document
    for card in cards:
        for source in card.get('source_refs', []):
            current = document(source['document_id'])
            if current is None or current['version'] != source['version']:
                raise HTTPException(410, '教材版本已变化')
    return row, reference, cards


@router.post('/view')
def view(request: CardViewKey):
    with session_scope() as db:
        _, reference, cards = _owned(db, request)
        native = reference.get('_native_assessment')
    if native:
        return _native(request, reference, cards, None)
    return {'learning_cards': cards}


def native_identity(request, reference):
    from integrations.deeptutor.native_contract import NativeTurnKey
    from knowledge.course_config import COURSE_ID
    if os.getenv('DEEPTUTOR_NATIVE_ENABLED', '0') != '1':
        raise HTTPException(503, '原生测评入口尚未启用')
    binding = reference.get('_native_assessment') or {}
    if (binding.get('student_id') != request.student_id or binding.get('session_id') != request.session_id
            or binding.get('course_id') != COURSE_ID):
        raise HTTPException(409, '题卡会话绑定已失效')
    try:
        key = NativeTurnKey.model_validate({k: binding.get(k) for k in NativeTurnKey.model_fields}).model_dump()
        target = {'path_id': binding['path_id'], 'question_id': binding['question_id']}
        if any(not isinstance(v, str) or not 1 <= len(v) <= 100 for v in target.values()):
            raise ValueError('invalid binding')
    except (ValueError, KeyError) as exc:
        raise HTTPException(409, '题卡服务端绑定无效') from exc
    return binding, key | target


def _native(request, reference, cards, action):
    from integrations.deeptutor.client import DeepTutorBackend, BackendUnavailable
    binding, key = native_identity(request, reference)
    if action:
        card = next((c for c in cards if c['card_id'] == request.card_id and c.get('schema') == 'learning-cards/v2'), None)
        if card is None:
            raise HTTPException(404, '题卡未登记')
        values = request.model_dump(exclude=set(CardViewKey.model_fields))
    else:
        values = {}
    try:
        result = DeepTutorBackend(timeout=25)._post('/internal/heart/native/assessment/cards/action' if action else
            '/internal/heart/native/assessment/cards', values | key)
    except (BackendUnavailable, ValueError) as exc:
        if getattr(exc.__cause__, 'code', None) == 409:
            raise HTTPException(409, '题卡状态已变化，请恢复后再操作') from exc
        raise HTTPException(503, '测评操作未确认，请恢复题卡后重试') from exc
    if not isinstance(result.get('learning_cards'), list) or len(result['learning_cards']) > 4:
        raise HTTPException(503, '题卡响应无效')
    with session_scope(immediate=True) as db:
        row, latest, old = _owned(db, request)
        if max((c.get('revision', 0) for c in old), default=0) > result.get('revision', 0):
            return {'learning_cards': old}
        epoch = (reference['learning_cards'][0]['memory_epoch'] if reference.get('learning_cards') else binding.get('memory_epoch'))
        if epoch is None:
            raise HTTPException(410, '题卡记忆身份已失效')
        latest['_native_assessment'] = {**latest.get('_native_assessment', {}), **binding, 'memory_epoch': epoch}
        latest['learning_cards'] = [dict(c, memory_epoch=epoch) for c in result['learning_cards']]
        row.reference = latest
    return result


@router.post('/action')
def native_action(request: NativeCardAction):
    with session_scope() as db:
        _, reference, cards = _owned(db, request)
    return _native(request, reference, cards, True)


@router.post('/expand')
def expand(request: CardExpansion):
    with session_scope(immediate=True) as db:
        row, reference, cards = _owned(db, request)
        card = next((c for c in cards if c['card_id'] == request.card_id), None)
        if card is None or 'set_expanded' not in card.get('allowed_actions', []):
            raise HTTPException(404, '卡片或动作未登记')
        if any(n > len(card.get('steps', [])) for n in request.expanded):
            raise HTTPException(422, '展开步骤不存在')
        receipts = reference.setdefault('_learning_card_receipts', {})
        payload = request.model_dump(exclude={'student_id', 'session_id', 'conversation_id'})
        receipt = receipts.get(request.command_id)
        if receipt:
            if receipt != payload:
                raise HTTPException(409, '重复命令参数冲突')
            return {'learning_cards': cards}
        if card.get('view_revision', 0) != request.base_revision:
            raise HTTPException(409, '卡片状态已变化，请恢复最新状态')
        if len(receipts) >= 128:
            raise HTTPException(409, '卡片交互次数已达上限')
        card['expanded'] = sorted(set(request.expanded))
        card['view_revision'] = request.base_revision + 1
        receipts[request.command_id] = payload
        row.reference = reference
        return {'learning_cards': cards}
