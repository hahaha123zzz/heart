import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AddMaterialsDialog } from "@/components/reading/library/AddMaterialsDialog";

const mock = vi.hoisted(() => ({
  authStatus: vi.fn(),
  addMaterial: vi.fn(),
  checkDuplicates: vi.fn(),
  createWorkspace: vi.fn(),
  importUrls: vi.fn(),
  listLibrary: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("@/components/watching/WatchingBrowser", () => ({
  WatchingBrowser: ({ onSelectUrl, onDismiss }: {
    onSelectUrl?(url: string): void;
    onDismiss(): void;
  }) => (
    <button
      type="button"
      onClick={() => {
        onSelectUrl?.("https://youtu.be/abc123xyz00");
        onDismiss();
      }}
    >
      Select video
    </button>
  ),
}));

vi.mock("@/lib/auth", () => ({ fetchAuthStatus: mock.authStatus }));

vi.mock("@/lib/reading-api", () => ({
  uploadMaterial: vi.fn(),
}));

vi.mock("@/lib/reading-workspace-api", () => ({
  addReadingWorkspaceMaterial: mock.addMaterial,
  checkReadingDuplicates: mock.checkDuplicates,
  createReadingWorkspace: mock.createWorkspace,
  importReadingUrls: mock.importUrls,
  listReadingLibraryMaterials: mock.listLibrary,
  readingContentId: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  mock.authStatus.mockResolvedValue({ learning_policy: null });
  mock.listLibrary.mockResolvedValue({ materials: [] });
  mock.checkDuplicates.mockResolvedValue([]);
  mock.importUrls.mockResolvedValue({
    workspace: { workspace_id: "workspace-1" },
  });
});

afterEach(cleanup);

describe("Reading Add Materials Invidious entry", () => {
  it("imports a selected video through Reading instead of the Watching route", async () => {
    const onDone = vi.fn();
    render(
      <AddMaterialsDialog
        mode="add"
        workspaceId="workspace-1"
        onClose={vi.fn()}
        onDone={onDone}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Browse Invidious" }));
    fireEvent.click(screen.getByRole("button", { name: "Select video" }));
    await waitFor(() =>
      expect(mock.importUrls).toHaveBeenCalledWith({
        urls: ["https://youtu.be/abc123xyz00"],
        workspace_id: "workspace-1",
      }),
    );
    await waitFor(() =>
      expect(onDone).toHaveBeenCalledWith({
        workspace: { workspace_id: "workspace-1" },
      }),
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Select video" }),
      ).toBeNull(),
    );
    expect(mock.addMaterial).not.toHaveBeenCalled();
  });
});

for (const [label, status] of [
  ["learner import denied", { learning_policy: { reading: { allow_upload: false } } }],
  ["unknown auth status", null],
] as const) {
  it(`keeps authorized material selection but hides personal imports: ${label}`, async () => {
    mock.authStatus.mockResolvedValue(status);
    const { container } = render(<AddMaterialsDialog mode="add" workspaceId="workspace-1" onClose={vi.fn()} onDone={vi.fn()} />);
    await waitFor(() => expect(mock.authStatus).toHaveBeenCalled());
    expect(screen.getByText("选择已授权教材")).toBeInTheDocument();
    expect(container.querySelector('input[type="file"]')).toBeNull();
    expect(screen.queryByRole("button", { name: "Browse Invidious" })).toBeNull();
    expect(mock.importUrls).not.toHaveBeenCalled();
  });
}
