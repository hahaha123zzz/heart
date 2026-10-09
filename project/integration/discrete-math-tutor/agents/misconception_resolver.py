"""Misconception Resolver —— 判断新误解假设是否与已有误解语义相同（去重）。

【自主实现】真实运行时 LLM 会用不同措辞的 type 描述同一个错误概念，
导致同一误解被拆成多行（如 suppression_confusion 与 重评=抑制）。
策略（两级）：
1. 先做规范化精确匹配（normalize_type + 别名表）；
2. 仍匹配不到时，让 LLM 在"已有误解列表"中判断是否同义，返回要并入的 id。
只有当"出现新假设且已有误解"时才触发 LLM，成本可控。
"""

from __future__ import annotations

from typing import List, Optional

from llm.client import LLMClient
from models.misconception import Misconception, normalize_type

SYSTEM_PROMPT = """[AGENT:misconception_resolver]
你在做误解去重。给定"已有误解列表"和一个"新误解假设"，
判断新假设是否与某条已有误解表达的是**同一个错误概念**（意思相同即可，措辞不同没关系）。
只输出 JSON：{"matched_id": 要并入的已有误解 id（整数），若都不是同一概念则 null, "reason": "一句话"}"""


class MisconceptionResolver:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def resolve(
        self, hypothesis, existing: List[Misconception]
    ) -> Optional[int]:
        """返回应并入的已有误解 id；返回 None 表示应新建。"""
        if not existing:
            return None

        # 1) 规范化精确匹配
        target = normalize_type(getattr(hypothesis, "type", "") or "")
        if target:
            for item in existing:
                if item.id is not None and normalize_type(item.type) == target:
                    return item.id

        # 2) LLM 语义匹配
        payload = [
            {"id": m.id, "type": m.type, "description": m.description}
            for m in existing
            if m.id is not None
        ]
        if not payload:
            return None
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "已有误解：" + str(payload) + "\n"
                    "新假设：" + str(
                        {
                            "type": getattr(hypothesis, "type", ""),
                            "description": getattr(hypothesis, "description", ""),
                        }
                    )
                ),
            },
        ]
        data = self.llm.chat_json(messages)
        matched = data.get("matched_id")
        if isinstance(matched, bool):
            return None
        if isinstance(matched, int):
            return matched
        if isinstance(matched, str) and matched.strip().isdigit():
            return int(matched.strip())
        return None
