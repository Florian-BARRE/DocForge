// ====== Code Summary ======
// The light/dark theme store. The palette lives in CSS variables (index.css) keyed off
// <html data-theme>; this hook reads the current value, flips it, and persists the choice. The
// initial value is set before first paint by an inline script in index.html (no flash).

import { useCallback, useEffect, useState } from "react";

export type ThemeName = "dark" | "light";
const STORAGE_KEY = "docforge_theme";

function current(): ThemeName {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

/** Read the active theme + a setter that updates <html data-theme> and persists it. */
export function useTheme(): { theme: ThemeName; setTheme: (t: ThemeName) => void; toggle: () => void } {
  const [theme, setThemeState] = useState<ThemeName>(current);

  // Keep in sync if another tab changes the preference.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY && (e.newValue === "light" || e.newValue === "dark")) {
        document.documentElement.dataset.theme = e.newValue;
        setThemeState(e.newValue);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const setTheme = useCallback((next: ThemeName) => {
    document.documentElement.dataset.theme = next;
    localStorage.setItem(STORAGE_KEY, next);
    setThemeState(next);
  }, []);

  const toggle = useCallback(() => setTheme(current() === "light" ? "dark" : "light"), [setTheme]);

  return { theme, setTheme, toggle };
}
