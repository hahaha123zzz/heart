"""规则优先的语义标签（D2 / D3）。

只在明确句式上产出标签，其余弃权；不调模型、不写业务状态。
单标签维度按“具体优先”取第一条命中；认知任务按出现位置排序，最多 3 条。
否定前缀（不要/别/先别/不用/不必/无需）不产出标签。
"""
from __future__ import annotations

import re

from models.input_understanding import SemanticAnnotation

# (维度, 取值, 正则)。顺序即单标签维度的优先级。
RULES = (
    ("difficulty_locus", "pace", r"太快|跟不上|讲得太多|一次讲太多|信息量太大"),
    ("difficulty_locus", "memory", r"记不住|背不下来|想不起来|记不牢"),
    ("difficulty_locus", "discrimination", r"分不清|区分不开|分不开|搞混|容易混淆|混淆了|把.{0,8}混淆"),
    ("difficulty_locus", "procedure", r"不会(?:做|下手|开始|用)|不知道(?:怎么|从哪|第一步)|没思路|无从下手"),
    ("difficulty_locus", "comprehension", r"没听懂|听不懂|没弄懂|没明白|不理解|看不懂|还是不懂|不太懂"),

    ("self_report", "understood", r"^(?:我)?(?:已经)?(?:懂了|明白了|理解了)[。！!\s]*$"),
    ("self_report", "confused", r"有点懵|有点迷糊|脑子有点乱"),

    ("engagement", "skip", r"不想做了|不做了|先跳过|跳过这题|这题算了|不学这个了"),
    ("engagement", "answer_seeking", r"(?:直接|干脆).{0,4}(?:给|告诉).{0,4}答案|直接说答案"),
    ("engagement", "off_task", r"今天天气|讲个笑话|你叫什么名字"),

    ("cognitive_demand", "create", r"设计(?:一个|个|一套)|提出.{0,8}改进|设计方案|改进方案"),
    ("cognitive_demand", "evaluate", r"合理吗|有没有问题|是否合理|有没有缺陷|站得住|靠不靠谱|有没有漏洞"),
    ("cognitive_demand", "analyze", r"分析|找出.{0,6}(?:变量|因素|问题)|拆解|哪个是.{0,6}变量"),
    ("cognitive_demand", "apply", r"如果.{0,15}(?:会|该|应该)|在.{0,10}情境下|实际(?:研究|场景)中"),
    ("cognitive_demand", "comprehend", r"为什么|有什么区别|区别是|怎么理解|是什么意思|什么关系"),
    ("cognitive_demand", "recall", r"^(?:请)?(?:说出|列出|背一下|复述|默写)"),
)

NEGATED = re.compile(r"(?:不要|不用|别|先别|不必|无需|不想|并非|没有)\s*$")
_MAX_DEFAULT = 1


def _is_negated(text: str, start: int) -> bool:
    return bool(NEGATED.search(text[max(0, start - 6):start]))


def extract(raw_text: str) -> list[SemanticAnnotation]:
    """规则标签；quote 逐字来自原话。"""
    from agents.input_understanding import ontology

    max_labels = {name: int(spec.get("max_labels", _MAX_DEFAULT))
                  for name, spec in ontology.labels().items()}
    found: dict[str, list[tuple[int, str, str]]] = {}
    for dimension, label, pattern in RULES:
        match = next((m for m in re.finditer(pattern, raw_text)
                      if not _is_negated(raw_text, m.start())), None)
        if match is None:
            continue
        found.setdefault(dimension, []).append((match.start(), label, match.group(0)))
    result = []
    for dimension, rows in found.items():
        if dimension == "cognitive_demand":
            # 认知任务表述顺序即任务顺序。
            rows = sorted(rows)[:max_labels.get(dimension, _MAX_DEFAULT)]
        else:
            rows = rows[:1]
        for _, label, quote in rows:
            result.append(SemanticAnnotation(dimension=dimension, label=label,
                                             quote=quote, source="rule"))
    return _dedupe(result)


def _dedupe(rows: list[SemanticAnnotation]) -> list[SemanticAnnotation]:
    seen = set()
    output = []
    for row in rows:
        key = (row.dimension, row.label)
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def merge(existing, incoming) -> list[SemanticAnnotation]:
    """规则标签优先；新标签只补空缺，并受注册表 cap 与取值校验约束。"""
    from agents.input_understanding import ontology

    max_labels = {name: int(spec.get("max_labels", _MAX_DEFAULT))
                  for name, spec in ontology.labels().items()}
    output = [SemanticAnnotation.model_validate(row.model_dump() if hasattr(row, "model_dump") else row)
              for row in existing]
    counts: dict[str, int] = {}
    for row in output:
        counts[row.dimension] = counts.get(row.dimension, 0) + 1
    for candidate in incoming:
        row = SemanticAnnotation.model_validate(
            candidate.model_dump() if hasattr(candidate, "model_dump") else candidate)
        if not ontology.valid_label(row.dimension, row.label):
            raise ValueError("unknown_semantic_label")
        if any(old.dimension == row.dimension and old.label == row.label for old in output):
            continue
        if counts.get(row.dimension, 0) >= max_labels.get(row.dimension, _MAX_DEFAULT):
            continue
        output.append(row)
        counts[row.dimension] = counts.get(row.dimension, 0) + 1
    return output


def annotate(turn):
    """把规则标签并入本轮；已存在的标签（模型或先前规则）不重复。"""
    if not turn.annotations:
        rows = extract(turn.envelope.raw_text)
    else:
        rows = merge(turn.annotations, extract(turn.envelope.raw_text))
    value = turn.model_dump()
    value["annotations"] = [row.model_dump() for row in rows]
    if rows and not value.get("ontology_version"):
        from agents.input_understanding import ontology
        value["ontology_version"] = ontology.version()
    from models.input_understanding import GroundedTurn
    return GroundedTurn.model_validate(value)
