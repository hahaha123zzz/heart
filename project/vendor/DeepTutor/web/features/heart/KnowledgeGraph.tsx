"use client";

import cytoscape, { type Core } from "cytoscape";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

interface GraphNode {
  id: string;
  type: string;
  description: string;
  chapter: string;
}

interface GraphEdge {
  source: string;
  target: string;
  weight: number;
  description: string;
}

const CHAPTERS = Array.from({ length: 16 }, (_, index) => index + 1);

export default function KnowledgeGraph() {
  const [chapter, setChapter] = useState(2);
  const [query, setQuery] = useState("");
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [error, setError] = useState("");
  const host = useRef<HTMLDivElement>(null);
  const cy = useRef<Core | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ chapter: String(chapter), limit: "80" });
      if (query.trim()) params.set("q", query.trim());
      const response = await fetch(`/api/graph/subgraph?${params}`, { credentials: "same-origin" });
      if (!response.ok) {
        setError(response.status === 401 ? "请先登录" : "图谱加载失败");
        return;
      }
      const payload = await response.json();
      setNodes(payload.nodes ?? []);
      setEdges(payload.edges ?? []);
      setTruncated(Boolean(payload.truncated));
      setSelected(null);
    } finally {
      setLoading(false);
    }
  }, [chapter, query]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!host.current) return;
    cy.current?.destroy();
    cy.current = null;
    if (nodes.length === 0) return;
    const instance = cytoscape({
      container: host.current,
      elements: [
        ...nodes.map((node) => ({ data: { id: node.id, label: node.id } })),
        ...edges.map((edge, index) => ({
          data: { id: `e${index}`, source: edge.source, target: edge.target },
        })),
      ],
      style: [
        {
          selector: "node",
          style: {
            "background-color": "var(--primary)",
            label: "data(label)",
            color: "var(--foreground)",
            "font-size": 10,
            "text-valign": "bottom",
            "text-margin-y": 4,
            width: 14,
            height: 14,
          },
        },
        {
          selector: "edge",
          style: {
            width: 1,
            "line-color": "var(--border)",
            "curve-style": "bezier",
          },
        },
        { selector: "node:selected", style: { "background-color": "var(--info)" } },
      ],
      layout: { name: "cose", animate: false, idealEdgeLength: 90, nodeRepulsion: 6000 } as never,
      wheelSensitivity: 0.2,
    });
    instance.on("tap", "node", (event) => {
      const id = event.target.id();
      setSelected(nodes.find((node) => node.id === id) ?? null);
    });
    cy.current = instance;
    return () => {
      instance.destroy();
      cy.current = null;
    };
  }, [nodes, edges]);

  return (
    <div className="flex h-full min-h-0 flex-col px-6 py-6">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <h1 className="text-xl font-semibold text-[var(--foreground)]">教材知识图谱</h1>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">
            按章节展示教材中的概念与关系；节点点击可看说明。
          </p>
        </div>
        <label className="ml-auto text-sm text-[var(--muted-foreground)]">
          章节
          <select
            value={chapter}
            onChange={(event) => setChapter(Number(event.target.value))}
            className="ml-2 rounded-lg border border-[var(--border)] bg-[var(--card)] px-2 py-1 text-sm text-[var(--foreground)]"
          >
            {CHAPTERS.map((value) => (
              <option key={value} value={value}>第 {value} 章</option>
            ))}
          </select>
        </label>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => { if (event.key === "Enter") void load(); }}
          placeholder="搜索概念"
          className="rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-1 text-sm text-[var(--foreground)]"
        />
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-lg bg-[var(--primary)] px-3 py-1 text-sm text-[var(--primary-foreground)]"
        >
          查询
        </button>
      </div>

      {error && <p className="mt-3 text-sm text-[var(--destructive)]">{error}</p>}
      {truncated && (
        <p className="mt-3 text-sm text-[var(--muted-foreground)]">
          仅显示前 80 个节点（部分显示）。
        </p>
      )}
      {!loading && nodes.length === 0 && !error && (
        <p className="mt-6 text-sm text-[var(--muted-foreground)]">本章暂无图谱节点。</p>
      )}

      <div className="mt-4 flex min-h-0 flex-1 gap-4">
        <div ref={host} className="min-h-[420px] flex-1 rounded-xl border border-[var(--border)] bg-[var(--card)]" />
        <aside className="w-72 shrink-0 overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
          {selected ? (
            <div className="space-y-3 text-sm">
              <h2 className="text-base font-semibold text-[var(--foreground)]">{selected.id}</h2>
              {selected.type && (
                <p className="text-[var(--muted-foreground)]">类型：{selected.type}</p>
              )}
              <p className="whitespace-pre-wrap text-[var(--foreground)]">
                {selected.description || "暂无说明。"}
              </p>
              <div className="flex gap-2">
                <Link href="/chat" className="rounded-md border border-[var(--border)] px-2 py-1 text-xs">
                  去学习
                </Link>
                <Link href="/learning/practice" className="rounded-md border border-[var(--border)] px-2 py-1 text-xs">
                  去练习
                </Link>
              </div>
              <p className="text-xs text-[var(--muted-foreground)]">
                掌握状态：尚未评估（等结果同步接入后显示）。
              </p>
            </div>
          ) : (
            <p className="text-sm text-[var(--muted-foreground)]">点击节点查看详情。</p>
          )}
        </aside>
      </div>
    </div>
  );
}
