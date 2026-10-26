"""从已发布对话的进度卡生成只读回顾建议，不依赖临时任务寿命。"""
import hashlib

from sqlalchemy import select

from database.database import session_scope
from database.models import ConversationRow, PDFCitationRow

REASONS = {
    'pending_snapshot': '上次讲解留有一道未作答检查，可以选择回顾或重新练习。',
    'provisional_feedback': '上次辅助反馈尚需独立核对，可回顾关键概念；这不是正式评分。',
    'requested_support': '你曾请求换一种讲法，可以选择回顾这个知识点。',
}


def review_followups(student_id, memory_repo, *, course_id, limit=20):
    with session_scope() as session:
        rows = session.execute(select(ConversationRow.id, ConversationRow.session_id,
            PDFCitationRow.reference.label('selection_ref')).join(PDFCitationRow,
            PDFCitationRow.conversation_id == ConversationRow.id).where(ConversationRow.student_id == student_id,
            ConversationRow.role == 'assistant').order_by(
            ConversationRow.created_at.desc(), ConversationRow.id.desc()).limit(200)).all()
        seen, epochs, items = set(), {}, []
        for row in rows:
            reference = row.selection_ref if isinstance(row.selection_ref, dict) else {}
            cards = reference.get('learning_cards')
            if not isinstance(cards, list):
                continue
            for card in cards[:3]:
                if (not isinstance(card, dict) or card.get('schema') != 'learning-cards/v1'
                        or card.get('kind') != 'learning_progress' or card.get('course_id') != course_id
                        or 'review_reason_code' not in card or type(card.get('memory_epoch')) is not int):
                    continue
                point, objective = card.get('title'), card.get('objective_id')
                if not isinstance(point, str) or not point.strip() or not isinstance(objective, str):
                    continue
                if point not in epochs:
                    epochs[point] = memory_repo.memory_epoch(student_id, point)
                if card['memory_epoch'] != epochs[point]:
                    continue
                key = (row.session_id or 'legacy', objective)
                if key in seen:
                    continue
                seen.add(key)
                code = card.get('review_reason_code')
                if not isinstance(code, str) or code not in REASONS:
                    continue
                identifier = hashlib.sha256(':'.join((student_id, *key)).encode()).hexdigest()[:24]
                items.append({'kind': 'learning_followup', 'followup_id': identifier,
                    'point': point, 'reason': REASONS[code], 'reason_code': code,
                    'location_label': card.get('location_label') if isinstance(card.get('location_label'), str) else '',
                    'session_id': row.session_id, 'conversation_id': row.id,
                    'evidence_status': 'formative_unverified', 'requires_retrieval': True,
                    'mastery_credit': False})
                if len(items) >= max(1, min(limit, 20)):
                    return items
        return items
