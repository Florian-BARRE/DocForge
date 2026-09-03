// ====== Code Summary ======
// The collapsible "Assumptions & rates" editor beneath the cost-estimate result — answers "why
// can't I edit this / what is it based on" directly: every number the estimator projected from is
// listed here, editable per-collection, with a per-field Reset (clear → falls back to the global
// default) and a top-level "Reset all". State is fully lifted here and passed down as controlled
// props, so clearing propagates through NumberField's own value-driven resync — no remount trick
// needed (contrast the search-pipeline editor's `resetVersion` key, which owns its OWN uncontrolled
// draft and therefore does need one).

import { useMemo, useState } from "react";
import {
  updateCollection,
  type AssumptionOverrides,
  type CostEstimateStage,
  type EstimateOverrides,
} from "../../../api/collections";
import { Button } from "../../../components/Button";
import { theme } from "../../../theme";
import { useToast } from "../../../shell/toast";
import { AdvancedDisclosure } from "../../search-pipeline/AdvancedDisclosure";
import { EstimateAssumptionsForm } from "./EstimateAssumptionsForm";
import { emptyRatesDraft, ratesDraftFromOverrides, ratesDraftToOverrides } from "./estimateOverridesDraft";
import { EstimateRatesForm } from "./EstimateRatesForm";
import { deriveRateTargets } from "./rateTargets";

interface EstimateOverridesEditorProps {
  collectionId: string;
  overrides: EstimateOverrides | null;
  /** The last run's per-stage breakdown — the source of which models/providers become editable. */
  stages: CostEstimateStage[];
  /** The last run's echoed effective assumptions — shown as each assumption field's placeholder. */
  assumptionPlaceholders: Record<string, unknown> | null;
  onSaved: (overrides: EstimateOverrides | null) => void;
}

function hasAnyValue(assumptions: AssumptionOverrides): boolean {
  return Object.values(assumptions).some((value) => value !== undefined);
}

export function EstimateOverridesEditor({ collectionId, overrides, stages, assumptionPlaceholders, onSaved }: EstimateOverridesEditorProps) {
  const toast = useToast();
  const [ratesDraft, setRatesDraft] = useState(() => ratesDraftFromOverrides(overrides?.rates));
  const [assumptionsDraft, setAssumptionsDraft] = useState<AssumptionOverrides>(() => ({ ...(overrides?.assumptions ?? {}) }));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const targets = useMemo(() => deriveRateTargets(stages, overrides?.rates), [stages, overrides]);

  const persist = async (next: EstimateOverrides | null) => {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateCollection(collectionId, { estimate_overrides: next });
      onSaved(updated.estimate_overrides);
      toast.success(next ? "Cost-estimate overrides saved" : "Reset to the global defaults");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const save = () => {
    const rates = ratesDraftToOverrides(ratesDraft);
    const assumptions = hasAnyValue(assumptionsDraft) ? assumptionsDraft : undefined;
    persist(rates || assumptions ? { rates, assumptions } : null);
  };

  const resetAll = () => {
    setRatesDraft(emptyRatesDraft());
    setAssumptionsDraft({});
    persist(null);
  };

  return (
    <AdvancedDisclosure summary="Assumptions & rates">
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
        Every figure above is projected from a per-model price and a set of extrapolation assumptions —
        editable here, per collection. A field you leave blank keeps using the global default; only what
        you set here is stored.
      </div>

      <EstimateRatesForm targets={targets} draft={ratesDraft} onChange={setRatesDraft} />
      <EstimateAssumptionsForm
        values={assumptionsDraft}
        placeholders={assumptionPlaceholders}
        onChange={(key, value) => setAssumptionsDraft((prev) => ({ ...prev, [key]: value }))}
      />

      {error && <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{error}</div>}

      <div style={{ display: "flex", gap: theme.space.s, justifyContent: "flex-end" }}>
        <Button size="sm" variant="ghost" disabled={saving} onClick={resetAll}>Reset all to defaults</Button>
        <Button size="sm" variant="primary" disabled={saving} onClick={save}>{saving ? "saving…" : "Save overrides"}</Button>
      </div>
    </AdvancedDisclosure>
  );
}
