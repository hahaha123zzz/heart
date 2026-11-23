"use client";

import { apiFetch } from "@/lib/api";

import { useEffect, useState } from "react";

import MemoryList from "./memory/MemoryList";
import type { MemoryEntry as Entry } from "./memory/types";
interface MemoryPayload { preferences: Entry[]; profile: Entry[]; has_more?: boolean; }
const EMPTY: MemoryPayload = { preferences: [], profile: [] };

export default function StudentMemory() {
  const [data, setData] = useState<MemoryPayload>(EMPTY);
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setData(EMPTY); setLoaded(false); setError("");
    apiFetch(`/api/heart/memory?q=${encodeURIComponent(query.trim())}`, { credentials: "same-origin", cache: "no-store", signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error("memory_unavailable"); return response.json(); })
      .then((value: MemoryPayload) => { if (!controller.signal.aborted) { setData(value); setLoaded(true); } })
      .catch(() => { if (!controller.signal.aborted) setError("无法读取记忆，请重新读取；聊天仍可继续。"); });
    return () => controller.abort();
  }, [query, reload]);
  async function mutate(url: string, method: string, body?: string) {
    if (busy || !loaded) return;
    setBusy(true); setError(""); setStatus("");
    try {
      const response = await apiFetch(url, { method, credentials: "same-origin", headers: body ? { "Content-Type": "application/json" } : undefined, body });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) { setLoaded(false); setData(EMPTY); setError(result.detail ?? "操作失败，请重新读取后再试。"); return; }
      if (method === "POST") setText("");
      setStatus(method === "POST" ? "已添加" : "已删除"); setReload(value => value + 1);
    } catch {
      setLoaded(false); setData(EMPTY); setError("未能确认操作结果，请重新读取记忆；不会自动重复提交。");
    } finally { setBusy(false); }
  }
  function section(title: string, hint: string, entries: Entry[], kind: "preference" | "profile") {
    return <section className="mt-8">
      <h2 className="text-base font-semibold">{title}</h2><p className="mt-1 text-sm text-muted-foreground">{hint}</p>
      {loaded && <MemoryList memories={entries} disabled={busy || !loaded} isFiltered={Boolean(query)} label={title} onDelete={item=>mutate(`/api/heart/memory/${kind}/${encodeURIComponent(item.id)}`, "DELETE")} />}
    </section>;
  }
  return <div className="mx-auto w-full max-w-3xl px-6 py-8">
    <h1 className="text-xl font-semibold">我的记忆</h1>
    <p className="mt-2 text-sm text-muted-foreground">查看、删除记忆，或主动添加学习偏好。长期记忆开关请到设置页调整；关闭后仍可管理这里的内容。</p>
    <label className="mt-6 block text-sm">搜索记忆<input aria-label="搜索记忆" value={query} maxLength={100} onChange={event => setQuery(event.target.value)} className="mt-2 w-full rounded-lg border border-border bg-card px-3 py-2" /></label>
    <div aria-label="教学偏好示例" className="mt-4 flex flex-wrap gap-2">{["回答简短，先给结论再解释", "回答详细，逐步展开", "多举相关例子，并区分教材原例与补充例子", "放慢节奏，每次聚焦一个要点", "先讲解，再进行可选练习", "先用可选练习了解问题，再讲解"].map(value=><button key={value} type="button" className="rounded-md border border-border px-3 py-2 text-sm" disabled={busy||!loaded} onClick={()=>setText(value)}>{value}</button>)}</div>
    <p className="mt-2 text-sm text-muted-foreground">点击示例可填入，确认添加后才保存。长期记忆开启时跨会话生效；本轮要求可在对话中直接说明，优先于长期偏好。</p>
    <form onSubmit={event => { event.preventDefault(); if (text.trim()) void mutate("/api/heart/memory/preference", "POST", JSON.stringify({ text: text.trim() })); }} className="mt-4 flex flex-wrap gap-2">
      <input aria-label="学习偏好" value={text} maxLength={500} onChange={event => setText(event.target.value)} placeholder="例如：讲题时多举例子，先给结论再展开" className="min-w-0 flex-1 rounded-lg border border-border bg-card px-3 py-2 text-sm" />
      <button type="submit" disabled={busy || !loaded || !text.trim()} className="shrink-0 rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">添加偏好</button>
    </form>
    {!loaded && !error && <p role="status" className="mt-3 text-sm">正在读取记忆…</p>}
    {status && <p role="status" className="mt-3 text-sm">{status}</p>}
    {error && <div className="mt-3 text-sm"><p role="alert">{error}</p><button type="button" onClick={() => setReload(value => value + 1)} className="mt-2 rounded-md border border-border px-3 py-1.5">重新读取记忆</button></div>}
    {data.has_more && <p className="mt-3 text-sm text-muted-foreground">当前显示最近 200 条匹配记忆，请缩小搜索范围查看其他内容。</p>}
    {section("学习偏好", "你确认过的讲解方式与节奏。", data.preferences, "preference")}
    {section("学习画像", "只有明确来源的学习信息才会显示，不代表掌握成绩。", data.profile, "profile")}
  </div>;
}
