"""可逆的中文引文匹配；只规范化空白与全角兼容字符。"""
# SPDX-License-Identifier: Apache-2.0
# Adapted from HKUDS/DeepTutor, commit 6cf793bd868ba5ecbe64722936d4be8fab5a01df,
# deeptutor/reading/_grounding.py: normalized_with_map / selection_range.
# 修改：适配中文 PDF 换行、保留所有匹配候选；不删除数字、负号或标点。
# License and attribution: third_party/DeepTutor/.
NORMALIZATION='fullwidth-ascii-whitespace-v1'


def normalized_with_map(value):
    normalized, positions = [], []
    for index, character in enumerate(value):
        if character.isspace():
            continue
        # NFKC 会把 x² 与 x2 折成相同文字，破坏公式含义；这里只转换全角ASCII。
        folded=chr(ord(character)-0xFEE0) if 0xFF01<=ord(character)<=0xFF5E else character
        normalized.append(folded)
        positions.append(index)
    return ''.join(normalized), positions


def normalized(value):
    return normalized_with_map(value)[0]


def selection_ranges(text, selection):
    haystack, positions = normalized_with_map(text)
    needle = normalized(selection)
    if not needle:
        return []
    matches, cursor = [], 0
    while (found := haystack.find(needle, cursor)) >= 0:
        matches.append((positions[found], positions[found + len(needle) - 1] + 1))
        cursor = found + 1
    return matches
