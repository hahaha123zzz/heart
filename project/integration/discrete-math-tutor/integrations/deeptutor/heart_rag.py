"""宿主教材检索工具：覆盖原生 rag/kb_files，复用宿主索引与页码定位。

原生 KB 期望 LlamaIndex/LightRAG 工作目录，宿主索引是自研 sqlite。
这里用原生工具协议 + 宿主已建索引，避免重建第二份索引。
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import quote as url_quote

from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult


class HeartCourseRagTool(BaseTool):
    """Search the course textbook through the host's verified sqlite index."""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="rag",
            description=(
                "在当前账号已授权的课程教材中检索相关原文，返回可核验的章节、PDF 页码、版本和可点击引用。"
            ),
            parameters=[
                ToolParameter(name="query", type="string", description="要检索的教材问题或概念。"),
                ToolParameter(name="kb_name", type="string", required=False,
                              description="课程教材名称；默认使用当前课程教材。"),
                ToolParameter(name="limit", type="integer", required=False, default=6,
                              description="最多返回段落数，范围 1-12。"),
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
            # Retrieve a wider candidate set so course permissions can be
            # applied before any passage is returned to the model.
            rows = await asyncio.to_thread(psychology_retrieval.retrieve, query, [], limit=40)
        except Exception as exc:  # noqa: BLE001 - 检索失败要回到模型而不是中断回合
            return ToolResult(content=f"教材检索暂不可用：{type(exc).__name__}", success=False)
        rows = await asyncio.to_thread(_authorized_course_rows, rows)
        rows = rows[:limit]
        if not rows:
            return ToolResult(content="已授权的教材范围内没有足够匹配原文；不要编造依据。",
                              metadata={"query": query})
        from .native_grounding import prepare_retrieval
        try:
            sources = await asyncio.to_thread(prepare_retrieval, query, rows, kwargs.get('_heart_context'), kb_name)
        except (ValueError, OSError):
            return ToolResult(content='本次检索原文未能通过正式证据核验，请缩小问题范围后重试。', success=False)
        if not sources:
            return ToolResult(content='没有可核验的教材证据，不要编造原文。', success=False)
        linked_sources = []
        citation_lines = []
        for source in sources:
            citation = _reader_citation(source)
            if not citation:
                continue
            source["reader_citation"] = citation
            linked_sources.append(source)
            location = f"第{source['chapter_id']}章，第{_reader_page(source)}页，{source['location']['section']}"
            citation_lines.append(f"来源：{citation}（{location}）\n已核验原文：\n{source['text']}")
        if not linked_sources:
            return ToolResult(content="检索到的段落无法与当前教材阅读版本核对，本次不提供引用。", success=False)
        lines = [
            f"教材检索结果（{len(linked_sources)} 条）。最终回答只引用已核验原文，"
            "并原样复制每条来源提供的完整 Markdown 教材角标链接；不要把跨章节页码改成当前章节页码。",
            *citation_lines,
        ]
        return ToolResult(content="\n\n".join(lines), sources=linked_sources)


def _authorized_course_rows(rows):
    """Remove passages from chapters the current learner cannot open."""
    from deeptutor.multi_user.context import get_current_user_or_none

    user = get_current_user_or_none()
    if user is None or user.is_admin:
        return rows
    from deeptutor.multi_user.learning_access import learning_material_allowed
    from knowledge.pdf_reader import document_for_chapter

    allowed = []
    for row in rows:
        chapter_id = getattr(row, "chapter_id", None)
        try:
            document = document_for_chapter(int(chapter_id))
        except (TypeError, ValueError):
            document = None
        if document and learning_material_allowed(str(document.get("version") or "")[:16]):
            allowed.append(row)
    return allowed


def _reader_page(source):
    """PDF page of a verified source: its own page, else its section's page."""
    page = source.get("page")
    if isinstance(page, int) and page > 0:
        return page
    try:
        from knowledge.pdf_reader import document_for_chapter

        record = document_for_chapter(int(source.get("chapter_id"))) or {}
    except (TypeError, ValueError):
        return None
    section_id = str(source.get("section_id") or "")
    for section in record.get("sections") or ():
        if str(section.get("id")) == section_id and isinstance(section.get("page"), int):
            return section["page"]
    return None


def _reader_citation(source):
    """Build a version-checked legacy-reader link for a verified RAG source."""
    document_id = str(source.get("document_id") or "")
    version = str(source.get("version") or "")
    try:
        chapter = int(source.get("chapter_id"))
        page = _reader_page(source)
    except (TypeError, ValueError):
        return ""
    if (not re.fullmatch(r"[a-f0-9]{64}", version)
            or not isinstance(page, int) or page < 1
            or chapter < 1):
        return ""
    material_id = version[:16]
    try:
        from deeptutor.reading import ReadingStore

        manifest = ReadingStore().manifest(material_id)
    except Exception:
        return ""
    if manifest.document_id != document_id or manifest.version != version:
        return ""
    revision = int(manifest.revision)
    quote = str(source.get("quote") or "")[:2000]
    suffix = f"?quote={url_quote(quote, safe='')}" if quote else ""
    href = f"#dt-material-{material_id}-revision-{revision}-locator-{page}{suffix}"
    return f"[教材第{chapter}章第{page}页]({href} \"citation\")"



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
