import { create } from "zustand";
import {
  applyTheme,
  getInitialTheme,
  toggleThemeMode,
  type ThemeMode,
} from "./lib/theme";

type ThemeState = {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
  toggle: () => void;
};

export const useTheme = create<ThemeState>((set, get) => ({
  // Начальное значение уже применено скриптом в index.html
  mode: getInitialTheme(),

  setMode: (mode) => {
    applyTheme(mode);
    set({ mode });
  },

  toggle: () => {
    const next = toggleThemeMode(get().mode);

    applyTheme(next);
    set({ mode: next });
  },
}));
