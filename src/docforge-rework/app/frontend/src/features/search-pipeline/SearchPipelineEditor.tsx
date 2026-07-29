// ====== Code Summary ======
// The search pipeline editor: a simple top section (the always-on fusion summary + the Reranking
// Switch — the only two things a non-technical user needs) over a collapsed-by-default "Avancé"
// rail exposing every node's raw config, in blob order (or a read-only step when a node has none).
// Unlike the ingestion stage rail there is NO stage compiler for search (`stages_view_url`/
// `stages_apply_url` are null) — every edit mutates the blob locally (config edits are a plain
// field replace; the rerank toggle is the one edit with real topology, see state/blobOps.ts) and
// validity is refreshed via `/inspect` (debounced while typing a config field, immediate on the
// rerank toggle since it's a single discrete action). Reusable standalone (fetches the product
// default) OR embedded in a collection page (seeded with `initialBlob`, saved via `onSave`).

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiIssueList } from "../../components/ApiIssueList";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { getDesign, inspect, listPipelineDesigns } from "../../api/pipelines";
import type { GroupBlob, Palette, ValidationIssue } from "../../api/types";
import { theme } from "../../theme";
import { AdvancedDisclosure } from "./AdvancedDisclosure";
import { SearchNodeCard } from "./SearchNodeCard";
import { SearchPipelineHeader } from "./SearchPipelineHeader";
import { SearchSimpleControls } from "./SearchSimpleControls";
import { isActionBlob, isRerankEnabled, setNodeConfigField, setRerankEnabled } from "./state/blobOps";

const DEBOUNCE_MS = 400;

export interface SearchPipelineEditorProps {
  /** Seed blob (e.g. a collection's stored search graph). Omitted → the product default. */
  initialBlob?: GroupBlob | null;
  /** When provided, a Save button PATCHes the blob back (disabled while invalid or unchanged). */
  onSave?: (blob: GroupBlob) => Promise<void>;
  /** When provided, a Reset button PATCHes the `{}` sentinel back — reverting to the stock default
   *  AND making the collection track future default changes, unlike re-saving the expanded blob. */
  onResetToDefault?: () => Promise<void>;
  title?: string;
  subtitle?: string;
}

export function SearchPipelineEditor({ initialBlob, onSave, onResetToDefault, title, subtitle }: SearchPipelineEditorProps) {
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
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : String(error));
    } finally {
      setResetting(false);
    }
  }, [onResetToDefault]);

  // 6. Save: PATCH the current blob back. Only offered when the caller wants persistence here.
  const handleSave = useCallback(async () => {
    if (!blob || !onSave || !valid || checking || debouncePending) return;
    setSaving(true);
    setSaveError(null);
    try {
      await onSave(blob);
      setSavedBlob(blob);
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : String(error));
    } finally {
      setSaving(false);
    }
  }, [blob, onSave, valid, checking, debouncePending]);

  const dirty = useMemo(() => JSON.stringify(blob) !== JSON.stringify(savedBlob), [blob, savedBlob]);

  if (loadError) return <ErrorState message={loadError} />;
  if (!palette || !blob) return <LoadingState label="loading search pipeline…" />;

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", background: theme.color.bg }}>
      <SearchPipelineHeader
        title={title ?? "Search pipeline"}
        subtitle={subtitle}
        valid={valid}
        checking={checking}
        debouncePending={debouncePending}
        issueCount={issues.length}
        dirty={dirty}
        onReset={onResetToDefault ? handleReset : undefined}
        resetting={resetting}
        onSave={onSave ? handleSave : undefined}
        saving={saving}
        saveError={saveError}
      />
      {issues.length > 0 && (
        <div style={{ padding: `${theme.space.s}px ${theme.space.l}px`, borderBottom: `1px solid ${theme.color.line}` }}>
          <ApiIssueList issues={issues} />
        </div>
      )}
      <div style={{ flex: 1, overflowY: "auto" }}>
        <div
          className="df-rise"
          style={{
            maxWidth: 860, margin: "0 auto", padding: theme.space.l,
            display: "flex", flexDirection: "column", gap: theme.space.l,
          }}
        >
          <SearchSimpleControls
            rerankEnabled={isRerankEnabled(blob)}
            onToggleRerank={toggleRerank}
          />
          <AdvancedDisclosure summary="Advanced">
            {blob.nodes.filter(isActionBlob).map((node, index) => (
              <SearchNodeCard
                key={node.id}
                step={index + 1}
                node={node}
                palette={palette}
                onChangeConfig={(field, value) => setNodeConfig(node.id, field, value)}
              />
            ))}
          </AdvancedDisclosure>
        </div>
      </div>
    </div>
  );
}
