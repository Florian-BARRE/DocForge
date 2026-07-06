// ====== Code Summary ======
// A provider stage's exclusive choice (parse/chunk/embed) — a select over `stage.available`,
// with the currently-picked node's palette summary shown underneath so the choice is legible
// without leaving the rail.

import { inputStyle } from "../../components/inputStyle";
import type { Palette, StageView } from "../../api/types";
import { theme } from "../../theme";
import type { StageRailActions } from "./actions";
import { findNodeCard } from "./state/paletteLookup";

interface ProviderPickerProps {
  stage: StageView;
  palette: Palette;
  actions: StageRailActions;
}

export function ProviderPicker({ stage, palette, actions }: ProviderPickerProps) {
  if (!stage.family) return null;
  const current = stage.provider ? findNodeCard(palette, stage.family, stage.provider) : undefined;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <select
        value={stage.provider ?? ""}
        onChange={(e) => actions.setProvider(stage.key, e.target.value)}
        style={{ ...inputStyle, width: "auto", minWidth: 220 }}
      >
        {stage.available.map((kind) => {
          const card = findNodeCard(palette, stage.family!, kind);
          return (
            <option key={kind} value={kind}>
              {card?.name ?? kind}
            </option>
          );
        })}
      </select>
      {current?.summary && (
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>{current.summary}</div>
      )}
    </div>
  );
}
