// ====== Code Summary ======
// The expiration picker for create/rotate — Never, three day-count presets, or a custom date.
// Purely presentational: it only reports the chosen ExpiryChoice, the ISO conversion happens at
// submit time in the parent (see expiry.ts).

import { Button } from "../../components/Button";
import { FormField } from "../../components/FormField";
import { inputStyle } from "../../components/inputStyle";
import { theme } from "../../theme";
import type { ExpiryChoice } from "./expiry";

interface ExpirySelectorProps {
  value: ExpiryChoice;
  onChange: (choice: ExpiryChoice) => void;
}

const PRESETS: { label: string; days: number }[] = [
  { label: "30 days", days: 30 },
  { label: "90 days", days: 90 },
  { label: "1 year", days: 365 },
];

export function ExpirySelector({ value, onChange }: ExpirySelectorProps) {
  const isCustom = value.kind === "custom";

  return (
    <FormField label="Expiration" hint="Never-expiring keys stay valid until manually revoked.">
      <div style={{ display: "flex", gap: theme.space.xs, flexWrap: "wrap" }}>
        <Button
          type="button" size="sm" variant={value.kind === "never" ? "primary" : "secondary"}
          onClick={() => onChange({ kind: "never" })}
        >
          Never
        </Button>
        {PRESETS.map((preset) => (
          <Button
            key={preset.days} type="button" size="sm"
            variant={value.kind === "preset" && value.days === preset.days ? "primary" : "secondary"}
            onClick={() => onChange({ kind: "preset", days: preset.days })}
          >
            {preset.label}
          </Button>
        ))}
        <Button
          type="button" size="sm" variant={isCustom ? "primary" : "secondary"}
          onClick={() => onChange({ kind: "custom", date: isCustom ? value.date : "" })}
        >
          Custom
        </Button>
      </div>
      {isCustom && (
        <input
          type="date"
          // Block past dates — a custom expiry in the past would mint an already-expired key.
          min={new Date().toISOString().slice(0, 10)}
          style={{ ...inputStyle, marginTop: theme.space.xs }}
          value={value.date}
          onChange={(e) => onChange({ kind: "custom", date: e.target.value })}
        />
      )}
    </FormField>
  );
}
