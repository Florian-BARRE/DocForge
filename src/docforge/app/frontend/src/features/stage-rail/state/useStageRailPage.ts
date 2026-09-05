// ====== Code Summary ======
// All state/effects behind the stage rail: discovery + initial `/stages/view` load, the serialized
// `/apply` queue every mutating gesture funnels through, the ONE local-mirror-then-debounce
// exception for typing, and the action façade handed to every card — extracted out of
// `StageRailPage` so that component stays pure render.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { GroupBlob, Palette, StageAction, StageView, ValidationIssue } from "../../../api/types";
import { applyStageAction, getDesign, listPipelineDesigns, viewStages } from "../../../api/pipelines";
import { useToast } from "../../../shell/toast";
import type { StageRailActions } from "../actions";
import {
  buildSetChainAction, buildSetConfigAction, buildSetStackAction, buildSetStackMethodChainAction,
  localSetChainStepConfig, localSetChainStepScoreBelow, localSetStackMethodConfig, localSetStackMethodChainStepConfig,
  localSetStageConfig,
} from "./stageOps";

const DEBOUNCE_MS = 400;

export interface UseStageRailPageProps {
  /** Seed blob (e.g. a collection's stored pipeline). Omitted → the product default. */
  initialBlob?: GroupBlob | null;
  /** Fired after every settled apply — lets an embedding page track the draft + its validity. */
  onBlobChange?: (blob: GroupBlob, valid: boolean, issues: ValidationIssue[]) => void;
  /** When provided, a Save button PATCHes the blob back (disabled while invalid). */
  onSave?: (blob: GroupBlob) => Promise<void>;
}

export function useStageRailPage({ initialBlob, onBlobChange, onSave }: UseStageRailPageProps) {
  const toast = useToast();
  const [palette, setPalette] = useState<Palette | null>(null);
  const [applyUrl, setApplyUrl] = useState<string | null>(null);
  const [blob, setBlob] = useState<GroupBlob | null>(null);
  const [stages, setStages] = useState<StageView[] | null>(null);
  const [valid, setValid] = useState(true);
  const [issues, setIssues] = useState<ValidationIssue[]>([]);
  const [notices, setNotices] = useState<string[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [debouncePending, setDebouncePending] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const onBlobChangeRef = useRef(onBlobChange);
  onBlobChangeRef.current = onBlobChange;

  // 1. Discover the design surface, load the palette (for node-card names/summaries/schemas) and
  //    the (possibly seeded) blob's stage view — validity is folded into the SAME /stages/view
  //    response, so the open is one design GET + one view POST (no priming /inspect). The whole
  //    chain (discovery AND the inner design/view round-trip) funnels through one try/catch so a
  //    failure anywhere lands in `loadError` instead of an unhandled rejection + eternal spinner.
  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    (async () => {
      try {
        const { pipelines } = await listPipelineDesigns();
        const descriptor = pipelines[0];
        if (!descriptor) return;
        const design = await getDesign(descriptor.design_url);
        const seedBlob = initialBlob ?? design.blob;
        const viewResult = await viewStages(descriptor.stages_view_url, seedBlob);
        if (cancelled) return;
        setPalette(design.palette);
        setApplyUrl(descriptor.stages_apply_url);
        setBlob(seedBlob);
        setStages(viewResult.stages);
        const settledIssues = viewResult.build_error
          ? [{ code: "build_error", location: "blob", message: viewResult.build_error }]
          : viewResult.issues;
        setIssues(settledIssues);
        setValid(settledIssues.length === 0);
        onBlobChangeRef.current?.(seedBlob, settledIssues.length === 0, settledIssues);
      } catch (error) {
        if (!cancelled) setLoadError(error instanceof Error ? error.message : String(error));
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reloadKey]);

  const retryLoad = useCallback(() => setReloadKey((k) => k + 1), []);

  // 2. blobLatestRef/stagesLatestRef are the true "current state" for the NEXT round-trip —
  //    written synchronously wherever a change happens, so a rapid sequence of gestures never
  //    reads a stale value while React is still catching up on a re-render.
  const blobLatestRef = useRef<GroupBlob | null>(null);
  blobLatestRef.current = blob;
  const stagesLatestRef = useRef<StageView[] | null>(null);
  stagesLatestRef.current = stages;
  const applyUrlRef = useRef<string | null>(null);
  applyUrlRef.current = applyUrl;

  // 3. The apply loop: every mutating gesture funnels through here, SERIALIZED on one queue so a
  //    rapid sequence (a debounce settling while a click is still in flight…) can never
  //    interleave state — each call reads the blob left by the one before it, in order.
  const pendingRef = useRef(0);
  const queueRef = useRef<Promise<void>>(Promise.resolve());
  const applyAction = useCallback((action: StageAction) => {
    const url = applyUrlRef.current;
    if (!url) return;
    pendingRef.current += 1;
    setBusy(true);
    queueRef.current = queueRef.current.then(async () => {
      const current = blobLatestRef.current;
      if (!current) return;
      try {
        const result = await applyStageAction(url, current, action);
        blobLatestRef.current = result.blob;
        stagesLatestRef.current = result.stages;
        setBlob(result.blob);
        setStages(result.stages);
        setValid(result.valid);
        setIssues(result.issues);
        setNotices(result.notices);
        setApplyError(null);
        onBlobChangeRef.current?.(result.blob, result.valid, result.issues);
      } catch (error) {
        setApplyError(error instanceof Error ? error.message : String(error));
      } finally {
        pendingRef.current = Math.max(0, pendingRef.current - 1);
        if (pendingRef.current === 0) setBusy(false);
      }
    });
  }, []);

  // 4. The ONE exception: typing updates the local `stages` mirror immediately so the keystroke
  //    feels native, then debounces the actual `/apply` round-trip. `debouncePending` tracks that
  //    armed-but-not-yet-sent window so Save can be blocked — `blob` only mirrors the LAST settled
  //    `/apply`, so saving while a debounce is armed would persist a stale blob.
  const debounceRef = useRef<number>();
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
    [applyAction],
  );

  // 5. The action façade every card uses — thin adapters translating a gesture into ONE `/apply`
  //    action, discrete edits going straight through and typed edits going through the debounce.
  const actions = useMemo<StageRailActions>(() => ({
    enableStage: (stageKey) => applyAction({ action: "enable_stage", stage: stageKey }),
    disableStage: (stageKey) => applyAction({ action: "disable_stage", stage: stageKey }),
    setProvider: (stageKey, kind) => applyAction({ action: "set_provider", stage: stageKey, kind }),
    setConfig: (stageKey, field, value) => applyLocalThenDebounced(
      (s) => localSetStageConfig(s, stageKey, field, value),
      (s) => buildSetConfigAction(s, stageKey),
    ),
    setStackSteps: (stageKey, steps) => applyAction(buildSetStackAction(stagesLatestRef.current ?? [], stageKey, steps)),
    setStackMethodConfig: (stageKey, index, field, value) => applyLocalThenDebounced(
      (s) => localSetStackMethodConfig(s, stageKey, index, field, value),
      (s) => buildSetStackAction(s, stageKey),
    ),
    setChainSteps: (stageKey, slot, steps) => applyAction(buildSetChainAction(stagesLatestRef.current ?? [], stageKey, slot, steps)),
    setChainStepConfig: (stageKey, slot, index, field, value) => applyLocalThenDebounced(
      (s) => localSetChainStepConfig(s, stageKey, slot, index, field, value),
      (s) => buildSetChainAction(s, stageKey, slot),
    ),
    setChainStepScoreBelow: (stageKey, slot, index, value) => applyLocalThenDebounced(
      (s) => localSetChainStepScoreBelow(s, stageKey, slot, index, value),
      (s) => buildSetChainAction(s, stageKey, slot),
    ),
    setStackMethodChainSteps: (stageKey, methodIndex, steps) =>
      applyAction(buildSetStackMethodChainAction(stagesLatestRef.current ?? [], stageKey, methodIndex, steps)),
    setStackMethodChainStepConfig: (stageKey, methodIndex, stepIndex, field, value) => applyLocalThenDebounced(
      (s) => localSetStackMethodChainStepConfig(s, stageKey, methodIndex, stepIndex, field, value),
      (s) => buildSetStackMethodChainAction(
        s, stageKey, methodIndex,
        s.find((st) => st.key === stageKey)?.stack[methodIndex]?.chain?.steps ?? [],
      ),
    ),
  }), [applyAction, applyLocalThenDebounced]);

  // 6. Save: PATCH the current blob back. Only offered when the caller wants persistence here.
  const handleSave = useCallback(async () => {
    if (!blob || !onSave || !valid || busy || debouncePending) return;
    setSaving(true);
    setSaveError(null);
    try {
      await onSave(blob);
      toast.success("Ingestion pipeline saved");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setSaveError(message);
      toast.error(`Save failed — ${message}`);
    } finally {
      setSaving(false);
    }
  }, [blob, onSave, valid, busy, debouncePending, toast]);

  return {
    palette, stages, valid, issues, notices, loadError, applyError, busy, debouncePending, saving, saveError,
    actions, handleSave, retryLoad,
  };
}
