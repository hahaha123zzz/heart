"""真实教材/Q2定位的接线检查；选证模型为协议夹具，不评价语义或生成答案。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.build_layer4_benchmark import digest
from scripts.evaluate_layer4_benchmark import validate


class SelectionFixture:
    def __init__(self):
        self.calls = 0

    def chat_json(self, messages, **kwargs):
        self.calls += 1
        payload = json.loads(messages[-1]['content'])
        return {'evidence_ids': [row['evidence_id'] for row in payload['candidates'][:12]]}


class ForbiddenBackend:
    def search(self, **kwargs):
        raise AssertionError('明确对象不得回退到语义检索')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('产物已存在，禁止覆盖')
    os.environ.update(TUTOR_COURSE='experimental-psychology-3', FIXED_BOOK_RETRIEVAL_ENABLED='0',
                      CITATION_GROUNDING_MODE='active')
    from agents.course_search import shared_search
    from agents.q3_navigation import LearningTarget
    from knowledge.course_config import PSYCHOLOGY_DIR
    from knowledge.grounded_citations import CitationGroundingError
    app = Path(__file__).resolve().parents[1]
    files = ['scripts/accept_layer4_object_bridge.py', 'agents/course_search.py', 'agents/object_evidence.py',
             'knowledge/evidence_objects.py', 'knowledge/grounded_citations.py', 'knowledge/lightrag/coverage.py',
             'knowledge/course_config.py', 'knowledge/pdf_reader.py', 'knowledge/source_mapping.py',
             'scripts/parse_converted_textbook.py', 'agents/q3_navigation.py']
    fingerprints = {f: digest(app/f) for f in files}
    data = json.loads(args.data.read_text(encoding='utf-8'))
    validate(data, PSYCHOLOGY_DIR)
    index_hash = digest(PSYCHOLOGY_DIR/'rag_index.sqlite3')
    rows, failures = [], []
    for case in data['cases']:
        if case['category'] not in ('table', 'formula'):
            continue
        llm = SelectionFixture()
        navigation = shared_search(ForbiddenBackend(), message=case['question'], llm=llm)
        try:
            sources = navigation.search(target=LearningTarget('current', '原当前目标', 1, 1),
                                        query=case['question'], limit=10)
            row = {'status': 'verified_original_range' if sources else 'withheld_incomplete_object',
                   'sources': [s.to_dict() for s in sources]}
        except CitationGroundingError as exc:
            row = {'status': 'withheld_no_grounded_candidates', 'reason': str(exc), 'sources': []}
        except Exception as exc:
            failures.append(case['id'])
            row = {'status': 'failed', 'reason': f'{type(exc).__name__}: {exc}', 'sources': []}
        row.update(case_id=case['id'], category=case['category'], trace=navigation.calls,
                   selection_fixture_calls=llm.calls)
        rows.append(row)
    validate(data, PSYCHOLOGY_DIR)
    assert digest(PSYCHOLOGY_DIR/'rag_index.sqlite3') == index_hash
    assert all(digest(app/f) == value for f, value in fingerprints.items())
    report = {'scope': 'real_original_and_Q2_grounding_with_protocol_fixture_not_semantic_acceptance',
              'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'benchmark_sha256': digest(args.data), 'index_sha256': index_hash,
              'implementation_sha256': fingerprints, 'index_unchanged': True,
              'llm_calls': 0, 'semantic_quality_passed': False, 'failed_cases': failures, 'runs': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    from collections import Counter
    print(json.dumps({'cases': len(rows), 'statuses': dict(Counter(r['status'] for r in rows)),
                      'failed_cases': failures}, ensure_ascii=False))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
