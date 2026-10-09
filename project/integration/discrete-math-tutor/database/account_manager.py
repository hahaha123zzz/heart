"""AccountManager —— 测试账户与正式账户的区分、清理。

【自主实现】测试账户（account_type="test"）带 expires_at，测试结束可调用
destroy_test_account() 级联删除，或由 cleanup_expired() 在启动时清理过期账户。
正式账户（production）长期保存。
"""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path
from typing import Optional

from database.repository import Repository


class AccountManager:
    def __init__(self, repository: Optional[Repository] = None) -> None:
        self.repo = repository or Repository()

    def create_test_account(self, student_id: str, ttl_hours: int = 24) -> str:
        existing_type = self.repo.get_account_type(student_id)
        if existing_type == "production":
            raise ValueError("该学生 ID 属于正式账户，不能作为测试账户使用")
        expires_at = dt.datetime.utcnow() + dt.timedelta(hours=ttl_hours)
        self.repo.ensure_student(
            student_id, account_type="test", expires_at=expires_at
        )
        return student_id

    def create_production_account(self, student_id: str) -> str:
        self.repo.ensure_student(student_id, account_type="production")
        return student_id

    def destroy_test_account(self, student_id: str) -> bool:
        """删除测试账户及其全部级联数据（画像/状态/误解/证据/对话/计划）。"""
        if self.repo.get_account_type(student_id) != "test":
            return False
        return self.repo.delete_student(student_id)

    def cleanup_expired(self) -> int:
        """启动时调用：清理所有过期账户。返回删除数量。"""
        expired = self.repo.list_expired()
        removed = 0
        for student_id in expired:
            if self.destroy_test_account(student_id):
                removed += 1
        return removed

    def cleanup_after_code_update(self) -> int:
        """Forget test profiles on the next launch after relevant source changes."""
        root = Path(__file__).resolve().parents[1]
        files = list(root.glob("*.py"))
        for folder in ("agents", "database", "knowledge", "llm", "memory", "models"):
            files.extend((root / folder).rglob("*.py"))
            files.extend((root / folder).rglob("*.json"))
        digest = hashlib.sha256()
        for path in sorted(files):
            digest.update(str(path.relative_to(root)).encode("utf-8"))
            digest.update(path.read_bytes())
        return self.repo.clear_test_accounts_on_code_change(digest.hexdigest())
