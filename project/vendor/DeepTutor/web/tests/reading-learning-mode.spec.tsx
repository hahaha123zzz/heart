import React from 'react'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ReadingWorkspacePage } from '@/components/reading/workspace/ReadingWorkspace'

const LEARNING_KEY = 'reading-learning'
const source = vi.hoisted(() => ({ material: null as import('@/lib/reading-api').MaterialDetail | null, notice: vi.fn() }))

vi.mock('next/navigation', () => ({
  useParams: () => ({ workspaceId: 'reading-1' }),
  usePathname: () => '/reading/reading-1',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (value: string) => value }),
}))
vi.mock('@/features/chat/ChatStateAdapter', () => ({
  useChatStateAdapter: () => ({
    state: { isStreaming: false, sessionId: null },
    sendMessage: vi.fn(),
  }),
}))
vi.mock('@/components/reading/workspace/useReadingWorkspace', () => ({
  useReadingWorkspace: () => ({
    workspace: {
      workspace_id: 'reading-1',
      title: 'Immersive Reading',
      tabs: [],
      active_material_id: null,
    },
    setWorkspace: vi.fn(),
    conversations: [],
    setConversations: vi.fn(),
    loading: false,
    error: null,
    notice: null,
    setNotice: source.notice,
    material: source.material,
    annotations: [],
    activeTab: undefined,
    activeConversation: null,
    linkedSessionIds: [],
    activeLocator: null,
    setActiveLocator: vi.fn(),
    transcript: [],
    organizedNotes: null,
    setOrganizedNotes: vi.fn(),
    refresh: vi.fn(),
    switchMaterial: vi.fn(),
    removeMaterial: vi.fn(),
    newConversation: vi.fn(),
    organizeNotes: vi.fn(),
    buildMasteryPath: vi.fn(),
    renameWorkspace: vi.fn(),
    reportViewport: vi.fn(),
  }),
}))
vi.mock('@/components/reading/ReaderPane', () => ({
  ReaderPane: () => null,
  READER_ASK_EVENT: 'dt:reader-ask',
}))
// The shared reading-actions catalog fetches on mount; this spec is about the
// shell's panels, so it stands in as a pass-through (no actions, no header
// read-aloud button).
vi.mock('@/components/reading/ReadingActionsProvider', () => ({
  ReadingActionsProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}))
vi.mock('@/components/reading/workspace/SourceNavigator', () => ({
  SourceNavigator: ({ open }: { open: boolean }) => (
    <div data-testid="reading-navigator" data-open={String(open)}>
      navigator
    </div>
  ),
}))
vi.mock('@/components/reading/workspace/ReadingCompanion', () => ({
  ReadingCompanion: ({ selection }: { selection: { quote: string } | null }) => <div data-testid="reading-companion">{selection?.quote}</div>,
}))
vi.mock('@/components/reading/workspace/MediaReadingStage', () => ({
  MediaReadingStage: () => null,
}))
vi.mock('@/components/reading/library/AddMaterialsDialog', () => ({
  AddMaterialsDialog: () => null,
}))
vi.mock('@/components/reading/workspace/WorkspaceChrome', () => ({
  CompanionWelcome: () => null,
  EmptyWorkspace: () => null,
  MaterialFailure: () => null,
  MaterialProcessing: () => null,
  MenuItem: ({ label }: { label: string }) => <span>{label}</span>,
  iconForMaterial: () => () => null,
}))
vi.mock('@/components/reading/workspace/dialogs', () => ({
  ConversationLinkDialog: () => null,
  NotebookCaptureDialog: () => null,
  OrganizedNotesDialog: () => null,
  WorkspaceConfirmDialog: () => null,
  WorkspaceValueDialog: () => null,
}))

function visibleDialog() {
  const dialog = document.createElement('div')
  dialog.setAttribute('role', 'dialog')
  dialog.getBoundingClientRect = () => ({ width: 100 }) as unknown as DOMRect
  document.body.appendChild(dialog)
  return dialog
}

describe('reading fullscreen learning', () => {
  beforeEach(() => {
    source.material = null; source.notice.mockReset();
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: query === '(min-width: 1280px)',
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    })
  })

  it('fills the shell, isolates surrounding UI, closes panels, and restores them', async () => {
    const user = userEvent.setup()
    const shell = document.createElement('div')
    const sidebar = document.createElement('aside')
    // jsdom has no inert property, but the effect must preserve the original
    // value rather than just remove an attribute it did not own.
    Object.defineProperty(sidebar, 'inert', {
      configurable: true,
      value: false,
      writable: true,
    })
    const content = document.createElement('div')
    shell.append(sidebar, content)
    document.body.appendChild(shell)
    render(<ReadingWorkspacePage />, { container: content })

    const root = screen.getByRole('main')
    expect(root).toHaveAttribute('data-reading-workspace')
    expect(root).not.toHaveAttribute('data-learning')
    // The outline starts closed; learning mode opens it and hands it back.
    expect(screen.getByTestId('reading-navigator')).toHaveAttribute('data-open', 'false')
    expect(screen.getByTestId('reading-companion')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Fullscreen learning' }))
    expect(root).toHaveAttribute('data-learning', 'true')
    expect(screen.getByTestId('reading-navigator')).toHaveAttribute('data-open', 'true')
    expect(screen.queryByTestId('reading-companion')).not.toBeInTheDocument()
    await waitFor(() => expect(sidebar.inert).toBe(true))

    await user.click(screen.getByRole('button', { name: 'Exit learning mode' }))
    expect(root).not.toHaveAttribute('data-learning')
    expect(screen.getByTestId('reading-navigator')).toHaveAttribute('data-open', 'false')
    expect(screen.getByTestId('reading-companion')).toBeInTheDocument()
    expect(sidebar.inert).not.toBe(true)
    expect(sidebar.hasAttribute('inert')).toBe(false)
    expect(sessionStorage.getItem(LEARNING_KEY)).toBeNull()
  })

  it('does not steal Escape while a dialog is visible', async () => {
    const user = userEvent.setup()
    const dialog = visibleDialog()
    render(<ReadingWorkspacePage />)
    await user.click(screen.getByRole('button', { name: 'Fullscreen learning' }))
    await user.keyboard('{Escape}')
    expect(screen.getByRole('main')).toHaveAttribute('data-learning', 'true')

    dialog.remove()
    await user.keyboard('{Escape}')
    expect(screen.getByRole('main')).not.toHaveAttribute('data-learning')
  })

  it('expands and collapses contents while learning mode is active', async () => {
    const user = userEvent.setup()
    render(<ReadingWorkspacePage />)

    await user.click(screen.getByRole('button', { name: 'Fullscreen learning' }))
    expect(screen.getByTestId('reading-navigator')).toHaveAttribute('data-open', 'true')

    await user.click(screen.getByRole('button', { name: 'Collapse contents' }))
    expect(screen.getByTestId('reading-navigator')).toHaveAttribute('data-open', 'false')
    expect(screen.getByRole('button', { name: 'Reading companion' })).toHaveAttribute(
      'aria-expanded',
      'false'
    )

    await user.click(screen.getByRole('button', { name: 'Expand contents' }))
    expect(screen.getByTestId('reading-navigator')).toHaveAttribute('data-open', 'true')

    await user.click(screen.getByRole('button', { name: 'Exit learning mode' }))
    expect(screen.getByTestId('reading-navigator')).toHaveAttribute('data-open', 'false')
  })

  it("restores the same workspace's saved learning mode and entry panels", async () => {
    const user = userEvent.setup()
    sessionStorage.setItem(
      LEARNING_KEY,
      JSON.stringify({
        workspaceId: 'reading-1',
        panels: {
          companionOpen: true,
          navigatorOpen: false,
          navigatorCollapsed: false,
        },
      })
    )
    render(<ReadingWorkspacePage />)
    await waitFor(() => expect(screen.getByRole('main')).toHaveAttribute('data-learning', 'true'))
    expect(screen.getByTestId('reading-navigator')).toHaveAttribute('data-open', 'true')
    expect(screen.queryByTestId('reading-companion')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Exit learning mode' }))
    expect(screen.getByRole('main')).not.toHaveAttribute('data-learning')
    expect(screen.getByTestId('reading-companion')).toBeInTheDocument()
    expect(sessionStorage.getItem(LEARNING_KEY)).toBeNull()
  })
  it('invalidates a pending quote on a revision change without remounting and rejects a delayed old event', async () => {
    source.material = { filename: 'test.pdf', mime: 'application/pdf', title: 'Test', byte_size: 100, char_count: 20, created_at: 1, has_raw_view: true, extractor: 'fixture', annotation_count: 0, outline_text: '', material_id: 'abcdef1234567890', revision: 1, version: '1'.repeat(64), unit: 'page', unit_count: 2, outline: [], unit_refs: [], render_mode: 'pdf' };
    const view = render(<ReadingWorkspacePage />);
    const detail = { materialId: source.material.material_id, materialRevision: 1, version: source.material.version, quote: '旧版选区', locator: 1 };
    act(() => { window.dispatchEvent(new CustomEvent('dt:reader-ask', { detail })); });
    expect(screen.getByTestId('reading-companion')).toHaveTextContent('旧版选区');
    source.material = { ...source.material, revision: 2, version: '2'.repeat(64) };
    view.rerender(<ReadingWorkspacePage />);
    await waitFor(() => expect(screen.getByTestId('reading-companion')).not.toHaveTextContent('旧版选区'));
    expect(source.notice).toHaveBeenCalledWith('教材已切换或换版，旧选区已失效，请重新选择。');
    act(() => { window.dispatchEvent(new CustomEvent('dt:reader-ask', { detail })); });
    expect(screen.getByTestId('reading-companion')).not.toHaveTextContent('旧版选区');
    expect(source.notice).toHaveBeenLastCalledWith('教材已切换或换版，请重新选择引用。');
  });

})
