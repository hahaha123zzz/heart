"""同一次目录查询复用清单，保留别名、未知能力及可选依赖检查。"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


class NativeCatalogManifestTests(unittest.TestCase):
    def test_availability_reuses_manifests_without_changing_resolution(self):
        from deeptutor.app import DeepTutorApp
        app = DeepTutorApp.__new__(DeepTutorApp)
        app.capabilities = SimpleNamespace(get_manifests=Mock(return_value=[
            {"name": "chat", "cli_aliases": ["talk"]}, {"name": "math_animator"}]))
        manifests = app.capabilities.get_manifests()
        self.assertTrue(app.get_capability_availability("talk", manifests=manifests).available)
        with patch("deeptutor.app.facade.importlib.util.find_spec", return_value=None):
            self.assertFalse(app.get_capability_availability("math_animator", manifests=manifests).available)
        with self.assertRaises(ValueError):
            app.get_capability_availability("unknown", manifests=manifests)
        app.capabilities.get_manifests.assert_called_once()
        self.assertTrue(app.get_capability_availability("chat").available)
        self.assertEqual(app.capabilities.get_manifests.call_count, 2)


if __name__ == "__main__":
    unittest.main()
