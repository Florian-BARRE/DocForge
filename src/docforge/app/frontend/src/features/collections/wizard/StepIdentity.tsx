// ====== Code Summary ======
// Wizard step 1: identity + upload limits — rendered from the backend's own
// `CollectionContractModel` JSON Schema via the shared `SchemaForm`, the same generic renderer
// `NodeConfigForm`/`StageConfigForm` already drive off a node's `config_schema`. A new scalar
// field added to the backend contract model appears here automatically, no frontend edit needed.

import { useEffect, useState } from "react";
import type { CollectionPreset } from "../../../api/collections";
import { fetchCollectionContractSchema } from "../../../api/collections";
import type { JsonSchema } from "../../../api/types";
import { Button } from "../../../components/Button";
import { ErrorState } from "../../../components/ErrorState";
import { LoadingState } from "../../../components/LoadingState";
import { SchemaForm } from "../../../components/schema-form/SchemaForm";
import { theme } from "../../../theme";
import type { WizardMode } from "./CollectionWizard";
import { MaxFileSizeField } from "./MaxFileSizeField";
import { bytesToMb, mbToBytes } from "./wizardTypes";

interface StepIdentityProps {
  mode: WizardMode;
  name: string;
  onNameChange: (name: string) => void;
  formats: string[];
  onFormatsChange: (formats: string[]) => void;
  maxSizeMb: number;
  onMaxSizeMbChange: (mb: number) => void;
  /** `null` inherits the worker's global default job timeout. */
  jobTimeoutSeconds: number | null;
  onJobTimeoutSecondsChange: (seconds: number | null) => void;
  preset: CollectionPreset;
  onPresetChange: (preset: CollectionPreset) => void;
  /** Any contract field the wizard has no dedicated slot for yet — kept and resubmitted verbatim,
   *  so a brand-new backend field round-trips even before it earns its own named state. */
  extra: Record<string, unknown>;
  onExtraChange: (extra: Record<string, unknown>) => void;
  onNext: () => void;
}

export function StepIdentity({
  mode, name, onNameChange, formats, onFormatsChange, maxSizeMb, onMaxSizeMbChange,
  jobTimeoutSeconds, onJobTimeoutSecondsChange, preset, onPresetChange, extra, onExtraChange, onNext,
}: StepIdentityProps) {
  const [schema, setSchema] = useState<JsonSchema | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    fetchCollectionContractSchema()
      .then((result) => {
        if (!cancelled) setSchema(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  if (error) return <ErrorState message={error} onRetry={() => setAttempt((a) => a + 1)} />;
  if (!schema) return <LoadingState label="loading collection contract…" />;

  // 1. The create-only `preset` field is hidden from the schema in edit mode — it only ever
  //    selects the stock blob at creation, the edit wizard has no analogous notion.
  //    `max_file_size_bytes` is always pulled out too — it gets its own MB-labeled control
  //    (`MaxFileSizeField`) below instead of the generic schema-driven raw-byte number input.
  const properties = { ...schema.properties };
  if (mode === "edit") delete properties.preset;
  delete properties.max_file_size_bytes;
  const visibleSchema: JsonSchema = { ...schema, properties };

  // 2. Fold the wizard's named state + the untyped overflow bag into ONE values record keyed by
  //    the contract's own field names — this is the only place unit conversion happens
  //    (max_file_size_bytes is stored in the wizard as MB for display elsewhere in the app).
  const values: Record<string, unknown> = {
    ...extra,
    name,
    supported_formats: formats,
    max_file_size_bytes: mbToBytes(maxSizeMb),
    job_timeout_seconds: jobTimeoutSeconds,
    ...(mode === "create" ? { preset } : {}),
  };

  const handleChange = (field: string, value: unknown) => {
    switch (field) {
      case "name":
        onNameChange(typeof value === "string" ? value : "");
        break;
      case "supported_formats":
        onFormatsChange(Array.isArray(value) ? (value as string[]) : []);
        break;
      case "max_file_size_bytes":
        onMaxSizeMbChange(bytesToMb(typeof value === "number" ? value : 0));
        break;
      case "job_timeout_seconds":
        onJobTimeoutSecondsChange(typeof value === "number" ? value : null);
        break;
      case "preset":
        onPresetChange((value as CollectionPreset) ?? "standard");
        break;
      default:
        // A contract field the wizard doesn't know by name yet — kept verbatim in the overflow
        // bag and resubmitted as-is, so it still round-trips end to end.
        onExtraChange({ ...extra, [field]: value });
    }
  };

  const required = new Set(visibleSchema.required ?? []);
  const valid = [...required].every((field) => {
    const v = values[field];
    if (v === undefined || v === null) return false;
    if (typeof v === "string") return v.trim().length > 0;
    if (Array.isArray(v)) return v.length > 0;
    return true;
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.l, maxWidth: 480 }}>
      <div
        style={{
          background: theme.color.surface, border: `1px solid ${theme.color.line}`,
          borderRadius: theme.radius.l, boxShadow: theme.shadow.sm, padding: theme.space.l,
          display: "flex", flexDirection: "column", gap: "10px",
        }}
      >
        <SchemaForm schema={visibleSchema} values={values} onChange={handleChange} columns={1} />
        <MaxFileSizeField valueMb={maxSizeMb} onChange={onMaxSizeMbChange} />
      </div>
      <div>
        <Button variant="primary" disabled={!valid} onClick={onNext}>
          Next — schema
        </Button>
      </div>
    </div>
  );
}
