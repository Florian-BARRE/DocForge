// ====== Code Summary ======
// The 3-step collection wizard's parent — owns the whole draft plus the current step, each step
// is a dumb child receiving slices of this state. Submits once, on step 3. Reused for both
// creation (POST) and editing (PATCH an existing collection) via the `mode`/`initial` props;
// an `initial` collection prefills every field and the last step becomes "Review changes".

import { useState } from "react";
import { createCollection, updateCollection, type Collection } from "../../../api/collections";
import type { ApiIssue } from "../../../api/http";
import { HttpError } from "../../../api/http";
import { BackLink } from "../../../components/BackLink";
import { theme } from "../../../theme";
import type { Navigate } from "../../../shell/view";
import { StepIdentity } from "./StepIdentity";
import { StepReview } from "./StepReview";
import { StepSchema } from "./StepSchema";
import {
  draftFromCollection,
  mbToBytes,
  removedFieldNames,
  toFieldSpec,
  type DraftField,
} from "./wizardTypes";

export type WizardMode = "create" | "edit";

interface CollectionWizardProps {
  onNavigate: Navigate;
  /** Defaults to "create"; pass "edit" together with `initial`/`collectionId` to patch instead. */
  mode?: WizardMode;
  /** The collection being edited — required (and only used) in "edit" mode. */
  initial?: Collection;
  collectionId?: string;
}

const STEP_LABELS_BY_MODE: Record<WizardMode, string[]> = {
  create: ["Identity & limits", "Schema", "Review & create"],
  edit: ["Identity & limits", "Schema", "Review changes"],
};

export function CollectionWizard({ onNavigate, mode = "create", initial, collectionId }: CollectionWizardProps) {
  const prefill = initial ? draftFromCollection(initial) : null;

  const [step, setStep] = useState(0);
  const [name, setName] = useState(prefill?.name ?? "");
  const [formats, setFormats] = useState<string[]>(prefill?.formats ?? []);
  const [maxSizeMb, setMaxSizeMb] = useState(prefill?.maxSizeMb ?? 50);
  const [fields, setFields] = useState<DraftField[]>(prefill?.fields ?? []);
  const [submitting, setSubmitting] = useState(false);
  const [issues, setIssues] = useState<ApiIssue[]>([]);

  const stepLabels = STEP_LABELS_BY_MODE[mode];
  const removed = initial ? removedFieldNames(initial.fields, fields) : [];

  const backTarget = mode === "edit" && collectionId
    ? ({ name: "collection", collectionId } as const)
    : ({ name: "collections" } as const);

  const handleSubmit = async () => {
    setSubmitting(true);
    setIssues([]);
    try {
      const payload = {
        name: name.trim(),
        supported_formats: formats,
        max_file_size_bytes: mbToBytes(maxSizeMb),
        fields: fields.map(toFieldSpec),
      };
      const result = mode === "edit" && collectionId
        ? await updateCollection(collectionId, payload)
        : await createCollection(payload);
      onNavigate({ name: "collection", collectionId: result.id });
    } catch (error) {
      setIssues(error instanceof HttpError ? error.issues : [{ message: String(error) }]);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ padding: theme.space.l, overflowY: "auto", height: "100%" }}>
      <BackLink label={mode === "edit" ? "Collection" : "Collections"} onClick={() => onNavigate(backTarget)} />
      <h1 style={{ fontSize: theme.font.size.xl, margin: `${theme.space.s}px 0` }}>
        {mode === "edit" ? `Edit collection — ${initial?.name}` : "New collection"}
      </h1>
      <div style={{ display: "flex", gap: theme.space.m, marginBottom: theme.space.l, fontSize: theme.font.size.s }}>
        {stepLabels.map((label, index) => (
          <span key={label} style={{ color: index === step ? theme.color.accent : theme.color.dim, fontWeight: index === step ? 600 : 400 }}>
            {index + 1}. {label}
          </span>
        ))}
      </div>
      {step === 0 && (
        <StepIdentity
          mode={mode}
          name={name} onNameChange={setName}
          formats={formats} onFormatsChange={setFormats}
          maxSizeMb={maxSizeMb} onMaxSizeMbChange={setMaxSizeMb}
          onNext={() => setStep(1)}
        />
      )}
      {step === 1 && (
        <StepSchema mode={mode} fields={fields} onFieldsChange={setFields} onBack={() => setStep(0)} onNext={() => setStep(2)} />
      )}
      {step === 2 && (
        <StepReview
          mode={mode}
          name={name} formats={formats} maxSizeBytes={mbToBytes(maxSizeMb)} fields={fields}
          removedFieldNames={removed}
          onBack={() => setStep(1)} onSubmit={handleSubmit} submitting={submitting} issues={issues}
        />
      )}
    </div>
  );
}
