"""明确询问教材图号时，应回答对应图片，而非切回课程基础步骤。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class FigureFocusTests(unittest.TestCase):
    def test_explicit_figure_question_uses_matching_excerpt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="figure-focus-") as temp:
            os.environ["DATABASE_URL"] = "sqlite:///" + (Path(temp) / "test.sqlite").as_posix()
            os.environ["LLM_MOCK"] = "1"
            from database.database import engine
            from orchestrator import TutorOrchestrator

            try:
                tutor = TutorOrchestrator()
                for number, section in (("7.8", "7.1.3"),
                                        ("7.20", "7.3.2"),
                                        ("7.23", "7.3.2")):
                    with self.subTest(figure=number):
                        result = tutor.handle_turn(
                            "figure-focus-" + number,
                            "请解释教材图" + number + "的内容。",
                            account_type="test",
                        )
                        self.assertEqual(
                            [item["label"] for item in result["image_refs"]],
                            ["图" + number],
                        )
                        self.assertIn(section, result["textbook_sources"][0])
                        self.assertIsNone(result["question_spec"])
                        self.assertEqual(result["teaching_plan"]["action"], "explain")
                        self.assertFalse(result["step_advanced"])
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
