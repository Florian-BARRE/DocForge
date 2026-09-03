// ====== Code Summary ======
// The node's OUT contract, made visible: the five figure classes and the enrichment branch each routes
// to (OCR / vision model / skip). Read-only chips — the routing itself is fixed by the taxonomy — so the
// user can see, at a glance, what "classify" actually produces and where each class goes downstream. This
// is the graph-native half of the panel: IN a figure crop, OUT a class → a branch.

import { theme } from "../../../theme";
import { CLASS_ROUTES } from "./enrichClassifyModel";

export function ClassRoutingChips() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <div style={{ fontSize: theme.font.size.s, fontWeight: theme.font.weight.semibold, color: theme.color.text }}>
        Classes → enrichment branch
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.xs }}>
        {CLASS_ROUTES.map((route) => (
          <div
            key={route.kind}
            style={{
              display: "flex", alignItems: "baseline", gap: theme.space.xs,
              background: theme.color.surface2, border: `1px solid ${theme.color.line}`,
              borderRadius: theme.radius.pill, padding: `${theme.space.xs}px ${theme.space.m}px`,
            }}
          >
            <span style={{ fontSize: theme.font.size.s, fontWeight: theme.font.weight.medium, color: theme.color.text }}>
              {route.title}
            </span>
            <span style={{ fontSize: theme.font.size.xs, color: theme.color.dim }}>→ {route.target}</span>
          </div>
        ))}
      </div>
      <span style={{ fontSize: theme.font.size.xs, color: theme.color.mute, lineHeight: 1.4 }}>
        Each branch's providers (OCR readers, vision model) are edited in the chains below.
      </span>
    </div>
  );
}
