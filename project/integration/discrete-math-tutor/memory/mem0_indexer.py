"""把 PG 记忆卡片异步同步到 mem0；回合路径不阻塞。"""
from __future__ import annotations

import logging
import threading

from sqlalchemy import and_, or_, select

from database.database import session_scope
from database.models import MemoryDocumentRow

LOGGER = logging.getLogger(__name__)


class Mem0Indexer:
    def __init__(self, repo, store, interval=2, batch=32, source_kind=None):
        self.repo = repo
        self.store = store
        self.interval = interval
        self.batch = batch
        self.source_kind = source_kind
        self._stop = threading.Event()
        self._thread = None

    def _pending(self):
        with session_scope() as session:
            query = select(MemoryDocumentRow).where(or_(
                and_(MemoryDocumentRow.active,
                     or_(MemoryDocumentRow.mem0_id.is_(None),
                         MemoryDocumentRow.mem0_synced_hash.is_(None),
                         MemoryDocumentRow.mem0_synced_hash != MemoryDocumentRow.content_hash)),
                and_(MemoryDocumentRow.active.is_(False), MemoryDocumentRow.mem0_id.is_not(None)),
            ))
            if self.source_kind is not None:
                query = query.where(MemoryDocumentRow.source_kind == self.source_kind)
            rows = session.scalars(query.limit(self.batch)).all()
            return [{
                "id": row.id, "student_id": row.student_id, "content": row.content,
                "source_kind": row.source_kind, "source_id": row.source_id,
                "metadata": dict(row.source_metadata or {}), "content_hash": row.content_hash,
                "mem0_id": row.mem0_id, "mem0_synced_hash": row.mem0_synced_hash, "active": bool(row.active),
            } for row in rows]

    def _save(self, card_id, content_hash, memory_id):
        with session_scope(immediate=True) as session:
            row = session.get(MemoryDocumentRow, card_id)
            if row is None or row.content_hash != content_hash:
                return False
            row.mem0_id = memory_id
            row.mem0_synced_hash = content_hash
            return True

    def _clear(self, card_id, content_hash):
        with session_scope(immediate=True) as session:
            row = session.get(MemoryDocumentRow, card_id)
            if row is None or row.content_hash != content_hash:
                return False
            row.mem0_id = None
            row.mem0_synced_hash = None
            return True

    def _sync(self, card):
        if not card["active"]:
            if card["mem0_id"]:
                self.store.delete(card["mem0_id"])
                self._clear(card["id"], card["content_hash"])
            return
        if card["mem0_id"] and card["mem0_synced_hash"] != card["content_hash"]:
            self.store.delete(card["mem0_id"])
        memory_id = self.store.add_card(card["student_id"], {
            "card_id": card["id"],
            "content": card["content"],
            "source_kind": card["source_kind"],
            "source_id": card["source_id"],
            "verification": card["metadata"].get("verification", ""),
            "epoch": card["metadata"].get("epoch", 0),
        })
        if memory_id:
            self._save(card["id"], card["content_hash"], memory_id)

    def run_once(self):
        cards = self._pending()
        for card in cards:
            try:
                self._sync(card)
            except Exception as exc:
                LOGGER.warning("mem0 卡片同步失败，类别：%s", type(exc).__name__)
        return bool(cards)

    def _run(self):
        while not self._stop.is_set():
            try:
                processed = self.run_once()
            except Exception as exc:
                LOGGER.warning("mem0 同步轮询失败，类别：%s", type(exc).__name__)
                processed = False
            if not processed:
                self._stop.wait(self.interval)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="mem0-indexer", daemon=True)
        self._thread.start()

    def stop(self, timeout=10):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)
        return not self._thread or not self._thread.is_alive()

    def status(self):
        return {"enabled": True, "running": bool(self._thread and self._thread.is_alive())}
