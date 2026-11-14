// ====== Code Summary ======
// All state/effects behind the search pipeline editor: discovery + initial load, the debounced
// `/inspect` verify loop, the discrete rerank/query-transform edits, save/reset, and the derived
// rail-node list — extracted out of `SearchPipelineEditor` so that component stays pure render.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { issuesFromBuildError } from "../../../api/http";
import { getDesign, inspect, listPipelineDesigns } from "../../../api/pipelines";
import type { GroupBlob, Palette } from "../../../api/types";
import { useToast } from "../../../shell/toast";
import type { QueryTransformKind } from "./blobOps";
import { setNodeConfigField, setQueryTransform, setRerankEnabled } from "./blobOps";
import {
  QUERY_ANCHOR_ID, RERANK_ANCHOR_ID, hasRailNode, queryConfigOf, queryKindOf, railNodesOf,
} from "./searchRailModel";
import { useSearchInspectLoop } from "./useSearchInspectLoop";

// Re-exported: the rail and the minimap import the anchors from here.
export { QUERY_ANCHOR_ID, RERANK_ANCHOR_ID };
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
        seedVerdict(result.valid, result.build_error ? issuesFromBuildError(result.build_error) : result.issues);
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
  const { valid, issues, checking, debouncePending, seedVerdict, verifyDebounced, verifyNow, cancelDebounce } =
    useSearchInspectLoop(inspectUrl, blobLatestRef);

  // 3. Typing a node's config field: mutate the local blob immediately, debounce the /inspect.
  //    `debouncePending` tracks that armed-but-not-yet-sent window so Save can be blocked — the
  //    `valid` badge only reflects the LAST settled /inspect, which lags the local blob.
  const setNodeConfig = useCallback((nodeId: string, field: string, value: unknown) => {
    const current = blobLatestRef.current;
    if (!current) return;
    const next = setNodeConfigField(current, nodeId, field, value);
    blobLatestRef.current = next;
    setBlob(next);
    verifyDebounced();
  }, [verifyDebounced]);

  // 4. Toggling rerank is a discrete action (not a keystroke stream) — mutate + verify immediately,
  //    no debounce needed.
  const toggleRerank = useCallback((next: boolean) => {
    const current = blobLatestRef.current;
    if (!current) return;
    const updated = setRerankEnabled(current, next);
    blobLatestRef.current = updated;
    setBlob(updated);
    verifyNow(updated);
  }, [verifyNow]);

  // Selecting the query transform (Off/Rewrite/HyDE) is a discrete topology edit like the rerank
  // toggle — mutate + verify immediately, no debounce. Its provider config fields reuse the
  // debounced `setNodeConfig` path (the node id equals the transform kind).
  const selectQueryTransform = useCallback((next: QueryTransformKind | null) => {
    const current = blobLatestRef.current;
    if (!current) return;
    const updated = setQueryTransform(current, next);
    blobLatestRef.current = updated;
    setBlob(updated);
    verifyNow(updated);
  }, [verifyNow]);

  // 5. Reset: PATCHes the `{}` sentinel server-side (the caller then remounts this editor with the
  //    refreshed, sentinel-backed collection — see CollectionSearchPage). Not a local blob swap:
  //    saving the expanded default blob instead would freeze it, losing the "tracks future default
  //    changes" behaviour the sentinel gives.
  const handleReset = useCallback(async () => {
    if (!onResetToDefault) return;
    cancelDebounce();
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
  }, [onResetToDefault, toast, cancelDebounce]);

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

  // The rail's read-only/config steps (see railNodesOf) and the query-transform card's state.
  const railNodes = useMemo(() => railNodesOf(blob), [blob]);
  const hasAnchor = useMemo(() => hasRailNode(railNodes, RERANK_ANCHOR_ID), [railNodes]);
  const hasQueryAnchor = useMemo(() => hasRailNode(railNodes, QUERY_ANCHOR_ID), [railNodes]);
  const queryKind = useMemo(() => queryKindOf(blob), [blob]);
  const queryConfig = useMemo(() => queryConfigOf(blob, queryKind), [blob, queryKind]);

  return {
    palette, blob, valid, issues, checking, debouncePending, loadError, saving, resetting, saveError, dirty,
    railNodes, hasAnchor, hasQueryAnchor, queryKind, queryConfig,
    setNodeConfig, toggleRerank, selectQueryTransform, handleReset, handleSave,
  };
}
