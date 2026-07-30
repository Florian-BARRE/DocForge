// ====== Code Summary ======
// The app's top bar: the DocForge wordmark (display face + an ember mark), the two top-level
// destinations, and the right cluster — theme switch + API-token control. Uses the palette
// variables, so it reskins itself in light/dark.

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
      }}
    >
      {label}
    </button>
  );
}

export function TopBar({ view, onNavigate }: TopBarProps) {
  return (
    <header
      style={{
        display: "flex", alignItems: "center", gap: t.space.l,
        padding: `0 ${t.space.xl}px`, height: 58, flexShrink: 0,
        borderBottom: `1px solid ${t.color.line}`,
        background: "color-mix(in srgb, var(--panel) 82%, transparent)",
        backdropFilter: "blur(8px)",
      }}
    >
      {/* Brand — the animated forged-document mark + "DocForge" lockup (Forge in the accent). */}
      <button
        onClick={() => onNavigate({ name: "collections" })}
        style={{ display: "flex", alignItems: "center", gap: 9, background: "none", border: "none", cursor: "pointer", padding: 0 }}
        title="DocForge"
      >
        <ForgeMark size={42} />
        <span
          style={{
            fontFamily: t.font.display, fontWeight: 800, fontSize: 20,
            letterSpacing: "-0.035em", color: t.color.text, lineHeight: 1,
          }}
        >
          Doc<span style={{ color: t.color.accent }}>Forge</span>
        </span>
      </button>

      <nav style={{ display: "flex", gap: 4, marginLeft: t.space.s }}>
        <NavTab active={COLLECTIONS_VIEWS.includes(view.name)} label="Collections" onClick={() => onNavigate({ name: "collections" })} />
        <NavTab active={view.name === "workers"} label="Workers" onClick={() => onNavigate({ name: "workers" })} />
        <NavTab active={view.name === "api-keys"} label="API Keys" onClick={() => onNavigate({ name: "api-keys" })} />
      </nav>

      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: t.space.m }}>
        <ThemeToggle />
        <TokenControl />
      </div>
    </header>
  );
}
