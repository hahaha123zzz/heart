"""受限命题逻辑解析；模板用于召回，不表示数学等价。"""
from __future__ import annotations
import json
import re

ALIASES = {r"\leftrightarrow": "↔", r"\Rightarrow": "→", r"\rightarrow": "→",
           r"\land": "∧", r"\wedge": "∧", r"\lor": "∨", r"\vee": "∨",
           r"\neg": "¬", r"\lnot": "¬", r"\to": "→", "┐": "¬"}
TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_]*|[01]|[¬∧∨→↔()]")
SPAN = re.compile(r"[A-Za-z0-9_¬∧∨→↔() \t]+")
OPS = {"∧": "and", "∨": "or", "→": "implies", "↔": "iff"}


def normalize(text: str) -> str:
    for source in sorted(ALIASES, key=len, reverse=True):
        if source.startswith("\\"):
            text = re.sub(re.escape(source) + r"(?![A-Za-z])", lambda _: ALIASES[source], text)
        else:
            text = text.replace(source, ALIASES[source])
    return text


def parse(text: str):
    text = normalize(text).strip()
    if len(text) > 512:
        raise ValueError("formula too long")
    matches = list(TOKEN.finditer(text))
    previous = 0
    for match in matches:
        if text[previous:match.start()].strip():
            raise ValueError("unsupported formula token")
        previous = match.end()
    if text[previous:].strip():
        raise ValueError("unsupported formula token")
    tokens = [m.group() for m in matches]
    pos = 0
    depth = 0

    def expression(minimum=0):
        nonlocal pos, depth
        depth += 1
        if depth > 64 or pos >= len(tokens):
            raise ValueError("incomplete or deeply nested formula")
        token = tokens[pos]
        pos += 1
        if token == "¬":
            left = ("not", expression(5))
        elif token == "(":
            left = expression()
            if pos >= len(tokens) or tokens[pos] != ")":
                raise ValueError("unbalanced formula")
            pos += 1
        elif re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", token):
            left = ("var", token)
        elif token in {"0", "1"}:
            left = ("const", token)
        else:
            raise ValueError("missing operand")
        precedence = {"↔": 1, "→": 2, "∨": 3, "∧": 4}
        while pos < len(tokens) and tokens[pos] in precedence and precedence[tokens[pos]] >= minimum:
            op = tokens[pos]
            pos += 1
            right = expression(precedence[op] + (0 if op == "→" else 1))
            left = (OPS[op], left, right)
        depth -= 1
        return left

    tree = expression()
    if pos != len(tokens):
        raise ValueError("trailing formula tokens")
    return tree


def template(tree) -> str:
    variables = {}
    def walk(node):
        if node[0] == "var":
            variables.setdefault(node[1], f"v{len(variables)+1}")
            return ("var", variables[node[1]])
        if node[0] == "const":
            return node
        return (node[0], *(walk(child) for child in node[1:]))
    return json.dumps(walk(tree), separators=(",", ":"))


def extract(text: str) -> list[tuple[str, str]]:
    results = []
    for match in SPAN.finditer(normalize(text)):
        raw = match.group().strip()
        if not any(op in raw for op in "¬∧∨→↔"):
            continue
        try:
            key = template(parse(raw))
        except ValueError:
            continue
        if (raw, key) not in results:
            results.append((raw, key))
    return results


def build_formula_index(db) -> dict:
    db.execute("CREATE TABLE IF NOT EXISTS logic_formulas (chunk_id TEXT, raw TEXT, template TEXT, location TEXT, PRIMARY KEY(chunk_id,raw,location))")
    db.execute("CREATE INDEX IF NOT EXISTS idx_logic_template ON logic_formulas(template)")
    db.execute("DELETE FROM logic_formulas")
    count = 0
    # 第一版只审计第四章的命题逻辑，避免把其他学科符号误解释为命题。
    for chunk_id, kind, text in db.execute("SELECT id,kind,text FROM chunks WHERE chapter_id=4"):
        parts = [("body", text)]
        if kind == "table":
            header = next((line for line in text.splitlines() if line.startswith("|")), "")
            parts.extend(("header", cell.strip()) for cell in header.strip("|").split("|"))
        for location, content in parts:
            for raw, key in extract(content):
                db.execute("INSERT OR IGNORE INTO logic_formulas VALUES (?,?,?,?)", (chunk_id, raw, key, location))
                count += 1
    return {"formulas": db.execute("SELECT count(*) FROM logic_formulas").fetchone()[0],
            "formula_chunks": db.execute("SELECT count(DISTINCT chunk_id) FROM logic_formulas").fetchone()[0]}


def search_text(text: str) -> str:
    """只改变模型输入中的变量名，整段共享绑定；展示与生成保留原文。"""
    normalized = normalize(text)
    variables = {}
    def collect(node):
        if node[0] == "var":
            if node[1] not in variables:
                number = len(variables)
                variables[node[1]] = "pqrstuvwxyz"[number] if number < 11 else f"v{number+1}"
        elif node[0] != "const":
            for child in node[1:]:
                collect(child)
    for match in SPAN.finditer(normalized):
        if not any(op in match.group() for op in "¬∧∨→↔"):
            continue
        try:
            collect(parse(match.group().strip()))
        except ValueError:
            continue
    if not variables:
        return normalized
    # 一次替换，避免 A→p 后又把新 p 替换；只替换完整标识符。
    return re.sub(r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_]*(?![A-Za-z0-9_])",
                  lambda m: variables.get(m.group(), m.group()), normalized)
