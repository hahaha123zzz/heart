from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient

def test_native_journal_page_is_bounded_newest_first_and_private(monkeypatch):
    from deeptutor.api.routers import learning_journal as route
    records=[{"id":str(n)} for n in range(50,0,-1)]
    monkeypatch.setattr(route,"get_learning_journal_store",lambda:SimpleNamespace(overview=lambda:{"records":records,"updated_at":"one"}))
    app=FastAPI();app.include_router(route.router,prefix="/api/learning-journal")
    with TestClient(app) as client:
        first=client.get("/api/learning-journal")
        assert first.status_code==200 and first.headers["cache-control"]=="no-store"
        assert len(first.json()["records"])==20 and first.json()["next_offset"]==20
        assert first.json()["records"][0]["id"]=="50"
        last=client.get("/api/learning-journal?limit=20&offset=40").json()
        assert len(last["records"])==10 and last["next_offset"] is None
        assert client.get("/api/learning-journal?limit=1000").status_code==422
        assert client.get("/api/learning-journal?offset=51").status_code==422


def test_internal_learning_view_uses_the_same_bounded_native_page(monkeypatch):
    import asyncio
    from contextlib import nullcontext
    from integrations.deeptutor import native_learning_view
    from deeptutor.api.routers import learning_journal as route
    from deeptutor.services.workspace import context
    monkeypatch.setattr(context, "workspace_context", lambda value: nullcontext())
    monkeypatch.setattr(route, "get_learning_journal_store", lambda: SimpleNamespace(overview=lambda: {"records": list(range(26))}))
    class Bridge:
        async def bind_scope(self, request):
            return {"user_id": "fixture-user", "workspace_id": "fixture-space"}
        def user_scope(self, user_id):
            return nullcontext()
    result=asyncio.run(native_learning_view.read(Bridge(), SimpleNamespace(view="journal")))
    assert result["records"]==list(range(20)) and result["next_offset"]==20
