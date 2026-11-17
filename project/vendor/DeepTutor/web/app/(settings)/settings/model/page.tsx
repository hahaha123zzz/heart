"use client";

import { useEffect, useState } from "react";

interface ModelState {
  configured: boolean;
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

  useEffect(() => {
    fetch("/api/heart/model", { credentials: "same-origin" })
      .then((response) => (response.ok ? response.json() : { configured: false }))
      .then((value: ModelState) => {
        setState(value);
        setBaseUrl(value.base_url ?? "");
        setModel(value.model ?? "");
      })
      .catch(() => setStatus("无法读取当前配置"));
  }, []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setStatus("");
    try {
      const response = await fetch("/api/heart/model", {
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
      setState({ configured: true, base_url: baseUrl, model, api_key_masked: payload.api_key_masked });
      setApiKey("");
      setStatus("已保存，后续对话使用这个 Key");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setStatus("");
    try {
      const response = await fetch("/api/heart/model", { method: "DELETE", credentials: "same-origin" });
      if (response.ok) {
        setState({ configured: false });
        setStatus("已删除。删除后对话将不可用，直到重新配置。");
      } else {
        setStatus("删除失败");
      }
    } finally {
      setBusy(false);
    }
  }

  const field = "w-full rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-sm text-[var(--foreground)]";

  return (
    <div className="mx-auto max-w-2xl px-6 py-8">
      <h1 className="text-xl font-semibold text-[var(--foreground)]">我的模型</h1>
      <p className="mt-2 text-sm text-[var(--muted-foreground)]">
        对话、讲解与出题使用你自己的 OpenAI-compatible Key。教材检索与建库仍由平台维护。
      </p>

      {state.configured && (
        <div className="mt-4 rounded-lg border border-[var(--border)] bg-[var(--secondary)] px-4 py-3 text-sm text-[var(--foreground)]">
          当前：{state.model} · {state.base_url} · {state.api_key_masked}
        </div>
      )}

      <form onSubmit={save} className="mt-6 space-y-4">
        <label className="block">
          <span className="text-sm font-medium text-[var(--foreground)]">Base URL（必须 HTTPS）</span>
          <input className={`${field} mt-1`} value={baseUrl} required
                 placeholder="https://api.example.com/v1"
                 onChange={(event) => setBaseUrl(event.target.value)} />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-[var(--foreground)]">模型名称</span>
          <input className={`${field} mt-1`} value={model} required
                 placeholder="gpt-4o-mini"
                 onChange={(event) => setModel(event.target.value)} />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-[var(--foreground)]">API Key</span>
          <input className={`${field} mt-1`} value={apiKey} type="password" required
                 placeholder={state.configured ? "输入新 Key 以替换" : "sk-..."}
                 onChange={(event) => setApiKey(event.target.value)} />
        </label>
        <div className="flex items-center gap-3">
          <button type="submit" disabled={busy}
                  className="rounded-lg bg-[var(--primary)] px-4 py-2 text-sm font-medium text-[var(--primary-foreground)] disabled:opacity-50">
            保存
          </button>
          {state.configured && (
            <button type="button" onClick={remove} disabled={busy}
                    className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm text-[var(--foreground)] disabled:opacity-50">
              删除
            </button>
          )}
          <span className="text-sm text-[var(--muted-foreground)]">{status}</span>
        </div>
      </form>

      <p className="mt-6 text-xs text-[var(--muted-foreground)]">
        图片题需要支持图像输入的模型；不支持时请换模型。Key 只保存密文，读取接口只返回末四位。
      </p>
    </div>
  );
}
