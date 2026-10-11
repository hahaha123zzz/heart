"""在结构边界以内，对较长的普通讲解段落做可选语义细分。"""

from __future__ import annotations

import math
import re

from knowledge.structured_index import UNIT_START

SENTENCES = re.compile(r"(?<=[。！？；])|\n+")


def refine(records: list[dict], model, *, min_chars: int = 350, max_chars: int = 760) -> list[dict]:
    candidates: list[tuple[int, list[str]]] = []
    batch: list[str] = []
    for index, item in enumerate(records):
        if (item["kind"] != "text" or item["asset_ids"] or UNIT_START.match(item["text"])
                or len(item["text"]) < min_chars):
            continue
        sentences = [s.strip() for s in SENTENCES.split(item["text"]) if s.strip()]
        if len(sentences) < 4:
            continue
        candidates.append((index, sentences))
        batch.extend(sentences)
    if not batch:
        return records

    embeddings = list(model.embed(batch, batch_size=32))
    output = list(records)
    offset = 0
    for index, sentences in candidates:
        vectors = embeddings[offset:offset + len(sentences)]
        offset += len(sentences)
        similarities = []
        for left, right in zip(vectors, vectors[1:]):
            dot = sum(float(a) * float(b) for a, b in zip(left, right))
            norm_left = math.sqrt(sum(float(a) ** 2 for a in left)) or 1.0
            norm_right = math.sqrt(sum(float(b) ** 2 for b in right)) or 1.0
            similarities.append(dot / (norm_left * norm_right))
        if not similarities:
            continue
        # 仅在本单元内部最明显的主题转折处切，避免把定理和图表拆散。
        low = sorted(similarities)[max(0, len(similarities) // 4 - 1)]
        threshold = min(0.62, low)
        pieces: list[str] = []
        current = ""
        for number, sentence in enumerate(sentences):
            if (number and current and len(current) >= 150
                    and (similarities[number - 1] < threshold or len(current) + len(sentence) > max_chars)):
                pieces.append(current)
                current = ""
            current += sentence
        if current:
            pieces.append(current)
        if len(pieces) < 2 or min(map(len, pieces)) < 80:
            continue
        base = records[index]
        output[index] = [base | {"id": f"{base['id']}-s{number}", "text": piece}
                         for number, piece in enumerate(pieces)]
    flattened: list[dict] = []
    for item in output:
        flattened.extend(item if isinstance(item, list) else [item])
    return flattened
