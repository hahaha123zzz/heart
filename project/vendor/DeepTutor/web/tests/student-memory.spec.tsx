import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import StudentMemory from "@/features/heart/StudentMemory";
import StudentMemorySettings from "@/features/heart/StudentMemorySettings";

const request = vi.hoisted(() => vi.fn());
vi.mock("@/shared/api/client", () => ({ apiUrl: (path: string) => path, apiFetch: (...args: Parameters<typeof fetch>) => fetch(...args), requestJson: request }));
beforeEach(() => request.mockReset());
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("keeps an unknown memory switch disabled and re-reads after an uncertain write", async () => {
  request.mockResolvedValueOnce({ enabled: true }).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ enabled: false });
  render(<StudentMemorySettings />);
  const toggle = screen.getByRole("checkbox", { name: "开启长期记忆供辅导使用" });
  expect(toggle).toBeDisabled();
  await waitFor(() => expect(toggle).toBeChecked());
  fireEvent.click(toggle);
  expect(await screen.findByRole("alert")).toHaveTextContent("未能确认保存结果");
  expect(toggle).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "重新读取长期记忆开关" }));
  await waitFor(() => expect(toggle).not.toBeChecked());
  const writes = request.mock.calls.filter(([, options]) => options.method === "PUT");
  expect(writes).toHaveLength(1);
  expect(writes[0][1].body).toBe('{"enabled":false}');
});

it("does not allow changes when the memory setting cannot be read", async () => {
  request.mockRejectedValueOnce(new Error("offline"));
  render(<StudentMemorySettings />);
  expect(await screen.findByRole("alert")).toHaveTextContent("无法读取长期记忆开关");
  expect(screen.getByRole("checkbox")).toBeDisabled();
});

it("shows verified source and time, searches on the server, and deletes by stable id", async () => {
  const card = { id: "42", text: "多举例", source: "explicit_user", created_at: "2026-11-18T10:00:00" };
  const fetcher = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ preferences: [card], profile: [] }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ preferences: [card], profile: [] }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ deleted: "42" }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ preferences: [], profile: [] }) });
  vi.stubGlobal("fetch", fetcher);
  render(<StudentMemory />);
  expect(await screen.findByText("多举例")).toBeInTheDocument();
  expect(screen.getByText("来源：你主动添加")).toBeInTheDocument();
  expect(screen.getByText(/添加时间/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("搜索记忆"), { target: { value: "举例" } });
  await waitFor(() => expect(fetcher).toHaveBeenCalledWith("/api/heart/memory?q=%E4%B8%BE%E4%BE%8B", expect.objectContaining({ cache: "no-store" })));
  await screen.findByText("多举例");
  fireEvent.click(screen.getByRole("button", { name: "删除多举例" }));
  fireEvent.click(screen.getByRole("button", {name:"确认删除"}));
  await waitFor(() => expect(fetcher).toHaveBeenCalledWith("/api/heart/memory/preference/42", expect.objectContaining({ method: "DELETE" })));
  await waitFor(() => expect(screen.queryByText("多举例")).toBeNull());
});

it("handles a failed memory load without an unhandled rejection or write", async () => {
  const fetcher = vi.fn().mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ ok: true, json: async () => ({ preferences: [], profile: [] }) });
  vi.stubGlobal("fetch", fetcher);
  render(<StudentMemory />);
  expect(await screen.findByRole("alert")).toHaveTextContent("无法读取记忆");
  expect(screen.getByRole("button", { name: "添加偏好" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "重新读取记忆" }));
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  expect(fetcher.mock.calls.every(([, options]) => !options.method)).toBe(true);
});


it("clears stale entries and waits for a read after an uncertain deletion", async () => {
  const fetcher = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ preferences: [{ id: "5", text: "待删除偏好" }], profile: [] }) })
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ ok: true, json: async () => ({ preferences: [], profile: [] }) });
  vi.stubGlobal("fetch", fetcher);
  render(<StudentMemory />);
  fireEvent.click(await screen.findByRole("button", { name: "删除待删除偏好" }));
  fireEvent.click(screen.getByRole("button", {name:"确认删除"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("未能确认操作结果");
  expect(screen.queryByText("待删除偏好")).toBeNull();
  expect(screen.getByRole("button", { name: "添加偏好" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "重新读取记忆" }));
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  expect(fetcher.mock.calls.filter(([, options]) => options.method === "DELETE")).toHaveLength(1);
});


it("cancels deletion and does not invent missing source or time", async () => {
 const fetcher=vi.fn().mockResolvedValue({ok:true,json:async()=>({preferences:[{id:'no-meta',text:'无附加信息'}],profile:[]})});
 vi.stubGlobal('fetch',fetcher);render(<StudentMemory/>);
 fireEvent.click(await screen.findByRole('button',{name:'删除无附加信息'}));
 expect(screen.getByRole('alertdialog')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'取消'}));
 expect(screen.queryByRole('alertdialog')).toBeNull();
 expect(fetcher.mock.calls.some(([,options])=>options.method)).toBe(false);
 expect(screen.queryByText(/来源：|添加时间/)).toBeNull();
 expect(screen.queryByRole('button',{name:/编辑|更正/})).toBeNull();
});
