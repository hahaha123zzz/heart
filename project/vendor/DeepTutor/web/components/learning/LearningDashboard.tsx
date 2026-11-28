'use client'

import Link from 'next/link'
import { useTranslation } from 'react-i18next'
import { LearningShell } from './LearningShell'
import { LearningWays } from './LearningWays'

export function LearningDashboard() {
  const { t } = useTranslation()
  return (
    <LearningShell
      back={false}
      title="我的学习"
      subtitle={t('One tutor, your own way to learn.')}
    >
      <nav aria-label="学习记录与设置" className="mb-6 flex flex-wrap gap-3 text-sm">
        <Link href="/learning/journal" className="rounded-lg border border-border px-4 py-2 hover:bg-accent">学习档案与证据</Link>
        <Link href="/learning/graph" className="rounded-lg border border-border px-4 py-2 hover:bg-accent">知识图谱</Link>
        <Link href="/memory" className="rounded-lg border border-border px-4 py-2 hover:bg-accent">学习记忆</Link>
      </nav>
      <LearningWays />
    </LearningShell>
  )
}
