import React from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { browserStorage } from "@/shared/storage"
import { useLearningCreation, useLibraryFilter } from '@/components/learning/LibraryWorkspace'
import { ActivityLibrary } from '@/components/learning/ActivityLibrary'

const mocks = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), query: '', library: vi.fn() }))
vi.mock('@/hooks/useAuthStatus', () => ({ useAuthStatus: () => ({ userId: 'student-a', loading: false, statusAvailable: true }) }))
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mocks.push, replace: mocks.replace }),
  usePathname: () => '/learning/books',
  useSearchParams: () => new URLSearchParams(mocks.query),
}))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock('@/hooks/useChatWorkspaces', () => ({ useChatWorkspaces: () => ({
  workspaces: [{ workspace_id: 'other', display_name: 'Other', status: 'ready' }], error: '',
}) }))
vi.mock('@/lib/learning-library', async importOriginal => ({
  ...await importOriginal<typeof import('@/lib/learning-library')>(), learningLibrary: mocks.library,
}))
function Creation({ open }: { open: () => void }) {
  const creation = useLearningCreation(open)
  return <>{creation.dialog}<button onClick={creation.begin}>New</button></>
}
beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  mocks.query = ''
  window.history.replaceState({}, '', '/learning/books')
  mocks.library.mockResolvedValue({ items: [], unavailable_workspaces: [] })
})
it('chooses a new destination without treating the library filter as storage scope', () => {
  const open = vi.fn()
  render(<Creation open={open} />)
  fireEvent.click(screen.getByRole('button', { name: 'New' }))
  fireEvent.change(screen.getByLabelText('Save to workspace'), { target: { value: 'other' } })
  fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
  expect(mocks.push).toHaveBeenCalledWith('/learning/books?create=1&dt_workspace=other')
  expect(open).not.toHaveBeenCalled()
})
it('opens creation after client navigation even before window.location reflects the new query', async () => {
  const open = vi.fn()
  const view = render(<Creation open={open} />)
  mocks.query = 'create=1&dt_workspace=other'
  view.rerender(<Creation open={open} />)
  await waitFor(() => expect(open).toHaveBeenCalledOnce())
  expect(mocks.replace).toHaveBeenCalledWith('/learning/books?dt_workspace=other', { scroll: false })
})
it('keeps equal practice IDs in separate workspaces and filters without changing write scope', async () => {
  const libraryResult = { items: [
    { id: 1, question: 'Original question', content_workspace_id: '', content_workspace_name: 'Default workspace' },
    { id: 1, question: 'Other question', content_workspace_id: 'other', content_workspace_name: 'Other' },
  ], unavailable_workspaces: [] }
  let libraryPromise!: Promise<typeof libraryResult>
  let resolveLibrary!: (result: typeof libraryResult) => void
  mocks.library.mockImplementation(() => {
    libraryPromise = new Promise(resolve => { resolveLibrary = resolve })
    return libraryPromise
  })
  render(<ActivityLibrary kind="practice" onCreate={vi.fn()} />)
  await act(async () => {
    resolveLibrary(libraryResult)
    await libraryPromise.then(() => Promise.resolve())
  })
  expect(await screen.findByRole('link', { name: /Original question/ })).toHaveAttribute('href', '/learning/practice?store=1&question=1&dt_workspace=')
  expect(screen.getByRole('link', { name: /Other question/ })).toHaveAttribute('href', '/learning/practice?store=1&question=1&dt_workspace=other')
  fireEvent.change(screen.getByLabelText('Filter by workspace'), { target: { value: 'other' } })
  expect(screen.queryByRole('link', { name: /Original question/ })).toBeNull()
  expect(screen.getByRole('link', { name: /Other question/ })).toBeInTheDocument()
  expect(mocks.push).not.toHaveBeenCalled()
  expect(window.location.search).toBe('')
})

function Filter() {
  const result = useLibraryFilter([{ content_workspace_id: 'course', content_workspace_name: 'Course' }, { content_workspace_id: '', content_workspace_name: 'Default' }])
  return <>{result.control}</>
}
it('restores this account library filter while preserving write workspace', async () => {
  mocks.query = 'dt_workspace=destination'
  browserStorage.writeRaw('session', 'dt.learning.filter:student-a:/learning/books', 'course')
  render(<Filter />)
  await waitFor(() => expect(screen.getByLabelText('Filter by workspace')).toHaveValue('course'))
  expect(mocks.replace).toHaveBeenCalledWith('/learning/books?dt_workspace=destination&library_workspace=course', { scroll: false })
})
it('an explicit query wins over saved filters and selecting all clears the saved choice', () => {
  mocks.query = 'library_workspace=course&dt_workspace=destination'
  browserStorage.writeRaw('session', 'dt.learning.filter:student-a:/learning/books', 'another')
  render(<Filter />)
  expect(screen.getByLabelText('Filter by workspace')).toHaveValue('course')
  fireEvent.change(screen.getByLabelText('Filter by workspace'), { target: { value: '*' } })
  expect(browserStorage.readRaw('session', 'dt.learning.filter:student-a:/learning/books')).toBe('*')
  expect(mocks.replace).toHaveBeenCalledWith('/learning/books?dt_workspace=destination', { scroll: false })
})
