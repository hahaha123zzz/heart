"""旧 SQLite 教材索引的运行时停用开关；测试和离线工具可显式启用。"""
import os

MESSAGE = '旧教材索引已退役，请使用固定教材 LightRAG 或原文读取入口'


def enabled() -> bool:
    return os.getenv('HEART_LEGACY_INDEX_ENABLED', '0') == '1'


def require() -> None:
    if not enabled():
        raise RuntimeError(MESSAGE)
