"""Prove vendored algorithms are unchanged apart from import namespaces."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / 'agents/deeptutor_learning'
VENDOR = ROOT.parents[1] / 'vendor/DeepTutor'


def test_pinned_source_and_mechanical_import_adaptation():
    notice = json.loads((ENGINE / 'SOURCE_NOTICE.json').read_text(encoding='utf-8'))
    assert notice['commit'] == '6cf793bd868ba5ecbe64722936d4be8fab5a01df'
    assert notice['license'] == 'Apache-2.0'
    for entry in notice['files']:
        original = VENDOR / entry['path']
        assert hashlib.sha256(original.read_bytes()).hexdigest() == entry['sha256']
        expected = original.read_text(encoding='utf-8').replace('deeptutor.learning.', 'agents.deeptutor_learning.')
        expected = expected.replace('deeptutor.utils.text_display', 'agents.deeptutor_learning.text_display')
        expected = expected.replace('from deeptutor.learning import policy', 'from agents.deeptutor_learning import policy')
        target = (ROOT / 'tests/deeptutor_learning' / original.name
                  if '/tests/' in entry['path'] else ENGINE / original.name)
        assert target.read_text(encoding='utf-8').strip() == expected.strip(), entry['path']
