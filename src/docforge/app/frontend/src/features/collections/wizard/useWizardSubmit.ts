// ====== Code Summary ======
// Submit orchestration for CollectionWizard. Create mode POSTs directly. Edit mode first PATCHes with
// `dry_run: true`; a destructive `schema_diff` (removed fields / lost values) parks the request in
// `pendingChange` for the confirmation dialog instead of writing, and only `confirmPending` sends the
// real PATCH. A non-destructive edit saves straight away. A renamed row is sent as a `field_ops`
// rename (values kept) rather than remove + add.

import { useState } from "react";
import {
  createCollection, updateCollection,
  type CollectionPreset, type CreateCollectionRequest, type Collection, type SchemaDiff, type UpdateCollectionRequest,
} from "../../../api/collections";
import { HttpError, type ApiIssue } from "../../../api/http";
import { useToast } from "../../../shell/toast";
import type { Navigate } from "../../../shell/view";
import { isDestructive, toUpdateRequest } from "./schemaChange";
import type { DraftField } from "./wizardTypes";

interface PendingChange {
  request: UpdateCollectionRequest;
  diff: SchemaDiff;
}

interface UseWizardSubmitArgs {
  mode: "create" | "edit";
  collectionId?: string;
  initial?: Collection;
  payload: CreateCollectionRequest;
  fields: DraftField[];
  preset: CollectionPreset;
  onNavigate: Navigate;
  /** Set to the saved collection's id when the save lowered trace_verbosity away from 'full'. */
  onTraceOffer: (collectionId: string) => void;
}

export function useWizardSubmit({ mode, collectionId, initial, payload, fields, preset, onNavigate, onTraceOffer }: UseWizardSubmitArgs) {
  const toast = useToast();
  const [submitting, setSubmitting] = useState(false);
  const [issues, setIssues] = useState<ApiIssue[]>([]);
  const [pendingChange, setPendingChange] = useState<PendingChange | null>(null);

  const finish = (result: Collection) => {
    toast.success(mode === "edit" ? `Collection “${result.name}” updated` : `Collection “${result.name}” created`);
    // `initial` is this edit session's starting point (never re-fetched), so it reads as the PREVIOUS value.
    const nextVerbosity = (payload as unknown as Record<string, unknown>).trace_verbosity;
    if (mode === "edit" && initial?.trace_verbosity === "full" && nextVerbosity !== "full") {
      onTraceOffer(result.id);
    } else {
      onNavigate({ name: "collection", collectionId: result.id });
    }
  };

  const run = async (action: () => Promise<void>) => {
    setSubmitting(true);
    setIssues([]);
    try {
      await action();
    } catch (error) {
      const issueList = error instanceof HttpError ? error.issues : [{ message: String(error) }];
      setIssues(issueList);
      toast.error(`${mode === "edit" ? "Update" : "Create"} failed — ${issueList[0]?.message ?? "unknown error"}`);
    } finally {
      setSubmitting(false);
    }
  };

  const submit = () => run(async () => {
    if (mode !== "edit" || !collectionId || !initial) {
      finish(await createCollection({ ...payload, preset }));
      return;
    }
    const request = toUpdateRequest(payload, initial.fields, fields);
    const preview = await updateCollection(collectionId, { ...request, dry_run: true });
    if (isDestructive(preview.schema_diff)) {
      setPendingChange({ request, diff: preview.schema_diff });
      return;
    }
    finish(await updateCollection(collectionId, request));
  });

  const confirmPending = () => run(async () => {
    if (!pendingChange || !collectionId) return;
    const result = await updateCollection(collectionId, pendingChange.request);
    setPendingChange(null);
    finish(result);
  });

  return {
    submitting, issues, pendingDiff: pendingChange?.diff ?? null,
    submit, confirmPending, cancelPending: () => setPendingChange(null),
  };
}
