// ====== Code Summary ======
// The search rail's own sticky step index — the SAME numbered-circle visual language as the
// ingestion stage rail's `StageRailMinimap` (features/stage-rail/StageRailMinimap.tsx), MIRRORED
// here rather than imported: that component is typed over `StageView` (family/provider/chains/
// stack/…), which the search rail's flat `ActionBlob`-based steps don't have — a plain
// `{key,title,enabled}` entry (see state/searchMinimapEntries.ts) is all this rail needs. The
// jump-scroll/anchor-id convention (`stageAnchorId`) and the viewport tracker (`useActiveStageKey`)
// ARE reused as-is from features/stage-rail — those two are pure/generic (string keys + a DOM id
// convention), not coupled to StageView at all.

import { theme } from "../../theme";
import { stageAnchorId } from "../stage-rail/state/stageAnchor";
import type { SearchMinimapEntry } from "./state/searchMinimapEntries";

interface SearchPipelineMinimapProps {
  entries: SearchMinimapEntry[];
  activeKey: string | null;
}

function jumpToStep(key: string): void {
  document.getElementById(stageAnchorId(key))?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export function SearchPipelineMinimap({ entries, activeKey }: SearchPipelineMinimapProps) {
  return (
    <nav
      aria-label="Search pipeline step index"
      style={{
        position: "sticky", top: theme.space.l, alignSelf: "flex-start", flexShrink: 0, width: 176,
        display: "flex", flexDirection: "column", paddingTop: theme.space.xs + 2,
      }}
    >
      {entries.map((entry, index) => {
        const active = entry.key === activeKey;
        return (
          <div key={entry.key} style={{ display: "flex", alignItems: "stretch" }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0, width: 26 }}>
              <span
                aria-hidden
                style={{
                  width: 20, height: 20, borderRadius: theme.radius.pill, display: "grid", placeItems: "center",
                  fontSize: theme.font.size.xs, fontWeight: theme.font.weight.semibold, flexShrink: 0,
                  // accentSafe, not accent — same AA-contrast note as StageRailMinimap: this fill
                  // carries white knockout text, and plain accent fails AA at this size.
                  background: active ? theme.color.accentSafe : theme.color.surface2,
                  color: active ? theme.color.onAccent : theme.color.dim,
                  border: `1px solid ${active ? theme.color.accentSafe : theme.color.line}`,
                }}
              >
                {index + 1}
              </span>
              {index < entries.length - 1 && (
                <div style={{ width: 1, flex: 1, minHeight: theme.space.m, background: theme.color.line }} />
              )}
            </div>
            <button
              type="button"
              onClick={() => jumpToStep(entry.key)}
              title={entry.title}
              style={{
                flex: 1, minWidth: 0, background: "none", border: "none", cursor: "pointer",
                textAlign: "left", padding: `1px 0 ${theme.space.s}px ${theme.space.xs}px`,
                fontSize: theme.font.size.s, fontFamily: theme.font.family,
                fontWeight: active ? theme.font.weight.semibold : theme.font.weight.normal,
                color: active ? theme.color.text : theme.color.dim,
                opacity: entry.enabled ? 1 : 0.55,
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
              }}
            >
              {entry.title}
            </button>
          </div>
        );
      })}
    </nav>
  );
}
