"""复用已有画像及其显式变更来源；不调用会同步索引的memory_overview。"""
from sqlalchemy import select
from database.database import session_scope
from database.models import MemoryChangeRow
from models.interaction_preferences import InteractionPreferences


class ReadonlyMemoryContext:
    def __init__(self, memory):
        self.memory = memory

    def read(self, student_id, section):
        # 每次重读，不缓存删除前的偏好；查询与画像读取复用同一只读事务。
        with session_scope() as session:
            profile = self.memory.get_profile(student_id)
            explicit = set(session.scalars(select(MemoryChangeRow.item_key).distinct().where(
                MemoryChangeRow.student_id == student_id,
                MemoryChangeRow.action == 'set_preference',
                MemoryChangeRow.item_key.in_(InteractionPreferences.model_fields),
                MemoryChangeRow.source == 'explicit_user')).all())
            preferences = {key: value for key, value in profile.preferences.items()
                if key in explicit and key in InteractionPreferences.model_fields}
        values = InteractionPreferences.model_validate(preferences).model_dump(exclude_none=True)
        if section == 'profile':
            # 现有画像只有偏好和统计，没有可证实的专业/年级/基础，不能据此补造。
            return {'section': section, 'known': {}, 'missing': ['major', 'grade', 'prior_knowledge'],
                    'source_kind': 'stored_profile', 'truncated': False}
        return {'section': section, 'known': values,
                'missing': [] if values else ['confirmed_preferences'],
                'source_kind': 'explicit_user', 'truncated': False}
