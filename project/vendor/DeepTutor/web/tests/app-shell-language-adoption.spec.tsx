import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { AppShellProvider, useAppShell } from "@/context/AppShellContext";
import {
  LANGUAGE_STORAGE_KEY,
  RESPONSE_LANGUAGE_STORAGE_KEY,
} from "@/context/app-shell-storage";
import { apiFetch } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
  apiUrl: (path: string) => path,
}));

function LanguageProbe() {
  const { language, languageReady } = useAppShell();
  return <output data-testid="language" data-ready={languageReady}>{language}</output>;
}

beforeEach(() => {
  localStorage.clear();
  vi.mocked(apiFetch).mockReset();
  vi.mocked(apiFetch).mockResolvedValue({
    ok: true,
    json: async () => ({ language: "uk", response_language: "fr" }),
  } as Response);
});

afterEach(() => cleanup());

it("uses Chinese UI and preserves French output from the server", async () => {
  render(<AppShellProvider><LanguageProbe /></AppShellProvider>);

  await waitFor(() => {
    expect(screen.getByTestId("language")).toHaveTextContent("zh");
    expect(screen.getByTestId("language")).toHaveAttribute("data-ready", "true");
  });
  expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("zh");
  expect(localStorage.getItem(RESPONSE_LANGUAGE_STORAGE_KEY)).toBe("fr");
});

it("replaces an old French UI cache while adopting its missing output preference", async () => {
  localStorage.setItem(LANGUAGE_STORAGE_KEY, "fr");
  vi.mocked(apiFetch).mockResolvedValue({
    ok: true,
    json: async () => ({ language: "uk", response_language: "uk" }),
  } as Response);
  render(<AppShellProvider><LanguageProbe /></AppShellProvider>);

  await waitFor(() => {
    expect(screen.getByTestId("language")).toHaveTextContent("zh");
    expect(screen.getByTestId("language")).toHaveAttribute("data-ready", "true");
  });
  expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("zh");
  expect(localStorage.getItem(RESPONSE_LANGUAGE_STORAGE_KEY)).toBe("uk");
});


it("replaces an English UI cache without touching an explicit English answer language",async()=>{
 localStorage.setItem(LANGUAGE_STORAGE_KEY,"en");localStorage.setItem(RESPONSE_LANGUAGE_STORAGE_KEY,"en");
 render(<AppShellProvider><LanguageProbe/></AppShellProvider>);
 await waitFor(()=>expect(screen.getByTestId("language")).toHaveAttribute("data-ready","true"));
 expect(screen.getByTestId("language")).toHaveTextContent("zh");expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("zh");expect(localStorage.getItem(RESPONSE_LANGUAGE_STORAGE_KEY)).toBe("en");expect(apiFetch).not.toHaveBeenCalled();
 act(() => { window.dispatchEvent(new StorageEvent("storage",{key:LANGUAGE_STORAGE_KEY,newValue:"en"})); });
 expect(screen.getByTestId("language")).toHaveTextContent("zh");
});
