// ====== Code Summary ======
// The ONE local-mirror-then-debounce exception of the stage rail: typing updates the local `stages`
// mirror immediately so the keystroke feels native, then debounces the actual `/apply` round-trip.
// Also owns the slot-config merge window (keystrokes accumulate in one patch; a different slot
// starting mid-window flushes the previous one first). Extracted from useStageRailPage.

import { useCallback, useRef, useState, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import type { StageAction, StageView } from "../../../api/types";
import { buildSetSlotConfigAction, localSetSlotConfig } from "./stageOps";

const DEBOUNCE_MS = 400;

export interface StageDebouncedApplyDeps {
  applyAction: (action: StageAction) => void;
  /** The freshest stage views — written synchronously so rapid gestures never read a stale value. */
  stagesLatestRef: MutableRefObject<StageView[] | null>;
  setStages: Dispatch<SetStateAction<StageView[] | null>>;
}

export function useStageDebouncedApply({ applyAction, stagesLatestRef, setStages }: StageDebouncedApplyDeps) {
  // `debouncePending` tracks the armed-but-not-yet-sent window so Save can be blocked — `blob` only
  // mirrors the LAST settled `/apply`, so saving while a debounce is armed would persist a stale blob.
  const [debouncePending, setDebouncePending] = useState(false);
  const debounceRef = useRef<number | undefined>(undefined);
  const applyLocalThenDebounced = useCallback(
    (mutateLocally: (s: StageView[]) => StageView[], buildAction: (s: StageView[]) => StageAction) => {
      const current = stagesLatestRef.current;
      if (!current) return;
      const next = mutateLocally(current);
      stagesLatestRef.current = next;
      setStages(next);
      window.clearTimeout(debounceRef.current);
      setDebouncePending(true);
      debounceRef.current = window.setTimeout(() => {
        setDebouncePending(false);
        const settled = stagesLatestRef.current;
        if (settled) applyAction(buildAction(settled));
      }, DEBOUNCE_MS);
    },
    [applyAction, stagesLatestRef, setStages],
  );

  // Slot config edits are MERGES of the typed keys only, so keystrokes within one debounce
  // window accumulate in `slotPatchRef`. A different slot starting mid-window flushes the previous
  // slot's patch first — one `/apply` carries exactly one slot.
  const slotPatchRef = useRef<{ stage: string; slot: string; patch: Record<string, unknown> } | null>(null);
  const setSlotConfig = useCallback((stageKey: string, slot: string, field: string, value: unknown) => {
    const pending = slotPatchRef.current;
    if (pending && (pending.stage !== stageKey || pending.slot !== slot)) {
      window.clearTimeout(debounceRef.current);
      slotPatchRef.current = null;
      applyAction(buildSetSlotConfigAction(pending.stage, pending.slot, pending.patch));
    }
    const base = slotPatchRef.current ?? { stage: stageKey, slot, patch: {} };
    slotPatchRef.current = { ...base, patch: { ...base.patch, [field]: value } };
    applyLocalThenDebounced(
      (s) => localSetSlotConfig(s, stageKey, slot, field, value),
      () => {
        const settled = slotPatchRef.current;
        slotPatchRef.current = null;
        return buildSetSlotConfigAction(stageKey, slot, settled?.patch ?? { [field]: value });
      },
    );
  }, [applyAction, applyLocalThenDebounced]);

  return { debouncePending, applyLocalThenDebounced, setSlotConfig };
}
