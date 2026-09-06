// ====== Code Summary ======
// The sticky vertical stage index — numbered circles + connecting thread, mirroring the wizard's
// `WizardSteps` visual language but vertical and click-to-jump instead of linear-progress. Kills
// the "which of the 9/10 stages am I even looking at" disorientation the audit flagged: the
// currently-in-viewport stage (see `useActiveStageKey`) is the ONE circle that gets the forge accent
// — brand.md explicitly lists "active stage" among the few things orange is allowed to mark.

import { theme } from "../../theme";
import type { StageView } from "../../api/types";
import { stageAnchorId } from "./state/stageAnchor";

interface StageRailMinimapProps {
  stages: StageView[];
  activeKey: string | null;
}

function jumpToStage(stageKey: string): void {
  document.getElementById(stageAnchorId(stageKey))?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export function StageRailMinimap({ stages, activeKey }: StageRailMinimapProps) {
  return (
    <nav
      aria-label="Pipeline stage index"
      style={{
        position: "sticky", top: theme.space.l, alignSelf: "flex-start", flexShrink: 0, width: 176,
        display: "flex", flexDirection: "column", paddingTop: theme.space.xs + 2,
      }}
    >
      {stages.map((stage, index) => {
        const active = stage.key === activeKey;
        return (
          <div key={stage.key} style={{ display: "flex", alignItems: "stretch" }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0, width: 26 }}>
              <span
                aria-hidden
                style={{
                  width: 20, height: 20, borderRadius: theme.radius.pill, display: "grid", placeItems: "center",
                  fontSize: theme.font.size.xs, fontWeight: theme.font.weight.semibold, flexShrink: 0,
                  // accentSafe, not accent — see WizardSteps' identical note: this fill carries
                  // white knockout text, and plain accent fails AA at this size.
                  background: active ? theme.color.accentSafe : theme.color.surface2,
                  color: active ? theme.color.onAccent : theme.color.dim,
                  border: `1px solid ${active ? theme.color.accentSafe : theme.color.line}`,
                }}
              >
                {index + 1}
              </span>
              {index < stages.length - 1 && (
                <div style={{ width: 1, flex: 1, minHeight: theme.space.m, background: theme.color.line }} />
              )}
            </div>
            <button
              type="button"
              onClick={() => jumpToStage(stage.key)}
              title={stage.title}
              style={{
                flex: 1, minWidth: 0, background: "none", border: "none", cursor: "pointer",
                textAlign: "left", padding: `1px 0 ${theme.space.s}px ${theme.space.xs}px`,
                fontSize: theme.font.size.s, fontFamily: theme.font.family,
                fontWeight: active ? theme.font.weight.semibold : theme.font.weight.normal,
                color: active ? theme.color.text : theme.color.dim,
                opacity: stage.enabled ? 1 : 0.55,
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
              }}
            >
              {stage.title}
            </button>
          </div>
        );
      })}
    </nav>
  );
}
