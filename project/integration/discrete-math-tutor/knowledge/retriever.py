"""知识检索模块（第一版：本地误解目录匹配）。

【参考实现】"BKT + Misconception Diagnosis"类项目的 misconception 目录
（概念 → 常见错误概念），作为问题设计与状态评估的种子知识。
后续接入向量检索 / RAG 时，只需替换 retrieve_knowledge() 的实现，
其余模块不用改。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

_CATALOG_PATH = os.path.join(os.path.dirname(__file__), "misconception_catalog.json")


def load_misconception_catalog() -> Dict[str, List[Dict[str, Any]]]:
    try:
        with open(_CATALOG_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def retrieve_knowledge(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """按概念名匹配本地误解目录。第一版只做简单包含匹配。"""
    if not query:
        return []
    catalog = load_misconception_catalog()
    results: List[Dict[str, Any]] = []
    for concept, misconceptions in catalog.items():
        if concept in query or query in concept:
            for item in misconceptions:
                entry = dict(item)
                entry["concept"] = concept
                results.append(entry)
    return results[:top_k]
