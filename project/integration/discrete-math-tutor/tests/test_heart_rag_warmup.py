"""旧 SQLite 索引退役后，worker 启动不再打开或预热它。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "vendor/DeepTutor"))

import knowledge.hybrid_retrieval as hybrid
from integrations.deeptutor import heart_rag


def test_warm_retrieval_does_not_touch_the_retired_index(monkeypatch):
    def fail(*arguments, **keywords):
        raise AssertionError("worker warmup opened the retired SQLite index")
    monkeypatch.setattr(hybrid, "_vectors", fail)
    heart_rag.warm_retrieval()
