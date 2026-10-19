import tempfile
from pathlib import Path
import unittest

from scripts.check_deeptutor_native_baseline import test_summary


class BaselineReportTests(unittest.TestCase):
    def test_failures_errors_skips_are_not_counted_as_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'result.xml'
            path.write_text('<testsuites><testsuite><testcase name="ok"/>'
                '<testcase classname="module" name="race"><failure/></testcase>'
                '<testcase name="setup"><error/></testcase><testcase name="optional"><skipped/></testcase>'
                '</testsuite></testsuites>', encoding='utf-8')
            result = test_summary(path)
        self.assertEqual((result['tests'], result['passed'], result['skipped']), (4, 1, 1))
        self.assertEqual(result['failed'], ['module::race'])
        self.assertEqual(result['errors'], ['::setup'])


if __name__ == '__main__': unittest.main()
