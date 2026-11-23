import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import SettingsLayout from "@/app/(settings)/settings/layout";

const state = vi.hoisted(() => ({ resolved: true, hideAdminOnly: true, path: "/settings/model", mountAdmin: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => state.path, redirect: (path: string) => { throw new Error(`redirect:${path}`); } }));
vi.mock("@/features/settings/navigation/SettingsAccessProvider", () => ({ SettingsAccessProvider: ({ children }: { children: React.ReactNode }) => children, useSettingsAccess: () => state }));
vi.mock("@/features/settings/store", () => ({
  SettingsProvider: ({ children }: { children: React.ReactNode }) => { state.mountAdmin(); return children; },
  UiSettingsProvider: ({ children }: { children: React.ReactNode }) => children,
  ModelCatalogProvider: ({ children }: { children: React.ReactNode }) => children,
  SettingsDraftProvider: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("@/components/settings/SettingsMain", () => ({ default: ({ children }: { children: React.ReactNode }) => children }));
vi.mock("@/components/settings/SettingsTourOverlay", () => ({ SettingsTourOverlay: () => null }));
beforeEach(() => { state.resolved = true; state.hideAdminOnly = true; state.path = "/settings/model"; state.mountAdmin.mockClear(); });
it("student model settings never mount instance settings providers", () => {
  render(<SettingsLayout><h1>个人模型</h1></SettingsLayout>);
  expect(screen.getByRole("heading", { name: "个人模型" })).toBeInTheDocument();
  expect(state.mountAdmin).not.toHaveBeenCalled();
});
it("student instance-settings addresses go to their personal model", () => {
  state.path = "/settings/providers";
  expect(() => render(<SettingsLayout>private</SettingsLayout>)).toThrow("redirect:/settings/model");
  expect(state.mountAdmin).not.toHaveBeenCalled();
});
it("unresolved identity cannot mount instance settings", () => {
  state.resolved = false;
  render(<SettingsLayout>private</SettingsLayout>);
  expect(state.mountAdmin).not.toHaveBeenCalled();
  expect(screen.queryByText("private")).toBeNull();
});
it("administrators keep the existing instance settings", () => {
  state.hideAdminOnly = false;
  render(<SettingsLayout>instance settings</SettingsLayout>);
  expect(state.mountAdmin).toHaveBeenCalled();
});
