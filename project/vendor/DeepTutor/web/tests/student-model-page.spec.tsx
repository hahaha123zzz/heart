import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import StudentModelPage from "@/app/(settings)/settings/model/page";
vi.mock("@/features/heart/StudentAssessments", () => ({ StudentEvaluationSettings: () => null }));
vi.mock("@/features/heart/StudentMemorySettings", () => ({ default: () => null }));
vi.mock("@/features/heart/StudentModelCapabilities", () => ({ default: () => null }));
vi.mock("@/features/heart/StudentAccountSettings", () => ({ default: () => null }));

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("disables model fields until the initial read finishes so late data cannot overwrite edits", async () => {
  let finish!: (value: unknown) => void;
  vi.stubGlobal("fetch", vi.fn(() => new Promise(resolve => { finish = resolve; })));
  render(<StudentModelPage />);
  expect(screen.getByLabelText("模型服务地址（HTTPS）")).toBeDisabled();
  expect(screen.getByRole("button", { name: "保存" })).toBeDisabled();
  finish({ ok: true, json: async () => ({ configured: false }) });
  await waitFor(() => expect(screen.getByLabelText("模型服务地址（HTTPS）")).toBeEnabled());
});

it("keeps a failed configuration read disabled until an explicit retry succeeds", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ ok: true, json: async () => ({ configured: false }) }));
  render(<StudentModelPage />);
  fireEvent.click(await screen.findByRole("button", { name: "重新读取模型配置" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "保存" })).toBeEnabled());
});

it("requires reading back after a lost save response and clears the typed key", async () => {
  const fetcher = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ configured: false }) })
    .mockRejectedValueOnce(new Error("lost response"));
  vi.stubGlobal("fetch", fetcher);
  render(<StudentModelPage />);
  const save = screen.getByRole("button", { name: "保存" });
  await waitFor(() => expect(save).toBeEnabled());
  fireEvent.change(screen.getByLabelText("模型服务地址（HTTPS）"), { target: { value: "https://example.com/v1" } });
  fireEvent.change(screen.getByLabelText("模型名称"), { target: { value: "test-model" } });
  fireEvent.change(screen.getByLabelText("接口密钥（API Key）"), { target: { value: "test-only-key" } });
  fireEvent.click(save);
  expect(await screen.findByText("未能确认保存结果，请重新读取配置后再操作。")).toBeInTheDocument();
  expect(save).toBeDisabled(); expect(screen.getByLabelText("接口密钥（API Key）")).toHaveValue("");
  expect(fetcher).toHaveBeenCalledTimes(2);
});
