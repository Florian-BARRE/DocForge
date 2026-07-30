// ====== Code Summary ======
// The shared "loading…" placeholder — a centered spinner + label, used wherever a top-level
// fetch hasn't resolved yet (collections, explorer, monitoring, auth).

import { theme } from "../theme";

export function LoadingState({ label }: { label: string }) {
  return (
    <div
      style={{
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
        gap: theme.space.m, padding: theme.space.xxl, color: theme.color.dim, fontSize: theme.font.size.s,
      }}
    >
      <span
        style={{
          width: 22, height: 22, borderRadius: theme.radius.pill,
          border: `2px solid ${theme.color.line}`, borderTopColor: theme.color.accent,
          animation: "df-spin 0.8s linear infinite",
        }}
      />
      <span>{label}</span>
      <style>{"@keyframes df-spin { to { transform: rotate(360deg); } } @media (prefers-reduced-motion: reduce) { [style*=\"df-spin\"] { animation: none !important; } }"}</style>
    </div>
  );
}
