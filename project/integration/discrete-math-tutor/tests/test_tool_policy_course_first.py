from types import SimpleNamespace

from integrations.deeptutor import tool_policy


def _context(message, locator=None):
    metadata = {'reading_viewport': {'locator': locator}} if locator is not None else {}
    return SimpleNamespace(user_message=message, metadata=metadata)


def test_reading_viewport_uses_read_material_first():
    assert tool_policy.preferred_first_tool(_context('这段什么意思', locator=7)) == 'read_material'


def test_course_question_uses_rag_first():
    assert tool_policy.preferred_first_tool(_context('自变量是什么')) == 'rag'


def test_system_question_forces_nothing():
    assert tool_policy.preferred_first_tool(_context('今天几号')) is None


def test_apply_sets_first_tool_only_when_unset_and_available():
    pipeline = SimpleNamespace(initial_tool_choice=None)
    tool_policy.apply_first_tool_choice(pipeline, _context('自变量是什么'), ['rag', 'kb_files'])
    assert pipeline.initial_tool_choice == 'rag'

    pipeline.initial_tool_choice = 'ask_user'
    tool_policy.apply_first_tool_choice(pipeline, _context('自变量是什么'), ['rag'])
    assert pipeline.initial_tool_choice == 'ask_user'

    fresh = SimpleNamespace(initial_tool_choice=None)
    tool_policy.apply_first_tool_choice(fresh, _context('自变量是什么'), ['kb_files'])
    assert fresh.initial_tool_choice is None
