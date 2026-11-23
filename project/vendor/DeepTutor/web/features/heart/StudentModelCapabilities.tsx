"use client";

import { useEffect, useRef, useState } from "react";
import { apiUrl, requestJson } from "@/shared/api/client";
import { randomUuid } from "@/lib/random-uuid";
import { ApiError } from "@/shared/api/errors";

type Capability = "chat" | "assessment" | "tools" | "vision";
type CheckState = { status: string; message: string; error_code: string };
const LABELS: Record<Capability, string> = { chat: "基础文本响应", assessment: "结构化评估样例", tools: "工具调用样例", vision: "图像输入样例" };
const STATUS: Record<string, string> = { untested: "尚未验证", running: "正在验证", passed: "样例通过", failed: "未通过", unknown: "结果不明", stale: "配置已变化" };
type Payload = { credential_version: string; capabilities: Record<Capability, CheckState> };

export default function StudentModelCapabilities({ version, onConfigurationChanged }: { version: string; onConfigurationChanged: () => void }) {
  const [data, setData] = useState<Payload | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [readError, setReadError] = useState("");
  const [activity, setActivity] = useState("");
  const [checking, setChecking] = useState<Capability | null>(null);
  const [reload, setReload] = useState(0);
  const currentData = data?.credential_version === version ? data : null;
  const pending = useRef(false);
  const changed = useRef(onConfigurationChanged);
  changed.current = onConfigurationChanged;
  useEffect(() => { setConfirmed(false); setError(""); setActivity(""); }, [version]);
  useEffect(() => {
    const controller = new AbortController();
    let refreshing = false;
    const refresh = async () => {
      if (refreshing || document.visibilityState === "hidden") return;
      refreshing = true;
      try {
        const value = await requestJson<Payload>(apiUrl("/api/heart/model/checks"), { signal: controller.signal, cache: "no-store" });
        if (controller.signal.aborted) return;
        if (value.credential_version !== version) { changed.current(); return; }
        setData(value); setReadError("");
      } catch { if (!controller.signal.aborted) setReadError("无法读取验证状态，请重新读取；不会自动发起模型调用。"); }
      finally { refreshing = false; }
    };
    void refresh();
    const timer = window.setInterval(refresh, 3000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [version, reload]);
  async function check(capability: Capability) {
    if (pending.current || !confirmed || !currentData || Object.values(currentData.capabilities).some(item => item.status === "running")) return;
    let requestId: string;
    try { requestId = randomUuid(); }
    catch { setError("无法创建验证请求，本次未发送，请刷新页面后重试。"); return; }
    pending.current = true; setBusy(true); setChecking(capability); setError("");
    setActivity(`正在验证${LABELS[capability]}，请稍候；本次只发送一次请求。`);
    try {
      const result = await requestJson<CheckState>(apiUrl("/api/heart/model/checks"), { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_id: requestId, credential_version: version, capability, confirm_cost: true }),
      });
      setData(previous => previous?.credential_version === version ? {
        ...previous, capabilities: { ...previous.capabilities, [capability]: result },
      } : previous);
      setActivity(`${LABELS[capability]}：${STATUS[result.status] ?? "等待更新"}。${result.message || ""}再次验证请重新勾选费用确认。`);
    } catch (error) {
      setActivity("本次验证请求已结束，请先核对状态；再次验证请重新勾选费用确认。");
      setError(error instanceof ApiError && [409, 503].includes(error.status ?? 0) ? error.message
        : "未能确认验证结果，请重新读取状态；本次可能已计费，不会自动重发。");
    } finally { pending.current = false; setBusy(false); setChecking(null); setConfirmed(false); setReload(value => value + 1); }
  }
  const running = !!currentData && Object.values(currentData.capabilities).some(item => item.status === "running");
  return <section aria-labelledby="model-capabilities" className="mt-8 rounded-xl border border-border p-5">
    <h2 id="model-capabilities" className="font-semibold">模型能力验证</h2>
    <p className="mt-2 text-sm text-muted-foreground">每次选一项，会用你的个人模型发送一次收费请求，不自动重试。样例通过不代表真实教材评分或复杂图片识别已验收。</p>
    <p className="mt-2 text-sm text-muted-foreground">评分和复评须先通过结构化评估样例。更换 Key 或模型后需要重新验证；评估未通过不阻止继续尝试聊天。</p>
    <label className="mt-4 flex items-start gap-2 text-sm">
      <input type="checkbox" checked={confirmed} disabled={busy || running || !currentData} onChange={event => setConfirmed(event.target.checked)} />
      我已了解并同意本次所选能力验证产生的模型调用费用
    </label>
    <ul className="mt-4 space-y-4">
      {(Object.keys(LABELS) as Capability[]).map(capability => <li key={capability} className="rounded-lg border border-border p-3 text-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span>{LABELS[capability]}：{busy && checking === capability ? "正在验证" : STATUS[currentData?.capabilities[capability].status ?? "untested"] ?? "等待更新"}</span>
          <button type="button" disabled={busy || running || !currentData || !confirmed} onClick={() => void check(capability)}
            className="rounded-md border border-border px-3 py-1.5 disabled:opacity-50">{busy && checking === capability ? "正在验证" : "验证"}{LABELS[capability]}</button>
        </div>
        {currentData?.capabilities[capability].message && <p className="mt-2 whitespace-pre-wrap">{currentData.capabilities[capability].message}</p>}
      </li>)}
    </ul>
    {activity && <p role="status" aria-live="polite" className="mt-3 text-sm">{activity}</p>}
    {readError && <p role="alert" className="mt-3 text-sm">{readError}</p>}
    {error && <p role="alert" className="mt-3 text-sm">{error}</p>}
    <button type="button" disabled={busy} onClick={() => setReload(value => value + 1)} className="mt-3 rounded-md border border-border px-3 py-1.5 text-sm">重新读取验证状态</button>
  </section>;
}
