"""应用内正式复习列表；宿主仅投影原生状态，不重算间隔或评分。"""
import os
import json
from copy import deepcopy
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import Field
from sqlalchemy import select
from database.database import session_scope
from database.models import ConversationRow, PDFCitationRow, Student
from integrations.deeptutor.client import DeepTutorBackend, BackendUnavailable
from learning_cards_api import CardViewKey, _owned, native_identity

router = APIRouter(prefix='/api/learning/reviews', tags=['learning-review'])


class ReviewHostAction(CardViewKey):
    review_id: str = Field(min_length=1, max_length=100)
    command_id: str = Field(min_length=1, max_length=100)
    base_revision: int = Field(ge=0, strict=True)
    action: Literal['start', 'defer', 'finish', 'return']
    delay_hours: Literal[1, 24, 72] = 24


def _call(request, reference, action=False):
    _, key = native_identity(request, reference)
    values = request.model_dump(exclude=set(CardViewKey.model_fields)) if action else {}
    try:
        result = DeepTutorBackend(timeout=25)._post('/internal/heart/native/assessment/reviews/action' if action else
            '/internal/heart/native/assessment/reviews', values | key)
    except (BackendUnavailable, ValueError) as exc:
        if getattr(exc.__cause__, 'code', None) == 409:
            try:
                detail = json.loads(exc.__cause__.read(8192)).get('detail', {})
                code = detail.get('code') if isinstance(detail, dict) else ''
            except (ValueError, OSError):
                code = ''
            messages = {'review_ungraded': '请先完成作答与评分；尚未记为复习完成',
                'review_path_busy': '当前还有待答题，请先处理或返回后再开始复习',
                'review_path_not_bound': '请先回到这条学习路径',
                'review_already_graded_finish_first': '本次已经评分，请先确认完成，再安排下一次复习'}
            if code in ('assessment_source_unavailable', 'source_changed', 'assessment_question_changed'):
                raise HTTPException(410, '教材或审核来源待核对；未按遗忘处理') from exc
            raise HTTPException(409, messages.get(code, '复习状态已变化，请刷新后重试')) from exc
        raise HTTPException(503, '复习操作未确认，请刷新或重试') from exc
    if not isinstance(result.get('reviews'), list):
        raise HTTPException(503, '复习队列响应无效')
    return result


def scheduled_reviews(student_id, session_id):
    if not session_id or os.getenv('DEEPTUTOR_NATIVE_ENABLED', '0') != '1':
        return []
    with session_scope() as db:
        records = db.execute(select(ConversationRow.id, PDFCitationRow.reference).join(PDFCitationRow,
            PDFCitationRow.conversation_id == ConversationRow.id).where(ConversationRow.student_id == student_id,
            ConversationRow.session_id == session_id, ConversationRow.role == 'assistant').order_by(ConversationRow.id.desc()).limit(200)).all()
    output, seen = [], set()
    for conversation_id, reference in records:
        binding = reference.get('_native_assessment') or {}
        path_id = binding.get('path_id')
        if not path_id or path_id in seen:
            continue
        seen.add(path_id)
        request = CardViewKey(student_id=student_id, session_id=session_id, conversation_id=conversation_id)
        try:
            with session_scope() as db:
                _, reference, _ = _owned(db, request)
            result = _call(request, reference)
            output.extend(dict(row, conversation_id=conversation_id, revision=result['revision']) for row in result['reviews'])
        except HTTPException:
            output.append({'kind': 'review_unavailable', 'point': reference.get('section_title', '教材复习'),
                'reason': '复习状态或教材来源待核对；未作为遗忘或错误计分', 'status': 'source_unavailable'})
    return output


@router.get('')
def reviews(student_id: str, session_id: str):
    return {'reviews': scheduled_reviews(student_id, session_id)}


@router.post('/action')
def action(request: ReviewHostAction):
    with session_scope() as db:
        _, reference, _ = _owned(db, request)
    result = _call(request, reference, True)
    if result.get('learning_cards') and result.get('question_id'):
        # 原生已登记且可重放的题目，只在宿主保存一次展示投影。
        with session_scope(immediate=True) as db:
            _, latest, _ = _owned(db, request)
            db.scalar(select(Student).where(Student.student_id == request.student_id).with_for_update())
            owned = db.execute(select(ConversationRow, PDFCitationRow).join(PDFCitationRow,
                PDFCitationRow.conversation_id == ConversationRow.id).where(ConversationRow.student_id == request.student_id,
                ConversationRow.session_id == request.session_id,
                PDFCitationRow.reference['_native_assessment']['question_id'].as_string() == result['question_id'])).first()
            if owned:
                conversation, projection = owned
                target = deepcopy(projection.reference)
            else:
                if request.action != 'start':
                    return result
                conversation = ConversationRow(student_id=request.student_id, session_id=request.session_id,
                    role='assistant', content='复习题已准备。作答、提示或延后均由你选择。')
                db.add(conversation);db.flush()
                projection = PDFCitationRow(conversation_id=conversation.id, reference={})
                db.add(projection)
                target = {k: deepcopy(v) for k, v in latest.items() if not k.startswith('_') and k != 'learning_cards'}
            binding = dict(latest['_native_assessment'], question_id=result['question_id'])
            epoch = binding.get('memory_epoch')
            if epoch is None:
                epoch = latest.get('learning_cards', [{}])[0].get('memory_epoch')
            if epoch is None:
                raise HTTPException(410, '复习记忆身份已失效')
            target['_native_assessment'] = binding
            target['learning_cards'] = [dict(card, memory_epoch=epoch) for card in result['learning_cards']]
            projection.reference = target
            result.update(conversation_id=conversation.id, reply=conversation.content,
                pdf_references=target.get('pdf_references', []), textbook_sources=target.get('textbook_sources', []))
    return result
