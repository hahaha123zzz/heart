from types import SimpleNamespace

from deeptutor.services.session._turn_runtime_shared import _apply_course_defaults
from integrations.deeptutor.native_executor import start_options


def _course(*refs):
    return SimpleNamespace(resources=[
        SimpleNamespace(kind='knowledge_base', ref_id=ref) for ref in refs])


def test_empty_saved_kb_uses_course_default():
    result = _apply_course_defaults({}, _course('实验心理学-lightrag'),
                                    preferences={'knowledge_bases': []})
    assert result['knowledge_bases'] == ['实验心理学-lightrag']


def test_saved_kb_is_kept():
    result = _apply_course_defaults({}, _course('course-kb'),
                                    preferences={'knowledge_bases': ['mine']})
    assert result['knowledge_bases'] == ['mine']


def test_empty_request_kb_is_not_forwarded():
    request = SimpleNamespace(model_dump=lambda **_: {'capability': 'chat', 'knowledge_bases': []})
    assert 'knowledge_bases' not in start_options(request)


def test_named_request_kb_is_kept():
    request = SimpleNamespace(model_dump=lambda **_: {'capability': 'chat', 'knowledge_bases': ['mine']})
    assert start_options(request)['knowledge_bases'] == ['mine']
