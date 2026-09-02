// ====== Code Summary ======
// The 3-step collection wizard's parent — owns the whole draft plus the current step, each step
// is a dumb child receiving slices of this state. Submits once, on step 3. Reused for both
// creation (POST) and editing (PATCH an existing collection) via the `mode`/`initial` props;
// an `initial` collection prefills every field and the last step becomes "Review changes".

import { useState } from "react";
import { createCollection, updateCollection, type Collection, type CollectionPreset } from "../../../api/collections";
import type { ApiIssue } from "../../../api/http";
import { HttpError } from "../../../api/http";
import { useToast } from "../../../shell/toast";
import { BackLink } from "../../../components/BackLink";
import { PageHeader } from "../../../components/PageHeader";
import { theme } from "../../../theme";
import type { Navigate } from "../../../shell/view";
import { DangerZone } from "./DangerZone";
import { StepIdentity } from "./StepIdentity";
import { StepReview } from "./StepReview";
import { StepSchema } from "./StepSchema";
import { WizardSteps } from "./WizardSteps";
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
  const [jobTimeoutSeconds, setJobTimeoutSeconds] = useState<number | null>(prefill?.jobTimeoutSeconds ?? null);
  const [preset, setPreset] = useState<CollectionPreset>("standard");
  // Any contract field StepIdentity's schema-driven form renders that this wizard has no named
  // slot for yet — see StepIdentity's `extra`/`onExtraChange` doc for why this exists. In edit
  // mode, seeded from the loaded collection (`draftFromCollection`) so a stored value for such a
  // field survives onto the form instead of falling back to the schema default.
  const [extraContract, setExtraContract] = useState<Record<string, unknown>>(prefill?.extraContract ?? {});
  const [fields, setFields] = useState<DraftField[]>(prefill?.fields ?? []);
  const toast = useToast();
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
        ...extraContract,
        name: name.trim(),
        supported_formats: formats,
        max_file_size_bytes: mbToBytes(maxSizeMb),
        job_timeout_seconds: jobTimeoutSeconds,
        fields: fields.map(toFieldSpec),
      };
      const result = mode === "edit" && collectionId
        ? await updateCollection(collectionId, payload)
        // `preset` selects the stock ingestion blob (light = fast, enrichment-free); create-only.
        : await createCollection({ ...payload, preset });
      toast.success(mode === "edit" ? `Collection “${result.name}” updated` : `Collection “${result.name}” created`);
      onNavigate({ name: "collection", collectionId: result.id });
    } catch (error) {
      const issueList = error instanceof HttpError ? error.issues : [{ message: String(error) }];
      setIssues(issueList);
      toast.error(`${mode === "edit" ? "Update" : "Create"} failed — ${issueList[0]?.message ?? "unknown error"}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="df-rise" style={{ padding: theme.space.xl, maxWidth: 900, margin: "0 auto", overflowY: "auto", height: "100%" }}>
      <PageHeader
        eyebrow={<BackLink label={mode === "edit" ? "Collection" : "Collections"} onClick={() => onNavigate(backTarget)} />}
        title={mode === "edit" ? `Edit collection — ${initial?.name}` : "New collection"}
        subtitle={mode === "edit" ? "Update the contract — schema changes apply on submit." : "Define the contract this collection ingests against."}
      />
      <WizardSteps labels={stepLabels} current={step} />
      {step === 0 && (
        <StepIdentity
          mode={mode}
          name={name} onNameChange={setName}
          formats={formats} onFormatsChange={setFormats}
          maxSizeMb={maxSizeMb} onMaxSizeMbChange={setMaxSizeMb}
          jobTimeoutSeconds={jobTimeoutSeconds} onJobTimeoutSecondsChange={setJobTimeoutSeconds}
          preset={preset} onPresetChange={setPreset}
          extra={extraContract} onExtraChange={setExtraContract}
          onNext={() => setStep(1)}
        />
      )}
      {step === 1 && (
        <StepSchema mode={mode} fields={fields} onFieldsChange={setFields} onBack={() => setStep(0)} onNext={() => setStep(2)} />
      )}
      {step === 2 && (
        <StepReview
          mode={mode}
          name={name} formats={formats} maxSizeBytes={mbToBytes(maxSizeMb)} jobTimeoutSeconds={jobTimeoutSeconds} fields={fields}
          removedFieldNames={removed}
          onBack={() => setStep(1)} onSubmit={handleSubmit} submitting={submitting} issues={issues}
        />
      )}
      {/* Deletion is a settings action, not a wizard step — shown once, below every step, so it
          reads as belonging to the collection as a whole rather than to whichever step is active. */}
      {mode === "edit" && collectionId && initial && (
        <DangerZone collectionId={collectionId} collectionName={initial.name} onNavigate={onNavigate} />
      )}
    </div>
  );
}
