// ====== Code Summary ======
// Wizard step 3: review the whole draft, submit, and surface 409/422 rejections through the
// same ApiIssueList used across the app. In edit mode, also warns — before the PATCH goes out —
// about any field the user removed from the schema (deleted server-side along with its values).

import type { ApiIssue } from "../../../api/http";
import { ApiIssueList } from "../../../components/ApiIssueList";
import { Button } from "../../../components/Button";
import { Chip } from "../../../components/Chip";
import { theme } from "../../../theme";
import { SchemaTable } from "../SchemaTable";
import type { WizardMode } from "./CollectionWizard";
import { bytesToMb, toFieldSpec, type DraftField } from "./wizardTypes";

interface StepReviewProps {
  mode: WizardMode;
  name: string;
  formats: string[];
  maxSizeBytes: number;
  fields: DraftField[];
  removedFieldNames: string[];
  onBack: () => void;
  onSubmit: () => void;
  submitting: boolean;
  issues: ApiIssue[];
}

export function StepReview({
  mode, name, formats, maxSizeBytes, fields, removedFieldNames, onBack, onSubmit, submitting, issues,
}: StepReviewProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.l }}>
      <div
        style={{
          background: theme.color.surface, border: `1px solid ${theme.color.line}`,
          borderRadius: theme.radius.l, boxShadow: theme.shadow.sm, padding: theme.space.l,
        }}
      >
        <div style={{ fontFamily: theme.font.display, fontSize: theme.font.size.xxl, fontWeight: 700 }}>{name}</div>
        <div style={{ display: "flex", gap: 6, marginTop: theme.space.s, flexWrap: "wrap" }}>
          {formats.map((f) => <Chip key={f} tone="accent">{f}</Chip>)}
        </div>
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.m, marginTop: theme.space.s }}>
          Max file size: {bytesToMb(maxSizeBytes).toFixed(1)} MB · {fields.length} field(s)
        </div>
      </div>
      <SchemaTable fields={fields.map(toFieldSpec)} />
      {mode === "edit" && removedFieldNames.length > 0 && (
        <div
          style={{
            background: theme.color.warnSoft, borderLeft: `3px solid ${theme.color.warn}`,
            borderRadius: theme.radius.s, padding: `${theme.space.xs}px ${theme.space.s}px`,
            fontSize: theme.font.size.s, color: theme.color.warn,
          }}
        >
          <strong>{removedFieldNames.length} field{removedFieldNames.length > 1 ? "s" : ""} removed</strong> — submitting
          deletes {removedFieldNames.length > 1 ? "them" : "it"} and every value already stored against{" "}
          {removedFieldNames.length > 1 ? "them" : "it"}.
          <div style={{ display: "flex", gap: 4, marginTop: theme.space.xs, flexWrap: "wrap" }}>
            {removedFieldNames.map((f) => <Chip key={f} tone="warn">{f}</Chip>)}
          </div>
        </div>
      )}
      <ApiIssueList issues={issues} />
      <div style={{ display: "flex", gap: theme.space.s }}>
        <Button onClick={onBack} disabled={submitting}>Back</Button>
        <Button variant="primary" onClick={onSubmit} disabled={submitting}>
          {mode === "edit" ? (submitting ? "saving…" : "Save changes") : (submitting ? "creating…" : "Create collection")}
        </Button>
      </div>
    </div>
  );
}
