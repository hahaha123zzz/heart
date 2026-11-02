"""Add value-bound preference provenance without guessing historical values."""
from sqlalchemy import inspect, text


def migrate_preference_values(engine):
    with engine.begin() as connection:
        inspector = inspect(connection)
        if 'memory_changes' not in inspector.get_table_names():
            return False
        if 'confirmed_value' not in {c['name'] for c in inspector.get_columns('memory_changes')}:
            connection.execute(text('ALTER TABLE memory_changes ADD COLUMN confirmed_value FLOAT NULL'))
    return True
