// ====== Code Summary ======
// The search pipeline editor: a simple top section (the always-on fusion summary + the Reranking
// Switch — the only two things a non-technical user needs) over a collapsed-by-default "Advanced"
// rail exposing every node's raw config, in blob order (or a read-only step when a node has none).
// Unlike the ingestion stage rail there is NO stage compiler for search (`stages_view_url`/
// `stages_apply_url` are null) — every edit mutates the blob locally (config edits are a plain
// field replace; the rerank toggle is the one edit with real topology, see state/blobOps.ts) and
// validity is refreshed via `/inspect` (debounced while typing a config field, immediate on the
// rerank toggle since it's a single discrete action). Reusable standalone (fetches the product
// default) OR embedded in a collection page (seeded with `initialBlob`, saved via `onSave`).
// All state/effects live in `useSearchPipelineEditor`; the rail itself is `SearchPipelineRail` —
// this component adds the sticky minimap + viewport tracking (mirroring the ingestion
// `StageRailPage`, see SearchPipelineMinimap's own doc comment for why it's mirrored not imported)
// and is otherwise pure top-level layout.

import { useMemo, useRef } from "react";
import { ApiIssueList } from "../../components/ApiIssueList";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import type { GroupBlob } from "../../api/types";
import { theme } from "../../theme";
import { useActiveStageKey } from "../stage-rail/state/useActiveStageKey";
import { SearchPipelineHeader } from "./SearchPipelineHeader";
import { SearchPipelineMinimap } from "./SearchPipelineMinimap";
import { SearchPipelineRail } from "./SearchPipelineRail";
import { SearchScopeBanner } from "./SearchScopeBanner";
import { deriveSearchMinimapEntries } from "./state/searchMinimapEntries";
import { useSearchPipelineEditor, type UseSearchPipelineEditorProps } from "./state/useSearchPipelineEditor";

export type SearchPipelineEditorProps = UseSearchPipelineEditorProps;

export function SearchPipelineEditor(props: SearchPipelineEditorProps) {
  const editor = useSearchPipelineEditor(props);
  // Hooks run unconditionally, BEFORE the loading/error early returns below (rules-of-hooks) —
  // entries/keys fall back to `[]` while `editor.blob`/`editor.palette` are still null, so the
  // viewport tracker mounts cleanly through the loading -> loaded transition.
  const scrollRef = useRef<HTMLDivElement>(null);
  const minimapEntries = useMemo(
    () =>
      editor.blob && editor.palette
        ? deriveSearchMinimapEntries(editor.blob, editor.palette, editor.railNodes, editor.hasAnchor)
        : [],
    [editor.blob, editor.palette, editor.railNodes, editor.hasAnchor],
  );
  const stepKeys = useMemo(() => minimapEntries.map((entry) => entry.key), [minimapEntries]);
  const activeStepKey = useActiveStageKey(stepKeys, scrollRef);

  if (editor.loadError) return <ErrorState message={editor.loadError} />;
  if (!editor.palette || !editor.blob) return <LoadingState label="loading search pipeline…" />;
  const blob: GroupBlob = editor.blob;

  return (
    <div ref={scrollRef} style={{ height: "100%", overflowY: "auto", background: theme.color.bg }}>
      <div
        className="df-rise"
        style={{
          maxWidth: 1080, margin: "0 auto", padding: `0 ${theme.space.l}px ${theme.space.l}px`,
          display: "flex", alignItems: "flex-start", gap: theme.space.l,
        }}
      >
        <SearchPipelineMinimap entries={minimapEntries} activeKey={activeStepKey} />
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: theme.space.l }}>
          <SearchScopeBanner />
          <SearchPipelineHeader
            valid={editor.valid}
            checking={editor.checking}
            debouncePending={editor.debouncePending}
            issueCount={editor.issues.length}
            dirty={editor.dirty}
            onReset={props.onResetToDefault ? editor.handleReset : undefined}
            resetting={editor.resetting}
            onSave={props.onSave ? editor.handleSave : undefined}
            saving={editor.saving}
            saveError={editor.saveError}
          />
          {editor.issues.length > 0 && <ApiIssueList issues={editor.issues} />}
          <SearchPipelineRail
            blob={blob}
            palette={editor.palette}
            railNodes={editor.railNodes}
            hasAnchor={editor.hasAnchor}
            hasQueryAnchor={editor.hasQueryAnchor}
            queryKind={editor.queryKind}
            queryConfig={editor.queryConfig}
            onChangeNodeConfig={editor.setNodeConfig}
            onSelectQueryTransform={editor.selectQueryTransform}
            onToggleRerank={editor.toggleRerank}
          />
        </div>
      </div>
    </div>
  );
}
