"""任务偏好只调整同小节的候选次序，不参与召回或证据门槛。"""
import re
from collections import defaultdict

ALLOWED_TYPES = frozenset({"definition", "theorem", "proof", "example"})


def unit_types(row):
    if row["kind"] != "text":
        return frozenset()
    text = row["text"].lstrip()
    types = set()
    for label, name in (("定义", "definition"), ("定理", "theorem"), ("例", "example")):
        if re.match(label + r"\s*\d+(?:[.．]\d+)*(?!\d)", text):
            types.add(name)
    # 保守识别独立证明及与定理正文同块的证明，不以正文中的“证明”一词判定。
    if re.search(r"(?:^|\n)\s*(?:证明|证)(?:[：:.\s]|$)", text):
        types.add("proof")
    return frozenset(types)


def prefer_task_units(ranked, preferred_types, *, is_primary):
    preferred = set(preferred_types or ()) & ALLOWED_TYPES
    result = list(ranked)
    if not preferred:
        return result
    groups = defaultdict(list)
    for position, (_, row) in enumerate(result):
        # 没有小节定位的旧块不推断其结构归属；明确编号正文不被挪动。
        if row["section_id"] is not None and not is_primary(row):
            groups[(row["chapter_id"], row["section_id"])].append(position)
    for positions in groups.values():
        ordered = sorted((result[i] for i in positions),
                         key=lambda item: not bool(unit_types(item[1]) & preferred))
        for position, item in zip(positions, ordered):
            result[position] = item
    return result
