"""判断结论时按缺失依据补检索一次，保留原证据顺序。"""
import re


def recover_evidence(message, sources, fallback_chunks, decision, retrieve):
    if decision.status not in {'partial', 'insufficient'} or not decision.missing:
        return sources
    if not re.search(r'是否|成立|正确|反例|判断|真假|教材|定理|定义|章节|第[0-9一二三四五六七八九十]+章|前置|依据', message):
        return sources
    # 分别查询缺失依据，避免其中的定理编号把所有召回拉回旧单元。
    queries = [str(item)[:200].strip() for item in decision.missing[:3] if str(item).strip()]
    if not queries:
        return sources
    def key(item):
        return ('id', item.chunk_id) if item.chunk_id is not None else (item.source, item.section, item.text)
    result = list(sources)
    seen = {key(item) for item in result}
    added = 0
    for query in queries:
        if added >= 3 or len(result) >= 6:
            break
        for item in retrieve(query, fallback_chunks, limit=1):
            item_key = key(item)
            if item_key in seen:
                continue
            if added >= 3 or len(result) >= 6:
                break
            result.append(item)
            seen.add(item_key)
            added += 1
    return result
