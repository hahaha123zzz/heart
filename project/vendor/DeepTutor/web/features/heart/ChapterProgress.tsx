"use client";

import { useEffect, useState } from "react";
import { apiUrl, requestJson } from "@/shared/api/client";

type Progress = {
  catalog_available: boolean;
  points: {
    id: string;
    name: string;
    snapshot: { assessed_mastered: boolean; learning_stage: string; next_review_at: string | null; synced_at: string } | null;
    practice_review?: { correct: boolean | null; self_report: boolean; assistance_status?: string; next_review_at: string } | null;
    sync_pending: boolean;
    sync_blocked: boolean;
  }[];
};

export function ChapterProgress({ chapter }: { chapter: number }) {
  const [data, setData] = useState<Progress>();
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    requestJson<Progress>(apiUrl(`/api/heart/learning/chapter-progress?chapter=${chapter}`), {
      signal: controller.signal, cache: "no-store",
    }).then(value => { if (!controller.signal.aborted) { setData(value); setFailed(false); } })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [chapter, reload]);
  return (
    <section aria-labelledby="chapter-progress" className="my-5 rounded-xl border border-border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="chapter-progress" className="font-semibold">本章学习状态</h2>
        <button type="button" disabled={loading} className="rounded-md border border-border px-3 py-1 text-sm disabled:opacity-50"
          onClick={() => setReload(value => value + 1)}>刷新学习状态</button>
      </div>
      <p className="mt-2 text-sm text-muted-foreground">按教材知识点显示最近同步的学习记录。确认图谱实体对应关系后，才会在节点上显示个人状态。</p>
      {loading && <p role="status" className="mt-3 text-sm">正在读取学习状态…</p>}
      {failed && <p role="alert" className="mt-3 text-sm">学习状态读取失败{data ? "，下方记录可能已过时" : "，请刷新重试"}。</p>}
      {data && !data.catalog_available && <p className="mt-3 text-sm">知识点目录暂不可用。</p>}
      {data?.catalog_available && data.points.length === 0 && <p className="mt-3 text-sm">本章暂无已确认知识点。</p>}
      <ul className="mt-3 divide-y divide-border text-sm">
        {data?.points.map(point => <li key={point.id} className="space-y-1 py-3">
          <p className="font-medium">{point.name}</p>
          {point.sync_pending && <p>有评估结果待同步</p>}
          {point.sync_blocked && <p>有评估结果同步受阻</p>}
          {point.snapshot ? <>
            <p>{point.snapshot.assessed_mastered ? "已掌握" : point.snapshot.learning_stage === "practiced_with_help" ? "还没掌握（有辅助练习记录）" : "还没掌握"}</p>
            {point.snapshot.next_review_at && <p>记录中的复习时间：<time dateTime={point.snapshot.next_review_at}>{new Date(point.snapshot.next_review_at).toLocaleString("zh-CN")}</time></p>}
            <p className="text-muted-foreground">同步于 <time dateTime={point.snapshot.synced_at}>{new Date(point.snapshot.synced_at).toLocaleString("zh-CN")}</time></p>
          </> : <p className="text-muted-foreground">暂无学习记录</p>}
          {point.practice_review && <p>
            最近同步的题库复习：{point.practice_review.self_report ? "学生自评" : point.practice_review.correct === true ? "答对" : point.practice_review.correct === false ? "答错" : "未判分"}{point.practice_review.assistance_status === "assisted" ? "（已查看答案）" : ""}。题库下次复习：<time dateTime={point.practice_review.next_review_at}>{new Date(point.practice_review.next_review_at).toLocaleString("zh-CN")}</time>
          </p>}
        </li>)}
      </ul>
    </section>
  );
}
