// ====== Code Summary ======
// All state/effects behind the search pipeline editor: discovery + initial load, the debounced
// `/inspect` verify loop, the discrete rerank/query-transform edits, save/reset, and the derived
// rail-node list — extracted out of `SearchPipelineEditor` so that component stays pure render.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getDesign, inspect, listPipelineDesigns } from "../../../api/pipelines";
import type { GroupBlob, Palette, ValidationIssue } from "../../../api/types";
import { useToast } from "../../../shell/toast";
import type { QueryTransformKind } from "./blobOps";
import { isActionBlob, queryTransformKind, setNodeConfigField, setQueryTransform, setRerankEnabled } from "./blobOps";

const DEBOUNCE_MS = 400;
// The read-only step the toggleable reranking card is rendered right after (matches the backend's
// retrieve → rerank → hydrate splice in blobOps). Exported — `SearchPipelineRail` splices its card
// at the same anchor.
export const RERANK_ANCHOR_ID = "retrieve";
// The query-transform card is rendered right after `normalize` — the point its rewrite/HyDE node is
// spliced in (normalize → transform → encode, see blobOps.setQueryTransform). Exported for the same
// reason as `RERANK_ANCHOR_ID`.
export const QUERY_ANCHOR_ID = "normalize";

export interface UseSearchPipelineEditorProps {
  /** Seed blob (e.g. a collection's stored search graph). Omitted → the product default. */
  initialBlob?: GroupBlob | null;
  /** When provided, a Save button PATCHes the blob back (disabled while invalid or unchanged). */
  onSave?: (blob: GroupBlob) => Promise<void>;
  /** When provided, a Reset button PATCHes the `{}` sentinel back — reverting to the stock default
   *  AND making the collection track future default changes, unlike re-saving the expanded blob. */
  onResetToDefault?: () => Promise<void>;
}

export function useSearchPipelineEditor({ initialBlob, onSave, onResetToDefault }: UseSearchPipelineEditorProps) {
  const toast = useToast();
  const [palette, setPalette] = useState<Palette | null>(null);
  const [inspectUrl, setInspectUrl] = useState<string | null>(null);
  const [blob, setBlob] = useState<GroupBlob | null>(null);
  const [savedBlob, setSavedBlob] = useState<GroupBlob | null>(null);
  const [valid, setValid] = useState(true);
  const [issues, setIssues] = useState<ValidationIssue[]>([]);
  const [checking, setChecking] = useState(false);
  const [debouncePending, setDebouncePending] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // 1. Discover the search design surface, load its palette + (possibly seeded) blob, and run one
  //    /inspect to seed the validity badge — no /stages/view exists here to fold it in for free.
  useEffect(() => {
    let cancelled = false;
    listPipelineDesigns()
      .then(async ({ pipelines }) => {
        const descriptor = pipelines.find((p) => p.key === "search");
        if (!descriptor) throw new Error("no 'search' pipeline design is registered");
        const design = await getDesign(descriptor.design_url);
        const seedBlob = initialBlob ?? design.blob;
        const result = await inspect(descriptor.inspect_url, seedBlob);
        if (cancelled) return;
        setPalette(design.palette);
        setInspectUrl(descriptor.inspect_url);
        setBlob(seedBlob);
        setSavedBlob(seedBlob);
        setValid(result.valid);
        setIssues(result.build_error ? [{ code: "build_error", location: "blob", message: result.build_error }] : result.issues);
      })
      .catch((error) => {
        // Discovery / initial load is fatal (nothing to edit yet) — the whole chain, including the
        // discovery call and a missing "search" descriptor, must surface as an error state.
        if (!cancelled) setLoadError(error instanceof Error ? error.message : String(error));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 2. blobLatestRef is the true "current draft" for the next debounced /inspect — written
  //    synchronously so a rapid sequence of keystrokes never sends a stale snapshot.
  const blobLatestRef = useRef<GroupBlob | null>(null);
  blobLatestRef.current = blob;
  const inspectUrlRef = useRef<string | null>(null);
  inspectUrlRef.current = inspectUrl;
  const abortRef = useRef<AbortController>();
  const debounceRef = useRef<number>();

  const runInspect = useCallback((target: GroupBlob) => {
    const url = inspectUrlRef.current;
    if (!url) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setChecking(true);
    inspect(url, target, controller.signal)
      .then((result) => {
        if (blobLatestRef.current !== target) return; // a newer edit already superseded this check
        setValid(result.valid);
        setIssues(result.build_error ? [{ code: "build_error", location: "blob", message: result.build_error }] : result.issues);
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        if (blobLatestRef.current !== target) return; // a newer edit already superseded this check
        // A transient background verify blip must NOT tear down the editor (that would drop the
        // user's unsaved edits). Keep the draft mounted, mark it unverified (blocks Save) and show
        // the reason inline — a successful re-verify on the next keystroke clears it.
        setValid(false);
        setIssues([{
          code: "verify_failed",
          location: "inspect",
          message: error instanceof Error ? error.message : String(error),
        }]);
      })
      .finally(() => setChecking(false));
  }, []);

  // Tear down a pending debounce + any in-flight verify on unmount (the runtime path has no
  // per-render cleanup of its own, unlike the cancelled-flag guard on the initial load).
  useEffect(() => () => {
    window.clearTimeout(debounceRef.current);
    abortRef.current?.abort();
  }, []);

  // 3. Typing a node's config field: mutate the local blob immediately, debounce the /inspect.
  //    `debouncePending` tracks that armed-but-not-yet-sent window so Save can be blocked — the
  //    `valid` badge only reflects the LAST settled /inspect, which lags the local blob.
  const setNodeConfig = useCallback((nodeId: string, field: string, value: unknown) => {
    const current = blobLatestRef.current;
    if (!current) return;
    const next = setNodeConfigField(current, nodeId, field, value);
    blobLatestRef.current = next;
    setBlob(next);
    window.clearTimeout(debounceRef.current);
    setDebouncePending(true);
    debounceRef.current = window.setTimeout(() => {
      setDebouncePending(false);
      const settled = blobLatestRef.current;
      if (settled) runInspect(settled);
    }, DEBOUNCE_MS);
  }, [runInspect]);

  // 4. Toggling rerank is a discrete action (not a keystroke stream) — mutate + verify immediately,
  //    no debounce needed.
  const toggleRerank = useCallback((next: boolean) => {
    const current = blobLatestRef.current;
    if (!current) return;
    window.clearTimeout(debounceRef.current);
    setDebouncePending(false);
    const updated = setRerankEnabled(current, next);
    blobLatestRef.current = updated;
    setBlob(updated);
    runInspect(updated);
  }, [runInspect]);

  // Selecting the query transform (Off/Rewrite/HyDE) is a discrete topology edit like the rerank
  // toggle — mutate + verify immediately, no debounce. Its provider config fields reuse the
  // debounced `setNodeConfig` path (the node id equals the transform kind).
  const selectQueryTransform = useCallback((next: QueryTransformKind | null) => {
    const current = blobLatestRef.current;
    if (!current) return;
    window.clearTimeout(debounceRef.current);
    setDebouncePending(false);
    const updated = setQueryTransform(current, next);
    blobLatestRef.current = updated;
    setBlob(updated);
    runInspect(updated);
  }, [runInspect]);

  // 5. Reset: PATCHes the `{}` sentinel server-side (the caller then remounts this editor with the
  //    refreshed, sentinel-backed collection — see CollectionSearchPage). Not a local blob swap:
  //    saving the expanded default blob instead would freeze it, losing the "tracks future default
  //    changes" behaviour the sentinel gives.
  const handleReset = useCallback(async () => {
    if (!onResetToDefault) return;
    window.clearTimeout(debounceRef.current);
    setResetting(true);
    setSaveError(null);
    try {
      await onResetToDefault();
      toast.success("Search pipeline reset to default");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setSaveError(message);
      toast.error(`Reset failed — ${message}`);
    } finally {
      setResetting(false);
    }
  }, [onResetToDefault, toast]);

  // 6. Save: PATCH the current blob back. Only offered when the caller wants persistence here.
  const handleSave = useCallback(async () => {
    if (!blob || !onSave || !valid || checking || debouncePending) return;
    setSaving(true);
    setSaveError(null);
    try {
      await onSave(blob);
      setSavedBlob(blob);
      toast.success("Search pipeline saved");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setSaveError(message);
      toast.error(`Save failed — ${message}`);
    } finally {
      setSaving(false);
    }
  }, [blob, onSave, valid, checking, debouncePending, toast]);

  const dirty = useMemo(() => JSON.stringify(blob) !== JSON.stringify(savedBlob), [blob, savedBlob]);

  // The rail's read-only/config steps — rerank AND the query transform are drawn as their own
  // toggleable cards, so both are filtered out here to avoid rendering them twice. `normalize` stays
  // (it shares the `query` family but is the fixed first step, not a transform).
  const railNodes = useMemo(
    () =>
      blob
        ? blob.nodes
            .filter(isActionBlob)
            .filter((node) => node.family !== "rerank")
            .filter((node) => !(node.family === "query" && node.kind !== "normalize"))
        : [],
    [blob],
  );
  const hasAnchor = useMemo(() => railNodes.some((node) => node.id === RERANK_ANCHOR_ID), [railNodes]);
  const hasQueryAnchor = useMemo(() => railNodes.some((node) => node.id === QUERY_ANCHOR_ID), [railNodes]);
  const queryKind = useMemo(() => (blob ? queryTransformKind(blob) : null), [blob]);
  const queryConfig = useMemo(
    () => blob?.nodes.find((node) => isActionBlob(node) && node.id === queryKind) as { config: Record<string, unknown> } | undefined,
    [blob, queryKind],
  );

  return {
    palette, blob, valid, issues, checking, debouncePending, loadError, saving, resetting, saveError, dirty,
    railNodes, hasAnchor, hasQueryAnchor, queryKind, queryConfig,
    setNodeConfig, toggleRerank, selectQueryTransform, handleReset, handleSave,
  };
}
