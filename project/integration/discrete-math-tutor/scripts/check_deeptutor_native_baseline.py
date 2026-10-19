"""固定原生对话迁移基线；不读密钥、不调用模型、不修改学生数据库。"""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

HOST = Path(__file__).resolve().parents[1]
PROJECT = HOST.parents[1]
REPO = PROJECT.parent
VENDOR = PROJECT / 'vendor/DeepTutor'
MODULES = [
    'tests/services/session/test_capability_routing.py',
    'tests/agents/chat/test_agent_loop.py',
    'tests/capabilities/test_explore_context_capability.py',
    'tests/tools/test_ask_user.py',
    'tests/app/test_turn_application_service.py',
    'tests/services/session/test_context_builder.py',
]


def test_summary(path):
    root = ET.parse(path).getroot()
    cases = list(root.iter('testcase'))
    failures, errors = [], []
    for case in cases:
        name = case.get('classname', '') + '::' + case.get('name', '')
        if case.find('failure') is not None: failures.append(name)
        if case.find('error') is not None: errors.append(name)
    return {'tests': len(cases), 'failed': failures, 'errors': errors,
        'skipped': sum(case.find('skipped') is not None for case in cases),
        'passed': sum(all(case.find(tag) is None for tag in ('failure', 'error', 'skipped')) for case in cases)}


def main():
    sys.path.insert(0, str(PROJECT / 'scripts'))
    from vendor_deeptutor import verify
    snapshot = verify(VENDOR)
    run = HOST / '.runtime/deeptutor-native-baseline' / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
    run.mkdir(parents=True)
    status = subprocess.check_output(['git', 'status', '--porcelain=v1', '-z', '--untracked-files=normal'], cwd=REPO)
    (run / 'worktree-status.nul').write_bytes(status)
    packages = {}
    for name in ('fastapi', 'pydantic', 'openai', 'pytest', 'pytest-asyncio', 'llama-index-core',
                 'llama-index-vector-stores-faiss', 'sentence-transformers', 'faiss-cpu'):
        try: packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: packages[name] = None
    ports = {}
    for port in (8000, 18001):
        with socket.socket() as sock:
            sock.settimeout(.2)
            ports[str(port)] = sock.connect_ex(('127.0.0.1', port)) == 0
    report = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        'upstream': snapshot, 'python': sys.version, 'packages': packages, 'localhost_listening': ports,
        'worktree_status_sha256': hashlib.sha256(status).hexdigest(),
        'scope': '固定仓库副本、替身模型、隔离工作目录；非对话质量或上线验收',
        'modules': MODULES}
    output = run / 'report.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    env = dict(os.environ, PYTHONPATH=str(VENDOR), DEEPTUTOR_HOME=str(run / 'home'),
        PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONUTF8='1')
    command = [sys.executable, '-B', '-m', 'pytest', *MODULES, '-q', '-p', 'no:cacheprovider',
        '-p', 'pytest_asyncio.plugin', '--basetemp', str(run / 'pytest'), '--junitxml', str(run / 'upstream.xml')]
    with (run / 'upstream.log').open('w', encoding='utf-8') as log:
        process = subprocess.run(command, cwd=VENDOR, env=env, stdout=log, stderr=subprocess.STDOUT)
    report['exit_code'] = process.returncode
    if (run / 'upstream.xml').is_file(): report['tests'] = test_summary(run / 'upstream.xml')
    report['known_failure'] = 'test_cold_start_stalled_provider_settles_with_bounded_retries[partial_stream]'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'report': str(output), 'exit_code': process.returncode, 'tests': report.get('tests')}, ensure_ascii=False))
    raise SystemExit(process.returncode)


if __name__ == '__main__': main()
