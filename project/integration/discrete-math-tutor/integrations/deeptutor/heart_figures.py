"""原生链路的教材图表索引工具：只负责选择，不返回图片。"""
from __future__ import annotations

from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult


class HeartLookupFiguresTool(BaseTool):
    """按章/节或关键词查宿主教材图表索引。"""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="lookup_figures",
            description=(
                "查看教材图表索引（图x-y/表x-y），判断本轮回答是否需要引用教材原图或表格。"
                "索引只用于选择，不是原文证据；需要原图时再调用 rag(asset_id=...)。"
            ),
            parameters=[
                ToolParameter(name="query", type="string", required=False,
                              description="当前问题或关键词；明确写图号/表号时按编号查找。"),
                ToolParameter(name="chapter_id", type="integer", required=False,
                              description="章号；省略时全书语义检索。"),
                ToolParameter(name="section_id", type="integer", required=False,
                              description="节号；提供时必须同时提供章号。"),
                ToolParameter(name="limit", type="integer", required=False, default=8,
                              description="返回条数，默认8，最多20。"),
            ],
        )

    async def execute(self, **kwargs) -> ToolResult:
        try:
            chapter_id = int(kwargs["chapter_id"]) if kwargs.get("chapter_id") not in (None, "") else None
            section_id = int(kwargs["section_id"]) if kwargs.get("section_id") not in (None, "") else None
        except (TypeError, ValueError):
            return ToolResult(content="chapter_id 和 section_id 必须是整数。", success=False)
        if section_id is not None and chapter_id is None:
            return ToolResult(content="按小节查询需要同时提供章号。", success=False)
        query = str(kwargs.get("query") or "").strip()
        if chapter_id is None and section_id is None and not query:
            return ToolResult(content="请提供图号/表号、关键词或章号，再读取图表索引。", success=False)
        try:
            limit = max(1, min(20, int(kwargs.get("limit", 8))))
        except (TypeError, ValueError):
            limit = 8
        from knowledge.visual_index import format_entries, load_index
        index = load_index()
        if not index.entries:
            return ToolResult(content="教材图表索引尚未生成。", success=False)
        entries = index.lookup(chapter_id=chapter_id, section_id=section_id, query=query, limit=limit)
        if not entries:
            if chapter_id is not None and section_id is not None:
                scope = f"第{chapter_id}章第{section_id}节"
            elif chapter_id is not None:
                scope = f"第{chapter_id}章"
            else:
                scope = "全书"
            return ToolResult(content=f"{scope}没有匹配的图表索引，不要配图。", metadata={
                "chapter_id": chapter_id, "section_id": section_id, "count": 0})
        if chapter_id is not None and all(entry.chapter_id == chapter_id for entry in entries):
            scope = f"第{chapter_id}章" + (f"第{section_id}节" if section_id is not None else "")
        else:
            scope = "全书匹配"
        lines = [f"当前范围：{scope}（{len(entries)} 条）", format_entries(entries),
                 "需要原图时调用 rag(asset_id=...)，正文用 ![图题](media:资源ID) 展示。"
                 "状态为“待核”的条目只作线索；状态为“缺图”的条目没有 asset_id，不要声称展示了原图。"]
        return ToolResult(content="\n".join(lines), metadata={
            "chapter_id": chapter_id, "section_id": section_id,
            "count": len(entries), "labels": [entry.label for entry in entries],
            "entries": [{"label": entry.label, "asset_id": entry.asset_id,
                         "knowledge_points": list(entry.knowledge_points)}
                        for entry in entries]})


__all__ = ["HeartLookupFiguresTool"]
