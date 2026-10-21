"""Apache-2.0；DeepTutor 6cf793bd，book/agents/source_explorer.py 原样摘取。
来源和逐文件签名见 UPSTREAM.json；仅保留无应用依赖的均衡算法。
"""
from __future__ import annotations

def _balanced_slice(chunks: list[SourceChunk], *, limit: int) -> list[SourceChunk]:
    """Pick ``limit`` chunks with every source represented.

    Ranking is only meaningful *within* one engine, so we rank inside each
    source and then take round-robin across them. A global sort by ``score``
    handed the whole slice to whichever backend happened to emit the largest
    numbers, which silently dropped notebooks, chat excerpts and any KB on a
    different scoring scale out of the synthesis input entirely.
    """
    if len(chunks) <= limit:
        return list(chunks)

    by_source: dict[str, list[SourceChunk]] = {}
    for chunk in chunks:
        by_source.setdefault(f"{chunk.source}/{chunk.kb_name or ''}", []).append(chunk)
    for group in by_source.values():
        group.sort(key=lambda c: -c.score)

    picked: list[SourceChunk] = []
    groups = list(by_source.values())
    depth = 0
    while len(picked) < limit and any(depth < len(g) for g in groups):
        for group in groups:
            if depth < len(group):
                picked.append(group[depth])
                if len(picked) == limit:
                    break
        depth += 1
    return picked
