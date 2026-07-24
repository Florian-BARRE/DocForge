// ====== Code Summary ======
// The app's top bar: static product label (no backend endpoint serves a display name — see
// MEMORY for the discussed alternatives) + the two top-level destinations (Collections, Workers).

import { theme } from "../theme";
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

export function TopBar({ view, onNavigate }: TopBarProps) {
  const tabStyle = (active: boolean): React.CSSProperties => ({
    background: active ? theme.color.accentSoft : "none",
    color: active ? theme.color.accent : theme.color.dim,
    border: "none", borderRadius: theme.radius.s,
    padding: "5px 12px", fontSize: theme.font.size.m, cursor: "pointer",
  });

  return (
    <header
      style={{
        display: "flex", alignItems: "center", gap: theme.space.m,
        padding: `${theme.space.s}px ${theme.space.l}px`,
        borderBottom: `1px solid ${theme.color.line}`,
        background: theme.color.panel,
      }}
    >
      <strong style={{ fontSize: theme.font.size.xl, color: theme.color.text }}>DocForge</strong>
      <nav style={{ display: "flex", gap: theme.space.xs, marginLeft: theme.space.l }}>
        <button style={tabStyle(COLLECTIONS_VIEWS.includes(view.name))} onClick={() => onNavigate({ name: "collections" })}>
          Collections
        </button>
        <button style={tabStyle(view.name === "workers")} onClick={() => onNavigate({ name: "workers" })}>
          Workers
        </button>
        <button style={tabStyle(view.name === "api-keys")} onClick={() => onNavigate({ name: "api-keys" })}>
          API Keys
        </button>
      </nav>
      <div style={{ marginLeft: "auto" }}>
        <TokenControl />
      </div>
    </header>
  );
}
