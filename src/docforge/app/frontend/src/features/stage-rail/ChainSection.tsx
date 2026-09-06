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
import { ChainFlow } from "./ChainFlow";
import { ChainStepList } from "./ChainStepList";
import { familyIsScored } from "../../components/schema-form/paletteLookup";

interface ChainSectionProps {
  stageKey: string;
  chain: ChainView;
  palette: Palette;
  actions: StageRailActions;
}

export function ChainSection({ stageKey, chain, palette, actions }: ChainSectionProps) {
  const scored = familyIsScored(palette, chain.family);
  // A chain-owned stage (parse/embed): `chain.title`/`chain.description` mirror the stage's OWN
  // title/description verbatim (see StageViewer.__stage_chain_view) — the stage card above already
  // shows both, so repeating them here would be the same text three times over. An enrich per-figure
  // branch or a contextualize method's chain has a genuinely distinct title, so it keeps showing it.
  const isStageOwnedChain = chain.slot === stageKey;

  return (
    <div
      style={{
        position: "relative", overflow: "hidden",
        border: `1px solid ${theme.color.chain}`, background: theme.color.chainSoft,
        borderRadius: theme.radius.m, padding: theme.space.m, paddingLeft: theme.space.m + 3,
        display: "flex", flexDirection: "column", gap: theme.space.xs,
      }}
    >
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: theme.color.chain }} />
      <div style={{ display: "flex", alignItems: "baseline", gap: theme.space.s, flexWrap: "wrap" }}>
        <strong style={{ color: theme.color.chain, fontSize: theme.font.size.m }}>
          ⛓ {isStageOwnedChain ? "Fallback chain" : chain.title}
        </strong>
        <Chip tone={scored ? "info" : "dim"} title={scored ? "Escalates to the next provider on a low quality score, or if the call fails" : "This family reports no quality score — escalates only if the provider call fails"}>
          {scored ? "quality-gated" : "failure-only"}
        </Chip>
        {!isStageOwnedChain && <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>{chain.description}</span>}
      </div>
      <ChainFlow steps={chain.steps} family={chain.family} palette={palette} scored={scored} />
      <ChainStepList
        steps={chain.steps}
        family={chain.family}
        available={chain.available}
        palette={palette}
        scored={scored}
        primaryKindEditable={isStageOwnedChain}
        onStepsChange={(steps) => actions.setChainSteps(stageKey, chain.slot, steps)}
        onStepConfigChange={(index, field, value) => actions.setChainStepConfig(stageKey, chain.slot, index, field, value)}
        onStepScoreBelowChange={scored ? (index, value) => actions.setChainStepScoreBelow(stageKey, chain.slot, index, value) : undefined}
      />
    </div>
  );
}
