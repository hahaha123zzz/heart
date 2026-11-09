"""Project tests; prevent imports resolving to third-party tests packages."""

import os

# 生产默认由原生 worker 执行；只验证宿主边界的测试不启动子进程，
# 需要原生行为的测试必须自己显式 patch DEEPTUTOR_NATIVE_ENABLED='1'。
os.environ.setdefault("DEEPTUTOR_NATIVE_ENABLED", "0")
# 单元测试不依赖已发布教材或外部检索服务；需要它们的测试自己显式打开。
os.environ.setdefault("FIXED_BOOK_RETRIEVAL_ENABLED", "0")
os.environ.setdefault("RAG_RETRIEVAL_ENGINE", "legacy")
# 旧执行链路不依赖本地循环；需要它的测试显式设置 LOCAL_AGENT_LOOP_ENABLED=1。
os.environ.setdefault("LOCAL_AGENT_LOOP_ENABLED", "0")
