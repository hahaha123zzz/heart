"""本次安排的显式增量迁移；不在 init_db 或读取请求中自动修改旧库。"""
from sqlalchemy import inspect, text


def has_session_plan(engine):
    return 'q5_learning_bindings' in inspect(engine).get_table_names() and any(
        c['name'] == 'session_plan' for c in inspect(engine).get_columns('q5_learning_bindings'))


def migrate_session_plan(engine):
    with engine.begin() as connection:
        if 'q5_learning_bindings' not in inspect(connection).get_table_names():
            raise ValueError('先建立既有 Q5 表，再运行本次安排迁移')
        if not any(c['name'] == 'session_plan' for c in inspect(connection).get_columns('q5_learning_bindings')):
            connection.execute(text('ALTER TABLE q5_learning_bindings ADD COLUMN session_plan JSON NULL'))
    return has_session_plan(engine)
