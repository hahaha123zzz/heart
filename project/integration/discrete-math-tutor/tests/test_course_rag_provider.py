from pathlib import Path

from integrations.deeptutor import course_rag_provider
from integrations.deeptutor.published_course import COURSE


def test_course_aliases_use_published_knowledge_base(monkeypatch, tmp_path):
    version = "a" * 64
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    monkeypatch.setattr(
        course_rag_provider,
        "_published",
        lambda: (tmp_path / "published", {"version": version}),
    )
    assert course_rag_provider.canonical_names(
        [COURSE, "实验心理学", "custom-kb", "实验心理学"]
    ) == ["heart_" + version[:24], "custom-kb"]


def test_missing_published_pack_keeps_native_chat_available(monkeypatch):
    monkeypatch.setattr(course_rag_provider, "_published", lambda: None)
    assert course_rag_provider.register_course_sources("course") is None
    assert course_rag_provider.canonical_names([COURSE, COURSE]) == [COURSE]
