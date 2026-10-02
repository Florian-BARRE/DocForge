// ====== Code Summary ======
// State machine of the document metadata editor: loads the collection's field schema (the same
// source as the corpus filters / schema page), holds the draft, saves ONLY the changed fields and
// maps a 422 onto per-field errors. The component stays presentational.

import { useCallback, useEffect, useMemo, useState } from "react";
import { getCollection, type FieldSpec } from "../../../../api/collections";
import { updateDocumentMetadata, type MetadataUpdateResponse } from "../../../../api/documents";
import type { MetadataValue } from "../../../../api/explorer";
import { HttpError } from "../../../../api/http";
import { changedValues, chunkScopeFields, currentValues, isEditableField, mapFieldErrors, type DraftValues } from "./metadataDraft";

export function useMetadataEditor(
  documentId: string,
  collectionId: string,
  metadata: MetadataValue[],
  onSaved: (updated: DraftValues, specs: FieldSpec[]) => void,
) {
  const [fields, setFields] = useState<FieldSpec[] | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<DraftValues>({});
  const [saving, setSaving] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalErrors, setGeneralErrors] = useState<string[]>([]);
  const [result, setResult] = useState<MetadataUpdateResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCollection(collectionId)
      .then((collection) => { if (!cancelled) setFields(collection.fields); })
      .catch(() => { if (!cancelled) setFields([]); });
    return () => { cancelled = true; };
  }, [collectionId]);

  const editable = useMemo(() => (fields ?? []).filter(isEditableField), [fields]);
  const readOnlyChunkFields = useMemo(() => chunkScopeFields(fields ?? []), [fields]);
  const baseline = useMemo(() => currentValues(metadata), [metadata]);
  const changed = useMemo(() => changedValues(editable, baseline, draft), [editable, baseline, draft]);
  const dirty = Object.keys(changed).length > 0;

  const startEdit = useCallback(() => {
    setDraft({ ...baseline });
    setFieldErrors({});
    setGeneralErrors([]);
    setResult(null);
    setEditing(true);
  }, [baseline]);

  const cancel = useCallback(() => setEditing(false), []);
  const setValue = useCallback((name: string, value: unknown) => setDraft((prev) => ({ ...prev, [name]: value })), []);

  const save = useCallback(async () => {
    setSaving(true);
    setFieldErrors({});
    setGeneralErrors([]);
    try {
      const response = await updateDocumentMetadata(documentId, changed);
      setResult(response);
      setEditing(false);
      onSaved(changed, editable);
    } catch (error) {
      if (error instanceof HttpError && error.status === 422) {
        const mapped = mapFieldErrors(error.issues.map((issue) => issue.message), editable.map((f) => f.field_name));
        setFieldErrors(mapped.byField);
        setGeneralErrors(mapped.general);
      } else {
        setGeneralErrors([error instanceof Error ? error.message : String(error)]);
      }
    } finally {
      setSaving(false);
    }
  }, [documentId, changed, editable, onSaved]);

  return { loaded: fields !== null, editable, readOnlyChunkFields, editing, draft, dirty, saving, fieldErrors, generalErrors, result, startEdit, cancel, setValue, save };
}
