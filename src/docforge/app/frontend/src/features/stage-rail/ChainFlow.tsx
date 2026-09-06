// ====== Code Summary ======
// Read-only left-to-right overview of a fallback chain — "Provider → [condition] → Provider" — sat
// above the editable ChainStepList so the chain's shape is legible at a glance before diving into
// the per-step edit surface below. Each condition chip mirrors the SAME per-step escalation rule
// ChainStepCard already renders inline (a quality threshold when the family scores AND this step
// actually carries one, failure-only otherwise) — never a second source of truth for the rule. A
// single-step chain renders one provider chip and no arrows.

import { Fragment } from "react";
import { Chip } from "../../components/Chip";
import type { ChainStep, Palette } from "../../api/types";
import { theme } from "../../theme";
import { findNodeCard } from "../../components/schema-form/paletteLookup";

interface ChainFlowProps {
  steps: ChainStep[];
  family: string;
  palette: Palette;
  /** Whether this family carries a score a threshold can escalate on — same flag ChainStepCard gates its input on. */
  scored: boolean;
}

/** Plain-English label for the transition LEAVING `step` — quality-gated when the family scores AND
 *  this step actually carries a threshold, failure-only otherwise (an unset threshold on a scored
 *  family still falls through on failure only, exactly as ChainStepCard's own placeholder says). */
function transitionLabel(step: ChainStep, scored: boolean): string {
  if (scored && step.score_below != null) return `quality < ${step.score_below}`;
  return "on failure";
}

export function ChainFlow({ steps, family, palette, scored }: ChainFlowProps) {
  if (steps.length === 0) return null;

  return (
    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: theme.space.xs }}>
      {steps.map((step, index) => (
        <Fragment key={index}>
          {index > 0 && (
            <>
              <FlowArrow />
              <Chip tone="dim">{`[${transitionLabel(steps[index - 1], scored)}]`}</Chip>
              <FlowArrow />
            </>
          )}
          <Chip tone="neutral">{findNodeCard(palette, family, step.kind)?.name ?? step.kind}</Chip>
        </Fragment>
      ))}
    </div>
  );
}

function FlowArrow() {
  return (
    <span aria-hidden="true" style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
      →
    </span>
  );
}
