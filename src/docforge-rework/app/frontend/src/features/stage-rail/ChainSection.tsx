// ====== Code Summary ======
// One fallback chain (a model-call site of the enrich stage) — the visually-distinct block, in
// its own chain accent color, so it never reads as "just another stage option". Add a step from
// the family's available kinds, remove, reorder; every discrete edit resends the whole ordered
// step list via `set_chain`.

import { useState } from "react";
import { Button } from "../../components/Button";
import { inputStyle } from "../../components/inputStyle";
import type { ChainView, Palette } from "../../api/types";
import { theme } from "../../theme";
import type { StageRailActions } from "./actions";
import { ChainStepCard } from "./ChainStepCard";
import { findNodeCard } from "./state/paletteLookup";

interface ChainSectionProps {
  stageKey: string;
  chain: ChainView;
  palette: Palette;
  actions: StageRailActions;
}

export function ChainSection({ stageKey, chain, palette, actions }: ChainSectionProps) {
  const [addKind, setAddKind] = useState("");

  const move = (from: number, to: number) => {
    if (to < 0 || to >= chain.steps.length) return;
    const next = [...chain.steps];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    actions.setChainSteps(stageKey, chain.slot, next);
  };
  const remove = (index: number) => actions.setChainSteps(stageKey, chain.slot, chain.steps.filter((_, i) => i !== index));
  const add = () => {
    if (!addKind) return;
    actions.setChainSteps(stageKey, chain.slot, [...chain.steps, { kind: addKind, config: {}, score_below: null }]);
    setAddKind("");
  };

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
        <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>{chain.description}</span>
      </div>
      {chain.steps.length === 0 && (
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
          No fallback configured yet — add a first attempt below.
        </div>
      )}
      {chain.steps.map((step, index) => (
        <ChainStepCard
          key={`${step.kind}-${index}`}
          stageKey={stageKey}
          slot={chain.slot}
          step={step}
          index={index}
          isLast={index === chain.steps.length - 1}
          card={findNodeCard(palette, chain.family, step.kind)}
          actions={actions}
          onMoveUp={() => move(index, index - 1)}
          onMoveDown={() => move(index, index + 1)}
          onRemove={() => remove(index)}
        />
      ))}
      <div style={{ display: "flex", gap: theme.space.s, alignItems: "center" }}>
        <select value={addKind} onChange={(e) => setAddKind(e.target.value)} style={{ ...inputStyle, width: "auto", minWidth: 200 }}>
          <option value="">add a fallback step…</option>
          {chain.available.map((kind) => {
            const card = findNodeCard(palette, chain.family, kind);
            return <option key={kind} value={kind}>{card?.name ?? kind}</option>;
          })}
        </select>
        <Button variant="secondary" onClick={add} disabled={!addKind}>Add fallback</Button>
      </div>
    </div>
  );
}
