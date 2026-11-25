"""宿主教材检索工具：覆盖原生 rag/kb_files，复用宿主索引与页码定位。

原生 KB 期望 LlamaIndex/LightRAG 工作目录，宿主索引是自研 sqlite。
这里用原生工具协议 + 宿主已建索引，避免重建第二份索引。
"""
from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import quote as url_quote

from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult

logger = logging.getLogger(__name__)


class HeartCourseRagTool(BaseTool):
    """Search the course textbook through the host's resident LightRAG backend.

    The host-local sqlite index remains only for non-native surfaces that carry
    no task authorization scope.
    """

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
        try:
            limit = max(1, min(int(kwargs.get("limit") or 6), 12))
        except (TypeError, ValueError):
            limit = 6
        context = kwargs.get("_heart_context")
        metadata = getattr(context, "metadata", None)
        if isinstance(metadata, dict):
            calls = int(metadata.get("_heart_course_rag_calls") or 0) + 1
            metadata["_heart_course_rag_calls"] = calls
            if calls > 2:
                # 首轮一批 + 一次定向补查；避免同一回合无限检索拖长等待。
                return ToolResult(
                    content="本轮教材检索已达到两批上限；请直接基于已返回的原文作答，"
                            "缺少的部分明确说明，不要再次调用检索。",
                    metadata={"query": query, "calls": calls})
        from .client import BackendUnavailable
        from .course_rag_provider import search_course
        try:
            result = await search_course(query, limit=limit, context=context)
        except BackendUnavailable:
            logger.warning("course search lacks a native task scope", exc_info=True)
            return ToolResult(content="当前账号缺少教材检索授权；不要编造依据。", success=False,
                              metadata={"query": query})
        except Exception:  # noqa: BLE001 - 工具异常不得中断回合
            logger.warning("course search failed", exc_info=True)
            return ToolResult(content="教材检索暂不可用，请稍后重试；不要编造依据。",
                              success=False, metadata={"query": query})
        if result is None:
            # 非原生入口（无任务授权上下文）沿用宿主本地索引。
            evidence = await asyncio.to_thread(_verified_sources, query, limit, context)
            result = {"sources": evidence}
        error = result.get("error_type")
        if error in ("not_ready", "unavailable"):
            return ToolResult(content="教材检索后端暂不可用，请稍后重试；不要编造依据。",
                              success=False, metadata={"query": query, "error": error})
        if error == "timeout":
            return ToolResult(content="教材检索超时，请稍后重试；不要编造依据。",
                              success=False, metadata={"query": query, "error": error})
        if error == "permission":
            return ToolResult(content="当前账号无权检索该教材内容；不要编造依据。",
                              success=False, metadata={"query": query, "error": error})
        if error == "stale":
            return ToolResult(content="教材版本已变化，请重新打开教材后再问。",
                              success=False, metadata={"query": query, "error": error})
        if error == "invalid":
            return ToolResult(content="检索请求无效，请缩小问题范围后再问。",
                              success=False, metadata={"query": query, "error": error})
        evidence = result.get("sources") or []
        if not evidence:
            return ToolResult(content="本轮没有检索到可核验的教材原文；不要编造依据。",
                              metadata={"query": query, "backend": result.get("backend"),
                                        "mode": result.get("mode"), "cache_hit": result.get("cache_hit")})
        if result.get("cache_hit") and result.get("content"):
            # 同一回合相同查询：原文已在模型上下文里，只提示引用编号。
            return ToolResult(content=result["content"], sources=evidence,
                              metadata={"query": query, "backend": result.get("backend"),
                                        "mode": result.get("mode"), "cache_hit": True})
        citation_lines = []
        linked = 0
        for source in evidence:
            citation = _reader_citation(source)
            if citation:
                source["reader_citation"] = citation
                linked += 1
            location = f"第{source['chapter_id']}章，第{_reader_page(source)}页，{source['location']['section']}"
            head = citation or "（未能生成教材链接，答复时说明页码）"
            citation_lines.append(
                f"来源链接（答复句末必须原样复制这一整段 Markdown，只写“第X章第Y页”不算引用）：\n"
                f"{head}\n"
                f"位置：{location}，source_id={source.get('rag_source_id', '')}\n"
                f"已核验原文：\n{source['text']}"
            )
        if result.get("backend") == "lightrag" and not linked:
            # 默认 LightRAG 路径必须给可点击角标；本地索引路径保留 read_source 兜底。
            return ToolResult(content="检索到的段落无法与当前教材阅读版本核对，本次不提供引用。",
                              success=False, metadata={"query": query, "error": "uncited"})
        lines = [
            f"教材检索结果（{len(evidence)} 条）。最终回答只引用已核验原文，"
            "并原样复制每条来源提供的完整 Markdown 教材角标链接；不要把跨章节页码改成当前章节页码。",
            *citation_lines,
        ]
        content = "\n\n".join(lines)
        logger.info("course_rag_tool backend=%s mode=%s sources=%d linked=%d chars=%d cache_hit=%s",
                    result.get("backend"), result.get("mode"), len(evidence), linked,
                    len(content), result.get("cache_hit"))
        return ToolResult(content=content, sources=evidence,
                          metadata={"query": query, "backend": result.get("backend"),
                                    "mode": result.get("mode"), "cache_hit": result.get("cache_hit")})


def _retrieve_rows(query: str) -> list:
    from knowledge import psychology_retrieval
    # Retrieve a wider candidate set so course permissions and evidence checks
    # run before any passage reaches the model.
    return psychology_retrieval.retrieve(query, [], limit=40)


def _verified_sources(query: str, limit: int = 3, context=None) -> list[dict]:
    """Authorized passages that passed formal evidence verification."""
    try:
        rows = _retrieve_rows(query)
    except Exception:
        logger.warning("course evidence retrieval failed", exc_info=True)
        return []
    rows = _authorized_course_rows(rows)[:max(limit * 4, limit)]
    if not rows:
        return []
    try:
        from .native_grounding import prepare_retrieval
        sources = prepare_retrieval(query, rows, context, "实验心理学")
    except Exception:
        logger.warning("course evidence verification failed", exc_info=True)
        return []
    return sources[:limit]


def course_evidence(query: str, limit: int = 3, context=None) -> list[dict]:
    """Verified textbook evidence that can be linked to a precise reader page."""
    evidence = []
    for source in _verified_sources(query, limit, context):
        citation = _reader_citation(source)
        if not citation:
            continue
        source["reader_citation"] = citation
        evidence.append(source)
    return evidence[:limit]


def warm_course_retrieval() -> None:
    """Load embedding/rerank indexes before the first student turn."""
    try:
        _retrieve_rows("自变量和因变量")
    except Exception:
        logger.warning("course retrieval warmup failed", exc_info=True)


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
    """PDF page of a verified source: the located rect's page, else the section's."""
    evidence = (source.get("location") or {}).get("evidence") or {}
    for rect in evidence.get("rects") or ():
        page = rect.get("page")
        if isinstance(page, int) and page > 0:
            return page
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


def _short_quote(text, limit=240):
    text = str(text or "")
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for separator in ("。", "；", "！", "？", "\n"):
        boundary = cut.rfind(separator)
        if boundary >= 4:
            return cut[:boundary + 1]
    return cut


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
    # 角标链接要短到模型能完整复制；截断必须落在句末，否则定位不到矩形。
    quote = _short_quote(source.get("quote"))
    suffix = f"?quote={url_quote(quote, safe='')}" if quote else ""
    href = f"#dt-material-{material_id}-revision-{revision}-locator-{page}{suffix}"
    return f"[教材第{chapter}章第{page}页]({href} \"citation\")"



CATALOG_DEFAULT_LIMIT = 40


class HeartCourseFilesTool(BaseTool):
    """List the course textbook's chapters from the host manifest.

    This tool serves catalog, chapter-name and file-scope questions only. Page
    bodies stay out of the tool message; the model reads原文 through ``rag``.
    """

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="kb_files",
            description=(
                "列出当前账号已授权的课程教材目录：章号、标题、节数、页数和文档 ID。"
                "只用于目录、章名和文件范围查询，不返回逐页正文。"
            ),
            parameters=[
                ToolParameter(name="pattern", type="string", required=False,
                              description="Optional substring filter on chapter titles."),
                ToolParameter(name="limit", type="integer", required=False,
                              description=f"最多列出的章数，默认 {CATALOG_DEFAULT_LIMIT}。"),
            ],
        )

    async def execute(self, **kwargs) -> ToolResult:
        pattern = str(kwargs.get("pattern") or "").strip().lower()
        try:
            limit = max(1, min(int(kwargs.get("limit") or CATALOG_DEFAULT_LIMIT), 100))
        except (TypeError, ValueError):
            limit = CATALOG_DEFAULT_LIMIT

        def list_files():
            from knowledge.pdf_reader import documents
            return _authorized_documents(documents())

        try:
            rows = await asyncio.to_thread(list_files)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(content=f"教材清单暂不可用：{type(exc).__name__}", success=False)
        selected = [row for row in rows
                    if not pattern or pattern in str(row.get("title", "")).lower()]
        listed = selected[:limit]
        omitted = len(selected) - len(listed)
        if not listed:
            lines = [f"没有匹配「{kwargs.get('pattern')}」的章节" if pattern
                     else "当前没有可访问的教材清单"]
        else:
            lines = [f"教材共 {len(rows)} 章，当前列出 {len(listed)} 章："]
            lines.extend(f"- {_catalog_line(row)}" for row in listed)
            if omitted:
                lines.append(f"另有 {omitted} 章未列出，请缩小 pattern 后再查。")
        return ToolResult(content="\n".join(lines),
                          metadata={"chapters": len(listed), "omitted": omitted})


def _authorized_documents(rows):
    """Keep only chapters whose material version the current learner may open."""
    from deeptutor.multi_user.context import get_current_user_or_none

    user = get_current_user_or_none()
    if user is None or user.is_admin:
        return rows
    from deeptutor.multi_user.learning_access import learning_material_allowed

    return [row for row in rows
            if learning_material_allowed(str(row.get("version") or "")[:16])]


def _catalog_line(row):
    """One chapter line: metadata only, never the manifest's page bodies."""
    sections = len(row.get("sections") or ())
    pages = row.get("page_count")
    if not isinstance(pages, int) or pages < 1:
        listed_pages = row.get("pages")
        pages = len(listed_pages) if isinstance(listed_pages, (list, tuple)) else None
    page_text = f"{pages} 页" if pages else "页数未知"
    return (f"第{row.get('chapter_id')}章 {row.get('title')}（{sections} 节，"
            f"{page_text}，文件 {row.get('document_id')}）")


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
