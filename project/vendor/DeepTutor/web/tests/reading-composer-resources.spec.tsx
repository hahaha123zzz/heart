import { render, fireEvent, screen } from "@testing-library/react";
import { getReadingTurnState, resetReadingTurnState, setReadingViewport } from "@/lib/reading-turn-state";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ResourceSelection } from "@/features/chat/ChatStateAdapter";
import type { ComposerResourceCatalog } from "@/hooks/useComposerResources";
import { initI18n } from "@/i18n/init";

initI18n("en");

const captured = vi.hoisted(() => ({
  props: null as {
    inputHeader?: React.ReactNode;
    resourceCatalog?: ComposerResourceCatalog;
    resourceSelection?: ResourceSelection;
    onResourceSelectionChange?: (selection: ResourceSelection) => void;
  } | null,
  catalogWorkspaceId: "" as string | null,
  setResourceSelection: vi.fn(),
  catalog: { skills: [{ id: "skill-1", name: "Tutor" }], mcp: [] },
  selection: { skills: ["skill-1"], mcp: [] as string[] },
}));

vi.mock("@/features/chat/ChatStateAdapter", () => ({
  useChatStateAdapter: () => ({
    state: {
      messages: [],
      knowledgeBases: [],
      llmSelection: null,
      personaSelection: "",
      resourceSelection: captured.selection,
      workspaceId: "reading-workspace",
      isStreaming: false,
    },
    sendMessage: vi.fn(),
    submitUserReply: vi.fn(),
    cancelStreamingTurn: vi.fn(),
    setKBs: vi.fn(),
    setLLMSelection: vi.fn(),
    setPersonaSelection: vi.fn(),
    setResourceSelection: captured.setResourceSelection,
  }),
}));

vi.mock("@/hooks/useChatWorkspaces", () => ({
  useChatWorkspaces: () => ({ workspaces: [], error: "" }),
}));

vi.mock("@/hooks/useComposerResources", () => ({
  useComposerResources: (workspaceId: string | null) => {
    captured.catalogWorkspaceId = workspaceId;
    return captured.catalog;
  },
}));

vi.mock("@/hooks/useWorkspaceChatActions", () => ({
  useWorkspaceChatActions: () => ({
    capabilities: [],
    activeCapabilityValue: "",
    selectCapability: vi.fn(),
  }),
}));

vi.mock("@/components/chat/home/StandaloneComposer", () => ({
  default: (props: typeof captured.props) => {
    captured.props = props;
    return <div>{props?.inputHeader}composer</div>;
  },
}));

const { ReadingComposer } = await import(
  "@/components/reading/workspace/ReadingComposer"
);

describe("ReadingComposer resources", () => {
  beforeEach(() => {
    captured.props = null;
    captured.catalogWorkspaceId = "";
    captured.setResourceSelection.mockClear();
  });

  it("offers workspace permitted skills and persists the manual selection", () => {
    render(
      <ReadingComposer
        placeholder="Ask about this text"
        selection={null}
        onSent={vi.fn()}
        onRemoveSelection={vi.fn()}
        linkedSessionIds={[]}
      />,
    );

    expect(captured.catalogWorkspaceId).toBe("reading-workspace");
    expect(captured.props?.resourceCatalog).toEqual(captured.catalog);
    expect(captured.props?.resourceSelection).toEqual(captured.selection);
    captured.props?.onResourceSelectionChange?.({ skills: [], mcp: [] });
    expect(captured.setResourceSelection).toHaveBeenCalledWith({
      skills: [], mcp: [],
    });
  });
});


it("removing the quoted passage clears the pending wire selection and regions", () => {
  resetReadingTurnState();
  setReadingViewport({ selection: "待移除中文", selectionPages: [{ locator: 1, quote: "待移除中文", rects: [[0.1,0.1,0.5,0.2]] }] });
  const removed = vi.fn();
  render(<ReadingComposer placeholder="Ask" selection={{ quote: "待移除中文", locator: 1 }} onSent={vi.fn()} onRemoveSelection={removed} linkedSessionIds={[]} />);
  fireEvent.click(screen.getByRole("button", { name: "Remove quoted passage" }));
  expect(removed).toHaveBeenCalledOnce();
  expect(getReadingTurnState().selection).toBe("");
  expect(getReadingTurnState().selectionPages).toEqual([]);
});
