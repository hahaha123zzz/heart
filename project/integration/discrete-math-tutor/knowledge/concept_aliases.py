"""核对教材原文后的术语别名，只扩展完整概念。"""
import re

CONCEPTS = (
    # 检索关联术语：欧拉图是具有欧拉回路的图，并非将图与回路定义成同一对象。
    ("euler_circuit", ("欧拉回路", "欧拉图")),
    ("subset", ("子集", "子集合", "包含关系", "包含于", "⊆")),
    ("ordered_pair", ("有序对", "二元有序组", "序偶", "ordered pairs")),
    ("cartesian_product", ("笛卡尔积", "笛卡儿积")),
)


def matched_aliases(query: str) -> list[tuple[str, tuple[str, ...]]]:
    return [(concept, aliases) for concept, aliases in CONCEPTS
            if any((re.search(r"\b" + re.escape(alias) + r"\b", query, re.I)
                    if alias.isascii() else alias in query) for alias in aliases)]


def expand_query(query: str) -> str:
    aliases = [alias for _, group in matched_aliases(query) for alias in group if alias not in query]
    return query + ("\n教材术语：" + "、".join(aliases) if aliases else "")
