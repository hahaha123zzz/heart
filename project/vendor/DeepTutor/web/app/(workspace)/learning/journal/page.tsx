"use client";

import { Suspense } from "react";
import { LearningShell } from "@/components/learning/LearningShell";
import LearningJournalPanel from "@/components/space/LearningJournalPanel";
import { StudentAssessments } from "@/features/heart/StudentAssessments";

export default function LearningJournalPage() {
  return <LearningShell title="学习档案与证据" subtitle="查看辅导记录、厂家评估及已同步的教材证据。">
    <p className="mb-5 text-sm text-muted-foreground">辅导记录按当前工作区显示，聊天评估按当前账号显示。辅导档案用于延续学习；掌握判断以厂家测评记录为准。宿主同步可能稍有延迟，记录会明确标出状态。</p>
    <Suspense fallback={<p role="status">正在读取学习档案…</p>}><LearningJournalPanel /></Suspense>
    <StudentAssessments />
  </LearningShell>;
}
