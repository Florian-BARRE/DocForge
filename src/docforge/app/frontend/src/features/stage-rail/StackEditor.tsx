// ====== Code Summary ======
// The ordered method stack of a stackable stage (contextualize) — add from the family's
// available methods, remove, move up/down. Every discrete edit resends the WHOLE ordered list
// via `set_stack` (a full replacement — never a partial patch).

import { useState } from "react";
import { Button } from "../../components/Button";
import { inputStyle } from "../../components/inputStyle";
import type { Palette, StageView } from "../../api/types";
import { theme } from "../../theme";
import type { StageRailActions } from "./actions";
import { StackMethodCard } from "./StackMethodCard";
import { findFamily, findNodeCard } from "../../components/schema-form/paletteLookup";
import { useStableListKeys } from "./state/stableKeys";

interface StackEditorProps {
  stage: StageView;
  palette: Palette;
  actions: StageRailActions;
}

export function StackEditor({ stage, palette, actions }: StackEditorProps) {
  const [addKind, setAddKind] = useState("");
  const family = stage.family ?? "";
  const familyNodes = findFamily(palette, family)?.nodes ?? [];
  // Stable per-slot identity, independent of `kind`/index, so reordering two same-kind methods
  // can't leak one card's expanded/local state onto the other's config (see stableKeys.ts).
  const { keys, move: moveKeys, remove: removeKey, add: addKey } = useStableListKeys(stage.stack.length);

  const move = (from: number, to: number) => {
    if (to < 0 || to >= stage.stack.length) return;
    const next = [...stage.stack];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    moveKeys(from, to);
    actions.setStackSteps(stage.key, next);
  };
  const remove = (index: number) => {
    removeKey(index);
    actions.setStackSteps(stage.key, stage.stack.filter((_, i) => i !== index));
  };
  const add = () => {
    if (!addKind) return;
    addKey();
    actions.setStackSteps(stage.key, [...stage.stack, { kind: addKind, config: {} }]);
    setAddKind("");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s }}>
      {stage.stack.length === 0 && (
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
          No methods yet — chunks carry no extra context until you add one.
        </div>
      )}
      {stage.stack.map((method, index) => (
        <StackMethodCard
          key={keys[index]}
          stageKey={stage.key}
          method={method}
          index={index}
          isFirst={index === 0}
          isLast={index === stage.stack.length - 1}
          card={findNodeCard(palette, family, method.kind)}
          chainView={method.kind === "llm" ? stage.chains.find((c) => c.slot === `contextualize.${index}`) : undefined}
          palette={palette}
          actions={actions}
          onMoveUp={() => move(index, index - 1)}
          onMoveDown={() => move(index, index + 1)}
          onRemove={() => remove(index)}
        />
      ))}
      <div style={{ display: "flex", gap: theme.space.s, alignItems: "center" }}>
        <select value={addKind} onChange={(e) => setAddKind(e.target.value)} style={{ ...inputStyle, width: "auto", minWidth: 200, borderRadius: theme.radius.m }}>
          <option value="">add a method…</option>
          {familyNodes.map((n) => (
            <option key={n.kind} value={n.kind}>{n.name}</option>
          ))}
        </select>
        <Button variant="secondary" size="sm" onClick={add} disabled={!addKind}>+ Add</Button>
      </div>
    </div>
  );
}
