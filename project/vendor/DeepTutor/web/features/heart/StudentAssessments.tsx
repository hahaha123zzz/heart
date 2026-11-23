"use client";

import { useEffect, useState } from "react";
import { apiUrl, requestJson } from "@/shared/api/client";
import { AssessmentEvidence } from "./AssessmentEvidence";
import { ApiError } from "@/shared/api/errors";

interface Assessment {
  id: string;
  status: string;
  created_at: string;
  knowledge_point: string;
  passed: boolean | null;
  feedback: string;
  answer: string;
  publication_status: string;
  source_status?:string;source_url?:string;
  assistance_status: string;
  independent: boolean;
  pause_reason?: string;
  pause_message?: string;
  citations: { quote: string; document_id: string; version: string }[];
  reassessment?: { id: string; status: string; publication_status: string; passed: boolean | null;
    feedback: string; reason: string; effective: boolean; can_retry: boolean; pause_reason?: string; pause_message?: string } | null;
}

function progressLabel(job: Assessment) {
  if (job.status === "paused" && job.pause_reason && job.pause_reason !== "credential_missing") return "等待评估能力验证";
  if (job.status === "completed") {
    if (job.publication_status === "published") return "已记录并同步";
    if (job.publication_status === "blocked") return "评分已保存，同步受阻";
    return "评分已保存，等待同步";
  }
  return ({ queued: "排队中", claimed: "准备评估", sent: "评估中", paused: "等待模型配置",
    unknown: "结果不明，未自动重试", cancelled: "已取消", discarded: "本次未计入评估",
    failed: "评估未完成" } as Record<string, string>)[job.status] ?? "等待更新";
}

function ReassessmentPanel({ job, onSubmitted }: { job: Assessment; onSubmitted: () => void }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [requestId, setRequestId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const review = job.reassessment;
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy || !confirmed || !reason.trim()) return;
    setBusy(true); setError("");
    try {
      await requestJson(apiUrl(`/api/heart/evaluation/jobs/${encodeURIComponent(job.id)}/reassessment`), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_id: requestId, reason: reason.trim(), confirm_cost: true,
          confirm_unknown_retry: review?.status === "unknown" }),
      });
      setOpen(false); onSubmitted();
    } catch (error) {
      setError(error instanceof ApiError && [404, 409, 422].includes(error.status ?? 0)
        ? error.message : "未能确认申请结果。请先刷新记录查看；再次提交会使用同一申请编号，不会重复创建任务。");
    } finally { setBusy(false); }
  }
  return (
    <div className="mt-4 border-t border-border pt-3 text-sm">
      {review && <div aria-label="复评记录">
        <p className="font-medium">复评状态：{progressLabel({ ...job, ...review })}</p>
        {review.pause_message && <p className="mt-1">暂停原因：{review.pause_message}</p>}
        <p className="mt-1">原结论：{job.passed ? "通过" : "未通过"}</p>
        {review.passed !== null && <p className="mt-1">{review.effective ? "当前有效结论" : "复评结论（待同步）"}：{review.passed ? "通过" : "未通过"}</p>}
        {review.passed !== null && <AssessmentEvidence jobId={review.id} label="查看复评同步证据与误区" />}
        <p className="mt-1 whitespace-pre-wrap break-words">申请原因：{review.reason}</p>
        {review.feedback && <p className="mt-1 whitespace-pre-wrap break-words">复评依据：{review.feedback}</p>}
      </div>}
      {(!review || review.can_retry) && !open && <button type="button"
        className="mt-2 rounded-md border border-border px-3 py-1.5 hover:bg-accent"
        onClick={() => { setRequestId(crypto.randomUUID()); setReason(review?.reason ?? ""); setConfirmed(false); setError(""); setOpen(true); }}>
        {review ? "再次申请复评" : "申请复评"}
      </button>}
      {open && <form aria-label="复评申请" onSubmit={submit} className="mt-3 space-y-3">
        <p className="text-muted-foreground">使用你当前的个人模型，最多一次评估及一次归属修正，会产生额外调用费用。每条原评分仅允许一次成功复评。</p>
        {review?.status === "unknown" && <p>上次请求结果不明，可能已计费。再次申请可能重复计费，旧请求的迟到结果将不再采用。</p>}
        <label className="block">复评原因
          <textarea required maxLength={1000} value={reason} disabled={busy} onChange={event => setReason(event.target.value)}
            className="mt-1 block w-full rounded-md border border-border bg-background p-2" />
        </label>
        <label className="flex items-start gap-2">
          <input type="checkbox" checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} />
          {review?.status === "unknown" ? "我已了解上次可能已计费，并同意再次调用产生的费用" : "我已了解并同意本次复评可能产生的模型调用费用"}
        </label>
        <div className="flex flex-wrap gap-3">
          <button type="submit" disabled={busy || !confirmed || !reason.trim()} className="rounded-md border border-border px-3 py-1.5 disabled:opacity-50">{busy ? "正在提交…" : "确认并提交复评"}</button>
          <button type="button" disabled={busy} onClick={() => setOpen(false)} className="rounded-md px-3 py-1.5">取消</button>
        </div>
        {error && <p role="alert">{error}</p>}
      </form>}
    </div>
  );
}

export function StudentAssessments() {
  const [jobs, setJobs] = useState<Assessment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let busy = false;
    const refresh = async () => {
      if (busy || document.visibilityState === "hidden") return;
      busy = true;
      try {
        const value = await requestJson<{ jobs: Assessment[] }>(apiUrl("/api/heart/evaluation/jobs"),
          { signal: controller.signal, cache: "no-store" });
        if (!controller.signal.aborted) { setJobs(value.jobs); setError(false); }
      } catch {
        if (!controller.signal.aborted) setError(true);
      } finally {
        busy = false;
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void refresh();
    const timer = window.setInterval(refresh, 15_000);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      controller.abort();
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [reload]);
  return (
    <section aria-labelledby="student-assessments" className="my-6 rounded-xl border border-border p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="student-assessments" className="font-semibold">聊天评估记录</h2>
        <button type="button" onClick={() => setReload(value => value + 1)}
          className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-accent">刷新记录</button>
      </div>
      <p className="mt-2 text-sm text-muted-foreground">显示最近 20 条记录。评估通过后，还需核验是否独立作答，才可作为掌握依据。</p>
      {loading && <p role="status" className="mt-3 text-sm">正在读取评估记录…</p>}
      {error && <p role="alert" className="mt-3 text-sm">无法读取最新评估状态。已有内容可能已过时，请刷新后再查看。</p>}
      {!loading && !error && jobs.length === 0 && <p className="mt-3 text-sm text-muted-foreground">还没有评估记录。有教材依据的有效作答会在后台评估。</p>}
      <ul className="mt-4 space-y-4">
        {jobs.map(job => (
          <li key={job.id} className="rounded-lg border border-border p-4">
            <div className="flex flex-wrap justify-between gap-2 text-sm">
              <span className="font-medium">{job.knowledge_point || "聊天作答"}</span>
              <span>{progressLabel(job)}</span>
            </div>
            {job.source_status==="deleted"&&<p className="mt-2 text-xs text-muted-foreground">原会话已删除；评估和必要作答依据仍保留。</p>}
            {job.source_status==="available"&&job.source_url&&<a href={job.source_url} className="mt-2 inline-block text-xs underline">返回原会话</a>}
            {job.passed !== null && (
              <>
                <p className="mt-2 text-sm">{job.reassessment ? "原评估结论" : "评估结论"}：{job.passed ? "通过" : "未通过"}</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {job.assistance_status === "assisted" ? "辅助作答，不更新掌握状态" : "独立性待核验，不更新掌握状态"}
                </p>
                <p className="mt-2 whitespace-pre-wrap text-sm">{job.feedback}</p>
                <details className="mt-3 text-sm">
                  <summary className="cursor-pointer">查看作答与教材依据</summary>
                  <p className="mt-2 whitespace-pre-wrap">作答：{job.answer}</p>
                  {job.citations.map((cite, index) => (
                    <blockquote key={index} className="mt-2 border-l-2 border-border pl-3 whitespace-pre-wrap">
                      {cite.quote}
                      <footer className="mt-1 break-all text-xs text-muted-foreground">教材：{cite.document_id} · 版本：{cite.version}</footer>
                    </blockquote>
                  ))}
                </details>
                <AssessmentEvidence jobId={job.id} label={job.reassessment ? "查看原评估同步证据与误区" : undefined} />
                {job.publication_status === "published" && <ReassessmentPanel job={job} onSubmitted={() => setReload(value => value + 1)} />}
              </>
            )}
            {job.status === "paused" && <p className="mt-2 text-sm text-muted-foreground">{job.pause_message || "请到个人模型设置检查或重新保存配置。"}</p>}
            {job.status === "unknown" && <p className="mt-2 text-sm text-muted-foreground">本次请求可能已产生费用，系统不会自动再次调用模型。</p>}
            <time dateTime={job.created_at} className="mt-3 block text-xs text-muted-foreground">{new Date(job.created_at).toLocaleString("zh-CN")}</time>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function StudentEvaluationSettings() {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setEnabled(null);
    requestJson<{ enabled: boolean }>(apiUrl("/api/heart/evaluation"), { signal: controller.signal, cache: "no-store" })
      .then(value => { if (!controller.signal.aborted) { setEnabled(value.enabled); setError(""); } })
      .catch(() => { if (!controller.signal.aborted) setError("无法读取评估开关，请重试。"); });
    return () => controller.abort();
  }, [reload]);
  async function save() {
    if (enabled === null || busy) return;
    setBusy(true);
    setError("");
    try {
      const value = await requestJson<{ enabled: boolean }>(apiUrl("/api/heart/evaluation"), {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !enabled }),
      });
      setEnabled(value.enabled);
    } catch { setEnabled(null); setError("未能确认保存结果，请重新读取后再操作。"); }
    finally { setBusy(false); }
  }
  return (
    <section aria-labelledby="student-evaluation-settings" className="mt-8 rounded-xl border border-border p-5">
      <h2 id="student-evaluation-settings" className="font-semibold">聊天自动评估</h2>
      <p className="mt-2 text-sm text-muted-foreground">在后台用你的个人模型评估有教材依据的作答，会产生额外调用费用。每条候选作答评估一次，归属错误时最多修正一次。</p>
      <label className="mt-4 flex items-center gap-3 text-sm">
        <input type="checkbox" checked={enabled === true} disabled={enabled === null || busy} onChange={save} />
        开启聊天自动评估
      </label>
      <p className="mt-3 text-xs text-muted-foreground">关闭后取消尚未开始的评估；已开始的请求和已保存的结果仍会处理完成。重新开启不会补评关闭期间的聊天。</p>
      {enabled === null && !error && <p role="status" className="mt-2 text-sm">正在读取开关…</p>}
      {error && <p role="alert" className="mt-2 text-sm">{error}</p>}
      {enabled === null && error && <button type="button" className="mt-2 rounded-md border border-border px-3 py-1.5 text-sm" onClick={() => setReload(value => value + 1)}>重新读取</button>}
    </section>
  );
}
