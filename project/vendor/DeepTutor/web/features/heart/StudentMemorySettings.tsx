"use client";

import { useEffect, useState } from "react";
import { apiUrl, requestJson } from "@/shared/api/client";

export default function StudentMemorySettings() {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setEnabled(null); setError("");
    requestJson<{ enabled: boolean }>(apiUrl("/api/heart/memory/settings"), { signal: controller.signal, cache: "no-store" })
      .then(value => { if (!controller.signal.aborted) setEnabled(value.enabled); })
      .catch(() => { if (!controller.signal.aborted) setError("无法读取长期记忆开关，请重新读取。"); });
    return () => controller.abort();
  }, [reload]);
  async function change() {
    if (enabled === null || busy) return;
    setBusy(true); setError("");
    try {
      const result = await requestJson<{ enabled: boolean }>(apiUrl("/api/heart/memory/settings"), {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !enabled }),
      });
      setEnabled(result.enabled);
    } catch {
      setEnabled(null); setError("未能确认保存结果，请重新读取开关；不会自动重复提交。");
    } finally { setBusy(false); }
  }
  return <section className="mt-8 rounded-xl border border-border p-4">
    <h2 className="font-semibold">长期记忆</h2>
    <label className="mt-3 flex items-center gap-2 text-sm">
      <input type="checkbox" checked={enabled === true} disabled={enabled === null || busy} onChange={() => void change()} />
      开启长期记忆供辅导使用
    </label>
    <p className="mt-2 text-sm text-muted-foreground">关闭后辅导不读取长期记忆，也不自动新增。旧内容仍可查看、删除，并可手动添加偏好。重新开启不会补扫旧聊天，与聊天自动评估分别控制。</p>
    <p className="mt-2 text-sm text-muted-foreground">自动整理覆盖已同步的评分和聊天中明确说出的部分学习困难。这些记忆用于辅导，不改变掌握成绩。</p>
    {enabled === null && !error && <p role="status" className="mt-2 text-sm">正在读取开关…</p>}
    {error && <p role="alert" className="mt-2 text-sm">{error}</p>}
    {enabled === null && error && <button type="button" className="mt-2 rounded-md border border-border px-3 py-1.5 text-sm" onClick={() => setReload(value => value + 1)}>重新读取长期记忆开关</button>}
  </section>;
}
