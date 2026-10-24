"""可复现的隔离回归与浏览器PDF夹具；不读取正式学生数据库。"""
from pathlib import Path
import argparse
import json
import os
import shutil
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixture-only', action='store_true')
    args = parser.parse_args()
    os.chdir(ROOT)
    from tests.test_first_wave_tools import TextbookResourceFixture
    from agents.tools.first_wave_runtime import ReaderGotoTool
    fixture = TextbookResourceFixture()
    fixture.setUp()
    try:
        out = ROOT / '.runtime/q4-joint-browser'
        out.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fixture.path, out / 'reader.pdf')
        action = ReaderGotoTool(2).run(fixture.pages(page=2, quote=fixture.texts[1]),
                                       fixture.context).metadata['data']['action']
        data = {'chapters': [{'id': 1, 'title': '实验方法', 'sections': [{'id': 1, 'title': '变量'}]}],
            'section': {'id': 1, 'title': '变量', 'chapter_id': 1, 'chapter_title': '实验方法',
                'source': '心理学.txt', 'content': '变量与实验方法', 'blocks': [],
                'pdf': dict(fixture.record, url='/api/pdf/documents/' + fixture.docid + '/file',
                            section=fixture.record['sections'][0])}, 'action': action}
        (out / 'fixture.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        if args.fixture_only:
            return 0
        modules = ['tests.test_first_wave_tools', 'tests.test_first_wave_integration',
            'tests.test_q4_tool_foundation', 'tests.test_q3_agent_loop', 'tests.test_q3_q4_integration',
            'tests.test_stream_retraction', 'tests.test_answer_stream', 'tests.test_session_study_plan']
        result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromNames(modules))
        (out / 'unit-report.json').write_text(json.dumps({'tests': result.testsRun,
            'failures': len(result.failures), 'errors': len(result.errors), 'real_model': False}), encoding='utf-8')
        return int(not result.wasSuccessful())
    finally:
        fixture.doCleanups()


if __name__ == '__main__':
    raise SystemExit(main())
