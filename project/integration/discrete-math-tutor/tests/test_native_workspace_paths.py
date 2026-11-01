"""Reuse the upstream scope cache without caching directory validation."""
from pathlib import Path
import importlib.util
import tempfile
import unittest
from unittest.mock import Mock, patch
from integrations.deeptutor.worker import VENDOR_ROOT


class WorkspacePathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.find_spec('deeptutor')
        if not spec or not spec.origin or not Path(spec.origin).resolve().is_relative_to(VENDOR_ROOT.resolve()):
            raise unittest.SkipTest('需要将仓库固定 vendor/DeepTutor 加入 PYTHONPATH')

    def test_initialization_reuses_scoped_service_but_checks_directories_each_time(self):
        from deeptutor.multi_user import paths
        from deeptutor.multi_user.models import UserScope
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scope = UserScope('user', 'synthetic', root)
            service = Mock()
            with patch.object(paths, 'get_path_service_for_scope', return_value=service):
                for _ in range(2):
                    self.assertEqual(paths.ensure_scope_workspace(scope), root.resolve())
            self.assertEqual(service.ensure_all_directories.call_count, 2)
            self.assertTrue((root / 'knowledge_bases').is_dir())
            self.assertTrue((root / 'memory').is_dir())

    def test_scope_cache_does_not_reuse_another_root(self):
        from deeptutor.multi_user import paths
        from deeptutor.multi_user.models import UserScope
        with tempfile.TemporaryDirectory() as directory:
            a = paths.get_path_service_for_scope(UserScope('user', 'same-id', Path(directory) / 'a'))
            b = paths.get_path_service_for_scope(UserScope('user', 'same-id', Path(directory) / 'b'))
            self.assertIsNot(a, b)
            self.assertNotEqual(a.workspace_root, b.workspace_root)


if __name__ == '__main__':
    unittest.main()
