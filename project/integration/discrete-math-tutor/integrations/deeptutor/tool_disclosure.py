"""按需工具定义披露：低频工具的 schema 等模型显式加载后再发送。

常用检索/补读工具仍直接进可调用层；这里只收窄目录类、阅读辅助类和 exec。
每轮重新建立加载器，场景切换自然收回上一轮的已加载工具。
"""
from __future__ import annotations

from contextvars import ContextVar

# 低频工具：清单里保留名称和一句用途，schema 由 load_tools 按需附加。
DEFERRED_TOOLS = frozenset((
    'kb_files',
    'exec',
    'reading_list_tabs',
    'reading_switch_tab',
    'view_figure',
    'reader_annotate',
))

_LOADER: ContextVar['ToolDisclosure | None'] = ContextVar('heart_tool_disclosure', default=None)


class ToolDisclosure:
    """单个回合内的按需工具加载器；每轮从空开始。"""

    def __init__(self, registry, names, *, delegate=None, direct=()):
        self.registry = registry
        self.mounted = frozenset(names)
        self.direct = frozenset(direct)
        self.deferred = frozenset(
            name for name in names if name in DEFERRED_TOOLS and name not in self.direct)
        self.delegate = delegate
        self.loaded: set[str] = set()
        self.schemas: list[dict] | None = None

    def bind(self, schemas: list[dict]) -> None:
        self.schemas = schemas

    def load(self, names) -> dict:
        loaded, already, unknown = [], [], []
        for name in dict.fromkeys(str(name) for name in names or ()):
            if name in self.loaded:
                already.append(name)
                continue
            if name not in self.deferred:
                # MCP/CLI 扩展工具仍交给上游加载器，避免按需层把它们挡住。
                if self.delegate is not None:
                    outcome = self.delegate.load([name])
                    loaded.extend(outcome.get('loaded') or [])
                    already.extend(outcome.get('already_loaded') or [])
                    unknown.extend(outcome.get('unknown') or [])
                else:
                    unknown.append(name)
                continue
            if self.registry.get(name) is None:
                unknown.append(name)
                continue
            schema = self.registry.get(name).get_definition().to_openai_schema()
            self.loaded.add(name)
            if self.schemas is not None and not any(
                    item.get('function', {}).get('name') == name for item in self.schemas):
                self.schemas.append(schema)
            loaded.append(name)
        return {'loaded': loaded, 'already_loaded': already, 'unknown': unknown}


def current_loader() -> ToolDisclosure | None:
    return _LOADER.get()


def reset() -> None:
    _LOADER.set(None)


def prepare(pipeline, context, names: list[str], *, direct=()) -> bool:
    """为本轮建立加载器；返回是否挂载了 load_tools。"""
    if not names or getattr(pipeline, '_exclusive_capability_active', lambda _: False)(context):
        _LOADER.set(None)
        return False
    loader = ToolDisclosure(pipeline.tool_lookup, names,
                            delegate=getattr(pipeline, '_deferred_loader', None),
                            direct=direct)
    if not loader.deferred:
        _LOADER.set(None)
        return False
    allowed = getattr(context, 'allowed_builtin_tools', None)
    can_mount = ('load_tools' in names
                 or ((allowed is None or 'load_tools' in allowed)
                     and pipeline.tool_lookup.get('load_tools') is not None))
    if not can_mount:
        # 发不出 load_tools 时不能只藏 schema，否则工具会被静默锁死。
        _LOADER.set(None)
        return False
    if 'load_tools' not in names:
        names.append('load_tools')
    loader.mounted = frozenset(names)
    _LOADER.set(loader)
    return True


def filter_schemas(loader: ToolDisclosure | None, schemas: list[dict]) -> list[dict]:
    """未加载的按需工具不发送 schema；同时绑定 live 列表供 load 追加。"""
    if loader is None:
        return schemas
    kept = []
    for schema in schemas:
        name = (schema.get('function') or {}).get('name')
        if name in loader.deferred and name not in loader.loaded:
            continue
        kept.append(schema)
    loader.bind(kept)
    return kept


def require_loaded(loader: ToolDisclosure | None, name: str) -> None:
    """只允许执行本轮挂载过的工具；按需工具还须先加载。"""
    if loader is None:
        return
    if name not in loader.mounted:
        raise KeyError('工具未在本轮挂载')
    if name in loader.deferred and name not in loader.loaded:
        raise KeyError('工具需要先用 load_tools 加载')
