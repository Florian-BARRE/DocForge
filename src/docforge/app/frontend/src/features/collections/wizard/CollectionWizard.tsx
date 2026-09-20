// ====== Code Summary ======
// The 3-step collection wizard's parent — owns the whole draft plus the current step, each step
// is a dumb child receiving slices of this state. Submits once, on step 3. Reused for both
// creation (POST, standalone full-page layout) and editing (PATCH an existing collection). In
// "edit" mode this renders EMBEDDED — no own page header/back-link/scroll wrapper and no Danger
// Zone — because it's now one section ("Contract") of `settings/CollectionSettingsPage`, which owns
// the page chrome and the Danger Zone itself.

import { useState } from "react";
import { createCollection, updateCollection, type Collection, type CollectionPreset } from "../../../api/collections";
import type { ApiIssue } from "../../../api/http";
import { HttpError } from "../../../api/http";
import { useToast } from "../../../shell/toast";
import { BackLink } from "../../../components/BackLink";
import { PageHeader } from "../../../components/PageHeader";
import { theme } from "../../../theme";
import type { Navigate } from "../../../shell/view";
import { StepIdentity } from "./StepIdentity";
import { StepReview } from "./StepReview";
import { StepSchema } from "./StepSchema";
import { TracePurgeOfferDialog } from "../trace/TracePurgeOfferDialog";
import { WizardPreviewPanel } from "./WizardPreviewPanel";
import { WizardSteps } from "./WizardSteps";
import {
  buildWizardPayload,
  draftFromCollection,
  removedFieldNames,
  resolveMaxFileSizeBytes,
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
  const [tags, setTags] = useState<string[]>(prefill?.tags ?? []);
  const [maxSizeMb, setMaxSizeMb] = useState(prefill?.maxSizeMb ?? 50);
  // The collection's exact stored bytes (edit mode) — preserved verbatim by `resolveMaxFileSizeBytes`
  // below as long as the user hasn't touched the MiB field, so a no-op save never drifts the value
  // through a display-rounding round-trip (iteration-2 regression). `null` when creating: there is
  // no prior value to preserve, always derive from the field.
  const maxSizeBytesOriginal = prefill?.maxSizeBytesOriginal ?? null;
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
  // Set right after a successful edit-mode save that LOWERED trace_verbosity away from 'full' —
  // the navigate-away is held until the offer dialog resolves (accept or decline), otherwise the
  // wizard (and this dialog's own state) would unmount before the user could act on it.
  const [traceOfferCollectionId, setTraceOfferCollectionId] = useState<string | null>(null);

  const stepLabels = STEP_LABELS_BY_MODE[mode];
  const removed = initial ? removedFieldNames(initial.fields, fields) : [];

  const backTarget = mode === "edit" && collectionId
    ? ({ name: "collection", collectionId } as const)
    : ({ name: "collections" } as const);

  // Shared by the submit call below and the live preview panel — the two can never drift apart.
  const draftPayload = buildWizardPayload({
    extraContract, name, formats, tags, maxSizeMb, maxSizeBytesOriginal, jobTimeoutSeconds, fields,
  });

  const handleSubmit = async () => {
    setSubmitting(true);
    setIssues([]);
    try {
      const payload = draftPayload;
      const result = mode === "edit" && collectionId
        ? await updateCollection(collectionId, payload)
        // `preset` selects the stock ingestion blob (light = fast, enrichment-free); create-only.
        : await createCollection({ ...payload, preset });
      toast.success(mode === "edit" ? `Collection “${result.name}” updated` : `Collection “${result.name}” created`);

      // Offer to also purge the heavy trace payloads already stored under the OLD setting whenever
      // this save just lowered trace_verbosity away from 'full' — `initial` is this edit session's
      // starting point (never re-fetched mid-session), so it reliably reads as the PREVIOUS value.
      const previousVerbosity = initial?.trace_verbosity;
      const nextVerbosity = (payload as unknown as Record<string, unknown>).trace_verbosity;
      if (mode === "edit" && previousVerbosity === "full" && nextVerbosity !== "full") {
        setTraceOfferCollectionId(result.id);
      } else {
        onNavigate({ name: "collection", collectionId: result.id });
      }
    } catch (error) {
      const issueList = error instanceof HttpError ? error.issues : [{ message: String(error) }];
      setIssues(issueList);
      toast.error(`${mode === "edit" ? "Update" : "Create"} failed — ${issueList[0]?.message ?? "unknown error"}`);
    } finally {
      setSubmitting(false);
    }
  };

  const steps = (
    <>
      <WizardSteps labels={stepLabels} current={step} />
      {/* Step 0 (Identity) is a narrow form — the live preview panel fills the page's otherwise-idle
          right side. Step 1 (Schema) is the opposite: its table needs every pixel it can get
          (Name/Type/flags/Enum values/Origin/Scope), so the preview panel — which would otherwise
          squeeze the table into its own internal horizontal scroll on a merely-1200px-wide page —
          is dropped for that step; the table gets the full width instead. */}
      {step === 0 && (
        <div style={{ display: "flex", gap: theme.space.xl, alignItems: "flex-start", flexWrap: "wrap" }}>
          <div style={{ flex: "1 1 480px", minWidth: 0 }}>
            <StepIdentity
              mode={mode}
              name={name} onNameChange={setName}
              formats={formats} onFormatsChange={setFormats}
              tags={tags} onTagsChange={setTags}
              maxSizeMb={maxSizeMb} onMaxSizeMbChange={setMaxSizeMb}
              jobTimeoutSeconds={jobTimeoutSeconds} onJobTimeoutSecondsChange={setJobTimeoutSeconds}
              preset={preset} onPresetChange={setPreset}
              extra={extraContract} onExtraChange={setExtraContract}
              onNext={() => setStep(1)}
              excludeCollectionId={collectionId}
            />
          </div>
          <WizardPreviewPanel payload={draftPayload} />
        </div>
      )}
      {step === 1 && (
        <StepSchema mode={mode} fields={fields} onFieldsChange={setFields} onBack={() => setStep(0)} onNext={() => setStep(2)} />
      )}
      {step === 2 && (
        <StepReview
          mode={mode}
          name={name} formats={formats} tags={tags}
          maxSizeBytes={resolveMaxFileSizeBytes(maxSizeMb, maxSizeBytesOriginal)}
          jobTimeoutSeconds={jobTimeoutSeconds} fields={fields}
          removedFieldNames={removed}
          onBack={() => setStep(1)} onSubmit={handleSubmit} submitting={submitting} issues={issues}
        />
      )}
      {traceOfferCollectionId && (
        <TracePurgeOfferDialog
          collectionId={traceOfferCollectionId}
          onDone={() => {
            const id = traceOfferCollectionId;
            setTraceOfferCollectionId(null);
            onNavigate({ name: "collection", collectionId: id });
          }}
        />
      )}
    </>
  );

  // Edit mode is always embedded inside `settings/CollectionSettingsPage`'s "Contract" section,
  // which already supplies the breadcrumb/header/scroll chrome — rendering another one here would
  // duplicate it. Create mode is still reached as its own standalone route (`new-collection`), so
  // it keeps the full page treatment.
  if (mode === "edit") return steps;

  return (
    <div className="df-rise" style={{ padding: theme.space.xl, maxWidth: 1200, margin: "0 auto", overflowY: "auto", height: "100%" }}>
      <PageHeader
        eyebrow={<BackLink label="Collections" onClick={() => onNavigate(backTarget)} />}
        title="New collection"
        subtitle="Define the contract this collection ingests against."
      />
      {steps}
    </div>
  );
}
