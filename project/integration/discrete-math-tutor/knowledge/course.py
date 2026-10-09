"""Chapter navigation and small hand-checked demo quizzes for the supplied text."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

from knowledge.textbook import TEXTBOOK_DIR, load_textbook

CHAPTER_TITLES = {
    1: "集合代数", 2: "两个数学基本原理", 3: "计数", 4: "命题逻辑",
    5: "谓词逻辑", 6: "形式系统", 7: "图", 8: "特殊图",
    9: "关系", 10: "函数",
}

# Multiple-choice items are deliberately small: content is reviewable, not generated silently.
QUIZZES = {
    1: [("q1a", "若 A={1,2}，下列哪个数属于 A？", ["1", "3", "4", "5"], 0, "1 是集合 A 的元素。"),
        ("q1b", "A∪B 表示什么？", ["两集合所有元素", "仅共同元素", "A 中但不在 B 中的元素", "空集"], 0, "并集包含属于 A 或 B 的元素。")],
    2: [("q2a", "数学归纳法通常先验证什么？", ["起始情形", "结论的逆命题", "全部自然数", "反例"], 0, "先验证起始情形，再证明归纳步骤。"),
        ("q2b", "把 4 个物品放入 3 个盒子，鸽笼原理保证什么？", ["至少一个盒子有 2 个物品", "每盒恰好 1 个", "有空盒", "每盒至少 2 个"], 0, "物品数超过盒子数时，至少一盒有两个。")],
    3: [("q3a", "两个互斥选择分别有 2 种和 3 种，合计有几种？", ["5", "6", "1", "9"], 0, "互斥选择用加法原理。"),
        ("q3b", "先做 2 种选择，再做 3 种选择，共有几种组合？", ["6", "5", "3", "2"], 0, "分步完成用乘法原理。")],
    4: [("q4a", "‘2 是质数’是否是命题？", ["是，有确定真值", "不是，含数字", "不是，不能判断", "是，但没有真值"], 0, "命题是可以判断真假的陈述句。"),
        ("q4b", "p∧q 什么时候为真？", ["p 和 q 都真", "任意一个真", "都假", "p 假 q 真"], 0, "合取要求两者同时为真。")],
    5: [("q5a", "符号 ∀ 通常表示什么？", ["对所有", "存在一个", "不属于", "蕴含"], 0, "全称量词表示对论域中所有对象。"),
        ("q5b", "符号 ∃ 通常表示什么？", ["存在至少一个", "对所有", "不存在", "当且仅当"], 0, "存在量词表示至少有一个对象满足条件。")],
    6: [("q6a", "形式系统中的公理是什么？", ["作为推理起点的公式", "随意猜测", "任何反例", "待证结论的否定"], 0, "公理是系统内推理的起点。"),
        ("q6b", "证明中从已有公式得到新公式需要依据什么？", ["推理规则", "图的度数", "集合元素个数", "任意直觉"], 0, "形式证明按系统的推理规则进行。")],
    7: [("q7a", "图 G=(V,E) 中的 V 表示什么？", ["顶点集", "边集", "路径集", "回路集"], 0, "V 表示顶点集。"),
        ("q7b", "无向图中的一条边连接什么？", ["两个顶点", "两个集合", "两个真值", "两个公式"], 0, "无向边连接两个顶点。")],
    8: [("q8a", "二分图的顶点可以怎样划分？", ["分成两个内部无边的部分", "每个顶点自成一组", "只能有两条边", "只能有两个顶点"], 0, "二分图的顶点可分为两个独立部分。"),
        ("q8b", "树的一个基本特征是什么？", ["连通且无回路", "每点都有自环", "必有回路", "必为完全图"], 0, "树是连通的无回路图。")],
    9: [("q9a", "二元关系通常是哪个集合的子集？", ["A×B", "A∪B", "A∩B", "A\u2206B"], 0, "从 A 到 B 的二元关系是 A×B 的子集。"),
        ("q9b", "A 上的恒等关系包含哪些有序对？", ["(a,a)", "所有(a,b)", "只有不同元素对", "没有有序对"], 0, "恒等关系包含每个元素与自身组成的有序对。")],
    10: [("q10a", "函数要求定义域中每个元素对应几个值？", ["恰好一个", "至少两个", "任意多个", "零个"], 0, "函数对定义域每个元素都指定唯一的值。"),
         ("q10b", "若 f:A→B、g:B→C，g∘f 的定义域是？", ["A", "B", "C", "A∪C"], 0, "合成函数先应用 f，因此定义域是 A。")],
}


@lru_cache(maxsize=1)
def chapters() -> list[dict]:
    chunks = [chunk for chunk in load_textbook() if chunk.kind == "text"]
    files = {int(re.search(r"第(\d+)章", c.source).group(1)): c.source for c in chunks}
    result = []
    for number in range(1, 11):
        source = files[number]
        sections: list[dict] = []
        for chunk in chunks:
            if chunk.source != source:
                continue
            title = chunk.section.strip()
            if sections and sections[-1]["title"] == title:
                sections[-1]["content"] += "\n" + chunk.text
            else:
                sections.append({"id": len(sections) + 1, "title": title, "content": chunk.text})
        result.append({"id": number, "title": CHAPTER_TITLES[number], "source": source,
                       "sections": sections})
    return result


def chapter_summary() -> list[dict]:
    return [{"id": c["id"], "title": c["title"], "source": c["source"],
             "sections": [{"id": s["id"], "title": s["title"]} for s in c["sections"]]}
            for c in chapters()]


def get_chapter(chapter_id: int) -> dict | None:
    return next((c for c in chapters() if c["id"] == chapter_id), None)


def get_section(chapter_id: int, section_id: int) -> dict | None:
    chapter = get_chapter(chapter_id)
    if chapter is None:
        return None
    return next((s for s in chapter["sections"] if s["id"] == section_id), None)


def public_quiz(chapter_id: int) -> list[dict]:
    return [{"id": q[0], "question": q[1], "options": q[2]} for q in QUIZZES.get(chapter_id, [])]


def grade_quiz(chapter_id: int, answers: dict[str, int]) -> dict:
    questions = QUIZZES.get(chapter_id)
    if not questions:
        raise ValueError("章节不存在")
    items = []
    for qid, text, options, correct, explanation in questions:
        chosen = answers.get(qid)
        if type(chosen) is not int or not 0 <= chosen < len(options):
            chosen = None
        items.append({"id": qid, "chosen": chosen, "correct": correct,
                      "is_correct": chosen == correct, "explanation": explanation})
    score = round(100 * sum(item["is_correct"] for item in items) / len(items))
    return {"chapter_id": chapter_id, "score": score, "items": items}
