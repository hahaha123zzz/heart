"""Add conversation-session ownership to existing databases without rewriting history."""

from sqlalchemy import inspect, text


def migrate_conversation_sessions(engine):
    """Idempotently add the nullable session column used by new chat threads."""
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "conversations" not in inspector.get_table_names():
            return False
        columns = {column["name"] for column in inspector.get_columns("conversations")}
        if "session_id" not in columns:
            connection.execute(text("ALTER TABLE conversations ADD COLUMN session_id VARCHAR(64) NULL"))
        indexes = {index["name"] for index in inspect(connection).get_indexes("conversations")}
        if "ix_conversations_student_session_id" not in indexes:
            connection.execute(text(
                "CREATE INDEX ix_conversations_student_session_id "
                "ON conversations (student_id, session_id, id)"
            ))
    return True
