"use client";

import StudentAccountSettings from "@/features/heart/StudentAccountSettings";
import { apiFetch } from "@/lib/api";

import { useEffect, useState } from "react";
import StudentMemorySettings from "@/features/heart/StudentMemorySettings";
import StudentModelCapabilities from "@/features/heart/StudentModelCapabilities";
import { StudentEvaluationSettings } from "@/features/heart/StudentAssessments";

interface ModelState {
  configured: boolean;
  credential_version?: string;
  base_url?: string;
  model?: string;
  api_key_masked?: string;
  updated_at?: string;
}

export default function StudentModelPage() {
  const [state, setState] = useState<ModelState>({ configured: false });
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoaded(false);
    apiFetch("/api/heart/model", { credentials: "same-origin", signal: controller.signal, cache: "no-store" })
      .then(response => { if (!response.ok) throw new Error("model_read_failed"); return response.json(); })
      .then((value: ModelState) => {
        if (controller.signal.aborted) return;
        setState(value);
        setBaseUrl(value.base_url ?? "");
        setModel(value.model ?? "");
        setLoaded(true);
      })
      .catch(() => { if (!controller.signal.aborted) setStatus("无法读取当前配置，请重新读取后再编辑。"); });
    return () => controller.abort();
  }, [reload]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (busy || !loaded) return;
    setBusy(true);
    setStatus("");
    try {
      const response = await apiFetch("/api/heart/model", {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_url: baseUrl, model, api_key: apiKey }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        setStatus(payload.detail ?? "保存失败");
        return;
      }
      setState({ configured: true, base_url: baseUrl, model, api_key_masked: payload.api_key_masked, credential_version: payload.credential_version });
      setApiKey("");
      setStatus("已保存，后续对话使用这个 Key");
    } catch {
      setApiKey(""); setLoaded(false); setStatus("未能确认保存结果，请重新读取配置后再操作。");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setStatus("");
    try {
      const response = await apiFetch("/api/heart/model", { method: "DELETE", credentials: "same-origin" });
      if (response.ok) {
        setState({ configured: false });
        setStatus("已删除。删除后对话将不可用，直到重新配置。");
      } else {
        setStatus("删除失败");
      }
    } catch {
      setLoaded(false); setStatus("未能确认删除结果，请重新读取配置后再操作。");
    } finally {
      setBusy(false);
    }
  }

  const field = "w-full rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-sm text-[var(--foreground)]";

  return (
    <div className="mx-auto max-w-2xl px-6 py-8">
      <h1 className="text-xl font-semibold text-[var(--foreground)]">我的模型</h1>
      <p className="mt-2 text-sm text-[var(--muted-foreground)]">
        对话、讲解与出题使用你自己的模型服务和接口密钥，支持 OpenAI 兼容接口。教材检索与建库仍由平台维护。
      </p>

      {state.configured && (
        <div className="mt-4 rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-4 py-3 text-sm text-[var(--foreground)]">
          当前：{state.model} · {state.base_url} · {state.api_key_masked}
        </div>
      )}

      {!loaded && !status && <p role="status" className="mt-4 text-sm">正在读取模型配置…</p>}
      {!loaded && status && <button type="button" className="mt-4 rounded-md border border-border px-3 py-2 text-sm" onClick={() => { setStatus(""); setReload(value => value + 1); }}>重新读取模型配置</button>}
      <form aria-busy={!loaded || busy} onSubmit={save} className="mt-6 space-y-4">
        <label className="block">
          <span className="text-sm font-medium text-[var(--foreground)]">模型服务地址（HTTPS）</span>
          <input className={`${field} mt-1`} value={baseUrl} required disabled={!loaded || busy}
                 placeholder="https://api.example.com/v1"
                 onChange={(event) => setBaseUrl(event.target.value)} />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-[var(--foreground)]">模型名称</span>
          <input className={`${field} mt-1`} value={model} required disabled={!loaded || busy}
                 placeholder="gpt-4o-mini"
                 onChange={(event) => setModel(event.target.value)} />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-[var(--foreground)]">接口密钥（API Key）</span>
          <input className={`${field} mt-1`} value={apiKey} type="password" required disabled={!loaded || busy}
                 placeholder={state.configured ? "输入新 Key 以替换" : "sk-..."}
                 onChange={(event) => setApiKey(event.target.value)} />
        </label>
        <div className="flex items-center gap-3">
          <button type="submit" disabled={busy || !loaded}
                  className="rounded-lg bg-[var(--primary)] px-4 py-2 text-sm font-medium text-[var(--primary-foreground)] disabled:opacity-50">
            保存
          </button>
          {state.configured && (
            <button type="button" onClick={remove} disabled={busy || !loaded}
                    className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm text-[var(--foreground)] disabled:opacity-50">
              删除
            </button>
          )}
          <span className="text-sm text-[var(--muted-foreground)]">{status}</span>
        </div>
      </form>

      {loaded && state.configured && state.credential_version && <StudentModelCapabilities version={state.credential_version} onConfigurationChanged={() => { setStatus("配置已更新，正在重新读取。"); setReload(value => value + 1); }} />}
      <StudentEvaluationSettings />
      <StudentMemorySettings />
      <StudentAccountSettings />

      <p className="mt-6 text-xs text-[var(--muted-foreground)]">
        图片题需要支持图像输入的模型；不支持时请换模型。Key 只保存密文，读取接口只返回末四位。
      </p>
    </div>
  );
}
