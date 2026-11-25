from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / 'vendor/DeepTutor/deeptutor/agents/chat/prompts'


def test_chat_prompts_require_textbook_first_and_disclose_missing_evidence():
    zh = (ROOT / 'zh/agentic_chat.yaml').read_text(encoding='utf-8')
    en = (ROOT / 'en/agentic_chat.yaml').read_text(encoding='utf-8')
    assert '先检索教材' in zh and '没有检索到教材依据' in zh and '通识解释' in zh
    assert 'search the textbook first' in en
    assert 'no textbook evidence was retrieved' in en and 'general-knowledge' in en
