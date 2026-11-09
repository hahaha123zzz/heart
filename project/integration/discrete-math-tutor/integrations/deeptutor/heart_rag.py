"""宿主教材检索工具：覆盖原生 rag/kb_files，复用宿主索引与页码定位。

原生 KB 期望 LlamaIndex/LightRAG 工作目录，宿主索引是自研 sqlite。
这里用原生工具协议 + 宿主已建索引，避免重建第二份索引。
"""
from __future__ import annotations

import asyncio

from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult


class HeartCourseRagTool(BaseTool):
    """Search the course textbook through the host's verified sqlite index."""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="rag",
            description=(
                "Retrieve relevant passages from the course textbook attached to "
                "this turn. Returns the page and section so a claim can be traced."
            ),
            parameters=[
                ToolParameter(name="query", type="string", description="Search query."),
                ToolParameter(name="kb_name", type="string", required=False,
                              description="Knowledge base name; the course textbook is the default."),
                ToolParameter(name="limit", type="integer", required=False, default=6,
                              description="Maximum passages, 1-12."),
            ],
        )

    async def execute(self, **kwargs) -> ToolResult:
        query = str(kwargs.get("query") or "").strip()
        if not query:
            return ToolResult(content="query 不能为空。", success=False)
        limit = max(1, min(int(kwargs.get("limit") or 6), 12))
        kb_name = str(kwargs.get("kb_name") or "实验心理学")
        try:
            from knowledge import psychology_retrieval
            rows = await asyncio.to_thread(psychology_retrieval.retrieve, query, [], limit=limit)
        except Exception as exc:  # noqa: BLE001 - 检索失败要回到模型而不是中断回合
            return ToolResult(content=f"教材检索暂不可用：{type(exc).__name__}", success=False)
        if not rows:
            return ToolResult(content="教材索引没有匹配段落；不要编造原文。",
                              metadata={"query": query})
        from .native_grounding import prepare_retrieval
        try:
            sources = await asyncio.to_thread(prepare_retrieval, query, rows, kwargs.get('_heart_context'), kb_name)
        except (ValueError, OSError):
            return ToolResult(content='本次检索原文未能通过正式证据核验，请缩小问题范围后重试。', success=False)
        if not sources:
            return ToolResult(content='没有可核验的教材证据，不要编造原文。', success=False)
        lines = [f"教材检索结果（{len(sources)} 条，引用写作 [序号]）："]
        for source in sources:
            location = f"第{source['chapter_id']}章，第{source['page']}页，{source['location']['section']}"
            lines.append(f"[{source['index']}] {location} (source_id={source['rag_source_id']})\n{source['text']}")
        return ToolResult(content="\n\n".join(lines), sources=sources)



class HeartCourseFilesTool(BaseTool):
    """List the course textbook's chapters/sections from the host manifest."""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="kb_files",
            description="List the course textbook's chapters and sections with page ranges.",
            parameters=[ToolParameter(name="pattern", type="string", required=False,
                                       description="Optional substring filter on chapter titles.")],
        )

    async def execute(self, **kwargs) -> ToolResult:
        pattern = str(kwargs.get("pattern") or "").strip().lower()

        def list_files():
            from knowledge.pdf_reader import documents
            return documents()

        try:
            rows = await asyncio.to_thread(list_files)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(content=f"教材清单暂不可用：{type(exc).__name__}", success=False)
        selected = [row for row in rows if not pattern or pattern in str(row.get("title", "")).lower()]
        lines = [f"教材共 {len(rows)} 章，当前列出 {len(selected)} 章："]
        for row in selected:
            sections = len(row.get("sections") or ())
            pages = row.get("pages") or ""
            lines.append(f"- 第{row.get('chapter_id')}章 {row.get('title')}（{sections} 节"
                         f"{'，' + str(pages) + ' 页' if pages else ''}，文件 {row.get('document_id')}）")
        return ToolResult(content="\n".join(lines), metadata={"chapters": len(selected)})


def install_heart_tools() -> None:
    """用宿主实现替换同名内置工具；进程内重复调用是幂等的。

    同时改写内置目录，保证注册表因插件状态重建后仍加载宿主实现。
    """
    from deeptutor.runtime.registry.tool_registry import get_tool_registry
    from deeptutor.tools.builtin_specs import BUILTIN_TOOL_SPEC_BY_NAME, BuiltinToolSpec

    BUILTIN_TOOL_SPEC_BY_NAME["rag"] = BuiltinToolSpec(
        "rag", "integrations.deeptutor.heart_rag:HeartCourseRagTool")
    BUILTIN_TOOL_SPEC_BY_NAME["kb_files"] = BuiltinToolSpec(
        "kb_files", "integrations.deeptutor.heart_rag:HeartCourseFilesTool")
    registry = get_tool_registry()
    registry.load_builtins()
    registry.register(HeartCourseRagTool())
    registry.register(HeartCourseFilesTool())


def warm_retrieval() -> None:
    """worker 启动时加载本地 embedding，避免首个 rag 请求等待模型加载。"""
    import logging
    import time

    logger = logging.getLogger(__name__)
    started = time.perf_counter()
    try:
        from knowledge.hybrid_retrieval import INDEX, _vectors

        _vectors(str(INDEX), INDEX.stat().st_mtime_ns)
        from knowledge import psychology_retrieval

        psychology_retrieval.retrieve("自变量和因变量", [], limit=1)
    except Exception:  # noqa: BLE001 - 预热失败不应阻止服务启动
        logger.warning("教材检索预热失败，将在首次请求时重试", exc_info=True)
    else:
        logger.info("教材检索预热完成 %.1fs", time.perf_counter() - started)
