"""Resolve confirmed values from the latest preference change per key."""
from sqlalchemy import select
from database.models import MemoryChangeRow


def confirmed_preferences(session, student_id, preferences):
    rows = session.scalars(select(MemoryChangeRow).where(
        MemoryChangeRow.student_id == student_id,
        MemoryChangeRow.action == 'set_preference',
    ).order_by(MemoryChangeRow.id)).all()
    latest = {row.item_key: row for row in rows}
    return {key: value for key, value in preferences.items()
            if key in latest and latest[key].source == 'explicit_user'
            and latest[key].confirmed_value is not None
            and not isinstance(value, bool) and value == latest[key].confirmed_value}
