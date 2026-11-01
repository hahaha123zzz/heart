"""Native filesystem helper keeps permissions while avoiding Windows no-op writes."""
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from integrations.deeptutor.worker import VENDOR_ROOT


class SecretFileTests(unittest.TestCase):
    def helper(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('native_secret_files_under_test',
            VENDOR_ROOT / 'deeptutor/utils/secret_files.py')
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        return helper

    def test_windows_writable_file_does_not_need_a_metadata_write(self):
        helper = self.helper()
        target = Mock()
        target.stat.return_value = SimpleNamespace(st_file_attributes=0)
        with patch.object(helper, 'os', SimpleNamespace(name='nt')):
            helper.ensure_private_file(target)
        target.chmod.assert_not_called()

    def test_windows_readonly_attribute_is_still_cleared(self):
        helper = self.helper()
        target = Mock()
        target.stat.return_value = SimpleNamespace(st_file_attributes=stat.FILE_ATTRIBUTE_READONLY)
        with patch.object(helper, 'os', SimpleNamespace(name='nt')):
            helper.ensure_private_file(target)
        target.chmod.assert_called_once_with(0o600)

    def test_existing_directory_and_restored_permissions_are_rechecked(self):
        helper = self.helper()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'private'
            helper.ensure_private_directory(target)
            (target / 'secret').write_text('synthetic', encoding='utf-8')
            target.chmod(0o777 if os.name != 'nt' else stat.S_IREAD)
            helper.ensure_private_directory(target)
            info = target.stat()
            if os.name == 'nt':
                self.assertFalse(info.st_file_attributes & stat.FILE_ATTRIBUTE_READONLY)
            else:
                self.assertEqual(stat.S_IMODE(info.st_mode), 0o700)
            self.assertEqual((target / 'secret').read_text(encoding='utf-8'), 'synthetic')

    def test_file_cannot_be_used_as_directory(self):
        helper = self.helper()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'file'
            target.touch()
            with self.assertRaises(FileExistsError):
                helper.ensure_private_directory(target)


if __name__ == '__main__':
    unittest.main()
