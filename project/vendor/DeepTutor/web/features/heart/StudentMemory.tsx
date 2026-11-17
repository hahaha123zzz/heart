"use client";

import { useCallback, useEffect, useState } from "react";

interface Entry {
  id: string;
  text: string;
}

interface MemoryPayload {
  preferences: Entry[];
  profile: Entry[];
}

const EMPTY: MemoryPayload = { preferences: [], profile: [] };

export default function StudentMemory() {
  const [data, setData] = useState<MemoryPayload>(EMPTY);
  const [text, setText] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const response = await fetch("/api/heart/memory", { credentials: "same-origin" });
    if (response.ok) setData(await response.json());
    else setStatus("无法读取记忆");
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function addPreference(event: React.FormEvent) {
    event.preventDefault();
    const value = text.trim();
    if (!value) return;
    setBusy(true);
    setStatus("");
    try {
      const response = await fetch("/api/heart/memory/preference", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: value }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        setStatus(payload.detail ?? "保存失败");
        return;
      }
      setData((current) => ({ ...current, preferences: payload.preferences ?? current.preferences }));
      setText("");
      setStatus("已添加");
    } finally {
      setBusy(false);
    }
  }

  async function remove(kind: "preference" | "profile", id: string) {
    setBusy(true);
    setStatus("");
    try {
      const response = await fetch(`/api/heart/memory/${kind}/${encodeURIComponent(id)}`, {
        method: "DELETE",
        credentials: "same-origin",
      });
      if (!response.ok) {
        setStatus("删除失败");
        return;
      }
      await load();
      setStatus("已删除");
    } finally {
      setBusy(false);
    }
  }

  const card =
    "rounded-xl border border-[var(--border)] bg-[var(--card)] px-4 py-3 text-sm text-[var(--foreground)]";

  function section(title: string, hint: string, items: Entry[], kind: "preference" | "profile") {
    return (
      <section className="mt-8">
        <h2 className="text-base font-semibold text-[var(--foreground)]">{title}</h2>
        <p className="mt-1 text-sm text-[var(--muted-foreground)]">{hint}</p>
        {items.length === 0 ? (
          <p className="mt-3 text-sm text-[var(--muted-foreground)]">还没有内容。</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {items.map((item) => (
              <li key={item.id} className={`${card} flex items-start justify-between gap-4`}>
                <span className="whitespace-pre-wrap">{item.text}</span>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => remove(kind, item.id)}
                  className="shrink-0 rounded-md border border-[var(--border)] px-2 py-1 text-xs text-[var(--muted-foreground)] disabled:opacity-50"
                >
                  删除
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    );
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-8">
      <h1 className="text-xl font-semibold text-[var(--foreground)]">我的记忆</h1>
      <p className="mt-2 text-sm text-[var(--muted-foreground)]">
        这里是从学习过程中整理出的偏好与画像。你可以查看、删除，也可以主动补充学习偏好。
      </p>

      <form onSubmit={addPreference} className="mt-6 flex gap-2">
        <input
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="例如：讲题时多举例子，先给结论再展开"
          className="w-full rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-sm text-[var(--foreground)]"
        />
        <button
          type="submit"
          disabled={busy || !text.trim()}
          className="shrink-0 rounded-lg bg-[var(--primary)] px-4 py-2 text-sm font-medium text-[var(--primary-foreground)] disabled:opacity-50"
        >
          添加偏好
        </button>
      </form>
      {status && <p className="mt-2 text-sm text-[var(--muted-foreground)]">{status}</p>}

      {section("学习偏好", "你确认过的讲解方式与节奏。", data.preferences, "preference")}
      {section("学习画像", "根据学习记录整理的画像，删除后不再用于生成。", data.profile, "profile")}
    </div>
  );
}
