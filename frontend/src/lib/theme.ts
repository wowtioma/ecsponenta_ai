// ============================================================
// ТЕМА ОФОРМЛЕНИЯ: СВЕТЛАЯ / ТЁМНАЯ (ЧБ)
// ============================================================
//
// Тема хранится в localStorage и применяется атрибутом
// data-theme на <html>. Начальное значение выставляет
// встроенный скрипт в index.html, чтобы не было вспышки
// светлой темы при загрузке.

export type ThemeMode = "light" | "dark";

export const THEME_STORAGE_KEY = "synonyx:theme";

const THEME_COLOR: Record<ThemeMode, string> = {
  light: "#FFFFFF",
  dark: "#070707",
};

function isThemeMode(value: unknown): value is ThemeMode {
  return value === "light" || value === "dark";
}

function readStoredTheme(): ThemeMode | null {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY);
    return isThemeMode(value) ? value : null;
  } catch {
    return null;
  }
}

function systemTheme(): ThemeMode {
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  } catch {
    return "light";
  }
}

export function getInitialTheme(): ThemeMode {
  if (typeof document !== "undefined") {
    const applied = document.documentElement.dataset.theme;

    if (isThemeMode(applied)) return applied;
  }

  return readStoredTheme() ?? systemTheme();
}

export function applyTheme(mode: ThemeMode): void {
  const root = document.documentElement;

  root.dataset.theme = mode;
  root.style.colorScheme = mode;

  const meta = document.querySelector('meta[name="theme-color"]');

  if (meta) meta.setAttribute("content", THEME_COLOR[mode]);

  try {
    localStorage.setItem(THEME_STORAGE_KEY, mode);
  } catch {
    // Приватный режим браузера может запрещать localStorage
  }
}

export function toggleThemeMode(mode: ThemeMode): ThemeMode {
  return mode === "dark" ? "light" : "dark";
}
