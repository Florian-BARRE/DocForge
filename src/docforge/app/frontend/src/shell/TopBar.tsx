// ====== Code Summary ======
// The app's top bar: the DocForge wordmark (display face + an ember mark), the two top-level
// destinations, and the right cluster — theme switch + API-token control. Uses the palette
// variables, so it reskins itself in light/dark.
//
// Below ~640px the nav collapses into a menu button (brand + theme toggle + token stay visible,
// as required by orchestrator brief) — a scoped <style> block owns the breakpoint since a plain
// inline `style` object cannot express `@media`. React state only toggles the `--open` class; the
// media query itself is what decides whether that class does anything, so desktop is unaffected.
//
// The open dropdown is rendered through a PORTAL straight into `document.body`, not as an
// absolutely-positioned child of <header>. The header's `backdrop-filter` (the frosted-glass
// look) establishes its own CSS stacking context — any z-index inside it is scoped to that
// context, so a plain `position: absolute` dropdown paints UNDER whatever the app renders below
// the header (main content is a later DOM sibling and wins the root-level paint order). Portaling
// to <body> puts the dropdown in the ROOT stacking context instead, where its z-index actually
// competes with the rest of the page — this is the fix, not a cosmetic tweak.

import { useState } from "react";
import { createPortal } from "react-dom";
import { theme as t } from "../theme";
import { ForgeMark } from "./ForgeMark";
import { ThemeToggle } from "./ThemeToggle";
import { TokenControl } from "./TokenControl";
import type { Navigate, View } from "./view";

const COLLECTIONS_VIEWS: View["name"][] = [
  "collections", "new-collection", "collection", "collection-edit", "collection-pipeline",
  "collection-search-pipeline", "collection-search", "collection-jobs", "collection-documents",
  "document", "job",
];

// The header's fixed height — shared by its own `height` style and the portaled dropdown's `top`
// offset below, so the two never drift apart.
const HEADER_HEIGHT = 58;

const RESPONSIVE_NAV_CSS = `
  .df-topbar-nav { display: flex; }
  .df-topbar-menu-btn { display: none; }
  .df-topbar-dropdown { display: none; }
  @media (max-width: 640px) {
    .df-topbar-menu-btn { display: inline-flex; }
    .df-topbar-nav { display: none; }
    .df-topbar-dropdown.df-topbar-dropdown--open {
      display: flex;
      flex-direction: column;
      align-items: stretch;
      position: fixed;
      top: ${HEADER_HEIGHT}px;
      left: 0;
      right: 0;
      padding: ${t.space.s}px ${t.space.l}px;
      gap: 2px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      box-shadow: var(--shadow-2);
      z-index: 1000;
    }
  }
`;

interface TopBarProps {
  view: View;
  onNavigate: Navigate;
}

function NavTab({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        position: "relative",
        background: active ? t.color.surface2 : "transparent",
        color: active ? t.color.text : t.color.dim,
        border: "none", borderRadius: t.radius.m,
        padding: "7px 14px", fontSize: t.font.size.l, fontWeight: active ? 600 : 500,
        cursor: "pointer", transition: "background .16s ease, color .16s ease",
        textAlign: "left",
      }}
    >
      {label}
    </button>
  );
}

function MenuGlyph({ open }: { open: boolean }) {
  return open ? (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  ) : (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 6h18M3 12h18M3 18h18" />
    </svg>
  );
}

export function TopBar({ view, onNavigate }: TopBarProps) {
  const [menuOpen, setMenuOpen] = useState(false);

  const navigate: Navigate = (target) => {
    setMenuOpen(false);
    onNavigate(target);
  };

  // Shared between the always-in-DOM desktop nav and the portaled mobile dropdown — same links,
  // two different mount points.
  const navLinks = (
    <>
      <NavTab active={COLLECTIONS_VIEWS.includes(view.name)} label="Collections" onClick={() => navigate({ name: "collections" })} />
      <NavTab active={view.name === "workers"} label="Workers" onClick={() => navigate({ name: "workers" })} />
      <NavTab active={view.name === "api-keys"} label="API Keys" onClick={() => navigate({ name: "api-keys" })} />
    </>
  );

  return (
    <header
      style={{
        display: "flex", alignItems: "center", gap: t.space.l, flexWrap: "wrap", minWidth: 0,
        position: "relative",
        padding: `0 ${t.space.xl}px`, height: HEADER_HEIGHT, flexShrink: 0,
        borderBottom: `1px solid ${t.color.line}`,
        background: "color-mix(in srgb, var(--panel) 82%, transparent)",
        backdropFilter: "blur(8px)",
      }}
    >
      <style>{RESPONSIVE_NAV_CSS}</style>

      {/* Brand — the animated forged-document mark + "DocForge" lockup (Forge in the accent). */}
      <button
        onClick={() => navigate({ name: "collections" })}
        style={{ display: "flex", alignItems: "center", gap: 9, background: "none", border: "none", cursor: "pointer", padding: 0, flexShrink: 0 }}
        title="DocForge"
      >
        <ForgeMark size={42} />
        <span
          style={{
            fontFamily: t.font.display, fontWeight: 800, fontSize: 20,
            letterSpacing: "-0.035em", color: t.color.text, lineHeight: 1,
          }}
        >
          Doc<span style={{ color: t.color.accentSafe }}>Forge</span>
        </span>
      </button>

      {/* Global-nav collapse trigger — hidden above 640px, where the inline nav is shown instead. */}
      <button
        className="df-topbar-menu-btn"
        onClick={() => setMenuOpen((open) => !open)}
        aria-expanded={menuOpen}
        aria-label={menuOpen ? "Close navigation menu" : "Open navigation menu"}
        title="Menu"
        style={{
          alignItems: "center", justifyContent: "center", width: 30, height: 26,
          border: `1px solid ${t.color.line}`, borderRadius: t.radius.s,
          background: menuOpen ? t.color.surface2 : "transparent", color: t.color.dim, cursor: "pointer",
        }}
      >
        <MenuGlyph open={menuOpen} />
      </button>

      <nav className="df-topbar-nav" style={{ gap: 4, marginLeft: t.space.s }}>
        {navLinks}
      </nav>

      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: t.space.m, flexShrink: 0 }}>
        <ThemeToggle />
        <TokenControl />
      </div>

      {menuOpen &&
        createPortal(
          <nav className="df-topbar-dropdown df-topbar-dropdown--open" aria-label="Mobile navigation">
            {navLinks}
          </nav>,
          document.body,
        )}
    </header>
  );
}
