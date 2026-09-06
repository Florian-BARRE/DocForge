// ====== Code Summary ======
// The light/dark switch — a segmented control (sun | moon) that flips the palette via useTheme,
// active side lit by the accent-soft wash. `compact` swaps this for a single icon-only button
// (current theme's icon, click toggles) for contexts too narrow for the two-button control — the
// sidebar's collapsed rail (see SidebarFooter).

import { theme as t } from "../theme";
import { useTheme, type ThemeName } from "./useTheme";

function Sun() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}
function Moon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  );
}

interface ThemeToggleProps {
  compact?: boolean;
}

export function ThemeToggle({ compact = false }: ThemeToggleProps = {}) {
  const { theme, setTheme, toggle } = useTheme();

  if (compact) {
    const Icon = theme === "light" ? Sun : Moon;
    return (
      <button
        onClick={toggle}
        title={`Theme: ${theme} (click to switch)`}
        aria-label="Toggle theme"
        style={{
          display: "grid", placeItems: "center", width: 30, height: 26, flexShrink: 0,
          border: `1px solid ${t.color.line}`, borderRadius: t.radius.s, cursor: "pointer",
          background: "transparent", color: t.color.dim,
        }}
      >
        <Icon />
      </button>
    );
  }

  const seg = (name: ThemeName): React.CSSProperties => {
    const active = theme === name;
    return {
      display: "grid", placeItems: "center", width: 30, height: 26,
      border: "none", borderRadius: t.radius.s, cursor: "pointer",
      background: active ? t.color.accentSoft : "transparent",
      color: active ? t.color.accent : t.color.mute,
      transition: "background .18s ease, color .18s ease",
    };
  };
  return (
    <div
      role="group"
      aria-label="Theme"
      style={{
        display: "flex", gap: 2, padding: 2,
        border: `1px solid ${t.color.line}`, borderRadius: t.radius.m, background: t.color.surface,
      }}
    >
      <button style={seg("light")} onClick={() => setTheme("light")} aria-label="Light theme" title="Light"><Sun /></button>
      <button style={seg("dark")} onClick={() => setTheme("dark")} aria-label="Dark theme" title="Dark"><Moon /></button>
    </div>
  );
}
