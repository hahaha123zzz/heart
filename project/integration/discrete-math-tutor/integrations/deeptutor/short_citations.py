"""把模型写的本轮短引用 [S1] 解析成服务端生成的可点击教材链接。

短 ID 只在本回合有效；来源是否可引用由证据投影决定，未知 ID 不生成链接。
"""
from __future__ import annotations

import re
from contextvars import ContextVar

# [S1] / [S1, S2] / [S2、S3]
_SHORT = re.compile(r'\[(S\d+(?:\s*[,，、]\s*S\d+)*)\]')
_BACKTICK = re.compile(r'```')

# 本轮 worker 内的短 ID → 已核验链接映射；由宿主 rag 工具写入。
current_short_sources: ContextVar[dict] = ContextVar('heart_short_sources', default={})


def _links(sources) -> dict[str, str]:
    if isinstance(sources, dict):
        rows = [(str(key), source) for key, source in sources.items()]
    else:
        rows = [(
            str(source.get('short_id') or (
                f"S{source['index']}" if source.get('index') else '')) if isinstance(source, dict) else '',
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
        parts = [part.strip() for part in re.split(r'[,，、]', match.group(1))]
        known = [links[part] for part in parts if part in links]
        unknown = [part for part in parts if part not in links]
        # 未知 ID 保持可见；没有已披露来源就不生成正式链接。
        if not known:
            return match.group(0)
        return ''.join(known) + ''.join(f'[{part}]' for part in unknown)
    return _SHORT.sub(render, chunk)


def _protect(text: str, render) -> str:
    """代码块和行内代码不解析；未闭合的 ``` 视为延续到正文末尾。"""
    out, last = [], 0
    while last < len(text):
        if text.startswith('```', last):
            end = text.find('```', last + 3)
            end = len(text) if end == -1 else end + 3
            out.append(text[last:end])
            last = end
            continue
        if text[last] == '`':
            end = text.find('`', last + 1)
            if end != -1:
                out.append(text[last:end + 1])
                last = end + 1
                continue
        nxt = text.find('`', last)
        if nxt == -1:
            nxt = len(text)
        out.append(render(text[last:nxt]))
        last = nxt
    return ''.join(out)


def resolve(text: str, sources) -> str:
    """替换正文中的完整短 ID；代码块保持原样。"""
    links = _links(sources)
    if not text or not links:
        return text
    return _protect(text, lambda chunk: _replace(chunk, links))


def to_numeric(text: str, sources) -> str:
    """把短 ID 换成发布门禁使用的本轮编号（[S1, S2] → [1][2]）。"""
    index = {}
    rows = sources.values() if isinstance(sources, dict) else (sources or ())
    for source in rows:
        if not isinstance(source, dict) or not source.get('index'):
            continue
        identifier = source.get('short_id') or f"S{source['index']}"
        index[str(identifier)] = int(source['index'])

    def render(match):
        numbers = [index[part.strip()] for part in re.split(r'[,，、]', match.group(1))
                   if part.strip() in index]
        return ''.join(f'[{number}]' for number in numbers) if numbers else match.group(0)

    return _protect(text, lambda chunk: _SHORT.sub(render, chunk))


def _hold_start(text: str) -> int:
    """流式输出中暂不发布的尾部：半个短 ID 或未闭合的代码块。"""
    start = len(text)
    tail = re.search(r'\[S\d*(?:\s*[,，、]\s*S\d*)?$', text)
    if tail:
        start = tail.start()
    fences = [match.start() for match in _BACKTICK.finditer(text[:start])]
    if len(fences) % 2:
        start = min(start, fences[-1])
    return start


class ShortCitationStream:
    """逐块发布：完整短 ID 立即替换；跨块标记和代码块暂存到可判定时。"""

    def __init__(self, sources):
        self.sources = sources
        self.buffer = ""

    def feed(self, chunk: str) -> str:
        self.buffer += str(chunk or "")
        keep = _hold_start(self.buffer)
        emit, self.buffer = self.buffer[:keep], self.buffer[keep:]
        return resolve(emit, self.sources) if emit else ""

    def flush(self) -> str:
        text, self.buffer = self.buffer, ""
        return resolve(text, self.sources) if text else ""
