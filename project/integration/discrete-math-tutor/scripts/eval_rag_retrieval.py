"""小型人工标注集：比较旧检索与结构混合检索的证据命中率。"""

from __future__ import annotations

import json
import re
import time

from knowledge.hybrid_retrieval import retrieve_hybrid
from knowledge.textbook import load_textbook, retrieve

# (问题, 章节, 小节标题片段, 资源类型)。这些标签只验证出处，不评价生成回答。
GOLD = [
    ("集合及其元素是什么？", 1, "集合及其元素", "text"),
    ("空集的定义是什么？", 1, "集合的表示", "text"),
    ("数学归纳法怎么证明？", 2, "数学归纳原理", "text"),
    ("牛顿二项式定理是什么？", 3, "组合的计数", "text"),
    ("命题的合取什么时候为真？", 4, "逻辑联结词", "text"),
    ("全称量词表示什么？", 5, "量词", "text"),
    ("形式系统中的公理是什么？", 6, "谓词演算形式系统FC", "text"),
    ("图7.11表示什么？", 7, "路径与回路", "text"),
    ("定理7.4如何证明？", 7, "路径与回路", "text"),
    ("哈密顿图是什么？", 7, "哈密顿", "text"),
    ("什么是二元关系？", 9, "关系", "text"),
    ("根据绝对值函数的表格，x=-3时f(x)是多少？", 10, "函数的基本概念", "table"),
    ("函数的逆是什么？", 10, "函数的逆", "text"),
]


def evaluate() -> dict:
    chunks = load_textbook()
    results = {}
    for label, method in (("旧检索", retrieve), ("结构混合检索", retrieve_hybrid)):
        hits = []
        started = time.perf_counter()
        for question, chapter, section, kind in GOLD:
            found = method(question, chunks, limit=2)
            hit = any(
                int(re.search(r"第(\d+)章", item.source).group(1)) == chapter
                and section in item.section and (item.kind == kind or (question.startswith("命题的合取") and item.kind == "table"))
                for item in found if re.search(r"第(\d+)章", item.source)
            )
            hits.append({"question": question, "hit": hit,
                         "sources": [f"{item.source}/{item.section}/{item.kind}" for item in found]})
        results[label] = {"hit_at_2": sum(item["hit"] for item in hits),
                          "total": len(hits), "elapsed_seconds": round(time.perf_counter() - started, 2),
                          "misses": [item for item in hits if not item["hit"]]}
    return results


if __name__ == "__main__":
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
