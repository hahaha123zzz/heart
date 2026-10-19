"""归档旧资源后，正式默认入口仍可启动；仅使用临时学习库。"""
import os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class PsychologyCutoverTests(unittest.TestCase):
    def test_original_main_without_legacy_resources(self):
        script = '''
from fastapi.testclient import TestClient
from main import app
from knowledge.course_config import COURSE_ID
from knowledge.exercise_mapping import resolve_mapping
assert COURSE_ID == 'experimental-psychology-3'
client = TestClient(app)
home = client.get('/').text
assert '/static/visualizations/graph.js' not in home
assert '/static/visualizations/guided.js' in home
assert client.get('/static/textbook/manifest.json').status_code == 404
assert resolve_mapping('old-question','1','old-version') is None
paths = app.openapi()['paths']
assert not any(path.startswith(('/api/relations','/api/truth-table','/api/visualizations','/api/course-preview')) for path in paths)
assert len(client.get('/api/course/chapters').json()) == 11
assert client.get('/health').json()['course_id'] == COURSE_ID
print('PASS: 正式入口、图解脚本、旧教材资源和旧题映射隔离')
'''
        with tempfile.TemporaryDirectory() as folder:
            env = os.environ | {'DATABASE_URL':'sqlite:///'+str(Path(folder)/'test.db'), 'LLM_MOCK':'1', 'MEMORY_WORKER_ENABLED':'0'}
            env.pop('TUTOR_COURSE', None)
            env.pop('COURSE_DATABASE_URL', None)
            result = subprocess.run([sys.executable,'-X','utf8','-c',script], cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout+'\n'+result.stderr)

if __name__ == '__main__': unittest.main()
