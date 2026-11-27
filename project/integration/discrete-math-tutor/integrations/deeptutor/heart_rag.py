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

    _heart_course_rag = True

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
        from .client import BackendUnavailable
        from .course_rag_provider import search_course, source_content
        try:
            result = await search_course(query, limit=limit, context=context,
                                         budget_chars=kwargs.get("budget_chars"))
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
            named = _named_figure_content(query)
            if named:
                return ToolResult(content=named, metadata={"query": query, "figures_only": True})
            return ToolResult(content="本轮没有检索到可核验的教材原文；不要编造依据。",
                              metadata={"query": query, "backend": result.get("backend"),
                                        "mode": result.get("mode"), "cache_hit": result.get("cache_hit")})
        if result.get("cache_hit") and result.get("content"):
            # 同一回合相同查询：原文已在模型上下文里，只提示短 ID。
            _attach_citations(evidence, context)
            return ToolResult(content=_evidence_content(result, evidence, kwargs.get("budget_chars"),
                                                       cache_hit=True),
                              sources=evidence,
                              metadata={"query": query, "backend": result.get("backend"),
                                        "mode": result.get("mode"), "cache_hit": True})
        linked = _attach_citations(evidence, context)
        if result.get("backend") == "lightrag" and not linked:
            # 默认 LightRAG 路径必须给可点击角标；本地索引路径保留 read_source 兜底。
            return ToolResult(content="检索到的段落无法与当前教材阅读版本核对，本次不提供引用。",
                              success=False, metadata={"query": query, "error": "uncited"})
        content = _evidence_content(result, evidence, kwargs.get("budget_chars"))
        logger.info("course_rag_tool backend=%s mode=%s sources=%d linked=%d chars=%d cache_hit=%s",
                    result.get("backend"), result.get("mode"), len(evidence), linked,
                    len(content), result.get("cache_hit"))
        return ToolResult(content=content, sources=evidence,
                          metadata={"query": query, "backend": result.get("backend"),
                                    "mode": result.get("mode"), "cache_hit": result.get("cache_hit")})


def _named_figure_content(query):
    """明确点名的图号即使检索没命中，也直接给出已登记原图。"""
    from knowledge.figures import retrieve_figures
    try:
        figures = retrieve_figures(query, [])
    except (ValueError, OSError, KeyError):
        return ""
    if not figures:
        return ""
    lines = ["用户点名的教材原图（教材登记原图，正文用 media: 直接展示，不要说无法提供）："]
    for figure in figures:
        note = " ".join((figure.context or "").split())[:160]
        lines.append(f"![{figure.label}](media:{figure.id})"
                     + (f"（教材说明：{note}）" if note else ""))
    return "\n".join(lines)


def _evidence_content(result, evidence, budget_chars, *, cache_hit=False):
    """只把能生成正式链接的证据写成短 ID；混合结果不留无法解析的编号。"""
    from .course_rag_provider import source_content
    content = str(result.get("content") or "")
    linked = [source for source in evidence if source.get("reader_citation")]
    if cache_hit and content:
        # 命中回合缓存时只补提示，不把整段原文再次展开。
        if result.get("backend") == "lightrag" and 0 < len(linked) < len(evidence):
            content += f"\n\n另有 {len(evidence) - len(linked)} 条原文未通过阅读版本核验，不作为引用。"
        return content
    content = content or source_content(evidence, budget_chars)
    if result.get("backend") != "lightrag":
        return content
    if not linked or len(linked) == len(evidence):
        return content
    dropped = len(evidence) - len(linked)
    return (source_content(linked, budget_chars)
            + f"\n\n另有 {dropped} 条原文未通过阅读版本核验，不作为引用。")


def _attach_citations(evidence, context):
    """生成正式链接并登记本轮短 ID，供发布边界解析 [S1]。"""
    linked = 0
    metadata = getattr(context, "metadata", None) if context is not None else None
    short = metadata.get("_heart_short_sources") if isinstance(metadata, dict) else None
    for source in evidence:
        citation = _reader_citation(source)
        if not citation:
            continue
        source["reader_citation"] = citation
        linked += 1
        identifier = str(source.get("short_id") or "")
        if not identifier:
            continue
        if not isinstance(short, dict):
            short = {}
            if isinstance(metadata, dict):
                metadata["_heart_short_sources"] = short
        row = short.setdefault(identifier, {**source})
        row["reader_citation"] = citation
        row["page"] = _reader_page(source)
    return linked


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
    """旧 SQLite 检索已退役；固定教材的 LightRAG 就绪由宿主启动核验。"""
    import logging

    logging.getLogger(__name__).info("旧教材索引已退役，跳过旧检索预热")
