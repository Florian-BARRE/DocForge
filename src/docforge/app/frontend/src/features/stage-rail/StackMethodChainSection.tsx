// ====== Code Summary ======
// The `llm` contextualize method's OWN fallback chain, nested inside its StackMethodCard — the
// subtlest chain surface in the rail: a chain living INSIDE a stack entry rather than addressed by
// a slot. Edited exclusively through `set_stack` (StackMethod.chain), never `set_chain` — the
// compiler has no slot for it. Still rendered in the shared chain accent so it reads as the same
// concept as every other fallback chain, just visually nested one level under its owning method.

import { Chip } from "../../components/Chip";
import type { ChainView, Palette } from "../../api/types";
import { theme } from "../../theme";
import type { StageRailActions } from "./actions";
import { ChainStepList } from "./ChainStepList";
import { familyIsScored } from "../../components/schema-form/paletteLookup";

interface StackMethodChainSectionProps {
  stageKey: string;
  methodIndex: number;
  /** The informational ChainView the backend surfaces at slot `contextualize.{index}` for this
   *  method — supplies title/description/available kinds; steps come from `method.chain` itself. */
  chainView: ChainView;
  palette: Palette;
  actions: StageRailActions;
}

export function StackMethodChainSection({
  stageKey, methodIndex, chainView, palette, actions,
}: StackMethodChainSectionProps) {
  const scored = familyIsScored(palette, chainView.family);

  return (
    <div
      style={{
        marginTop: theme.space.s, marginLeft: theme.space.l + theme.space.s,
        border: `1px solid ${theme.color.chain}`, borderLeft: `3px solid ${theme.color.chain}`,
        background: theme.color.chainSoft,
        borderRadius: theme.radius.m, padding: theme.space.s,
        display: "flex", flexDirection: "column", gap: theme.space.xs,
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: theme.space.s, flexWrap: "wrap" }}>
        <strong style={{ color: theme.color.chain, fontSize: theme.font.size.s }}>⛓ {chainView.title}</strong>
        <Chip tone={scored ? "warn" : "dim"}>{scored ? "quality-gated" : "failure-only"}</Chip>
        <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>{chainView.description}</span>
      </div>
      <ChainStepList
        steps={chainView.steps}
        family={chainView.family}
        available={chainView.available}
        palette={palette}
        scored={scored}
        onStepsChange={(steps) => actions.setStackMethodChainSteps(stageKey, methodIndex, steps)}
        onStepConfigChange={(index, field, value) => actions.setStackMethodChainStepConfig(stageKey, methodIndex, index, field, value)}
      />
    </div>
  );
}
