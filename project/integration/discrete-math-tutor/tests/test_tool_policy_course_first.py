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


def test_catalogue_question_skips_body_prefetch():
    assert tool_policy.skip_kb_seed(_context('教材目录', kbs=[canonical_kb_name()])) is True


def test_full_catalogue_phrasings_skip_body_prefetch():
    for message in ('教材有哪些章节', '这本书哪几章', '全书目录'):
        assert tool_policy.skip_kb_seed(_context(message, kbs=[canonical_kb_name()])) is True


def test_page_or_chapter_lookup_still_retrieves():
    for message in ('自变量在哪一页', '教材目录里自变量是哪一章', '哪几章讲了自变量'):
        assert tool_policy.skip_kb_seed(_context(message, kbs=[canonical_kb_name()])) is False


def test_courtesy_and_short_followups_skip_prefetch():
    for message in ('谢谢', '继续', '你好呀', '好的'):
        assert tool_policy.skip_kb_seed(_context(message, kbs=[canonical_kb_name()])) is True


def test_system_question_skips_prefetch():
    assert tool_policy.skip_kb_seed(_context('今天几号', kbs=[canonical_kb_name()])) is True


def test_other_capability_skips_prefetch():
    assert tool_policy.skip_kb_seed(_context(
        '自变量是什么', capability='deep_research', kbs=[canonical_kb_name()])) is True


def test_no_course_kb_keeps_existing_behavior():
    assert tool_policy.skip_kb_seed(_context('你好')) is False
