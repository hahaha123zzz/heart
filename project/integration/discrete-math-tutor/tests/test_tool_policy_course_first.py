from types import SimpleNamespace

from integrations.deeptutor import tool_policy
from integrations.deeptutor.course_rag_provider import canonical_kb_name


def _context(message, capability='chat', kbs=None):
    return SimpleNamespace(user_message=message, active_capability=capability,
                           knowledge_bases=kbs or [], metadata={})


def test_course_question_is_prefetched():
    assert tool_policy.skip_kb_seed(_context('自变量是什么', kbs=[canonical_kb_name()])) is False


def test_greeting_skips_prefetch():
    assert tool_policy.skip_kb_seed(_context('你好', kbs=[canonical_kb_name()])) is True


def test_system_question_skips_prefetch():
    assert tool_policy.skip_kb_seed(_context('今天几号', kbs=[canonical_kb_name()])) is True


def test_other_capability_skips_prefetch():
    assert tool_policy.skip_kb_seed(_context(
        '自变量是什么', capability='deep_research', kbs=[canonical_kb_name()])) is True


def test_no_course_kb_keeps_existing_behavior():
    assert tool_policy.skip_kb_seed(_context('你好')) is False
