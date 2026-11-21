import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from knowledge import answer_release
from orchestrator import retrieve_course
from scripts.run_release_health import (
    assess_metrics,
    update_circuit,
)
from scripts.measure_first_token import percentile


class AnswerReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "index.sqlite3").write_bytes(b"index-v1")
        (self.root / "questions.json").write_text("[]", encoding="utf-8")
        self.manifest_path = self.root / "release.json"
        manifest = {
            "schema": "answer-accuracy-release-v1",
            "created_at": "fixture",
            "source_commit": "fixture",
            "course_id": "discrete-math",
            "artifacts": [
                {"path": "index.sqlite3", "sha256": answer_release.sha256_path(self.root / "index.sqlite3")},
                {"path": "questions.json", "sha256": answer_release.sha256_path(self.root / "questions.json")},
            ],
            "features": {
                "query_understanding": {
                    "mode": "canary",
                    "percent": 5,
                    "test_accounts_active": True,
                },
                "semantic_section_resolver": {
                    "mode": "shadow",
                    "percent": 0,
                    "test_accounts_active": False,
                },
            },
            "thresholds": {
                "minimum_samples": 20,
                "maximum_unsupported_citation_rate": 0.15,
                "maximum_out_of_scope_false_recall_rate": 0.10,
                "maximum_first_token_p95_ms": 3000,
            },
        }
        manifest["release_id"] = answer_release.expected_release_id(manifest)
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.root_patch = patch.object(answer_release, "ROOT", self.root)
        self.root_patch.start()
        answer_release._verified_state.cache_clear()

    def tearDown(self):
        answer_release._verified_state.cache_clear()
        self.root_patch.stop()
        self.temp.cleanup()

    def test_manifest_hashes_are_required_and_tampering_fails_closed(self):
        self.assertTrue(answer_release.verify(self.manifest_path)["ok"])
        (self.root / "index.sqlite3").write_bytes(b"changed")
        result = answer_release.decision(
            "query_understanding",
            student_id="tester",
            account_type="test",
            manifest_path=self.manifest_path,
            circuit_path=self.root / "circuit.json",
        )
        self.assertFalse(result.active)
        self.assertEqual(result.mode, "off")
        self.assertIn("哈希变化", result.reason)

    def test_test_accounts_are_active_and_same_bucket_is_stable(self):
        test_decision = answer_release.decision(
            "query_understanding",
            student_id="tester",
            account_type="test",
            manifest_path=self.manifest_path,
            circuit_path=self.root / "circuit.json",
        )
        self.assertTrue(test_decision.active)
        first = answer_release.decision(
            "query_understanding",
            student_id="student-1",
            manifest_path=self.manifest_path,
            circuit_path=self.root / "circuit.json",
        )
        second = answer_release.decision(
            "query_understanding",
            student_id="student-1",
            manifest_path=self.manifest_path,
            circuit_path=self.root / "circuit.json",
        )
        self.assertEqual(first.bucket, second.bucket)
        self.assertEqual(first.active, second.active)

    def test_shadow_and_open_circuit_never_change_answer_path(self):
        shadow = answer_release.decision(
            "semantic_section_resolver",
            student_id="student-1",
            manifest_path=self.manifest_path,
            circuit_path=self.root / "circuit.json",
        )
        self.assertFalse(shadow.active)
        self.assertTrue(shadow.shadow)
        circuit = self.root / "circuit.json"
        update_circuit("query_understanding", open_feature=True, path=circuit)
        blocked = answer_release.decision(
            "query_understanding",
            student_id="tester",
            account_type="test",
            manifest_path=self.manifest_path,
            circuit_path=circuit,
        )
        self.assertFalse(blocked.active)
        self.assertEqual(blocked.mode, "off")

    def test_health_thresholds_open_for_unsupported_recall_or_latency(self):
        thresholds = {
            "minimum_samples": 20,
            "maximum_unsupported_citation_rate": 0.15,
            "maximum_out_of_scope_false_recall_rate": 0.10,
            "maximum_first_token_p95_ms": 3000,
        }
        metrics = {
            "samples": 20,
            "unsupported_citation_rate": 0.2,
            "out_of_scope_false_recall_rate": 0.0,
            "first_token_p95_ms": 1000,
        }
        result = assess_metrics(metrics, thresholds)
        self.assertFalse(result["healthy"])
        self.assertIn("无依据回答率超限", result["reasons"])
        metrics = {
            "samples": 20,
            "unsupported_citation_rate": 0.1,
            "out_of_scope_false_recall_rate": 0.2,
            "first_token_p95_ms": 3500,
        }
        result = assess_metrics(metrics, thresholds)
        self.assertEqual(len(result["reasons"]), 2)

    def test_first_token_percentiles_use_captured_answer_deltas(self):
        self.assertEqual(percentile([], 0.95), None)
        self.assertEqual(percentile([100, 200, 300, 400, 500], 0.95), 500)
        self.assertEqual(percentile([500, 100, 300], 0.50), 300)

    def test_retrieval_uses_old_path_when_release_is_off(self):
        sentinel = [object()]
        with patch("orchestrator.release_decision", return_value=SimpleNamespace(
                active=False, shadow=False)), \
             patch("orchestrator.retrieve_hybrid", return_value=sentinel) as old, \
             patch("orchestrator.understand_query") as resolver, \
             patch("orchestrator.expand_section_context") as expand:
            result = retrieve_course(
                "原始问题",
                [],
                limit=3,
                student_id="student",
                account_type="production",
            )
        self.assertIs(result, sentinel)
        old.assert_called_once_with("原始问题", [], limit=3)
        resolver.assert_not_called()
        expand.assert_not_called()

    def test_retrieval_uses_resolved_query_when_release_is_active(self):
        resolved = [object()]
        with patch("orchestrator.release_decision", return_value=SimpleNamespace(
                active=True, shadow=False)), \
             patch("orchestrator.understand_query", return_value=SimpleNamespace(
                 retrieval_query="结构问题")), \
             patch("orchestrator.retrieve_hybrid", return_value=resolved), \
             patch("orchestrator.expand_section_context", return_value=resolved):
            result = retrieve_course(
                "原始问题",
                [],
                limit=3,
                student_id="tester",
                account_type="test",
            )
        self.assertIs(result, resolved)


if __name__ == "__main__":
    unittest.main()
