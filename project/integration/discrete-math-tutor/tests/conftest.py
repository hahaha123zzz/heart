"""测试默认保留旧检索路径；运行时部署不设置该开关。"""
import os

os.environ.setdefault('HEART_LEGACY_INDEX_ENABLED', '1')
