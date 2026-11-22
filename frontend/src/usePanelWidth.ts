import { useCallback, useEffect, useState } from "react";

// ============================================================
// ШИРИНА ПРАВОЙ ПАНЕЛИ
// ============================================================

export const PANEL_MIN_WIDTH = 360;
export const PANEL_MIN_CHAT_WIDTH = 340;
export const PANEL_STEP = 48;
export const SPLITTER_WIDTH = 14;

const WIDTH_KEY = "synonyx:panel-width";
const COLLAPSED_KEY = "synonyx:panel-collapsed";

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function readStoredNumber(key: string): number | null {
  try {
    const raw = localStorage.getItem(key);
    const value = raw === null ? NaN : Number(raw);

    return Number.isFinite(value) ? value : null;
  } catch {
    return null;
  }
}

function readStoredBoolean(key: string): boolean {
  try {
    return localStorage.getItem(key) === "true";
  } catch {
    return false;
  }
}

function viewportMax(): number {
  const viewport =
    typeof window === "undefined" ? 1440 : window.innerWidth;

  return Math.max(
    PANEL_MIN_WIDTH + 80,
    viewport - PANEL_MIN_CHAT_WIDTH - SPLITTER_WIDTH,
  );
}

export function defaultPanelWidth(): number {
  const viewport =
    typeof window === "undefined" ? 1440 : window.innerWidth;

  return clamp(
    Math.round(viewport * 0.56),
    PANEL_MIN_WIDTH,
    viewportMax(),
  );
}

export function usePanelWidth() {
  const [width, setWidthState] = useState<number>(() => {
    const stored = readStoredNumber(WIDTH_KEY);

    return stored === null
      ? defaultPanelWidth()
      : clamp(stored, PANEL_MIN_WIDTH, viewportMax());
  });

  const [collapsed, setCollapsed] = useState<boolean>(() =>
    readStoredBoolean(COLLAPSED_KEY),
  );

  useEffect(() => {
    try {
      localStorage.setItem(WIDTH_KEY, String(width));
    } catch {
      // localStorage может быть недоступен
    }
  }, [width]);

  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSED_KEY, String(collapsed));
    } catch {
      // localStorage может быть недоступен
    }
  }, [collapsed]);

  // После изменения окна ширина не должна выходить за пределы
  useEffect(() => {
    const onResize = () => {
      setWidthState((current) =>
        clamp(current, PANEL_MIN_WIDTH, viewportMax()),
      );
    };

    window.addEventListener("resize", onResize);

    return () => window.removeEventListener("resize", onResize);
  }, []);

  const setWidth = useCallback(
    (next: number | ((current: number) => number)) => {
      setWidthState((current) => {
        const value =
          typeof next === "function" ? next(current) : next;

        return Math.round(
          clamp(value, PANEL_MIN_WIDTH, viewportMax()),
        );
      });
    },
    [],
  );

  const adjust = useCallback(
    (delta: number) => setWidth((current) => current + delta),
    [setWidth],
  );

  const resetWidth = useCallback(
    () => setWidth(defaultPanelWidth()),
    [setWidth],
  );

  const toggleCollapsed = useCallback(
    () => setCollapsed((value) => !value),
    [],
  );

  return {
    width,
    collapsed,
    setWidth,
    adjust,
    resetWidth,
    toggleCollapsed,
  };
}
