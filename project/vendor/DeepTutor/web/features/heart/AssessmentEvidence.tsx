"use client";

import { useEffect, useState } from "react";
import { requestJson } from "@/shared/api/client";

interface EvidenceDetail {
  publication_status: string;
  catalog_current: boolean;
  catalog_available?: boolean;
  vendor_evidence_id: string | null;
  evidence: { id: number; source_quote: string; learning_stage: string; assessed_mastered: boolean; synced_at: string } | null;
  misconceptions: { id: number; type: string; status: string; reason: string }[];
}

export function AssessmentEvidence({ jobId, label = "查看同步证据与误区" }: { jobId: string; label?: string }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<EvidenceDetail>();
  const [error, setError] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setData(undefined); setError(false);
    requestJson<EvidenceDetail>(`/api/heart/learning/evidence/${encodeURIComponent(jobId)}`, { cache: "no-store", signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) setData(value); })
      .catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [jobId, open, reload]);
  return <div className="mt-3 text-sm">
    <button type="button" aria-expanded={open} className="underline" onClick={() => setOpen(value => !value)}>{open ? "收起同步证据与误区" : label}</button>
    {open && <div className="mt-3 space-y-2 rounded-lg border border-border p-3">
      {!data && !error && <p role="status">正在读取同步证据…</p>}
      {error && <p role="alert">同步证据读取失败，请重试。</p>}
      {data && <>
        {!data.catalog_current && <p>{data.catalog_available === false ? "当前教材目录不可用，暂不核对目录归属。" : "该记录属于旧教材目录，不计入当前目录进度。"}</p>}
        {data.evidence ? <>
          <p>宿主已收到厂家凭证；以下为该次同步时的记录。</p>
          <p>凭证编号：{data.evidence.id}；厂家凭证：{data.vendor_evidence_id || "未提供"}</p>
          <p>{data.evidence.assessed_mastered ? "该次同步时已达到掌握要求" : "该次同步时尚未达到掌握要求"}</p>
          <blockquote className="whitespace-pre-wrap border-l-2 border-border pl-3">{data.evidence.source_quote}</blockquote>
          <p>同步于 <time dateTime={data.evidence.synced_at}>{new Date(data.evidence.synced_at).toLocaleString("zh-CN")}</time></p>
          {data.misconceptions.length ? <ul>{data.misconceptions.map(item => <li key={item.id}>{item.type}（{({ hypothesis: "待确认线索", supported: "有支持证据", confirmed: "已确认", resolved: "已缓解", dismissed: "已排除" } as Record<string, string>)[item.status] || item.status}）：{item.reason}</li>)}</ul> : <p>这条同步证据没有关联的误区观察。</p>}
        </> : <p>{data.publication_status === "published" ? "同步凭证暂不可用，请刷新核对；厂家结论仍保留。" : data.publication_status === "blocked" ? "厂家结果已保存，宿主同步受阻。" : "宿主同步尚未完成，暂不展示为已同步证据。"}</p>}
      </>}
      <button type="button" className="underline" onClick={() => setReload(value => value + 1)}>重新读取同步证据</button>
    </div>}
  </div>;
}
