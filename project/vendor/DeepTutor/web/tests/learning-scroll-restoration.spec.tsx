import React from 'react'
import { fireEvent, render } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { LearningScrollRestoration } from '@/components/learning/LearningScrollRestoration'
import { browserStorage } from '@/shared/storage'
const state = vi.hoisted(() => ({ user: 'a', available: true }))
vi.mock('next/navigation', () => ({ usePathname: () => '/learning/journal', useSearchParams: () => new URLSearchParams('dt_workspace=course') }))
vi.mock('@/hooks/useAuthStatus', () => ({ useAuthStatus: () => ({ userId: state.user, loading: false, statusAvailable: state.available }) }))
beforeEach(() => { sessionStorage.clear(); state.user = 'a'; state.available = true })
const key = (user: string) => `dt.learning.scroll:${user}:/learning/journal?dt_workspace=course`
it('restores only this account and query, then saves a user scroll', () => {
  browserStorage.writeRaw('session', key('a'), '600')
  browserStorage.writeRaw('session', key('b'), '300')
  const view = render(<section data-feature-page><LearningScrollRestoration /><div data-page-container /></section>)
  const section = view.container.querySelector('section')!
  expect(section.scrollTop).toBe(600)
  fireEvent.wheel(section); section.scrollTop = 700; fireEvent.scroll(section)
  view.unmount()
  expect(browserStorage.readRaw('session', key('a'))).toBe('700')
  expect(browserStorage.readRaw('session', key('b'))).toBe('300')
})
it('does not read or save page state before identity is confirmed', () => {
  state.available = false
  browserStorage.writeRaw('session', key('a'), '600')
  const view = render(<section data-feature-page><LearningScrollRestoration /></section>)
  const section = view.container.querySelector('section')!
  expect(section.scrollTop).toBe(0)
  section.scrollTop = 100; fireEvent.scroll(section); view.unmount()
  expect(browserStorage.readRaw('session', key('a'))).toBe('600')
})
