"""执行TA5分层回归并汇总TE01—TE18；单测全绿不等于发布通过。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REPO = ROOT.parents[1]
HOST = ('test_teaching_modes', 'test_teaching_hint_lifecycle', 'test_teaching_evidence',
        'test_teaching_memory_corrections', 'test_learning_cards', 'test_learning_card_actions',
        'test_review_followups', 'test_q3_agent_loop', 'test_q3_task_loop', 'test_q3_entrypoint',
        'test_q5_learning', 'test_selection_loop', 'test_answer_stream', 'test_stream_retraction',
        'test_adaptive_tutoring', 'test_ta5_acceptance')
NATIVE = ('test_native_assessment', 'test_native_assessment_commands', 'test_native_learning_cards',
          'test_native_review', 'test_review_authorization', 'test_native_learning_authorization',
          'test_native_learning_sources', 'test_native_learning_write_guard',
          'test_native_teaching_prompt', 'test_native_learning_tool_adapter',
          'test_native_learning_session_state', 'test_native_learning_binding_adapter',
          'test_native_learning_migration')
# 模块覆盖是自动回归证据，不冒充真实教学、页面或人工抽查。
CASES = {
 'TE01': ('直接讲与引导', ('test_teaching_modes', 'test_native_teaching_prompt'), ('live', 'manual')),
 'TE02': ('查询不出题', ('test_teaching_modes', 'test_adaptive_tutoring'), ('live',)),
 'TE03': ('三级提示与恢复', ('test_teaching_hint_lifecycle', 'test_native_learning_cards'), ('live', 'browser')),
 'TE04': ('求例子与看图', ('test_teaching_modes', 'test_selection_loop'), ('live', 'manual')),
 'TE05': ('辅助与独立证据', ('test_teaching_evidence', 'test_native_assessment_commands'), ('live',)),
 'TE06': ('理解后路径推进', ('test_q5_learning',), ('live',)),
 'TE07': ('误解假设更正', ('test_teaching_memory_corrections', 'test_native_assessment_commands'), ('live', 'manual')),
 'TE08': ('偏好作用域', ('test_teaching_modes', 'test_native_teaching_prompt'), ('live',)),
 'TE09': ('待答中插问与返回', ('test_native_assessment_commands', 'test_native_learning_cards'), ('live', 'browser')),
 'TE10': ('幂等并发取消', ('test_q3_agent_loop', 'test_native_review', 'test_native_learning_authorization'), ('live', 'browser')),
 'TE11': ('题卡手机键盘', ('test_learning_cards', 'test_learning_card_actions', 'test_native_learning_cards'), ('live', 'browser')),
 'TE12': ('到期延后完成', ('test_native_review', 'test_review_authorization'), ('live', 'browser')),
 'TE13': ('版本图像和答案门禁', ('test_native_assessment_commands', 'test_native_learning_sources'), ('live',)),
 'TE14': ('删除与派生失效', ('test_teaching_memory_corrections', 'test_native_learning_authorization', 'test_review_authorization'), ('live', 'deletion_contract')),
 'TE15': ('信心不混作概率', ('test_native_assessment', 'test_teaching_evidence'), ('live',)),
 'TE16': ('重点关系有依据', ('test_teaching_modes',), ('live', 'manual')),
 'TE17': ('多入口统一原生', ('test_q3_entrypoint', 'test_selection_loop', 'test_native_learning_session_state'), ('live', 'browser', 'native_unified')),
 'TE18': ('同配置性能', ('test_teaching_modes', 'test_answer_stream', 'test_stream_retraction'), ('performance',)),
}


def source_digest():
    paths = []
    for folder in ('agents', 'integrations', 'models', 'llm', 'database', 'memory', 'knowledge', 'frontend', 'tests', 'scripts'):
        paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in ('.py', '.js', '.cjs', '.css', '.html')
                     and not any(part in ('node_modules', '__pycache__', 'textbook', 'dist', 'build') for part in p.parts))
    paths.extend(ROOT.glob('*.py'))
    digest = hashlib.sha256()
    for path in sorted(set(paths)):
        digest.update(path.relative_to(ROOT).as_posix().encode());digest.update(b'\0');digest.update(path.read_bytes())
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def validate_evidence(record, digest):
    if (record.get('case_id') not in CASES or record.get('status') != 'passed'
            or record.get('source_digest') != digest or record.get('layer') not in CASES[record['case_id']][2]
            or not record.get('artifacts')):
        return False
    for artifact in record['artifacts']:
        path = (ROOT/artifact['path']).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            return False
        if hashlib.sha256(path.read_bytes()).hexdigest() != artifact.get('sha256'):
            return False
    return True


def summarize(reports, evidence, digest):
    modules = {}
    for report in reports:
        if report.get('source_digest') != digest:
            raise ValueError('测试代码身份不同，不能拼接为同一版本验收')
        for name, result in report['modules'].items():
            if name in modules and modules[name] != result:
                raise ValueError('同一模块存在冲突测试结果')
            modules[name] = result
    accepted = {(r['case_id'], r['layer']) for r in evidence if validate_evidence(r, digest)}
    rows = []
    for key, (title, required, layers) in CASES.items():
        missing = [m for m in required if not modules.get(m, {}).get('passed')]
        missing += [layer for layer in layers if (key, layer) not in accepted]
        rows.append({'id': key, 'title': title, 'status': 'passed' if not missing else 'incomplete',
                     'missing': missing, 'unit_modules': list(required)})
    return {'cases': rows, 'release_ready': all(row['status'] == 'passed' for row in rows)}


def run_modules(names):
    output = {}
    for name in names:
        suite = unittest.defaultTestLoader.loadTestsFromName('tests.'+name)
        result = unittest.TextTestRunner(verbosity=1).run(suite)
        output[name] = {'tests_run': result.testsRun,
            'passed': result.wasSuccessful() and not result.skipped and result.testsRun > 0,
            'failures': [test.id() for test, _ in result.failures],
            'errors': [test.id() for test, _ in result.errors],
            'skipped': [test.id() for test, _ in result.skipped]}
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layer', choices=('host', 'native', 'summary'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reports', type=Path, nargs='*', default=[])
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    digest = source_digest()
    report = {'schema': 'ta5-acceptance/v1', 'source_digest': digest,
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        'created_at': datetime.now(timezone.utc).isoformat(), 'layer': args.layer}
    if args.layer == 'summary':
        report.update(summarize([read_json(p) for p in args.reports],
            read_json(args.evidence) if args.evidence else [], digest))
        code = 0 if report['release_ready'] else 2
    else:
        report['modules'] = run_modules(HOST if args.layer == 'host' else NATIVE)
        code = 0 if all(m['passed'] for m in report['modules'].values()) else 1
    if source_digest() != digest:
        raise RuntimeError('执行期间源码变化，本次不能作为稳定代码验收')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'layer': args.layer, 'report': str(args.output), 'exit_code': code}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
