// ====== Code Summary ======
// The ColBERT late-interaction re-rank toggle, plus its rescore-pool-size input (shown only while
// the toggle is on). Off/unset means "defer to the collection's saved search config" — the toggle
// only ever sends an explicit `true`, never `false`, so leaving it untouched changes nothing.

import { FormField } from "../../components/FormField";
import { inputStyle } from "../../components/inputStyle";
import { NumberField } from "../../components/schema-form/NumberField";
import { Switch } from "../../components/Switch";
import { theme } from "../../theme";

const MIN_POOL_SIZE = 1;
const MAX_POOL_SIZE = 1000;

interface LateInteractionControlsProps {
  enabled: boolean;
  onEnabledChange: (next: boolean) => void;
  rescorePoolSize: number;
  onRescorePoolSizeChange: (next: number) => void;
}

export function LateInteractionControls({
  enabled,
  onEnabledChange,
  rescorePoolSize,
  onRescorePoolSizeChange,
}: LateInteractionControlsProps) {
  return (
    <div style={{ display: "flex", gap: theme.space.l, alignItems: "center" }}>
      <div style={{ display: "flex", gap: theme.space.s, alignItems: "center" }}>
        <Switch checked={enabled} onChange={onEnabledChange} title="Late interaction (ColBERT re-rank)" />
        <span style={{ fontSize: theme.font.size.s, color: theme.color.text }}>
          Late interaction (ColBERT re-rank)
        </span>
        <span style={{ fontSize: theme.font.size.xs, color: theme.color.dim }}>
          {enabled ? "on" : "off — defers to collection config"}
        </span>
      </div>
      {enabled && (
        <div style={{ width: 160 }}>
          <FormField
            label="Candidates re-scored by ColBERT"
            hint="How many results ColBERT re-examines before returning the top ones — higher = more precise, slower."
          >
            <NumberField
              value={rescorePoolSize}
              min={MIN_POOL_SIZE}
              max={MAX_POOL_SIZE}
              style={inputStyle}
              onChange={(value) =>
                onRescorePoolSizeChange(
                  value === undefined
                    ? MIN_POOL_SIZE
                    : Math.min(MAX_POOL_SIZE, Math.max(MIN_POOL_SIZE, value)),
                )
              }
            />
          </FormField>
        </div>
      )}
    </div>
  );
}
