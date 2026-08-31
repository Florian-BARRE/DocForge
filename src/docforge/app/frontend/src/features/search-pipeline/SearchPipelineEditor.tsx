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
// this component is pure top-level layout.

import { ApiIssueList } from "../../components/ApiIssueList";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import type { GroupBlob } from "../../api/types";
import { theme } from "../../theme";
import { SearchPipelineHeader } from "./SearchPipelineHeader";
import { SearchPipelineRail } from "./SearchPipelineRail";
import { useSearchPipelineEditor, type UseSearchPipelineEditorProps } from "./state/useSearchPipelineEditor";

export type SearchPipelineEditorProps = UseSearchPipelineEditorProps;

export function SearchPipelineEditor(props: SearchPipelineEditorProps) {
  const editor = useSearchPipelineEditor(props);

  if (editor.loadError) return <ErrorState message={editor.loadError} />;
  if (!editor.palette || !editor.blob) return <LoadingState label="loading search pipeline…" />;
  const blob: GroupBlob = editor.blob;

  return (
    <div style={{ height: "100%", overflowY: "auto", background: theme.color.bg }}>
      <div
        className="df-rise"
        style={{
          maxWidth: 860, margin: "0 auto", padding: `0 ${theme.space.l}px ${theme.space.l}px`,
          display: "flex", flexDirection: "column", gap: theme.space.l,
        }}
      >
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
  );
}
