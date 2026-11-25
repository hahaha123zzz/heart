"""把模型写的本轮短引用 [S1] 解析成服务端生成的可点击教材链接。

短 ID 只在本回合有效；来源是否可引用由证据投影决定，未知 ID 不生成链接。
"""
from __future__ import annotations

import re
from contextvars import ContextVar

# [S1] / [S1, S2] / [S2，S3]
_SHORT = re.compile(r'\[(S\d+(?:\s*[,，]\s*S\d+)*)\]')
# 代码块与行内代码里的示例 ID 不解析。
_CODE = re.compile(r'```.*?```|`[^`\n]*`', re.S)

# 本轮 worker 内的短 ID → 已核验链接映射；由宿主 rag 工具写入。
current_short_sources: ContextVar[dict] = ContextVar('heart_short_sources', default={})


def _links(sources) -> dict[str, str]:
    if isinstance(sources, dict):
        rows = [(str(key), source) for key, source in sources.items()]
    else:
        rows = [(
            str(source.get('short_id') or (
                f"S{source['index']}" if source.get('index') else '')),
            source,
        ) for source in sources or ()]
    links = {}
    for identifier, source in rows:
        if not isinstance(source, dict):
            continue
        citation = source.get('reader_citation') or source.get('citation') or ''
        if identifier and citation:
            links[identifier] = str(citation)
    return links


def _replace(chunk: str, links: dict[str, str]) -> str:
    def render(match):
        citations = [links[part.strip()] for part in re.split(r'[,，]', match.group(1))
                     if part.strip() in links]
        # 未知 ID 保持原样：没有已披露来源就不生成正式链接。
        return ''.join(citations) if citations else match.group(0)
    return _SHORT.sub(render, chunk)


def resolve(text: str, sources) -> str:
    """替换正文中的完整短 ID；代码块保持原样。"""
    links = _links(sources)
    if not text or not links:
        return text
    out, last = [], 0
    for block in _CODE.finditer(text):
        out.append(_replace(text[last:block.start()], links))
        out.append(block.group(0))
        last = block.end()
    out.append(_replace(text[last:], links))
    return ''.join(out)
