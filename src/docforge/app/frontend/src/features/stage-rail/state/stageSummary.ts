// ====== Code Summary ======
// The collapsed stage card's one-line "what's actually chosen" summary — derived purely from the
// StageView + palette the rail already has, never a hardcoded per-stage string. Read generically
// off `StageKind` (the fixed 4-value shape the whole rail is built on — see StageMeta.kind in the
// backend), so a renamed provider/kind, or a new stack method, needs zero change here.

import { findNodeCard } from "../../../components/schema-form/paletteLookup";
import type { Palette, StageView } from "../../../api/types";

/** True for the one case a chain-capable provider stage (parse/embed) IS its own chain — see
 *  StageCard's identical check; kept in sync rather than shared since each reads a different half
 *  of the same fact (StageCard gates rendering, this only needs the step count). */
function ownChainStepCount(stage: StageView): number {
  const owns = stage.chains.length === 1 && stage.chains[0].slot === stage.key;
  return owns ? stage.chains[0].steps.length : 0;
}

export function summarizeStage(stage: StageView, palette: Palette): string {
  if (!stage.enabled) return "off";
  switch (stage.kind) {
    case "fixed":
      return "always on";
    case "provider": {
      const card = stage.provider ? findNodeCard(palette, stage.family ?? "", stage.provider) : undefined;
      const providerLabel = card?.name ?? stage.provider ?? "no provider selected";
      const steps = ownChainStepCount(stage);
      return steps > 1 ? `${providerLabel} · ${steps} fallback steps` : providerLabel;
    }
    case "toggle": {
      const chainSteps = stage.chains.reduce((total, chain) => total + chain.steps.length, 0);
      return chainSteps > 0 ? `configured · ${chainSteps} chain step${chainSteps === 1 ? "" : "s"}` : "configured";
    }
    case "stack": {
      const count = stage.stack.length;
      return count === 0 ? "no methods yet" : `${count} method${count === 1 ? "" : "s"}`;
    }
    default:
      return "";
  }
}
