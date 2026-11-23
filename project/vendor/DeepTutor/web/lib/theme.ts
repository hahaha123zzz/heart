import { browserStorage } from "@/shared/storage";

export type Theme = "light" | "dark" | "glass" | "snow";
export const THEME_STORAGE_KEY = "deeptutor-theme";
const FIXED_THEME: Theme = "snow";
type ThemeChangeListener = (theme: Theme) => void;
const themeListeners = new Set<ThemeChangeListener>();

export function subscribeToThemeChanges(listener: ThemeChangeListener): () => void {
  themeListeners.add(listener);
  return () => themeListeners.delete(listener);
}

export function getStoredTheme(): Theme {
  return FIXED_THEME;
}

export function saveThemeToStorage(_theme: Theme): boolean {
  if (typeof window === "undefined") return false;
  try {
    return browserStorage.writeRaw("local", THEME_STORAGE_KEY, FIXED_THEME);
  } catch {
    return false;
  }
}

export function getSystemTheme(): Theme {
  return FIXED_THEME;
}

export function applyThemeToDocument(_theme: Theme): void {
  if (typeof document === "undefined") return;
  document.documentElement.classList.remove("dark", "theme-glass");
  document.documentElement.classList.add("theme-snow");
}

export function initializeTheme(): Theme {
  applyThemeToDocument(FIXED_THEME);
  saveThemeToStorage(FIXED_THEME);
  return FIXED_THEME;
}

export function setTheme(_theme: Theme): void {
  initializeTheme();
  themeListeners.forEach(listener => listener(FIXED_THEME));
}
