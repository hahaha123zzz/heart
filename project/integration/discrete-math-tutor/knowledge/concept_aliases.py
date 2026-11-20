"""核对教材原文后的术语别名，只扩展完整概念。"""
import re

CONCEPTS = (
    # 检索关联术语：欧拉图是具有欧拉回路的图，并非将图与回路定义成同一对象。
    ("euler_circuit", ("欧拉回路", "欧拉图")),
    ("subset", ("子集", "子集合", "包含关系", "包含于", "⊆")),
    ("ordered_pair", ("有序对", "二元有序组", "序偶", "ordered pairs")),
    ("cartesian_product", ("笛卡尔积", "笛卡儿积")),
)

GENERIC_QUERY_PATTERNS = (
    r"什么条件(?:下)?",
    r"什么时候",
    r"什么",
    r"怎样",
    r"如何",
    r"为什么",
    r"为何",
    r"是否",
    r"适用于",
    r"一定",
    r"请解释",
    r"请问",
    r"之间",
    r"有什么关系",
    r"有何区别",
)


def clean_query(query: str) -> str:
    """移除只表达提问方式、不参与教材概念匹配的套话。"""
    value = query
    for pattern in GENERIC_QUERY_PATTERNS:
        value = re.sub(pattern, " ", value, flags=re.I)
    value = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", value)
    value = re.sub(r"\s+([，。！？；：,.!?;:])", r"\1", value)
    return re.sub(r"\s+", " ", value).strip().rstrip("?？!！。.")


def structural_terms(query: str) -> list[str]:
    """补充教材实际采用的章节名和结构术语。

    这些规则只扩展已识别概念，不引入外部答案。具体教材仍须由检索和
    原文坐标核验。
    """
    additions: list[str] = []
    if re.search(r"有序对|有序组|序偶", query):
        additions.append("有序对 笛卡儿积 二元组")
    if re.search(r"[A-Za-z][A-Za-z0-9]*∧[A-Za-z]|合取", query):
        additions.append("第4章 4.1.2 逻辑联结词 合取")
    if re.search(r"连通.{0,4}无圈|无圈.{0,4}连通", query) and "树" in query:
        additions.append("第8章 8.3.1 树的基本概念 连通 无圈")
    elif "树" in query:
        additions.append("第8章 树 基本概念")
    if re.search(r"函数.{0,4}复合|复合函数|f\s*[○∘]\s*g", query):
        additions.append("函数的合成 复合函数 应用次序")
    if re.search(r"命题.{0,6}否定|否定.{0,6}真值", query):
        additions.append("否定 逻辑联结词 真值")
    return additions


def matched_aliases(query: str) -> list[tuple[str, tuple[str, ...]]]:
    return [(concept, aliases) for concept, aliases in CONCEPTS
            if any((re.search(r"\b" + re.escape(alias) + r"\b", query, re.I)
                    if alias.isascii() else alias in query) for alias in aliases)]


def expand_query(query: str) -> str:
    cleaned = clean_query(query)
    aliases = [alias for _, group in matched_aliases(cleaned)
               for alias in group if alias not in cleaned]
    additions = [*aliases, *structural_terms(cleaned)]
    additions = list(dict.fromkeys(additions))
    return cleaned + ("\n教材术语：" + "、".join(additions) if additions else "")
