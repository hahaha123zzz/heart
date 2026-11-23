"""启动预热：把可共享的客户端、索引和注册表在服务启动时加载，避免首轮承担冷启动。"""
from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import time

log = logging.getLogger("heart.warmup")


def _run(name: str, fn) -> None:
    started = time.perf_counter()
    try:
        fn()
    except Exception as exc:  # 预热失败不能阻止服务启动，真实请求仍会报原错误
        message = f"warmup {name} failed: {exc}"
        log.warning(message)
        print(message, flush=True)
    else:
        message = f"warmup {name} {time.perf_counter() - started:.2f}s"
        log.info(message)
        print(message, flush=True)


def warm_host() -> None:
    """宿主进程：模型客户端、教材索引和本地推理入口。"""
    from llm.client import LLMClient
    _run("host_llm_client", lambda: LLMClient()._client_lazy())
    from knowledge.pdf_reader import documents
    _run("host_pdf_documents", lambda: documents())
    from knowledge.inference_runtime import runtime_status
    _run("host_inference_runtime", runtime_status)


def warm_worker() -> None:
    """原生 worker：模型客户端、工具/提示注册表和聊天管线模块。"""
    from deeptutor.services.llm import get_llm_client
    _run("worker_llm_client", get_llm_client)
    from deeptutor.runtime.registry.tool_registry import get_tool_registry
    _run("worker_tool_registry", get_tool_registry)
    from deeptutor.services.prompt.manager import get_prompt_manager
    _run("worker_prompt_manager", get_prompt_manager)
    import deeptutor.agents.chat.capability  # noqa: F401
    import deeptutor.agents.loop.pipeline  # noqa: F401
    import deeptutor.services.session.context_builder  # noqa: F401


def install_worker_warmup(app) -> None:
    """异步资源在服务事件循环中预热，避免绑定到临时循环。"""
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def warmed_lifespan(application):
        async with original_lifespan(application) as state:
            started = time.perf_counter()
            try:
                from deeptutor.services.sandbox import get_sandbox_service
                level = await get_sandbox_service().isolation_level()
            except Exception as exc:
                message = f"warmup worker_sandbox failed: {type(exc).__name__}"
                log.warning(message)
            else:
                message = f"warmup worker_sandbox {time.perf_counter() - started:.2f}s level={level.value}"
                log.info(message)
            print(message, flush=True)
            yield state

    app.router.lifespan_context = warmed_lifespan
