// ====== Code Summary ======
// The ordered list of a fallback chain's steps + its "add a fallback" control — shared by the
// stage-level ChainSection and the stack method's nested chain editor (StackMethodChainSection) so
// the two surfaces render and behave identically. Every discrete edit (add/remove/reorder) is
// resolved to the WHOLE ordered step list and handed to `onStepsChange`; the caller decides how
// that list becomes a StageAction (a slot-addressed `set_chain` at the top level, a `set_stack`
// with the method's chain replaced when nested).

import { useState } from "react";
import { Button } from "../../components/Button";
import { inputStyle } from "../../components/inputStyle";
import type { ChainStep, Palette } from "../../api/types";
import { theme } from "../../theme";
import { ChainStepCard } from "./ChainStepCard";
import { findNodeCard } from "../../components/schema-form/paletteLookup";
import { useStableListKeys } from "./state/stableKeys";

interface ChainStepListProps {
  steps: ChainStep[];
  family: string;
  available: string[];
  palette: Palette;
  /** Whether the family carries a score a threshold can escalate on (gates the input, per step). */
  scored: boolean;
  onStepsChange: (steps: ChainStep[]) => void;
  onStepConfigChange: (index: number, field: string, value: unknown) => void;
  onStepScoreBelowChange?: (index: number, value: number | null) => void;
}

export function ChainStepList({
  steps, family, available, palette, scored, onStepsChange, onStepConfigChange, onStepScoreBelowChange,
}: ChainStepListProps) {
  const [addKind, setAddKind] = useState("");
  // Stable per-slot identity, independent of `kind`/index, so reordering two same-kind fallback
  // steps can't leak one card's expanded/local state onto the other's config (see stableKeys.ts).
  const { keys, move: moveKeys, remove: removeKey, add: addKey } = useStableListKeys(steps.length);

  const move = (from: number, to: number) => {
    if (to < 0 || to >= steps.length) return;
    const next = [...steps];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    moveKeys(from, to);
    onStepsChange(next);
  };
  const remove = (index: number) => {
    removeKey(index);
    onStepsChange(steps.filter((_, i) => i !== index));
  };
  const add = () => {
    if (!addKind) return;
    addKey();
    onStepsChange([...steps, { kind: addKind, config: {}, score_below: null }]);
    setAddKind("");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      {steps.length === 0 && (
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
          No fallback configured yet — add a first attempt below.
        </div>
      )}
      {steps.map((step, index) => (
        <ChainStepCard
          key={keys[index]}
          step={step}
          index={index}
          isLast={index === steps.length - 1}
          scored={scored}
          card={findNodeCard(palette, family, step.kind)}
          onMoveUp={() => move(index, index - 1)}
          onMoveDown={() => move(index, index + 1)}
          onRemove={() => remove(index)}
          onConfigChange={(field, value) => onStepConfigChange(index, field, value)}
          onScoreBelowChange={onStepScoreBelowChange ? (value) => onStepScoreBelowChange(index, value) : undefined}
        />
      ))}
      <div style={{ display: "flex", gap: theme.space.s, alignItems: "center" }}>
        <select value={addKind} onChange={(e) => setAddKind(e.target.value)} style={{ ...inputStyle, width: "auto", minWidth: 200 }}>
          <option value="">add a fallback step…</option>
          {available.map((kind) => {
            const card = findNodeCard(palette, family, kind);
            return <option key={kind} value={kind}>{card?.name ?? kind}</option>;
          })}
        </select>
        <Button variant="secondary" onClick={add} disabled={!addKind}>Add fallback</Button>
      </div>
    </div>
  );
}
