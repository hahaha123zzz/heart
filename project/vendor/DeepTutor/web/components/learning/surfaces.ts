import { ClipboardCheck, type LucideIcon } from 'lucide-react'
import type { LearningKind } from '@/lib/learning-dashboard'
import { PRACTICE_HOME } from '@/lib/learning-routes'

export interface LearningSurface {
  kind: LearningKind | "practice"
  href: string
  /** Product copy — every field here is a translation key, never rendered raw. */
  title: string
  /** The one line that fits on a card. */
  description: string
  /** What the surface actually does, for someone who has never opened it. */
  intro: string
  /** Three capabilities, each true of the shipped feature. */
  highlights: readonly [string, string, string]
  /** Plural key for how much the learner already has here. */
  unit: string
  icon: LucideIcon
  /**
   * Identity hue. Per-surface colour is confined to the icon tile: everything
   * else on the card is theme tokens.
   */
  accent: string
}

export const LEARNING_SURFACES: readonly LearningSurface[] = [
  {
    kind: 'practice',
    href: PRACTICE_HOME,
    title: 'Practice',
    description: 'Your question bank, mistakes and daily reviews.',
    intro: 'Bring questions from every learning activity together, import your own, and build lasting recall through daily practice.',
    highlights: [
      'Questions from chat collect automatically',
      'Import your own questions from spreadsheets',
      'Mistakes return when they are due for review',
    ],
    unit: '{{count}} questions',
    icon: ClipboardCheck,
    accent: 'bg-sky-500/10 text-sky-600 dark:text-sky-400',
  },
] as const
