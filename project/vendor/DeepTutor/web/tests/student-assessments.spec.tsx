import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { StudentAssessments, StudentEvaluationSettings } from "@/features/heart/StudentAssessments";

const request = vi.hoisted(() => vi.fn());
vi.mock("@/shared/api/client", () => ({ apiUrl: (path: string) => path, requestJson: request }));
beforeEach(() => request.mockReset());
afterEach(cleanup);
const job = { id: "own-job", status: "completed", publication_status: "pending", created_at: "2026-11-18T06:00:00Z",
  knowledge_point: "自变量", passed: true, feedback: "解释符合教材", answer: "研究者操纵的变量", independent: false,
  assistance_status: "not_verified", citations: [{ quote: "教材引用", document_id: "实验心理学", version: "v1" }] };

it("reloads authoritative settings after a failed save without repeating the PUT", async () => {
  request.mockResolvedValueOnce({ enabled: false }).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ enabled: true });
  render(<StudentEvaluationSettings />);
  const toggle = screen.getByRole("checkbox", { name: "开启聊天自动评估" });
  await waitFor(() => expect(toggle).toBeEnabled());
  expect(toggle).not.toBeChecked();
  fireEvent.click(toggle);
  expect(await screen.findByRole("alert")).toHaveTextContent("未能确认保存结果");
  expect(toggle).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
  await waitFor(() => expect(toggle).toBeChecked());
  const writes = request.mock.calls.filter(([, options]) => options.method === "PUT");
  expect(writes).toHaveLength(1);
  expect(writes[0][1].body).toBe('{"enabled":true}');
  expect(screen.getByText(/额外调用费用/)).toBeInTheDocument();
  expect(screen.getByText(/不会补评/)).toBeInTheDocument();
});

it("keeps an unreadable switch disabled and supports a read retry", async () => {
  request.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ enabled: true });
  render(<StudentEvaluationSettings />);
  expect(await screen.findByRole("alert")).toHaveTextContent("无法读取评估开关");
  expect(screen.getByRole("checkbox")).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
  await waitFor(() => expect(screen.getByRole("checkbox")).toBeChecked());
});

it("distinguishes a passing evaluation from independent mastery and shows textbook evidence", async () => {
  request.mockResolvedValue({ jobs: [job, { ...job, id: "assisted", knowledge_point: "因变量", assistance_status: "assisted", publication_status: "published" }] });
  render(<StudentAssessments />);
  expect(await screen.findByText("自变量")).toBeInTheDocument();
  expect(screen.getByText("评分已保存，等待同步")).toBeInTheDocument();
  expect(screen.getByText("已记录并同步")).toBeInTheDocument();
  expect(screen.getByText("独立性待核验，不更新掌握状态")).toBeInTheDocument();
  expect(screen.getByText("辅助作答，不更新掌握状态")).toBeInTheDocument();
  expect(screen.getAllByText("教材引用")).toHaveLength(2);
});

it("marks retained results stale after refresh failure without resubmitting an assessment", async () => {
  request.mockResolvedValueOnce({ jobs: [job] }).mockRejectedValueOnce(new Error("offline"));
  render(<StudentAssessments />);
  await screen.findByText("自变量");
  fireEvent.click(screen.getByRole("button", { name: "刷新记录" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("已有内容可能已过时");
  expect(screen.getByText("自变量")).toBeInTheDocument();
  expect(request.mock.calls.every(([path, options]) => path === "/api/heart/evaluation/jobs" && !options.method)).toBe(true);
});

it("shows an empty state and aborts pending reads when unmounted", async () => {
  request.mockResolvedValue({ jobs: [] });
  const view = render(<StudentAssessments />);
  expect(await screen.findByText(/还没有评估记录/)).toBeInTheDocument();
  const signal = request.mock.calls[0][1].signal as AbortSignal;
  view.unmount();
  expect(signal.aborted).toBe(true);
});

it("shows an unknown outcome without offering an automatic model retry", async () => {
  request.mockResolvedValue({ jobs: [{ ...job, status: "unknown", passed: null, feedback: "", publication_status: "" }] });
  render(<StudentAssessments />);
  expect(await screen.findByText("结果不明，未自动重试")).toBeInTheDocument();
  expect(screen.getByText(/可能已产生费用/)).toBeInTheDocument();
  expect(screen.queryByText(/评估结论/)).toBeNull();
  expect(screen.getAllByRole("button")).toHaveLength(1);
});


it("saves a disabled setting only after the server confirms it", async () => {
  request.mockResolvedValueOnce({ enabled: true }).mockResolvedValueOnce({ enabled: false });
  render(<StudentEvaluationSettings />);
  const toggle = screen.getByRole("checkbox");
  await waitFor(() => expect(toggle).toBeChecked());
  fireEvent.click(toggle);
  await waitFor(() => expect(toggle).not.toBeChecked());
  expect(request).toHaveBeenLastCalledWith("/api/heart/evaluation", expect.objectContaining({ method: "PUT", body: '{"enabled":false}' }));
});


it("requires a reason and cost confirmation and deduplicates repeated submit clicks", async () => {
  let finish!: (value: unknown) => void;
  const submitted = new Promise(resolve => { finish = resolve; });
  const review = { id: "review-1", status: "paused", publication_status: "", passed: null, feedback: "", reason: "请核对", effective: false, can_retry: false };
  request.mockResolvedValueOnce({ jobs: [{ ...job, publication_status: "published" }] })
    .mockReturnValueOnce(submitted).mockResolvedValue({ jobs: [{ ...job, publication_status: "published", reassessment: review }] });
  render(<StudentAssessments />);
  fireEvent.click(await screen.findByRole("button", { name: "申请复评" }));
  const submit = screen.getByRole("button", { name: "确认并提交复评" });
  expect(submit).toBeDisabled();
  fireEvent.change(screen.getByRole("textbox", { name: "复评原因" }), { target: { value: "请核对" } });
  expect(submit).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox", { name: /同意本次复评/ }));
  fireEvent.click(submit); fireEvent.click(submit);
  const writes = request.mock.calls.filter(([, options]) => options.method === "POST");
  expect(writes).toHaveLength(1);
  expect(JSON.parse(writes[0][1].body)).toMatchObject({ reason: "请核对", confirm_cost: true, confirm_unknown_retry: false });
  expect(JSON.parse(writes[0][1].body).request_id).toMatch(/^[a-f0-9-]{36}$/);
  finish({ id: "review-1", status: "paused" });
  expect(await screen.findByText("复评状态：等待模型配置")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "申请复评" })).toBeNull();
});

it("keeps the same application id if the response is lost", async () => {
  request.mockResolvedValueOnce({ jobs: [{ ...job, publication_status: "published" }] })
    .mockRejectedValueOnce(new Error("lost response")).mockRejectedValueOnce(new Error("still offline"));
  render(<StudentAssessments />);
  fireEvent.click(await screen.findByRole("button", { name: "申请复评" }));
  fireEvent.change(screen.getByRole("textbox", { name: "复评原因" }), { target: { value: "核查依据" } });
  fireEvent.click(screen.getByRole("checkbox", { name: /同意本次复评/ }));
  fireEvent.click(screen.getByRole("button", { name: "确认并提交复评" }));
  await screen.findByText(/未能确认申请结果/);
  fireEvent.click(screen.getByRole("button", { name: "确认并提交复评" }));
  await waitFor(() => expect(request.mock.calls.filter(([, options]) => options.method === "POST")).toHaveLength(2));
  const writes = request.mock.calls.filter(([, options]) => options.method === "POST");
  expect(writes[0][1].body).toBe(writes[1][1].body);
});

it("shows old and effective reassessment conclusions without another paid application", async () => {
  request.mockResolvedValue({ jobs: [{ ...job, publication_status: "published", reassessment: {
    id: "review-done", status: "completed", publication_status: "published", passed: false,
    feedback: "调整原因：概念边界不足", reason: "核对边界", effective: true, can_retry: false,
  } }] });
  render(<StudentAssessments />);
  expect(await screen.findByText("原结论：通过")).toBeInTheDocument();
  expect(screen.getByText("当前有效结论：未通过")).toBeInTheDocument();
  expect(screen.getByText(/调整原因：概念边界不足/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /申请复评/ })).toBeNull();
});

it("requires explicit acknowledgement of possible duplicate charges after an unknown outcome", async () => {
  request.mockResolvedValueOnce({ jobs: [{ ...job, publication_status: "published", reassessment: {
    id: "unknown-review", status: "unknown", publication_status: "", passed: null, feedback: "",
    reason: "核查", effective: false, can_retry: true,
  } }] }).mockResolvedValueOnce({ id: "new-review", status: "queued" }).mockResolvedValue({ jobs: [] });
  render(<StudentAssessments />);
  fireEvent.click(await screen.findByRole("button", { name: "再次申请复评" }));
  expect(screen.getByText(/再次申请可能重复计费/)).toBeInTheDocument();
  const submit = screen.getByRole("button", { name: "确认并提交复评" });
  expect(submit).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox", { name: /上次可能已计费/ }));
  fireEvent.click(submit);
  await waitFor(() => expect(request.mock.calls.filter(([, options]) => options.method === "POST")).toHaveLength(1));
  const write = request.mock.calls.find(([, options]) => options.method === "POST");
  expect(JSON.parse(write![1].body).confirm_unknown_retry).toBe(true);
});
