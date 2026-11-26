"""短引用只把本轮已披露来源解析成正式链接。"""
import unittest

from integrations.deeptutor.short_citations import (
    ShortCitationStream,
    resolve,
    to_numeric,
)


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
        # 本轮没有已披露来源时，短 ID 不能作为引用发布。
        self.assertEqual(resolve("[S1]", [{"short_id": "S1", "reader_citation": ""}]), "")
        # 已知与未知混写时，已知生成链接，未知保持可见。
        self.assertEqual(resolve("对比[S1, S9]", SOURCES), f"对比{citation(5, 5)}[S9]")

    def test_internal_citation_form_is_mapped_or_dropped(self):
        self.assertEqual(resolve("见[citation:S1]", SOURCES), f"见{citation(5, 5)}")
        self.assertEqual(resolve("见[citation:S9]", SOURCES), "见")
        self.assertEqual(resolve("见[citation:S9]", []), "见")

    def test_code_examples_are_not_rewritten(self):
        text = "示例 `[S1]` 和\n```\n[S1]\n```\n正文[S1]"
        self.assertEqual(resolve(text, SOURCES),
                         f"示例 `[S1]` 和\n```\n[S1]\n```\n正文{citation(5, 5)}")

    def test_map_form_is_accepted_for_worker_context(self):
        mapping = {"S2": {"short_id": "S2", "reader_citation": citation(3, 7)}}
        self.assertEqual(resolve("见[S2]", mapping), f"见{citation(3, 7)}")

    def test_unclosed_fence_is_treated_as_code_to_the_end(self):
        self.assertEqual(resolve("```\n[S1]", SOURCES), "```\n[S1]")

    def test_unclosed_inline_code_does_not_hang(self):
        self.assertEqual(resolve("看 `code", SOURCES), "看 `code")
        self.assertEqual(resolve("````\n[S1]\n```", SOURCES), "````\n[S1]\n```")

    def test_no_links_strips_short_and_internal_markers(self):
        self.assertEqual(resolve("正文[S1][citation:S2]。", []), "正文。")

    def test_stream_holds_a_split_marker_until_complete(self):
        stream = ShortCitationStream(SOURCES)
        self.assertEqual(stream.feed("答案[S"), "答案")
        self.assertEqual(stream.feed("1]。"), f"{citation(5, 5)}。")
        self.assertEqual(stream.flush(), "")

    def test_stream_never_links_inside_a_fence_split_across_chunks(self):
        stream = ShortCitationStream(SOURCES)
        self.assertEqual(stream.feed("示例\n```\n[S1]"), "示例\n")
        self.assertEqual(stream.feed("\n```\n正文[S1]"),
                         f"```\n[S1]\n```\n正文{citation(5, 5)}")

    def test_stream_holds_a_marker_split_after_the_bracket(self):
        stream = ShortCitationStream(SOURCES)
        self.assertEqual(stream.feed("答案["), "答案")
        self.assertEqual(stream.feed("S1]。"), f"{citation(5, 5)}。")

    def test_stream_holds_a_three_marker_list(self):
        stream = ShortCitationStream(SOURCES)
        self.assertEqual(stream.feed("对比[S1, S2, "), "对比")
        self.assertEqual(stream.feed("S3]"), f"{citation(5, 5)}{citation(5, 9)}[S3]")

    def test_stream_holds_an_open_inline_code_span(self):
        stream = ShortCitationStream(SOURCES)
        self.assertEqual(stream.feed("答案`co"), "答案")
        self.assertEqual(stream.feed("de`和[S1]"), f"`code`和{citation(5, 5)}")

    def test_stream_flush_keeps_an_incomplete_marker_plain(self):
        stream = ShortCitationStream(SOURCES)
        self.assertEqual(stream.feed("正文[S1"), "正文")
        self.assertEqual(stream.flush(), "[S1")

    def test_stream_reads_sources_registered_after_it_starts(self):
        mapping = {}
        stream = ShortCitationStream(lambda: mapping)
        self.assertEqual(stream.feed("准备[S1]"), "准备[S1]")
        mapping["S1"] = {"short_id": "S1", "reader_citation": citation(5, 5)}
        self.assertEqual(stream.feed("继续[S1]"), f"继续{citation(5, 5)}")

    def test_numeric_markers_follow_turn_indices(self):
        text = "对比[S1, S2]，示例 `[S9]`，无据[S9]。"
        self.assertEqual(to_numeric(text, SOURCES),
                         "对比[1][2]，示例 `[S9]`，无据。")


if __name__ == "__main__":
    unittest.main()
