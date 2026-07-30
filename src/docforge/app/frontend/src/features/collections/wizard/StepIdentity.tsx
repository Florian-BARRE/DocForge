// ====== Code Summary ======
// Wizard step 1: identity + upload limits — name, accepted formats, per-file size cap. Shared
// by create (POST) and edit (PATCH) — only the name field's hint changes, since renaming an
// existing collection is allowed but choosing the very first name implies it will stick.

import { Button } from "../../../components/Button";
import { FormField } from "../../../components/FormField";
import { TagsInput } from "../../../components/TagsInput";
import { inputStyle } from "../../../components/inputStyle";
import { theme } from "../../../theme";
import type { WizardMode } from "./CollectionWizard";

interface StepIdentityProps {
  mode: WizardMode;
  name: string;
  onNameChange: (name: string) => void;
  formats: string[];
  onFormatsChange: (formats: string[]) => void;
  maxSizeMb: number;
  onMaxSizeMbChange: (mb: number) => void;
  onNext: () => void;
}

export function StepIdentity({
  mode, name, onNameChange, formats, onFormatsChange, maxSizeMb, onMaxSizeMbChange, onNext,
}: StepIdentityProps) {
  const valid = name.trim().length > 0 && formats.length > 0 && maxSizeMb > 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.l, maxWidth: 480 }}>
      <div
        style={{
          display: "flex", flexDirection: "column", gap: theme.space.l,
          background: theme.color.surface, border: `1px solid ${theme.color.line}`,
          borderRadius: theme.radius.l, boxShadow: theme.shadow.sm, padding: theme.space.l,
        }}
      >
        <FormField
          label="Name"
          hint={mode === "edit" ? "Unique human name — renaming is allowed, another collection just can't already use it." : "Unique human name."}
        >
          <input
            style={inputStyle}
            value={name}
            onChange={(e) => onNameChange(e.target.value)}
            placeholder="e.g. legal-contracts"
          />
        </FormField>
        <FormField label="Supported formats" hint="File extensions accepted at upload (e.g. pdf, docx).">
          <TagsInput values={formats} onChange={onFormatsChange} placeholder="pdf, docx, …" />
        </FormField>
        <FormField label="Max file size (MB)" hint="Upload rejected above this size.">
          <input
            type="number"
            min={1}
            style={inputStyle}
            value={maxSizeMb}
            onChange={(e) => onMaxSizeMbChange(Number(e.target.value))}
          />
        </FormField>
      </div>
      <div>
        <Button variant="primary" disabled={!valid} onClick={onNext}>
          Next — schema
        </Button>
      </div>
    </div>
  );
}
