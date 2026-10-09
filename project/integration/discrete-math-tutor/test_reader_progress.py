"""阅读器结构与流式事件回归测试。"""
import json
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from knowledge.content import chapter_blocks
from knowledge.course import chapters
from main import app

class ReaderTests(unittest.TestCase):
    def test_navigation_uses_only_original_text(self):
        for chapter in chapters():
            titles = [s["title"] for s in chapter["sections"]]
            self.assertEqual(len(titles), len(set(titles)))
            self.assertLess(len(titles), 20)

    def test_all_original_tables_formulas_and_vectors_are_visible(self):
        tables, vectors, formulas = 0, set(), set()
        for chapter in chapters():
            for blocks in chapter_blocks(chapter["id"]).values():
                for block in blocks:
                    if block["type"] == "image":
                        vectors.add(block["asset"]["id"])
                    elif block["type"] == "table":
                        tables += 1
                        for row in block["rows"]:
                            for cell in row:
                                for paragraph in cell["paragraphs"]:
                                    formulas.update(p["asset"]["id"] for p in paragraph if p["type"] == "formula")
                    elif block["type"] == "paragraph":
                        formulas.update(p["asset"]["id"] for p in block["segments"] if p["type"] == "formula")
        self.assertEqual(tables, 20)
        self.assertEqual(len(vectors), 133)
        self.assertEqual(len(formulas), 1209)

    def test_table_cell_values(self):
        tables = [b for blocks in chapter_blocks(10).values() for b in blocks if b["type"] == "table"]
        rows = [["".join(p.get("text", "") for paragraph in c["paragraphs"] for p in paragraph) for c in r] for r in tables[0]["rows"]]
        self.assertEqual(rows[0], ["x", "-3", "-2", "-1", "0", "1", "2", "3"])
        self.assertEqual(rows[1], ["f(x)", "3", "2", "1", "0", "1", "2", "3"])

    def test_original_absolute_value_symbols_survive(self):
        paragraphs = [b for rows in chapter_blocks(10).values() for b in rows if b['type']=='paragraph']
        original = next(b for b in paragraphs if '例10.2' in ''.join(p.get('text','') for p in b['segments']))
        text = ''.join(p.get('text','') for p in original['segments'])
        self.assertIn('| x |', text)

class StreamTests(unittest.TestCase):
    def test_progress_and_answer_are_ordered(self):
        def turn(*args, progress=None, **kwargs):
            progress("retrieving", "检索教材", "找到正文")
            progress("checking", "核对回答", "核对引用")
            return {"reply": "测试回答", "image_refs": []}
        with patch("main.orchestrator.handle_turn", side_effect=turn):
            response = TestClient(app).post("/api/chat/stream", json={"student_id":"stream-unit", "message":"测试"})
        frames = response.text.strip().split("\n\n")
        events = [(f.split("\n")[0].removeprefix("event: "), json.loads(f.split("\ndata: ")[1])) for f in frames]
        self.assertEqual(response.headers["content-type"], "text/event-stream; charset=utf-8")
        self.assertEqual(events[-1], ("done", {"reply":"测试回答", "image_refs":[]}))
        starts = [d["stage"] for e,d in events if e=="progress" and d["status"]=="running"]
        ends = [d["stage"] for e,d in events if e=="progress" and d["status"]=="completed"]
        self.assertEqual(starts, ["queued","retrieving","checking"])
        self.assertEqual(starts, ends)

    def test_stream_failure_has_terminal_safe_error(self):
        with patch("main.orchestrator.handle_turn", side_effect=RuntimeError("private-config")):
            response = TestClient(app).post("/api/chat/stream", json={"student_id":"stream-unit", "message":"测试"})
        self.assertIn("event: error", response.text)
        self.assertNotIn("private-config", response.text)
        self.assertNotIn("event: done", response.text)

if __name__ == "__main__":
    unittest.main()
