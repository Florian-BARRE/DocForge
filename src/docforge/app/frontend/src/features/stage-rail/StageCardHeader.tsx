// ====== Code Summary ======
// The clickable label block of a stage card's header — title, "needs X" chip, description, and
// (only while collapsed) a one-line summary of what's actually chosen, so collapsing a stage never
// hides WHAT it does, only its full editable body. Toggles the card's `expanded` state; the enable
// switch lives OUTSIDE this component (in StageCard, as a sibling) so a click here can never
// accidentally flip it.

import type { KeyboardEvent } from "react";
import { Chip } from "../../components/Chip";
import type { Palette, StageView } from "../../api/types";
import { theme } from "../../theme";
import { summarizeStage } from "./state/stageSummary";

interface StageCardHeaderProps {
  stage: StageView;
  palette: Palette;
  /** Whether this stage even HAS a body to collapse (fixed/disabled stages don't — see StageCard). */
  collapsible: boolean;
  expanded: boolean;
  onToggleExpand: () => void;
}

export function StageCardHeader({ stage, palette, collapsible, expanded, onToggleExpand }: StageCardHeaderProps) {
  const summary = collapsible && !expanded ? summarizeStage(stage, palette) : null;

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    onToggleExpand();
  };

  return (
    <div
      role={collapsible ? "button" : undefined}
      tabIndex={collapsible ? 0 : undefined}
      aria-expanded={collapsible ? expanded : undefined}
      onClick={collapsible ? onToggleExpand : undefined}
      onKeyDown={collapsible ? handleKeyDown : undefined}
      style={{ flex: 1, minWidth: 0, cursor: collapsible ? "pointer" : "default" }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s, flexWrap: "wrap" }}>
        <strong style={{ fontFamily: theme.font.display, fontSize: theme.font.size.xl, fontWeight: 700 }}>{stage.title}</strong>
        {stage.requires.length > 0 && (
          <Chip tone="dim" title={`Enabling this also enables: ${stage.requires.join(", ")}`}>
            needs {stage.requires.join(", ")}
          </Chip>
        )}
        {collapsible && (
          <span aria-hidden style={{ marginLeft: "auto", color: theme.color.mute, fontSize: theme.font.size.s }}>
            {expanded ? "▾" : "▸"}
          </span>
        )}
      </div>
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.s, marginTop: 2 }}>{stage.description}</div>
      {summary && (
        <div style={{ color: theme.color.text, fontSize: theme.font.size.s, marginTop: 4, fontWeight: theme.font.weight.medium }}>
          {summary}
        </div>
      )}
    </div>
  );
}
