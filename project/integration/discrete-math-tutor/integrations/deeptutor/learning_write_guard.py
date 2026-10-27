"""宿主受控命令的原生存储适配；不重写上游事务，不全局替换LearningStore。"""
from contextlib import contextmanager
import os
import sqlite3

from deeptutor.learning.storage import LearningStore
from .client import DeepTutorBackend
from .native_contract import NativeTaskCheck


class HostAuthorizedLearningStore(LearningStore):
    def __init__(self, check: NativeTaskCheck, root=None):
        self._host_check = check.model_copy(deep=True).model_dump()
        self._host_backend = DeepTutorBackend(base_url=os.getenv('DEEPTUTOR_HOST_URL', 'http://127.0.0.1:8000'))
        self._authorize()
        super().__init__(root=root)

    def _authorize(self):
        self._host_backend.authorize_native_task(self._host_check)

    @contextmanager
    def _connect(self, *, initialize=True):
        self._authorize()
        if initialize:
            self._ensure_initialized()
        # 沿用固定上游连接配置；禁用语句缓存，确保重复COMMIT仍触发authorizer。
        conn = sqlite3.connect(self.db_path, timeout=30.0, isolation_level=None, cached_statements=0)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute('PRAGMA busy_timeout = 30000')
        try:
            failure = []

            def authorize(action, arg1, arg2, database, source):
                # rollback不需要有效授权，过期任务必须仍能撤销未提交内容。
                transaction = action == sqlite3.SQLITE_TRANSACTION and arg1 in ('BEGIN', 'COMMIT')
                autocommit_write = action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE) and not conn.in_transaction
                if transaction or autocommit_write:
                    try:
                        self._authorize()
                    except Exception as exc:
                        failure.append(exc)
                        return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK

            conn.set_authorizer(authorize)
            try:
                yield conn
            except sqlite3.DatabaseError:
                if failure:
                    raise failure[0]
                raise
            finally:
                conn.set_authorizer(None)
        finally:
            conn.close()
