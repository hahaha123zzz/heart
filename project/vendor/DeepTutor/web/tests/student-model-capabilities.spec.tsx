import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import StudentModelCapabilities from "@/features/heart/StudentModelCapabilities";
const request = vi.hoisted(() => vi.fn());
vi.mock("@/shared/api/client", () => ({ apiUrl: (path: string) => path, requestJson: request }));
beforeEach(() => { request.mockReset(); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const version = "a".repeat(64);
function payload(status = "untested", message = "") {
  return { credential_version: version, capabilities: {
    chat: { status: "passed", error_code: "", message: "" },
    assessment: { status, error_code: message ? "quota_exhausted" : "", message },
    tools: { status: "untested", error_code: "", message: "" },
    vision: { status: "untested", error_code: "", message: "" },
  } };
}

it("requires explicit cost confirmation, sends one version-bound request and resets consent", async () => {
  let finish!: (value: unknown) => void;
  request.mockResolvedValueOnce(payload()).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })).mockResolvedValue(payload("passed"));
  render(<StudentModelCapabilities version={version} onConfigurationChanged={vi.fn()} />);
  const button = screen.getByRole("button", { name: "验证结构化评估样例" });
  expect(button).toBeDisabled();
  const consent = screen.getByRole("checkbox");
  await waitFor(() => expect(consent).toBeEnabled());
  fireEvent.click(consent); fireEvent.click(button); fireEvent.click(button);
  const writes = request.mock.calls.filter(([, options]) => options.method === "POST");
  expect(writes).toHaveLength(1);
  expect(JSON.parse(writes[0][1].body)).toMatchObject({ credential_version: version, capability: "assessment", confirm_cost: true });
  expect(consent).toBeChecked();
  expect(screen.getByRole("status")).toHaveTextContent("正在验证结构化评估样例");
  finish({ status: "passed", message: "", error_code: "" });
  expect(await screen.findByText("结构化评估样例：样例通过")).toBeInTheDocument();
  expect(consent).not.toBeChecked();
});

it("shows separate chat and assessment states and an actionable safe error", async () => {
  request.mockResolvedValue(payload("failed", "余额或配额不足，请补充额度后重新验证。"));
  render(<StudentModelCapabilities version={version} onConfigurationChanged={vi.fn()} />);
  expect(await screen.findByText("结构化评估样例：未通过")).toBeInTheDocument();
  expect(screen.getByText("基础文本响应：样例通过")).toBeInTheDocument();
  expect(screen.getByText(/余额或配额不足/)).toBeInTheDocument();
  expect(request.mock.calls.every(([, options]) => !options.method)).toBe(true);
});

it("does not show old capability success or enabled actions for a changed configuration", async () => {
  request.mockResolvedValue(payload("passed"));
  const changed = vi.fn();
  const view = render(<StudentModelCapabilities version={version} onConfigurationChanged={changed} />);
  await screen.findByText("结构化评估样例：样例通过");
  fireEvent.click(screen.getByRole("checkbox"));
  expect(screen.getByRole("button", { name: "验证结构化评估样例" })).toBeEnabled();
  view.rerender(<StudentModelCapabilities version={"b".repeat(64)} onConfigurationChanged={changed} />);
  expect(screen.getByRole("button", { name: "验证结构化评估样例" })).toBeDisabled();
  await waitFor(() => expect(changed).toHaveBeenCalled());
  expect(screen.queryByText("结构化评估样例：样例通过")).toBeNull();
  expect(screen.getByRole("checkbox")).toBeDisabled();
});

it("reads status after a lost probe response without automatically sending another paid request", async () => {
  const unknown = payload("unknown", "结果不明，可能已计费；不会自动重发。");
  request.mockResolvedValueOnce(payload()).mockRejectedValueOnce(new Error("lost response")).mockResolvedValue(unknown);
  render(<StudentModelCapabilities version={version} onConfigurationChanged={vi.fn()} />);
  await waitFor(() => expect(screen.getByRole("checkbox")).toBeEnabled());
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "验证结构化评估样例" }));
  expect(await screen.findByText("结构化评估样例：结果不明")).toBeInTheDocument();
  expect(request.mock.calls.filter(([, options]) => options.method === "POST")).toHaveLength(1);
  expect(screen.getByRole("checkbox")).not.toBeChecked();
});


it.each(["chat", "assessment", "tools", "vision"])("sends %s on browsers without crypto.randomUUID and shows its returned result", async capability => {
  const webCrypto = globalThis.crypto;
  vi.stubGlobal("crypto", {getRandomValues:webCrypto.getRandomValues.bind(webCrypto)});
  const labels: Record<string,string> = {chat:"基础文本响应",assessment:"结构化评估样例",tools:"工具调用样例",vision:"图像输入样例"};
  const result = payload();
  request.mockImplementation(async (_url, options) => {
    if (options.method === "POST") { result.capabilities[capability as keyof typeof result.capabilities].status="passed"; return {status:"passed",message:"",error_code:""}; }
    return result;
  });
  render(<StudentModelCapabilities version={version} onConfigurationChanged={vi.fn()} />);
  await waitFor(() => expect(screen.getByRole("checkbox")).toBeEnabled());
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", {name:`验证${labels[capability]}`}));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(`${labels[capability]}：样例通过`));
  const writes=request.mock.calls.filter(([,options])=>options.method==="POST");
  expect(writes).toHaveLength(1);
  expect(JSON.parse(writes[0][1].body)).toMatchObject({capability,confirm_cost:true,request_id:expect.stringMatching(/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/)});
});

it("keeps a lost-response warning visible after successful status refresh", async () => {
  request.mockImplementation(async (_url,options)=> {if(options.method==="POST") throw new Error("lost response");return payload();});
  render(<StudentModelCapabilities version={version} onConfigurationChanged={vi.fn()} />);
  await waitFor(() => expect(screen.getByRole("checkbox")).toBeEnabled());
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button",{name:"验证基础文本响应"}));
  await waitFor(()=>expect(screen.getByRole("alert")).toHaveTextContent("本次可能已计费"));
  fireEvent.click(screen.getByRole("button",{name:"重新读取验证状态"}));
  await waitFor(()=>expect(request.mock.calls.filter(([,options])=>!options.method).length).toBeGreaterThanOrEqual(3));
  expect(screen.getByRole("alert")).toHaveTextContent("本次可能已计费");
  expect(screen.getByRole("status")).toHaveTextContent("再次验证请重新勾选费用确认");
  expect(request.mock.calls.filter(([,options])=>options.method==="POST")).toHaveLength(1);
});
