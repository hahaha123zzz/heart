"""接入边界测试：地址、错误、能力目录与宿主进程隔离。"""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from fastapi import FastAPI
from fastapi.testclient import TestClient
from integrations.deeptutor.client import BackendUnavailable, DeepTutorBackend, _NoRedirect
from integrations.deeptutor.router import router


def response(value):
    return io.BytesIO(json.dumps(value).encode())


class BackendTests(unittest.TestCase):
    def test_reject_remote_credentials_and_ambiguous_urls(self):
        for value in ["https://127.0.0.1:18001", "http://example.com:18001", "http://127.0.0.1",
                      "http://user:pass@127.0.0.1:18001", "http://127.0.0.1:18001/a",
                      "http://127.0.0.1:18001?url=elsewhere", "http://127.0.0.1:99999"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                DeepTutorBackend(value)

    def test_ready_does_not_claim_model_was_verified(self):
        client = DeepTutorBackend()
        with patch.object(client.opener, "open", return_value=response({"status": "ready"})):
            self.assertEqual(client.status(), {"connected": True, "backend_ready": True,
                                               "model_execution_verified": False})

    def test_backend_failure_does_not_leak_exception(self):
        client = DeepTutorBackend()
        with patch.object(client.opener, "open", side_effect=OSError("private-details")):
            self.assertFalse(client.status()["connected"])
            with self.assertRaisesRegex(BackendUnavailable, "暂未就绪"):
                client.capabilities()

    def test_only_public_capability_fields_are_exposed(self):
        client = DeepTutorBackend()
        payload = {"capabilities": [{"id": "visualize", "available": True,
                   "manifest": {"description": "图解", "prompt": "private prompt"},
                   "config_schema": {"private": "data"}}]}
        with patch.object(client.opener, "open", return_value=response(payload)):
            self.assertEqual(client.capabilities(), [{"id": "visualize", "registered": True,
                "description": "图解", "model_execution_verified": False}])

    def test_malformed_or_oversized_response_is_rejected(self):
        client = DeepTutorBackend()
        for value in [[], {"capabilities": "invalid"}, {"capabilities": [{"id": "x"}]}]:
            with self.subTest(value=value), patch.object(client.opener, "open", return_value=response(value)):
                with self.assertRaises(BackendUnavailable):
                    client.capabilities()
        with patch.object(client.opener, "open", return_value=io.BytesIO(b" " * (1024 * 1024 + 1))):
            with self.assertRaises(BackendUnavailable):
                client.capabilities()

    def test_redirects_cannot_escape_local_backend(self):
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "redirect", {}, "http://example.com"))
        client = DeepTutorBackend()
        error = HTTPError(client.base_url, 302, "redirect", {}, None)
        with patch.object(client.opener, "open", side_effect=error):
            self.assertFalse(client.status()["connected"])

    def test_routes_degrade_without_importing_upstream(self):
        before = {key for key in sys.modules if key == "deeptutor" or key.startswith("deeptutor.")}
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as client, patch.object(DeepTutorBackend, "capabilities", side_effect=BackendUnavailable("private")):
            result = client.get("/api/deeptutor/capabilities")
            self.assertEqual(result.status_code, 503)
            self.assertNotIn("private", result.text)
        after = {key for key in sys.modules if key == "deeptutor" or key.startswith("deeptutor.")}
        self.assertEqual(before, after)


class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[3] / "scripts/vendor_deeptutor.py"
        spec = importlib.util.spec_from_file_location("snapshot_importer", path)
        cls.importer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.importer)

    def test_archive_paths_cannot_traverse_or_use_drive_names(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for value in ["", ".", "../outside", "/absolute", "C:/outside", "safe/../../outside", "safe\\..\\outside"]:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    self.importer.safe_path(root, value)

    def test_snapshot_detects_missing_and_modified_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            code = root / "sample.py"
            code.write_bytes(b"original")
            manifest = {"commit": self.importer.COMMIT,
                        "files": {"sample.py": self.importer.digest(b"original")}, "local_changes": []}
            (root / self.importer.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(self.importer.verify(root)["verified_files"], 1)
            code.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                self.importer.verify(root)
            code.unlink()
            with self.assertRaises(ValueError):
                self.importer.verify(root)

    def test_existing_destination_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(FileExistsError):
                self.importer.snapshot(Path("unused"), Path(temp))


class RuntimeSetupTests(unittest.TestCase):
    def load_module(self, name, relative):
        path = Path(__file__).resolve().parents[1] / relative
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_worker_scopes_runtime_and_rejects_source_directory(self):
        worker = self.load_module("worker_test", "integrations/deeptutor/worker.py")
        previous_cwd, previous_path = Path.cwd(), list(sys.path)
        try:
            with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ):
                vendor = Path(temp) / "vendor"
                vendor.mkdir()
                (vendor / "UPSTREAM_SNAPSHOT.json").write_text("{}")
                with patch.object(worker, "VENDOR_ROOT", vendor):
                    with self.assertRaises(ValueError):
                        worker.prepare(Path(temp) / "home", 0)
                    with self.assertRaises(ValueError):
                        worker.prepare(vendor / "data", 18001)
                    home = Path(temp) / "runtime"
                    worker.prepare(home, 18001)
                    self.assertEqual(Path(os.environ["DEEPTUTOR_HOME"]), home.resolve())
                    self.assertEqual(Path.cwd(), home.resolve())
                    self.assertEqual(sys.path[0], str(vendor))
                    os.chdir(previous_cwd)
        finally:
            os.chdir(previous_cwd)
            sys.path[:] = previous_path

    def test_setup_installs_only_into_separate_environment(self):
        setup = self.load_module("setup_test", "scripts/setup_deeptutor.py")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vendor = root / "vendor"
            vendor.mkdir()
            (vendor / "UPSTREAM_SNAPSHOT.json").write_text("{}")
            with patch.object(setup, "ROOT", root), patch.object(setup, "VENDOR", vendor), \
                    patch.object(setup.venv, "EnvBuilder") as builder, \
                    patch.object(setup.subprocess, "run") as run:
                setup.main()
                builder.return_value.create.assert_called_once_with(root / ".venv-deeptutor")
                command = run.call_args.args[0]
                self.assertEqual(command[-1], str(vendor))
                self.assertIn(".venv-deeptutor", command[0])
                self.assertTrue(run.call_args.kwargs["check"])

    def test_setup_reuses_tested_dependency_lock(self):
        setup = self.load_module("setup_locked_test", "scripts/setup_deeptutor.py")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "UPSTREAM_SNAPSHOT.json").write_text("{}")
            lock = root / setup.LOCK_NAME
            lock.write_text("example==1.0\n")
            with patch.object(setup, "ROOT", root), patch.object(setup, "VENDOR", root), \
                    patch.object(setup.venv, "EnvBuilder"), patch.object(setup.subprocess, "run") as run:
                setup.main()
                self.assertEqual(run.call_args.args[0][-2:], ["-r", str(lock)])
                self.assertEqual(run.call_args.kwargs["cwd"], root)


if __name__ == "__main__":
    unittest.main()
