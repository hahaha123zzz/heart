import asyncio
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

@pytest.mark.parametrize("native", [True, False])
def test_only_one_memory_index_pipeline_runs_for_selected_mode(monkeypatch, native):
    from integrations.deeptutor import runtime_config
    from memory.background_worker import memory_lifespan
    from memory import mem0_indexer, mem0_store
    from knowledge import fixed_book
    from llm import transport
    monkeypatch.setenv("MEM0_ENABLED", "1")
    monkeypatch.setenv("MEMORY_WORKER_ENABLED", "0")
    monkeypatch.setattr(runtime_config, "native_enabled", lambda: native)
    factory,store=Mock(),Mock()
    monkeypatch.setattr(mem0_indexer,"Mem0Indexer",factory)
    monkeypatch.setattr(mem0_store,"Mem0Store",store)
    async def nothing():pass
    monkeypatch.setattr(fixed_book,"start",nothing)
    monkeypatch.setattr(fixed_book,"stop",nothing)
    monkeypatch.setattr(transport,"close_pool",lambda:None)
    app=SimpleNamespace(state=SimpleNamespace(memory=SimpleNamespace(repo=object()),memory_llm=None))
    async def exercise():
        async with memory_lifespan(app):
            assert app.state.memory_worker is None
            assert (app.state.mem0_indexer is None) is native
    asyncio.run(exercise())
    if native:
        store.assert_not_called();factory.assert_not_called()
    else:
        store.assert_called_once_with(enabled=True)
        factory.return_value.start.assert_called_once()
        factory.return_value.stop.assert_called_once()
