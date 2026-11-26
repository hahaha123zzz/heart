"""把模型写的本轮短引用 [S1] 解析成服务端生成的可点击教材链接。

短 ID 只在本回合有效；来源是否可引用由证据投影决定，未知 ID 不生成链接。
"""
from __future__ import annotations

import re
from contextvars import ContextVar

# [S1] / [S1, S2] / [S2、S3]
_SHORT = re.compile(r'\[(S\d+(?:\s*[,，、]\s*S\d+)*)\]')
# 模型偶发输出的内部形式 [citation:S1]；发布边界同样要收口。
_CITATION = re.compile(r'\[citation:\s*(S\d+(?:\s*[,，、]\s*S\d+)*)\]', re.IGNORECASE)
# 流式输出末尾可能是短 ID 的前缀（"[", "[S1, " 等）。
_SHORT_TAIL = re.compile(r'\[(?:[\s,，、]*(?:S\d*)?)*$')

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


def _split_ids(value: str) -> list[str]:
    return [part.strip() for part in re.split(r'[,，、]', value) if part.strip()]


def _replace(chunk: str, links: dict[str, str]) -> str:
    def render(match):
        parts = _split_ids(match.group(1))
        known = [links[part] for part in parts if part in links]
        unknown = [part for part in parts if part not in links]
        # 已知来源生成链接；未知 ID 保持可见，方便核对模型输出。
        if not known:
            return match.group(0)
        return ''.join(known) + ''.join(f'[{part}]' for part in unknown)

    def citation(match):
        # [citation:Sx] 是内部形式；只保留已知来源，未知形式直接丢弃。
        return ''.join(links[part] for part in _split_ids(match.group(1)) if part in links)

    return _SHORT.sub(render, _CITATION.sub(citation, chunk))


def _strip_markers(chunk: str) -> str:
    """本轮没有已披露来源时，任何短 ID 都不能成为正式引用。"""
    return _SHORT.sub('', _CITATION.sub('', chunk))


def _open_code_start(text: str) -> int | None:
    """返回未闭合行内代码/代码围栏的起点；都已闭合时返回 None。"""
    index = 0
    while index < len(text):
        tick = text.find('`', index)
        if tick < 0:
            return None
        run = 1
        while tick + run < len(text) and text[tick + run] == '`':
            run += 1
        if run >= 3:
            closing = re.search(r'`{3,}', text[tick + run:])
            if closing is None:
                return tick
            index = tick + run + closing.end()
        else:
            end = text.find('`' * run, tick + run)
            if end < 0:
                return tick
            index = end + run
    return None


def _protect(text: str, render) -> str:
    """代码块和行内代码不解析；未闭合的代码延续到正文末尾。"""
    out, index = [], 0
    while index < len(text):
        if text[index] == '`':
            run = 1
            while index + run < len(text) and text[index + run] == '`':
                run += 1
            if run >= 3:
                closing = re.search(r'`{3,}', text[index + run:])
                end = len(text) if closing is None else index + run + closing.end()
            else:
                closing_at = text.find('`' * run, index + run)
                if closing_at < 0:
                    out.append(text[index:])
                    break
                end = closing_at + run
            out.append(text[index:end])
            index = end
            continue
        tick = text.find('`', index)
        if tick < 0:
            tick = len(text)
        out.append(render(text[index:tick]))
        index = tick
    return ''.join(out)


def resolve(text: str, sources) -> str:
    """替换正文中的完整短 ID；代码块保持原样。"""
    if not text:
        return text
    links = _links(sources)
    if not links:
        return _protect(text, _strip_markers)
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
        numbers = [index[part] for part in _split_ids(match.group(1)) if part in index]
        return ''.join(f'[{number}]' for number in numbers)

    return _protect(text, lambda chunk: _SHORT.sub(render, _CITATION.sub(render, chunk)))


def _hold_start(text: str) -> int:
    """流式输出中暂不发布的尾部：可能的短 ID 前缀或未闭合的代码。"""
    start = len(text)
    tail = _SHORT_TAIL.search(text)
    if tail:
        start = tail.start()
    open_code = _open_code_start(text[:start])
    if open_code is not None:
        start = min(start, open_code)
    return start


class ShortCitationStream:
    """逐块发布：完整短 ID 立即替换；跨块标记和代码块暂存到可判定时。

    ``sources`` 可以是映射、列表或返回当前映射的函数；预检索和后续 rag
    会在流开始后才登记短 ID，所以这里必须每次读取最新映射。
    """

    def __init__(self, sources):
        self._sources = sources
        self.buffer = ""

    def current(self):
        value = self._sources() if callable(self._sources) else self._sources
        return value or {}

    def feed(self, chunk: str) -> str:
        self.buffer += str(chunk or "")
        keep = _hold_start(self.buffer)
        emit, self.buffer = self.buffer[:keep], self.buffer[keep:]
        if not emit:
            return ""
        current = self.current()
        if not current:
            # 映射还没登记（工具尚未返回）时不丢弃标记，保存前还有整体解析。
            return emit
        return resolve(emit, current)

    def flush(self) -> str:
        text, self.buffer = self.buffer, ""
        return resolve(text, self.current()) if text else ""
