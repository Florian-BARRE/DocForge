// ====== Code Summary ======
// One fallback chain at a stage's own model-call site — the visually-distinct block, in its own
// chain accent color, so it never reads as "just another stage option". Generic over EVERY
// chain-bearing stage (parse, embed, metagen chunk/document, and enrich's per-figure sites) — the
// only thing that varies per stage is which wire slot the edit must carry, resolved by
// `buildSetChainAction`/`chainActionSlot` upstream, never here. The contextualize `llm` chain is
// deliberately NOT rendered through this component (see StackMethodChainSection): the compiler
// only accepts a `set_chain` for `stage="enrich"`, so a contextualize edit here would silently
// no-op even though the view exposes it for display parity.

import { Chip } from "../../components/Chip";
import type { ChainView, Palette } from "../../api/types";
import { theme } from "../../theme";
import type { StageRailActions } from "./actions";
import { ChainStepList } from "./ChainStepList";
import { familyIsScored } from "./state/paletteLookup";

interface ChainSectionProps {
  stageKey: string;
  chain: ChainView;
  palette: Palette;
  actions: StageRailActions;
}

export function ChainSection({ stageKey, chain, palette, actions }: ChainSectionProps) {
  const scored = familyIsScored(palette, chain.family);

  return (
    <div
      style={{
        border: `1px solid ${theme.color.chain}`, background: theme.color.chainSoft,
        borderRadius: theme.radius.m, padding: theme.space.s,
        display: "flex", flexDirection: "column", gap: theme.space.xs,
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: theme.space.s, flexWrap: "wrap" }}>
        <strong style={{ color: theme.color.chain, fontSize: theme.font.size.m }}>⛓ {chain.title}</strong>
        <Chip tone={scored ? "warn" : "dim"} title={scored ? "Escalates on a quality threshold or on failure" : "This family reports no quality score — escalates on failure only"}>
          {scored ? "quality-gated" : "failure-only"}
        </Chip>
        <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>{chain.description}</span>
      </div>
      <ChainStepList
        steps={chain.steps}
        family={chain.family}
        available={chain.available}
        palette={palette}
        scored={scored}
        onStepsChange={(steps) => actions.setChainSteps(stageKey, chain.slot, steps)}
        onStepConfigChange={(index, field, value) => actions.setChainStepConfig(stageKey, chain.slot, index, field, value)}
        onStepScoreBelowChange={scored ? (index, value) => actions.setChainStepScoreBelow(stageKey, chain.slot, index, value) : undefined}
      />
    </div>
  );
}
