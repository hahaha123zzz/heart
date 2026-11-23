"""同一学生ID的新旧课程数据库隔离；仅使用临时 PostgreSQL 库。"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

from tests.pg_support import temp_databases

ROOT = Path(__file__).resolve().parents[1]


class PsychologyMemoryTests(unittest.TestCase):
    def run_script(self, script, env):
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-c", script],
            cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)
        return result.stdout

    def test_course_database_is_isolated_from_legacy_database(self):
        with temp_databases() as pg:
            legacy = os.environ | pg | {"TUTOR_COURSE": "discrete-math", "LLM_MOCK": "1"}
            legacy.pop("COURSE_DATABASE_URL", None)
            self.run_script(
                """
from database.database import init_db
from memory.memory_manager import MemoryManager
init_db(); memory = MemoryManager(); memory.ensure_student('same-student')
memory.append('same-student','user','离散数学：欧拉图')
assert len(memory.get_history('same-student')) == 1
print('legacy-ok')
""",
                legacy,
            )
            psychology = os.environ | pg | {"TUTOR_COURSE": "experimental-psychology-3", "LLM_MOCK": "1"}
            self.run_script(
                """
from database.database import init_db, DATABASE_URL
from memory.memory_manager import MemoryManager
assert 'heart_test_' in DATABASE_URL
init_db(); memory = MemoryManager(); memory.ensure_student('same-student')
assert memory.get_history('same-student') == []
memory.append('same-student','user','心理学课程：被试间设计')
assert len(memory.get_history('same-student')) == 1
print('psychology-ok')
""",
                psychology,
            )


if __name__ == "__main__":
    unittest.main()
