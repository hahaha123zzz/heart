import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ChapterProgress } from "@/features/heart/ChapterProgress";

const request = vi.hoisted(() => vi.fn());
vi.mock("@/shared/api/client", () => ({ apiUrl: (path: string) => path, requestJson: request }));
afterEach(() => { cleanup(); request.mockReset(); });

it("distinguishes waiting for sync from the last recorded state and flags a failed refresh", async () => {
  request.mockResolvedValueOnce({ catalog_available: true, points: [
    { id: "kc-2-1", name: "章节知识点", snapshot: null, sync_pending: true, sync_blocked: false },
  ] }).mockRejectedValueOnce(new Error("offline"));
  render(<ChapterProgress chapter={2} />);
  expect(await screen.findByText("有评估结果待同步")).toBeInTheDocument();
  expect(screen.getByText("暂无已同步的学习状态")).toBeInTheDocument();
  expect(screen.queryByText(/尚未达到掌握要求/)).toBeNull();
  expect(request.mock.calls[0][0]).toContain("chapter=2");
  fireEvent.click(screen.getByRole("button", { name: "刷新学习状态" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("下方记录可能已过时");
  expect(screen.getByText("章节知识点")).toBeInTheDocument();
});
