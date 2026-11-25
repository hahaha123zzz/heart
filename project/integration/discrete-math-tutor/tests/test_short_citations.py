"""短引用只把本轮已披露来源解析成正式链接。"""
import unittest

from integrations.deeptutor.short_citations import resolve


def citation(chapter, page):
    return f'[教材第{chapter}章第{page}页](#dt-material-x "citation")'


SOURCES = [
    {"short_id": "S1", "index": 1, "reader_citation": citation(5, 5)},
    {"short_id": "S2", "index": 2, "reader_citation": citation(5, 9)},
]


class ShortCitationTests(unittest.TestCase):
    def test_single_marker_becomes_verified_link(self):
        self.assertEqual(resolve("自变量是研究者操纵的变量[S1]。", SOURCES),
                         f"自变量是研究者操纵的变量{citation(5, 5)}。")

    def test_sentence_end_multiple_markers_all_resolve(self):
        text = "对比见[S1, S2]。"
        self.assertEqual(resolve(text, SOURCES),
                         f"对比见{citation(5, 5)}{citation(5, 9)}。")
        self.assertEqual(resolve("对比见[S1][S2]。", SOURCES),
                         f"对比见{citation(5, 5)}{citation(5, 9)}。")

    def test_unknown_or_undisclosed_marker_stays_plain(self):
        self.assertEqual(resolve("伪造引用[S9]。", SOURCES), "伪造引用[S9]。")
        self.assertEqual(resolve("[S1]", [{"short_id": "S1", "reader_citation": ""}]), "[S1]")

    def test_code_examples_are_not_rewritten(self):
        text = "示例 `[S1]` 和\n```\n[S1]\n```\n正文[S1]"
        self.assertEqual(resolve(text, SOURCES),
                         f"示例 `[S1]` 和\n```\n[S1]\n```\n正文{citation(5, 5)}")

    def test_map_form_is_accepted_for_worker_context(self):
        mapping = {"S2": {"short_id": "S2", "reader_citation": citation(3, 7)}}
        self.assertEqual(resolve("见[S2]", mapping), f"见{citation(3, 7)}")


if __name__ == "__main__":
    unittest.main()
